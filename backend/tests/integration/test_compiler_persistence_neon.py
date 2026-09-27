"""Neon PostgreSQL integration tests for Phase 3A: Requirement Compiler draft persistence.

Verifies against live Neon database (Alembic HEAD 9727a73ca3e4):
1. Atomic persistence of Requirement, DatasetSchema proposal, TrustContract proposal, and OutboxEvent.
2. Rollback leaves zero rows.
3. Historical versions are preserved without overwriting existing versions.
4. TrustContract remains unapproved (approved_at is None).
5. Fixture cleanup restores all tables to zero rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.ai.fixture_provider import FixtureProvider
from app.application.requirement_compiler.models import CompilerResult
from app.application.requirement_compiler.service import RequirementCompiler
from app.core.config import Settings, get_settings
from app.db.engine import create_engine_instance
from app.db.models import Project
from app.persistence.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration

EXPECTED_BUSINESS_TABLES = [
    "projects",
    "requirements",
    "dataset_schemas",
    "trust_contracts",
    "workflows",
    "workflow_versions",
    "workflow_runs",
    "step_runs",
    "workflow_events",
    "sources",
    "raw_documents",
    "claims",
    "evidence_anchors",
    "entities",
    "entity_matches",
    "canonical_values",
    "conflicts",
    "datasets",
    "dataset_versions",
    "dataset_version_records",
    "outbox_events",
]


@pytest.fixture(scope="module")
def settings() -> Settings:
    s = get_settings()
    if not s.DATABASE_URL or not s.database_direct_url_unmasked:
        pytest.skip(
            "Skipping database integration tests: DATABASE_URL or DATABASE_DIRECT_URL not configured"
        )
    return s


@pytest.fixture
def compiler() -> RequirementCompiler:
    provider = FixtureProvider()

    def clock() -> datetime:
        return datetime(2025, 3, 1, 12, 0, 0, tzinfo=UTC)

    return RequirementCompiler(provider=provider, clock=clock)


@pytest.mark.asyncio
async def test_neon_compiler_draft_persistence_atomic_commit(
    compiler: RequirementCompiler,
    settings: Settings,
) -> None:
    """Verify atomic persistence of compiled draft and historical version preservation."""
    prompt = (
        "Find Indian AI startups that raised funding in the last 18 months. "
        "For each company include company name, funding round, amount, currency, "
        "announcement date, investors, and source URL."
    )
    result = await compiler.compile(
        prompt,
        scenario="golden_indian_ai_funding",
    )
    assert isinstance(result, CompilerResult)

    proj_id: uuid.UUID | None = None
    req_id: uuid.UUID | None = None
    schema_v1_id: uuid.UUID | None = None
    trust_v1_id: uuid.UUID | None = None
    schema_v2_id: uuid.UUID | None = None
    trust_v2_id: uuid.UUID | None = None

    async with SqlAlchemyUnitOfWork() as uow:
        # Create parent project
        slug = f"proj-compile-{uuid.uuid4().hex[:8]}"
        project = uow.projects.add(Project(name="Compiler Test Project", slug=slug))
        await uow.session.flush()
        proj_id = project.id

        # Persist compiled draft v1
        req, schema1, trust1 = await compiler.persist_compilation_draft(
            uow=uow,
            project_id=project.id,
            original_prompt=prompt,
            compiler_result=result,
        )
        await uow.session.flush()
        req_id = req.id
        schema_v1_id = schema1.id
        trust_v1_id = trust1.id

        # Persist revised compilation draft v2 for the same requirement
        result_v2 = await compiler.compile(
            prompt + " (Revision 2)",
            scenario="golden_indian_ai_funding",
        )
        assert isinstance(result_v2, CompilerResult)
        _, schema2, trust2 = await compiler.persist_compilation_draft(
            uow=uow,
            project_id=project.id,
            original_prompt=prompt + " (Revision 2)",
            compiler_result=result_v2,
            requirement_id=req_id,
        )
        await uow.session.flush()
        schema_v2_id = schema2.id
        trust_v2_id = trust2.id

        await uow.commit()

    assert proj_id is not None
    assert req_id is not None
    assert schema_v1_id is not None
    assert trust_v1_id is not None
    assert schema_v2_id is not None
    assert trust_v2_id is not None

    # Verify rows in a new transaction
    async with SqlAlchemyUnitOfWork() as verify_uow:
        db_req = await verify_uow.requirements.get_requirement(req_id)
        assert db_req is not None
        assert db_req.status == "COMPILED"
        assert db_req.project_id == proj_id

        # Version 1 schema and trust contract
        v1_schema = await verify_uow.requirements.get_dataset_schema_by_version(req_id, 1)
        assert v1_schema is not None
        assert v1_schema.id == schema_v1_id
        assert v1_schema.version_number == 1

        v1_trust = await verify_uow.requirements.get_trust_contract_by_version(req_id, 1)
        assert v1_trust is not None
        assert v1_trust.id == trust_v1_id
        assert v1_trust.version_number == 1
        assert v1_trust.approved_at is None  # Unapproved proposal

        # Version 2 schema and trust contract: historical versioning preserved
        v2_schema = await verify_uow.requirements.get_dataset_schema_by_version(req_id, 2)
        assert v2_schema is not None
        assert v2_schema.id == schema_v2_id
        assert v2_schema.version_number == 2

        v2_trust = await verify_uow.requirements.get_trust_contract_by_version(req_id, 2)
        assert v2_trust is not None
        assert v2_trust.id == trust_v2_id
        assert v2_trust.version_number == 2
        assert v2_trust.approved_at is None

        # Verify all schemas for requirement: both version 1 and 2 exist
        all_schemas = await verify_uow.requirements.list_dataset_schemas(req_id)
        assert len(all_schemas) == 2
        assert [s.version_number for s in all_schemas] == [1, 2]

        all_trusts = await verify_uow.requirements.list_trust_contracts(req_id)
        assert len(all_trusts) == 2
        assert [t.version_number for t in all_trusts] == [1, 2]

        # Verify outbox events
        events = await verify_uow.outbox.list_by_status("PENDING")
        compilation_events = [e for e in events if e.aggregate_id == req_id]
        assert len(compilation_events) == 2
        for evt in compilation_events:
            assert evt.event_type == "requirement.compiled"
            assert evt.payload["requires_confirmation"] is True

    # Clean up fixture cleanly to guarantee 0-row invariant in Neon
    engine = create_engine_instance()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM outbox_events WHERE aggregate_id = :id"),
                {"id": req_id},
            )
            await conn.execute(
                text("DELETE FROM trust_contracts WHERE requirement_id = :id"),
                {"id": req_id},
            )
            await conn.execute(
                text("DELETE FROM dataset_schemas WHERE requirement_id = :id"),
                {"id": req_id},
            )
            await conn.execute(
                text("DELETE FROM requirements WHERE id = :id"),
                {"id": req_id},
            )
            await conn.execute(
                text("DELETE FROM projects WHERE id = :id"),
                {"id": proj_id},
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_neon_compiler_draft_persistence_rollback(
    compiler: RequirementCompiler,
    settings: Settings,
) -> None:
    """Verify that an uncommitted compiler draft persistence rolls back completely."""
    prompt = "Find Indian AI startups that raised funding in the last 18 months."
    result = await compiler.compile(prompt, scenario="golden_indian_ai_funding")
    assert isinstance(result, CompilerResult)

    test_req_id = uuid.uuid4()
    slug = f"proj-rb-{uuid.uuid4().hex[:8]}"

    with pytest.raises(RuntimeError, match="Simulated rollback"):
        async with SqlAlchemyUnitOfWork() as uow:
            project = uow.projects.add(Project(name="Rollback Project", slug=slug))
            await uow.session.flush()

            await compiler.persist_compilation_draft(
                uow=uow,
                project_id=project.id,
                original_prompt=prompt,
                compiler_result=result,
                requirement_id=test_req_id,
            )
            await uow.session.flush()

            msg = "Simulated rollback"
            raise RuntimeError(msg)

    # Verify nothing was persisted
    async with SqlAlchemyUnitOfWork() as verify_uow:
        req = await verify_uow.requirements.get_requirement(test_req_id)
        assert req is None
        proj = await verify_uow.projects.get_by_slug(slug)
        assert proj is None


@pytest.mark.asyncio
async def test_neon_persistence_zero_rows_guarantee(settings: Settings) -> None:
    """Verify that all 21 business tables remain completely clean (0 rows) after tests."""
    engine = create_engine_instance()
    try:
        async with engine.connect() as conn:
            for table in EXPECTED_BUSINESS_TABLES:
                res = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))  # noqa: S608
                count = res.scalar()
                assert count == 0, f"Table {table} must be clean (0 rows), but found {count} rows."
    finally:
        await engine.dispose()
