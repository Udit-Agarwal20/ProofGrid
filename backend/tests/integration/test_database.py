"""Real Neon PostgreSQL integration tests for Phase 2A and Phase 2B.

Verifies:
1. Live pooled connection and direct migration connection.
2. Async engine and session lifecycles.
3. Health check status and error sanitization against real Neon.
4. Alembic current revision is Phase 2B HEAD (9727a73ca3e4).
5. All 21 business tables exist in PostgreSQL public schema (+ alembic_version).
6. No unexpected tables exist.
7. Critical foreign keys, unique constraints, and indexes exist in PostgreSQL catalog.
8. Minimal relational fixture inserts cleanly across all 21 models.
9. Foreign key rejection, unique constraint rejection, and check constraint rejection.
10. Transaction rollback leaves exactly zero test data behind.
11. Confirmation that all business tables have 0 rows.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings, get_settings
from app.db.engine import create_engine_instance
from app.db.health import check_database_health
from app.db.models import (
    CanonicalValue,
    Claim,
    Conflict,
    Dataset,
    DatasetSchema,
    DatasetVersion,
    DatasetVersionRecord,
    Entity,
    EntityMatch,
    EvidenceAnchor,
    OutboxEvent,
    Project,
    RawDocument,
    Requirement,
    Source,
    StepRun,
    TrustContract,
    Workflow,
    WorkflowEvent,
    WorkflowRun,
    WorkflowVersion,
)
from app.db.session import get_session_factory

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration

PHASE_2B_HEAD_REVISION = "b73a8d401e20"

EXPECTED_BUSINESS_TABLES = {
    "exports",
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
}


@pytest.fixture(scope="module")
def settings() -> Settings:
    s = get_settings()
    if not s.DATABASE_URL or not s.database_direct_url_unmasked:
        pytest.skip(
            "Skipping database integration tests: DATABASE_URL or DATABASE_DIRECT_URL not configured"
        )
    return s


# -----------------------------------------------------------------------------
# Phase 2A Connectivity & Lifecycle Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_neon_pooled_connectivity(settings: Settings) -> None:
    """Verify live connectivity and SELECT 1 against Neon pooled connection."""
    engine = create_engine_instance()
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            assert res.scalar() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_neon_direct_connectivity(settings: Settings) -> None:
    """Verify live connectivity and SELECT 1 against Neon direct migration connection."""
    direct_url = settings.database_direct_url_unmasked
    assert direct_url is not None
    engine = create_async_engine(direct_url)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            assert res.scalar() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_async_engine_lifecycle(settings: Settings) -> None:
    """Verify async engine instance creation, execution, and disposal."""
    engine = create_engine_instance(pool_size=2, max_overflow=0)
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT 42 AS answer"))
        row = res.mappings().one()
        assert row["answer"] == 42
    await engine.dispose()


@pytest.mark.asyncio
async def test_async_session_creation_and_cleanup(settings: Settings) -> None:
    """Verify AsyncSession lifecycle and clean closure."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        res = await session.execute(text("SELECT 100"))
        assert res.scalar() == 100
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_transaction_rollback_behavior(settings: Settings) -> None:
    """Verify that transaction rollbacks cleanly discard uncommitted transaction state."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        tx = await session.begin()
        assert session.in_transaction()
        await session.execute(text("SELECT 1"))
        await tx.rollback()
        assert not session.in_transaction()


@pytest.mark.asyncio
async def test_health_checker_success_against_neon(settings: Settings) -> None:
    """Verify check_database_health succeeds and returns healthy status and latency."""
    result = await check_database_health(timeout_seconds=10.0)
    assert result.status == "healthy"
    assert result.latency_ms is not None
    assert result.latency_ms > 0
    assert result.error is None


@pytest.mark.asyncio
async def test_health_checker_graceful_failure_simulation() -> None:
    """Verify check_database_health sanitizes error messages and handles faults gracefully."""

    class FaultyEngine:
        def connect(self) -> Any:
            raise ConnectionRefusedError(
                "Connection refused to postgresql://user:supersecretpass@badhost:5432/db"
            )

    result = await check_database_health(engine=FaultyEngine(), timeout_seconds=1.0)  # type: ignore[arg-type]
    assert result.status == "unhealthy"
    assert result.error is not None
    assert "ConnectionRefusedError" in result.error
    assert "supersecretpass" not in result.error


# -----------------------------------------------------------------------------
# Phase 2B Schema State & Constraint Verification Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alembic_current_revision_is_phase2b_head(settings: Settings) -> None:
    """Verify that Alembic's tracking table in Neon is at Phase 2B HEAD revision."""
    direct_url = settings.database_direct_url_unmasked
    assert direct_url is not None
    engine = create_async_engine(direct_url)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT version_num FROM alembic_version"))
            row = res.fetchone()
            assert row is not None, "alembic_version table is empty"
            version_num = row[0]
            assert version_num == PHASE_2B_HEAD_REVISION, (
                f"Expected revision '{PHASE_2B_HEAD_REVISION}', got: {version_num}"
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_neon_table_inventory(settings: Settings) -> None:
    """Verify exactly the 21 business tables plus alembic_version exist in Neon."""
    engine = create_engine_instance()
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                )
            )
            tables = {row[0] for row in res.fetchall()}
            expected_tables = EXPECTED_BUSINESS_TABLES | {"alembic_version"}
            assert tables == expected_tables, (
                f"Table inventory mismatch. Diff: {tables ^ expected_tables}"
            )
            assert len(tables) == 23
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_neon_critical_constraints_and_indexes(settings: Settings) -> None:
    """Verify critical named constraints and indexes exist in the live PostgreSQL catalog."""
    engine = create_engine_instance()
    try:
        async with engine.connect() as conn:

            def _inspect_catalog(
                sync_conn: Any,
            ) -> tuple[set[str], set[str], dict[str, dict[str, Any]]]:
                insp = inspect(sync_conn)
                indexes = set()
                constraints = set()
                foreign_keys: dict[str, dict[str, Any]] = {}
                for table in EXPECTED_BUSINESS_TABLES:
                    foreign_keys[table] = {}
                    for idx in insp.get_indexes(table):
                        indexes.add(idx["name"])
                    for uq in insp.get_unique_constraints(table):
                        if uq["name"]:
                            constraints.add(uq["name"])
                    for ck in insp.get_check_constraints(table):
                        if ck["name"]:
                            constraints.add(ck["name"])
                    for fk in insp.get_foreign_keys(table):
                        # Key by constrained column name
                        for col in fk["constrained_columns"]:
                            foreign_keys[table][col] = {
                                "referred_table": fk["referred_table"],
                                "referred_columns": fk["referred_columns"],
                                "options": fk.get("options", {}),
                            }
                return indexes, constraints, foreign_keys

            indexes, constraints, fks = await conn.run_sync(_inspect_catalog)

            # Check critical named unique constraints
            assert "ux_step_idempotency" in constraints
            assert "uq_sources_project_canonical_url" in constraints
            assert "uq_canonical_values_version_entity_field" in constraints
            assert "uq_dataset_version_records_version_entity" in constraints
            assert "uq_entity_matches_pair" in constraints

            # raw_documents content_hash must NOT be unique
            assert "ux_raw_documents_content_hash" not in constraints

            # Check critical named check constraints
            assert "ck_entity_matches_canonical_pair_order" in constraints
            assert "ck_canonical_values_trust_status" in constraints

            # Check critical named indexes
            assert "ix_step_runs_ready" in indexes
            assert "ix_claims_entity_field" in indexes
            assert "ux_entities_project_stable_key" in indexes
            assert "ix_raw_documents_project_content_hash" in indexes
            assert "ix_workflow_versions_dataset_schema_id" in indexes
            assert "ix_workflow_versions_trust_contract_id" in indexes
            assert "ix_trust_contracts_dataset_schema_id" in indexes
            assert "ix_dataset_versions_schema_id" in indexes
            assert "ix_datasets_workflow_id" in indexes
            assert "ix_claims_source_id" in indexes

            # Check 10 critical foreign key relationships in PostgreSQL catalog
            # 1. trust_contracts.dataset_schema_id -> dataset_schemas.id
            assert (
                fks["trust_contracts"]["dataset_schema_id"]["referred_table"] == "dataset_schemas"
            )
            # 2. workflow_versions.dataset_schema_id -> dataset_schemas.id
            assert (
                fks["workflow_versions"]["dataset_schema_id"]["referred_table"] == "dataset_schemas"
            )
            # 3. workflow_versions.trust_contract_id -> trust_contracts.id
            assert (
                fks["workflow_versions"]["trust_contract_id"]["referred_table"] == "trust_contracts"
            )
            # 4. datasets.workflow_id -> workflows.id
            assert fks["datasets"]["workflow_id"]["referred_table"] == "workflows"
            # 5. dataset_versions.dataset_schema_id -> dataset_schemas.id
            assert (
                fks["dataset_versions"]["dataset_schema_id"]["referred_table"] == "dataset_schemas"
            )
            # 6. dataset_versions.workflow_run_id -> workflow_runs.id
            assert fks["dataset_versions"]["workflow_run_id"]["referred_table"] == "workflow_runs"
            # 7. claims.source_id -> sources.id
            assert fks["claims"]["source_id"]["referred_table"] == "sources"
            # 8. claims.entity_id -> entities.id
            assert fks["claims"]["entity_id"]["referred_table"] == "entities"
            # 9. canonical_values.dataset_version_id -> dataset_versions.id
            assert (
                fks["canonical_values"]["dataset_version_id"]["referred_table"]
                == "dataset_versions"
            )
            # 10. conflicts.dataset_version_id -> dataset_versions.id
            assert fks["conflicts"]["dataset_version_id"]["referred_table"] == "dataset_versions"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_minimal_relational_fixture_insertion_and_rollback(
    settings: Settings,
) -> None:
    """Insert a minimal valid relational fixture across all models and verify clean rollback."""
    session_factory = get_session_factory()
    test_slug = f"test-project-{uuid.uuid4().hex[:8]}"

    async with session_factory() as session, session.begin():
        # 1. Project
        proj = Project(name="Synthetic Test Project", slug=test_slug)
        session.add(proj)
        await session.flush()

        # 2. Requirement
        req = Requirement(
            project_id=proj.id,
            original_prompt="Find synthetic test companies",
            requirement_spec={"goal": "test", "fields": [{"key": "name", "data_type": "text"}]},
            status="COMPILED",
        )
        session.add(req)
        await session.flush()

        # 3. DatasetSchema
        schema = DatasetSchema(
            project_id=proj.id,
            requirement_id=req.id,
            version_number=1,
            schema_definition={"fields": [{"key": "company_name", "data_type": "text"}]},
        )
        session.add(schema)
        await session.flush()

        # 4. TrustContract
        contract = TrustContract(
            project_id=proj.id,
            requirement_id=req.id,
            dataset_schema_id=schema.id,
            version_number=1,
            contract_definition={"require_evidence_anchor": True, "max_pages": 10},
        )
        session.add(contract)
        await session.flush()

        # 5. Workflow
        wf = Workflow(
            project_id=proj.id,
            requirement_id=req.id,
            name="Test Workflow",
            status="ACTIVE",
        )
        session.add(wf)
        await session.flush()

        # 6. WorkflowVersion
        wv = WorkflowVersion(
            workflow_id=wf.id,
            version_number=1,
            dataset_schema_id=schema.id,
            trust_contract_id=contract.id,
            plan_dag={"nodes": [{"id": "n1", "operator": "DISCOVER"}]},
        )
        session.add(wv)
        await session.flush()

        # 7. WorkflowRun
        run = WorkflowRun(
            project_id=proj.id,
            workflow_version_id=wv.id,
            status="RUNNING",
            run_mode="LIVE",
        )
        session.add(run)
        await session.flush()

        # 8. StepRun
        step = StepRun(
            workflow_run_id=run.id,
            node_id="n1",
            operator_type="DISCOVER",
            attempt=1,
            status="READY",
        )
        session.add(step)
        await session.flush()

        # 9. WorkflowEvent
        event = WorkflowEvent(
            workflow_run_id=run.id,
            sequence_number=1,
            event_type="RUN_STARTED",
            payload={"info": "started"},
        )
        session.add(event)
        await session.flush()

        # 10. Source
        src = Source(
            project_id=proj.id,
            canonical_url=f"https://synthetic-test.example.com/{uuid.uuid4().hex[:6]}",
            domain="synthetic-test.example.com",
            source_type="WEB_PAGE",
            source_metadata={"trust_rank": 1},
        )
        session.add(src)
        await session.flush()

        # 11. RawDocument
        doc = RawDocument(
            project_id=proj.id,
            workflow_run_id=run.id,
            source_id=src.id,
            retrieved_at=datetime.now(UTC),
            final_url=src.canonical_url,
            http_status=200,
            content_hash=f"hash_{uuid.uuid4().hex}",
            retrieval_metadata={"parser": "test"},
        )
        session.add(doc)
        await session.flush()

        # 12. Entity
        ent1 = Entity(
            project_id=proj.id,
            entity_type="company",
            canonical_name="Synthetic Corp Alpha",
            stable_entity_key=f"key_{uuid.uuid4().hex[:8]}",
        )
        ent2 = Entity(
            project_id=proj.id,
            entity_type="company",
            canonical_name="Synthetic Corp Beta",
            stable_entity_key=f"key_{uuid.uuid4().hex[:8]}",
        )
        session.add_all([ent1, ent2])
        await session.flush()

        # 13. EntityMatch (enforcing canonical UUID ordering source < target)
        src_ent, tgt_ent = (ent1, ent2) if ent1.id < ent2.id else (ent2, ent1)
        match = EntityMatch(
            project_id=proj.id,
            source_entity_id=src_ent.id,
            target_entity_id=tgt_ent.id,
            decision="KEEP_SEPARATE",
            signals={"lexical_similarity": 0.1},
        )
        session.add(match)
        await session.flush()

        # 14. Claim
        claim = Claim(
            project_id=proj.id,
            workflow_run_id=run.id,
            raw_document_id=doc.id,
            source_id=src.id,
            entity_id=ent1.id,
            field_key="company_name",
            raw_value="Synthetic Corp Alpha",
            validation_flags=["extracted_text_match"],
            claim_hash=f"chash_{uuid.uuid4().hex}",
        )
        session.add(claim)
        await session.flush()

        # 15. EvidenceAnchor
        anchor = EvidenceAnchor(
            claim_id=claim.id,
            raw_document_id=doc.id,
            anchor_type="TEXT_SPAN",
            locator={"start": 0, "end": 20},
            quoted_text="Synthetic Corp Alpha",
            verification_status="EXACT",
        )
        session.add(anchor)
        await session.flush()

        # 16. Dataset
        dataset = Dataset(
            project_id=proj.id,
            workflow_id=wf.id,
            name="Synthetic Dataset",
            slug=f"ds-{uuid.uuid4().hex[:8]}",
        )
        session.add(dataset)
        await session.flush()

        # 17. DatasetVersion (project_id scoped)
        dv = DatasetVersion(
            project_id=proj.id,
            dataset_id=dataset.id,
            dataset_schema_id=schema.id,
            workflow_run_id=run.id,
            version_number=1,
            status="FINALIZED",
            record_count=1,
        )
        session.add(dv)
        await session.flush()

        # 18. CanonicalValue (dataset-version scoped)
        cv = CanonicalValue(
            project_id=proj.id,
            dataset_version_id=dv.id,
            entity_id=ent1.id,
            field_key="company_name",
            value="Synthetic Corp Alpha",
            trust_status="VERIFIED",
            selected_claim_id=claim.id,
        )
        session.add(cv)
        await session.flush()

        # 19. Conflict (dataset-version scoped)
        conflict = Conflict(
            project_id=proj.id,
            dataset_version_id=dv.id,
            entity_id=ent1.id,
            field_key="funding_amount",
            conflict_type="VALUE_MISMATCH",
            status="OPEN",
            details={"source_a": "$5M", "source_b": "$6M"},
        )
        session.add(conflict)
        await session.flush()

        # 20. DatasetVersionRecord (dataset-version scoped)
        dvr = DatasetVersionRecord(
            project_id=proj.id,
            dataset_version_id=dv.id,
            entity_id=ent1.id,
            record_data={"company_name": "Synthetic Corp Alpha"},
            trust_summary={"overall_trust": "VERIFIED"},
            record_hash=f"rhash_{uuid.uuid4().hex}",
        )
        session.add(dvr)
        await session.flush()

        # 21. OutboxEvent
        outbox = OutboxEvent(
            project_id=proj.id,
            aggregate_type="dataset_version",
            aggregate_id=dv.id,
            event_type="DATASET_VERSION_FINALIZED",
            payload={"version_number": 1},
            status="PENDING",
        )
        session.add(outbox)
        await session.flush()

        # Assert all 21 models exist in the transaction
        for model_cls, model_id in [
            (Project, proj.id),
            (Requirement, req.id),
            (DatasetSchema, schema.id),
            (TrustContract, contract.id),
            (Workflow, wf.id),
            (WorkflowVersion, wv.id),
            (WorkflowRun, run.id),
            (StepRun, step.id),
            (WorkflowEvent, event.id),
            (Source, src.id),
            (RawDocument, doc.id),
            (Entity, ent1.id),
            (EntityMatch, match.id),
            (Claim, claim.id),
            (EvidenceAnchor, anchor.id),
            (Dataset, dataset.id),
            (DatasetVersion, dv.id),
            (CanonicalValue, cv.id),
            (Conflict, conflict.id),
            (DatasetVersionRecord, dvr.id),
            (OutboxEvent, outbox.id),
        ]:
            item = await session.get(model_cls, model_id)
            assert item is not None, f"Failed to retrieve {model_cls.__name__}"

        # Roll back everything
        await session.rollback()

    # Verify completely clean after rollback
    async with session_factory() as session:
        proj_check = await session.execute(select(Project).where(Project.slug == test_slug))
        assert proj_check.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_neon_foreign_key_violation_rejected(settings: Settings) -> None:
    """Verify that inserting a row with a non-existent foreign key is strictly rejected."""
    session_factory = get_session_factory()
    non_existent_id = uuid.uuid4()

    async with session_factory() as session, session.begin():
        req = Requirement(
            project_id=non_existent_id,
            original_prompt="Should fail FK check",
            requirement_spec={},
        )
        session.add(req)
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert "foreign key constraint" in str(exc_info.value).lower()
        await session.rollback()


@pytest.mark.asyncio
async def test_neon_unique_constraint_violation_rejected(settings: Settings) -> None:
    """Verify that duplicate unique values are rejected by PostgreSQL."""
    session_factory = get_session_factory()
    test_slug = f"unique-test-{uuid.uuid4().hex[:8]}"
    async with session_factory() as session, session.begin():
        p1 = Project(name="Project 1", slug=test_slug)
        session.add(p1)
        await session.flush()

        p2 = Project(name="Project 2", slug=test_slug)
        session.add(p2)
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert (
            "unique constraint" in str(exc_info.value).lower()
            or "duplicate key" in str(exc_info.value).lower()
        )
        await session.rollback()


@pytest.mark.asyncio
async def test_neon_check_constraint_violation_rejected(settings: Settings) -> None:
    """Verify that values violating check constraints are rejected by PostgreSQL."""
    session_factory = get_session_factory()

    async with session_factory() as session, session.begin():
        p = Project(name="Test Project", slug=f"p-{uuid.uuid4().hex[:8]}")
        session.add(p)
        await session.flush()

        # Attempt to insert invalid status into requirement
        req = Requirement(
            project_id=p.id,
            original_prompt="Prompt",
            requirement_spec={},
            status="INVALID_STATUS_VALUE",
        )
        session.add(req)
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert "check constraint" in str(exc_info.value).lower()
        await session.rollback()


@pytest.mark.asyncio
async def test_neon_entity_match_pair_order_and_no_self_match(settings: Settings) -> None:
    """Verify entity_matches rejects self-matches and enforces canonical UUID order."""
    session_factory = get_session_factory()
    test_slug = f"em-test-{uuid.uuid4().hex[:8]}"

    async with session_factory() as session, session.begin():
        p = Project(name="EM Project", slug=test_slug)
        session.add(p)
        await session.flush()

        e1 = Entity(project_id=p.id, canonical_name="E1", entity_type="company")
        e2 = Entity(project_id=p.id, canonical_name="E2", entity_type="company")
        session.add_all([e1, e2])
        await session.flush()

        # 1. Self-match must be rejected by check constraint
        m_self = EntityMatch(
            project_id=p.id,
            source_entity_id=e1.id,
            target_entity_id=e1.id,
            decision="AUTO_MERGE",
            signals={},
        )
        session.add(m_self)
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert "ck_entity_matches_canonical_pair_order" in str(exc_info.value).lower()
        await session.rollback()

    async with session_factory() as session, session.begin():
        p = Project(name="EM Project 2", slug=f"{test_slug}-2")
        session.add(p)
        await session.flush()

        e1 = Entity(project_id=p.id, canonical_name="E1", entity_type="company")
        e2 = Entity(project_id=p.id, canonical_name="E2", entity_type="company")
        session.add_all([e1, e2])
        await session.flush()

        # Determine smaller and larger UUID
        smaller_id, larger_id = (e1.id, e2.id) if e1.id < e2.id else (e2.id, e1.id)

        # 2. Inverted order (larger < smaller is FALSE) must be rejected
        m_inv = EntityMatch(
            project_id=p.id,
            source_entity_id=larger_id,
            target_entity_id=smaller_id,
            decision="AUTO_MERGE",
            signals={},
        )
        session.add(m_inv)
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert "ck_entity_matches_canonical_pair_order" in str(exc_info.value).lower()
        await session.rollback()


@pytest.mark.asyncio
async def test_neon_raw_document_independent_provenance_identical_content_hash(
    settings: Settings,
) -> None:
    """Verify separate sources can store identical content_hash without unique violation."""
    session_factory = get_session_factory()
    test_slug = f"prov-test-{uuid.uuid4().hex[:8]}"

    async with session_factory() as session, session.begin():
        p = Project(name="Prov Project", slug=test_slug)
        session.add(p)
        await session.flush()

        s1 = Source(
            project_id=p.id,
            canonical_url=f"https://source1.example.com/{uuid.uuid4().hex[:6]}",
            domain="source1.example.com",
            source_type="WEB_PAGE",
            source_metadata={},
        )
        s2 = Source(
            project_id=p.id,
            canonical_url=f"https://source2.example.com/{uuid.uuid4().hex[:6]}",
            domain="source2.example.com",
            source_type="WEB_PAGE",
            source_metadata={},
        )
        session.add_all([s1, s2])
        await session.flush()

        shared_hash = f"identical_sha256_{uuid.uuid4().hex}"
        d1 = RawDocument(
            project_id=p.id,
            source_id=s1.id,
            final_url=s1.canonical_url,
            content_hash=shared_hash,
            retrieval_metadata={},
        )
        d2 = RawDocument(
            project_id=p.id,
            source_id=s2.id,
            final_url=s2.canonical_url,
            content_hash=shared_hash,
            retrieval_metadata={},
        )
        # Both must succeed without unique constraint error!
        session.add_all([d1, d2])
        await session.flush()

        assert d1.id != d2.id
        assert d1.content_hash == d2.content_hash
        await session.rollback()


@pytest.mark.asyncio
async def test_neon_canonical_values_dataset_version_scoped(settings: Settings) -> None:
    """Verify canonical values are dataset-version scoped; v1 and v2 coexist for same entity."""
    session_factory = get_session_factory()
    test_slug = f"cv-version-test-{uuid.uuid4().hex[:8]}"

    async with session_factory() as session, session.begin():
        p = Project(name="CV Version Project", slug=test_slug)
        session.add(p)
        await session.flush()

        req = Requirement(
            project_id=p.id,
            original_prompt="CV test",
            requirement_spec={"goal": "test"},
        )
        session.add(req)
        await session.flush()

        schema = DatasetSchema(
            project_id=p.id,
            requirement_id=req.id,
            version_number=1,
            schema_definition={"fields": []},
        )
        session.add(schema)
        await session.flush()

        ds = Dataset(project_id=p.id, name="Test DS", slug=f"ds-{uuid.uuid4().hex[:8]}")
        session.add(ds)
        await session.flush()

        dv1 = DatasetVersion(
            project_id=p.id,
            dataset_id=ds.id,
            dataset_schema_id=schema.id,
            version_number=1,
            status="FINALIZED",
            record_count=1,
        )
        dv2 = DatasetVersion(
            project_id=p.id,
            dataset_id=ds.id,
            dataset_schema_id=schema.id,
            version_number=2,
            status="FINALIZED",
            record_count=1,
        )
        session.add_all([dv1, dv2])
        await session.flush()

        ent = Entity(project_id=p.id, canonical_name="Acme Corp", entity_type="company")
        session.add(ent)
        await session.flush()

        # v1 value: 4.5M, SUPPORTED
        cv1 = CanonicalValue(
            project_id=p.id,
            dataset_version_id=dv1.id,
            entity_id=ent.id,
            field_key="funding_amount",
            value=4500000,
            trust_status="SUPPORTED",
        )
        # v2 value: 5.0M, VERIFIED
        cv2 = CanonicalValue(
            project_id=p.id,
            dataset_version_id=dv2.id,
            entity_id=ent.id,
            field_key="funding_amount",
            value=5000000,
            trust_status="VERIFIED",
        )
        session.add_all([cv1, cv2])
        await session.flush()

        # Both must exist simultaneously
        fetched_cv1 = await session.get(CanonicalValue, cv1.id)
        fetched_cv2 = await session.get(CanonicalValue, cv2.id)
        assert fetched_cv1 is not None and fetched_cv1.value == 4500000
        assert fetched_cv2 is not None and fetched_cv2.value == 5000000

        # Duplicate in same dataset version must be rejected
        cv_dup = CanonicalValue(
            project_id=p.id,
            dataset_version_id=dv1.id,
            entity_id=ent.id,
            field_key="funding_amount",
            value=9999999,
            trust_status="VERIFIED",
        )
        session.add(cv_dup)
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert "uq_canonical_values_version_entity_field" in str(exc_info.value).lower()
        await session.rollback()


@pytest.mark.asyncio
async def test_neon_schema_version_reproducibility_coexistence(
    settings: Settings,
) -> None:
    """Verify Requirement -> Schema v1/v2 -> Trust Contract v1/v2 -> Workflow Version v1/v2 -> Dataset Version 1/2 coexist."""
    session_factory = get_session_factory()
    test_slug = f"repro-test-{uuid.uuid4().hex[:8]}"

    async with session_factory() as session, session.begin():
        # Logical identities: 1 Project, 1 Requirement, 1 Workflow, 1 Dataset
        proj = Project(name="Reproducibility Project", slug=test_slug)
        session.add(proj)
        await session.flush()

        req = Requirement(
            project_id=proj.id,
            original_prompt="Track corporate funding rounds over time",
            requirement_spec={"fields": [{"key": "round_name"}, {"key": "amount"}]},
            status="ACCEPTED",
        )
        session.add(req)
        await session.flush()

        wf = Workflow(
            project_id=proj.id,
            requirement_id=req.id,
            name="Funding Round Extraction Pipeline",
            status="ACTIVE",
        )
        session.add(wf)
        await session.flush()

        dataset = Dataset(
            project_id=proj.id,
            workflow_id=wf.id,
            name="Corporate Funding Dataset",
            slug=f"ds-funding-{uuid.uuid4().hex[:8]}",
        )
        session.add(dataset)
        await session.flush()

        # --- VERSION 1 ---
        schema_v1 = DatasetSchema(
            project_id=proj.id,
            requirement_id=req.id,
            version_number=1,
            schema_definition={"version": 1, "fields": ["round_name", "amount"]},
        )
        session.add(schema_v1)
        await session.flush()

        trust_v1 = TrustContract(
            project_id=proj.id,
            requirement_id=req.id,
            dataset_schema_id=schema_v1.id,
            version_number=1,
            contract_definition={"min_sources": 1, "require_anchors": True},
        )
        session.add(trust_v1)
        await session.flush()

        wv_1 = WorkflowVersion(
            workflow_id=wf.id,
            version_number=1,
            dataset_schema_id=schema_v1.id,
            trust_contract_id=trust_v1.id,
            plan_dag={"version": 1, "steps": ["DISCOVER", "EXTRACT"]},
        )
        session.add(wv_1)
        await session.flush()

        run_1 = WorkflowRun(
            project_id=proj.id,
            workflow_version_id=wv_1.id,
            status="COMPLETED",
            run_mode="LIVE",
        )
        session.add(run_1)
        await session.flush()

        dv_1 = DatasetVersion(
            project_id=proj.id,
            dataset_id=dataset.id,
            dataset_schema_id=schema_v1.id,
            workflow_run_id=run_1.id,
            version_number=1,
            status="FINALIZED",
            record_count=10,
        )
        session.add(dv_1)
        await session.flush()

        # --- VERSION 2 (Schema evolution, Trust Contract revision, new Workflow Version, new Dataset Version) ---
        schema_v2 = DatasetSchema(
            project_id=proj.id,
            requirement_id=req.id,
            version_number=2,
            schema_definition={"version": 2, "fields": ["round_name", "amount", "lead_investor"]},
        )
        session.add(schema_v2)
        await session.flush()

        trust_v2 = TrustContract(
            project_id=proj.id,
            requirement_id=req.id,
            dataset_schema_id=schema_v2.id,
            version_number=2,
            contract_definition={"min_sources": 2, "require_anchors": True},
        )
        session.add(trust_v2)
        await session.flush()

        wv_2 = WorkflowVersion(
            workflow_id=wf.id,
            version_number=2,
            dataset_schema_id=schema_v2.id,
            trust_contract_id=trust_v2.id,
            plan_dag={"version": 2, "steps": ["DISCOVER", "EXTRACT", "VALIDATE_INVESTOR"]},
        )
        session.add(wv_2)
        await session.flush()

        run_2 = WorkflowRun(
            project_id=proj.id,
            workflow_version_id=wv_2.id,
            status="COMPLETED",
            run_mode="LIVE",
        )
        session.add(run_2)
        await session.flush()

        dv_2 = DatasetVersion(
            project_id=proj.id,
            dataset_id=dataset.id,
            dataset_schema_id=schema_v2.id,
            workflow_run_id=run_2.id,
            version_number=2,
            status="FINALIZED",
            record_count=15,
        )
        session.add(dv_2)
        await session.flush()

        # Direct assertions proving reproducibility and coexistence without mutating Version 1
        assert dv_1.dataset_schema_id == schema_v1.id
        assert dv_2.dataset_schema_id == schema_v2.id

        assert wv_1.dataset_schema_id == schema_v1.id
        assert wv_1.trust_contract_id == trust_v1.id

        assert wv_2.dataset_schema_id == schema_v2.id
        assert wv_2.trust_contract_id == trust_v2.id

        # Verify query retrieval directly from session
        fetched_dv1 = await session.get(DatasetVersion, dv_1.id)
        fetched_dv2 = await session.get(DatasetVersion, dv_2.id)
        assert fetched_dv1 is not None and fetched_dv1.dataset_schema_id == schema_v1.id
        assert fetched_dv2 is not None and fetched_dv2.dataset_schema_id == schema_v2.id

        fetched_wv1 = await session.get(WorkflowVersion, wv_1.id)
        fetched_wv2 = await session.get(WorkflowVersion, wv_2.id)
        assert fetched_wv1 is not None
        assert fetched_wv1.dataset_schema_id == schema_v1.id
        assert fetched_wv1.trust_contract_id == trust_v1.id
        assert fetched_wv2 is not None
        assert fetched_wv2.dataset_schema_id == schema_v2.id
        assert fetched_wv2.trust_contract_id == trust_v2.id

        # Rollback cleanly
        await session.rollback()


@pytest.mark.asyncio
async def test_neon_claim_provenance_and_nullable_entity(settings: Settings) -> None:
    """Verify claim references source, raw_document, entity and allows initial NULL entity_id."""
    session_factory = get_session_factory()
    test_slug = f"claim-prov-test-{uuid.uuid4().hex[:8]}"

    async with session_factory() as session, session.begin():
        # Setup parent entities: Project, Requirement, Workflow, WorkflowVersion, WorkflowRun, Source, RawDocument
        proj = Project(name="Claim Provenance Project", slug=test_slug)
        session.add(proj)
        await session.flush()

        req = Requirement(
            project_id=proj.id,
            original_prompt="Extract founders",
            requirement_spec={},
        )
        session.add(req)
        await session.flush()

        schema = DatasetSchema(
            project_id=proj.id,
            requirement_id=req.id,
            version_number=1,
            schema_definition={},
        )
        session.add(schema)
        await session.flush()

        tc = TrustContract(
            project_id=proj.id,
            requirement_id=req.id,
            dataset_schema_id=schema.id,
            version_number=1,
            contract_definition={},
        )
        session.add(tc)
        await session.flush()

        wf = Workflow(project_id=proj.id, requirement_id=req.id, name="Extraction WF")
        session.add(wf)
        await session.flush()

        wv = WorkflowVersion(
            workflow_id=wf.id,
            version_number=1,
            dataset_schema_id=schema.id,
            trust_contract_id=tc.id,
            plan_dag={},
        )
        session.add(wv)
        await session.flush()

        run = WorkflowRun(
            project_id=proj.id,
            workflow_version_id=wv.id,
            status="RUNNING",
            run_mode="LIVE",
        )
        session.add(run)
        await session.flush()

        src = Source(
            project_id=proj.id,
            canonical_url=f"https://provenance-example.com/{uuid.uuid4().hex[:6]}",
            domain="provenance-example.com",
            source_type="WEB_PAGE",
            source_metadata={},
        )
        session.add(src)
        await session.flush()

        doc = RawDocument(
            project_id=proj.id,
            workflow_run_id=run.id,
            source_id=src.id,
            retrieved_at=datetime.now(UTC),
            final_url=src.canonical_url,
            content_hash=f"hash_{uuid.uuid4().hex}",
            retrieval_metadata={},
        )
        session.add(doc)
        await session.flush()

        entity = Entity(
            project_id=proj.id,
            canonical_name="Jane Doe",
            entity_type="person",
            stable_entity_key=f"person_{uuid.uuid4().hex[:8]}",
        )
        session.add(entity)
        await session.flush()

        # 1. Extraction before resolution: entity_id is NULL initially
        claim_unresolved = Claim(
            project_id=proj.id,
            workflow_run_id=run.id,
            raw_document_id=doc.id,
            source_id=src.id,
            entity_id=None,
            field_key="founder_name",
            raw_value="Jane Doe",
            validation_flags=["raw_span_match"],
            claim_hash=f"hash_unres_{uuid.uuid4().hex}",
        )
        session.add(claim_unresolved)
        await session.flush()

        assert claim_unresolved.id is not None
        assert claim_unresolved.entity_id is None
        assert claim_unresolved.source_id == src.id
        assert claim_unresolved.raw_document_id == doc.id

        # 2. Fully resolved claim: references source, raw_document, AND entity
        claim_resolved = Claim(
            project_id=proj.id,
            workflow_run_id=run.id,
            raw_document_id=doc.id,
            source_id=src.id,
            entity_id=entity.id,
            field_key="founder_name",
            raw_value="Jane Doe",
            validation_flags=["resolved_entity_match"],
            claim_hash=f"hash_res_{uuid.uuid4().hex}",
        )
        session.add(claim_resolved)
        await session.flush()

        # Direct assertions required by prompt
        assert claim_resolved.source_id == src.id
        assert claim_resolved.raw_document_id == doc.id
        assert claim_resolved.entity_id == entity.id

        # Verify persistence and query retrieval
        fetched_unresolved = await session.get(Claim, claim_unresolved.id)
        assert fetched_unresolved is not None
        assert fetched_unresolved.entity_id is None
        assert fetched_unresolved.source_id == src.id
        assert fetched_unresolved.raw_document_id == doc.id

        fetched_resolved = await session.get(Claim, claim_resolved.id)
        assert fetched_resolved is not None
        assert fetched_resolved.source_id == src.id
        assert fetched_resolved.raw_document_id == doc.id
        assert fetched_resolved.entity_id == entity.id

        # Rollback cleanly
        await session.rollback()


@pytest.mark.asyncio
async def test_neon_fixture_cleanup_guarantee(settings: Settings) -> None:
    """Verify all 21 business tables are completely empty after integration test execution."""
    engine = create_engine_instance()
    try:
        async with engine.connect() as conn:
            for table in EXPECTED_BUSINESS_TABLES:
                res = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))  # noqa: S608
                count = res.scalar()
                assert count == 0, f"Table {table} must be clean (0 rows), but found {count} rows."
    finally:
        await engine.dispose()
