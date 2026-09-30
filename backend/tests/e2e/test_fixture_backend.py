"""Whole golden journey over actual Postgres, without any live model or public web."""

import io
import json
import zipfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api import routes
from app.application.acquisition.http import SafeHttpAcquirer
from app.application.acquisition.search import FixtureSearchProvider
from app.application.execution.operators import OperatorExecutor, WorkerRunner
from app.application.extraction.service import Extractor
from app.core.config import Settings
from app.domain.clock import utc_now
from app.main import app
from app.persistence.queries.queue import PostgresQueue
from app.persistence.repositories.workspace import WorkspaceRepository

pytestmark = pytest.mark.integration
GOLDEN = "Find Indian AI startups that raised more than $1M in the last 12 months. Include company, website, founders, headquarters, funding round, funding amount, investors, funding date, and original evidence."


async def test_golden_fixture_api_worker_proof_export_refresh(
    isolated_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = uuid4()
    settings = Settings(
        AI_PROVIDER="fixture",
        ACQUISITION_MODE="FIXTURE",
        DEMO_PROJECT_ID=project_id,
    )
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    monkeypatch.setattr(routes, "get_session_factory", lambda: isolated_db)

    async def workspace() -> AsyncIterator[WorkspaceRepository]:
        async with isolated_db() as session, session.begin():
            yield WorkspaceRepository(session, project_id, utc_now())

    app.dependency_overrides[routes.workspace] = workspace
    queue = PostgresQueue(isolated_db, project_id)
    runner = WorkerRunner(
        queue,
        OperatorExecutor(queue, SafeHttpAcquirer(), FixtureSearchProvider([]), Extractor()),
        "e2e-worker",
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/requirements/compile",
                json={"prompt": GOLDEN, "reference_date": "2026-09-30T00:00:00Z"},
            )
            assert response.status_code == 200, response.text
            req = response.json()["requirement_id"]
            assert (await client.post(f"/v1/requirements/{req}/plan")).status_code == 409
            confirmed = await client.post(
                f"/v1/requirements/{req}/confirm", json={"expected_version": 1}
            )
            assert confirmed.status_code == 200, confirmed.text
            plan = await client.post(f"/v1/requirements/{req}/plan")
            assert plan.status_code == 200, plan.text
            workflow = plan.json()["id"]
            body = {
                "workflow_version_id": plan.json()["data"]["workflow_version_id"],
                "idempotency_key": str(uuid4()),
            }
            run = await client.post(f"/v1/workflows/{workflow}/runs", json=body)
            assert run.status_code == 200, run.text
            run_id = run.json()["id"]
            repeated = await client.post(f"/v1/workflows/{workflow}/runs", json=body)
            assert repeated.json()["id"] == run_id
            for _ in range(10):
                if not await runner.tick():
                    break
            state = (await client.get(f"/v1/runs/{run_id}")).json()["data"]
            assert state["status"] in {"COMPLETED", "PARTIAL"}, state
            assert state["metrics"]["records"] == 2, state
            dataset = state["metrics"]["dataset_id"]
            version = state["metrics"]["dataset_version_id"]
            base = f"/v1/datasets/{dataset}/versions/{version}"
            records = (
                await client.get(base + "/records", params={"sort": "funding_amount:desc"})
            ).json()
            assert records["total"] == 2
            nimbus = next(
                r for r in records["items"] if r["values"]["company_name"] == "Nimbus AI Demo"
            )
            assert nimbus["trust"]["funding_amount"] == "CONFLICTING", nimbus
            proof = (
                await client.get(base + f"/records/{nimbus['entity_id']}/proof/funding_amount")
            ).json()
            assert len(proof["claims"]) == 2, proof
            assert {c["normalized_value"]["amount"] for c in proof["claims"]} == {
                "4500000",
                "5000000",
            }
            assert all(
                c["evidence"]["verification_status"] != "UNANCHORED" for c in proof["claims"]
            )
            assert all(c["acquisition"]["acquisition_method"] == "FIXTURE" for c in proof["claims"])
            assert (
                await client.get(base + "/records", params={"filter": "nonexistent.gt:3"})
            ).status_code == 422
            assert (
                await client.get(base + "/records", params={"filter": "funding_amount.gt:3000000"})
            ).json()["total"] == 1
            exported = (
                await client.post(
                    "/v1/exports", json={"dataset_version_id": version, "format": "csv"}
                )
            ).json()
            bundle = await client.get(exported["data"]["download_url"])
            assert bundle.status_code == 200, bundle.text
            archive = zipfile.ZipFile(io.BytesIO(bundle.content))
            assert "entity_id" in archive.read("dataset.csv").decode()
            assert json.loads(archive.read("evidence.json"))["dataset_version_id"] == version
            stream = await client.get(f"/v1/runs/{run_id}/events", headers={"Last-Event-ID": "1"})
            assert "id: 1\n" not in stream.text and "run.completed" in stream.text
            import os

            if os.getenv("PROOFGRID_BENCHMARK") == "1":
                import statistics
                import time
                from pathlib import Path

                samples = {}
                for name, path in {
                    "grid": base + "/records",
                    "proof": base + f"/records/{nimbus['entity_id']}/proof/funding_amount",
                }.items():
                    durations = []
                    for _ in range(20):
                        started = time.perf_counter()
                        response = await client.get(path)
                        assert response.status_code == 200
                        durations.append((time.perf_counter() - started) * 1000)
                    samples[name] = {
                        "samples": 20,
                        "p50_ms": round(statistics.median(durations), 1),
                        "p95_ms": round(sorted(durations)[18], 1),
                    }
                Path("/tmp/proofgrid-performance.json").write_text(json.dumps(samples))
            # Reviewer display selection must affect only subsequent snapshots.
            selected = next(
                c["id"] for c in proof["claims"] if c["normalized_value"]["amount"] == "5000000"
            )
            reviewed = await client.post(
                f"/v1/review/conflict/{proof['conflict']['id']}",
                json={
                    "decision": "SELECT_DISPLAY",
                    "selected_claim_id": selected,
                    "note": "Demo display choice",
                },
            )
            assert reviewed.status_code == 200
            historical = (
                await client.get(base + f"/records/{nimbus['entity_id']}/proof/funding_amount")
            ).json()
            assert historical["canonical_value"]["amount"] == "4500000"
            assert historical["trust_status"] == "CONFLICTING"
            assert (
                await client.get(f"/v1/workflows/{workflow}/versions/{body['workflow_version_id']}")
            ).status_code == 200
            assert (await client.get(f"/v1/datasets/{dataset}")).status_code == 200
            # Re-run preserves entities and allocates a new immutable dataset version.
            body["idempotency_key"] = str(uuid4())
            second = (await client.post(f"/v1/workflows/{workflow}/runs", json=body)).json()["id"]
            for _ in range(10):
                if not await runner.tick():
                    break
            latest = (await client.get(f"/v1/runs/{second}")).json()["data"]
            diff = await client.get(
                f"/v1/datasets/{dataset}/diff",
                params={"before": version, "after": latest["metrics"]["dataset_version_id"]},
            )
            assert diff.status_code == 200
            changed = next(
                item for item in diff.json()["items"] if item["entity_id"] == nimbus["entity_id"]
            )
            assert changed["state"] == "CHANGED"
            latest_proof = (
                await client.get(
                    f"/v1/datasets/{dataset}/versions/{latest['metrics']['dataset_version_id']}/records/{nimbus['entity_id']}/proof/funding_amount"
                )
            ).json()
            assert latest_proof["canonical_value"]["amount"] == "5000000"
            assert (
                latest_proof["trust_status"] == "CONFLICTING" and len(latest_proof["claims"]) == 2
            )
            async with isolated_db() as session:
                foreign = WorkspaceRepository(session, uuid4(), datetime.now(UTC))
                from app.core.errors import ProofGridError

                with pytest.raises(ProofGridError):
                    await foreign.proof(
                        UUID(dataset), UUID(version), UUID(nimbus["entity_id"]), "funding_amount"
                    )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "preset,page_budget,expected",
    [("synthetic", 1, "Nimbus AI Demo"), ("captured", 2, "Sarvam AI")],
)
async def test_partial_budget_and_captured_history_use_same_worker(
    isolated_db: async_sessionmaker[AsyncSession], preset: str, page_budget: int, expected: str
) -> None:
    from app.ai.fixture_provider import FixtureProvider
    from app.application.planning.service import fixture_plan
    from app.application.requirement_compiler.models import CompilationContext, CompilerResult
    from app.application.requirement_compiler.service import RequirementCompiler
    from app.domain.contracts import FieldSpec
    from app.domain.enums import FieldDataType

    project_id = uuid4()
    reference = datetime(2024 if preset == "captured" else 2026, 9, 30, tzinfo=UTC)
    compiled = await RequirementCompiler(FixtureProvider()).compile(
        GOLDEN, CompilationContext(reference_date=reference)
    )
    assert isinstance(compiled, CompilerResult)
    async with isolated_db() as session, session.begin():
        repo = WorkspaceRepository(session, project_id, utc_now())
        req = await repo.save_compilation(GOLDEN, compiled)
        await session.flush()
        spec = compiled.requirement_spec
        if preset == "captured":
            spec = spec.model_copy(
                update={
                    "fields": [
                        *spec.fields,
                        FieldSpec(key="country", label="Country", data_type=FieldDataType.LOCATION),
                    ]
                }
            )
        await repo.edit(
            req,
            1,
            spec=spec,
            policy=compiled.trust_contract_proposal.model_copy(update={"max_pages": page_budget}),
        )
        await repo.confirm(req, 2)
        _, schema, trust = await repo.requirement(req)
        planned = await repo.save_plan(
            req,
            schema.id,
            trust.id,
            fixture_plan(
                spec, compiled.trust_contract_proposal.model_copy(update={"max_pages": page_budget})
            ),
            "fixture",
        )
        await session.flush()
        run = await repo.create_run(
            planned.id, UUID(planned.data["workflow_version_id"]), uuid4(), "FIXTURE", 3, preset
        )
    queue = PostgresQueue(isolated_db, project_id)
    runner = WorkerRunner(
        queue,
        OperatorExecutor(queue, SafeHttpAcquirer(), FixtureSearchProvider([]), Extractor()),
        "partial-worker",
    )
    for _ in range(10):
        if not await runner.tick():
            break
    async with isolated_db() as session:
        repo = WorkspaceRepository(session, project_id, utc_now())
        result = await repo.run(run.id)
        assert result.data["status"] == "PARTIAL", result
        metrics = result.data["metrics"]
        assert metrics["records"] == 1
        dataset, version = UUID(metrics["dataset_id"]), UUID(metrics["dataset_version_id"])
        rows = await repo.records(
            dataset, version, limit=50, offset=0, sort=None, q=None, filters=[]
        )
        assert rows.items[0]["values"]["company_name"] == expected
        proof = await repo.proof(
            dataset, version, UUID(rows.items[0]["entity_id"]), "funding_amount"
        )
        assert proof.trust_status == "VERIFIED"
        assert all(c["acquisition"]["synthetic"] == (preset == "synthetic") for c in proof.claims)
        if preset == "captured":
            assert all(
                c["content_hash"] == c["acquisition"]["capture_sha256"] for c in proof.claims
            )
        if preset == "synthetic":
            assert any(error["code"] == "RUN_BUDGET_EXCEEDED" for error in metrics["source_errors"])
