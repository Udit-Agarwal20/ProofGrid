"""Fixed operator implementations. All expensive calls reserve durable budgets first."""

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.application.acquisition.http import SafeHttpAcquirer
from app.application.acquisition.models import AcquiredDocument
from app.application.acquisition.search import SearchProvider
from app.application.execution.contracts import ExecutionContext, ExecutionStore
from app.application.extraction.evidence import verify_anchor
from app.application.extraction.models import ClaimDraft
from app.application.extraction.service import Extractor, deterministic_extract
from app.core.errors import ProofGridError
from app.core.logging import get_logger
from app.domain.normalization import NormalizationError, normalize

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "funding"


def fixture_documents(preset: str = "synthetic") -> list[AcquiredDocument]:
    directory = FIXTURE_DIR if preset == "synthetic" else FIXTURE_DIR.parent / "captured_funding"
    manifest = json.loads((directory / "manifest.json").read_text())
    return [
        AcquiredDocument(
            **{k: v for k, v in item.items() if k != "file"},
            content=(directory / item["file"]).read_bytes().decode("utf-8"),
        )
        for item in manifest
    ]


class OperatorExecutor:
    def __init__(
        self,
        store: ExecutionStore,
        http: SafeHttpAcquirer,
        search: SearchProvider,
        extractor: Extractor,
        *,
        first_party_domains: list[str] | None = None,
        fixture_set: str = "synthetic",
    ):
        self.store, self.http, self.search, self.extractor = store, http, search, extractor
        self.first_party_domains = first_party_domains or []
        self.fixture_set = fixture_set

    async def execute(self, context: ExecutionContext) -> dict[str, Any]:
        operator, inputs = context.lease.operator, context.inputs
        fixture_set = context.metrics.get("fixture_set") or self.fixture_set
        node = next(n for n in context.plan.nodes if n.id == context.lease.node_id)
        if operator == "DISCOVER":
            if context.mode == "FIXTURE":
                return {
                    "urls": [d.url for d in fixture_documents(fixture_set)],
                    "fixture_label": "Captured historical public announcements"
                    if fixture_set == "captured"
                    else "Synthetic showcase raw evidence; not live business facts",
                }
            urls = [url for url in context.requirement.source_hints if "://" in url]
            errors: list[dict[str, Any]] = []
            for query in (
                []
                if urls and not node.params.get("queries")
                else node.params.get("queries") or [context.requirement.goal]
            ):
                try:
                    await self.store.reserve(context.lease, "search_queries")
                    hits = await self.search.search(query, limit=min(20, context.trust.max_pages))
                    urls.extend(hit.url for hit in hits)
                except ProofGridError as exc:
                    errors.append({"code": exc.code})
            return {
                "urls": list(dict.fromkeys(urls))[: context.trust.max_pages],
                "source_errors": errors,
            }
        if operator == "FETCH_HTTP":
            docs: list[AcquiredDocument] = []
            errors = list(inputs.get("source_errors", []))
            fixtures = (
                {d.url: d for d in fixture_documents(fixture_set)}
                if context.mode == "FIXTURE"
                else {}
            )
            for url in list(dict.fromkeys(inputs.get("urls", []) + node.params.get("urls", []))):
                try:
                    await self.store.reserve(context.lease, "pages")
                    doc = fixtures[url] if context.mode == "FIXTURE" else await self.http.fetch(url)
                    if context.mode != "FIXTURE":
                        doc = doc.model_copy(
                            update={
                                "metadata": {
                                    **doc.metadata,
                                    "first_party": urlsplit(doc.url).hostname
                                    in self.first_party_domains,
                                }
                            }
                        )
                    docs.append(doc)
                except ProofGridError as exc:
                    errors.append({"code": exc.code, "source_index": len(docs) + len(errors)})
                    if exc.code == "RUN_BUDGET_EXCEEDED":
                        break
            return {
                "documents": [d.model_dump(mode="json") for d in docs],
                "metrics": {"sources_fetched": len(docs), "source_errors": errors},
            }
        if operator == "EXTRACT":
            claims = []
            errors = list(context.metrics.get("source_errors", []))
            for document in context.documents:
                try:
                    drafts = deterministic_extract(
                        document["content"], document["content_type"], context.dataset_schema
                    )
                    if not drafts and self.extractor.provider is not None:
                        await self.store.reserve(context.lease, "llm_calls")
                        drafts, _ = await self.extractor.extract(
                            document["content"],
                            document["content_type"],
                            context.dataset_schema,
                            allow_llm=True,
                        )
                    for draft in drafts:
                        draft.raw_document_id = document["id"]
                        draft.source_id = document["source_id"]
                        claims.append(draft.model_dump(mode="json"))
                except Exception as exc:
                    errors.append(
                        {
                            "code": exc.code
                            if isinstance(exc, ProofGridError)
                            else "EXTRACTION_FAILED",
                            "raw_document_id": document["id"],
                        }
                    )
            return {
                "claims": claims[:10000],
                "metrics": {"source_errors": errors, "claims_proposed": len(claims)},
            }
        if operator in {"NORMALIZE", "VALIDATE"}:
            fields = {f.key: f for f in context.dataset_schema.fields}
            documents = {d["id"]: d for d in context.documents}
            claims = []
            for raw in inputs.get("claims", []):
                draft = ClaimDraft.model_validate(raw)
                if draft.field_key not in fields:
                    continue
                if operator == "NORMALIZE":
                    try:
                        draft.normalized_value = normalize(
                            draft.raw_value, str(fields[draft.field_key].data_type)
                        )
                    except NormalizationError:
                        draft.validation_flags.append("NORMALIZATION_FAILED")
                else:
                    stored_doc = documents[draft.raw_document_id]
                    draft.evidence = verify_anchor(
                        stored_doc["content"], draft.evidence, draft.raw_value
                    )
                    if not draft.evidence.verified:
                        draft.validation_flags.append("EVIDENCE_UNANCHORED")
                claims.append(draft.model_dump(mode="json"))
            return {"claims": claims}
        if operator in {"ENTITY_RESOLVE", "RECONCILE", "MATERIALIZE", "INDEX"}:
            return inputs
        if operator == "EXPORT":
            return {
                "format": node.params.get("format", "json"),
                "dataset_version_id": context.metrics.get("dataset_version_id"),
            }
        raise ProofGridError("OPERATOR_UNSUPPORTED", "Operator is not executable.")


class WorkerRunner:
    def __init__(self, store: ExecutionStore, executor: OperatorExecutor, worker_id: str):
        self.store, self.executor, self.worker_id = store, executor, worker_id

    async def tick(self) -> bool:
        await self.store.recover()
        lease = await self.store.claim(self.worker_id)
        if lease is None:
            return False
        log = get_logger("proofgrid.worker")
        ids = {
            "workflow_run_id": str(lease.run_id),
            "step_run_id": str(lease.step_id),
            "project_id": str(lease.project_id),
            "attempt": lease.attempt,
            "operator": lease.operator,
        }
        log.info("Step execution started", extra=ids)
        try:
            context = await self.store.context(lease)
        except Exception:
            await self.store.fail(lease, "STEP_CONTEXT_UNAVAILABLE", True)
            return True
        node = next(n for n in context.plan.nodes if n.id == lease.node_id)
        task = asyncio.create_task(self.executor.execute(context))

        async def heartbeat() -> None:
            while not task.done():
                await asyncio.sleep(5)
                if not await self.store.heartbeat(lease):
                    task.cancel()
                    return

        monitor = asyncio.create_task(heartbeat())
        try:
            async with asyncio.timeout(node.constraints.timeout_seconds):
                output = await task
            committed = await self.store.complete(lease, output)
            log.info("Step result processed", extra={**ids, "committed": committed})
        except ProofGridError as exc:
            log.warning("Step execution failed", extra={**ids, "error_code": exc.code})
            await self.store.fail(lease, exc.code, exc.retryable)
        except TimeoutError:
            await self.store.fail(lease, "STEP_TIMEOUT", True)
        except asyncio.CancelledError:
            await self.store.fail(lease, "RUN_CANCELLED", False)
        except Exception:
            await self.store.fail(lease, "INTERNAL_INVARIANT_VIOLATION", False)
        finally:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
        return True
