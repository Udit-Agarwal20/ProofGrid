"""Real Neon PostgreSQL integration tests for Phase 2C persistence layer.

Verifies against live Neon database (Alembic HEAD 9727a73ca3e4):
1. UnitOfWork shared AsyncSession invariant across all 8 repositories.
2. Atomic UnitOfWork commit and rollback with Transactional Outbox events.
3. No-hidden-commit guarantee on uncommitted context exit.
4. ProjectRepository lifecycle and queries.
5. RequirementRepository version-deterministic queries (schemas, trust contracts).
6. WorkflowRepository provenance and version queries (versions, runs, step runs, events).
7. SourceRepository source and raw document content-hash queries.
8. ClaimRepository claim and evidence anchor persistence.
9. EntityRepository canonical pair ordering enforcement and self-match rejection.
10. DatasetRepository dataset versioning, canonical values, conflicts, and records.
11. Persistence fixture cleanup guarantee across all 21 business tables.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, get_settings
from app.db.engine import create_engine_instance
from app.db.models import (
    CanonicalValue,
    Claim,
    Conflict,
    Dataset,
    DatasetSchema,
    DatasetVersion,
    DatasetVersionRecord,
    Entity,
    EvidenceAnchor,
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
from app.persistence.errors import (
    PersistenceConflictError,
    PersistenceIntegrityError,
    translate_db_error,
)
from app.persistence.repositories.outbox import OutboxEventCreate
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


@pytest.mark.asyncio
async def test_neon_uow_shared_session_instance(settings: Settings) -> None:
    """Verify live UnitOfWork binds the identical AsyncSession instance to all 8 repositories."""
    uow = SqlAlchemyUnitOfWork()
    async with uow:
        session = uow.session
        assert session is not None
        assert uow.projects.session is session
        assert uow.requirements.session is session
        assert uow.workflows.session is session
        assert uow.sources.session is session
        assert uow.claims.session is session
        assert uow.entities.session is session
        assert uow.datasets.session is session
        assert uow.outbox.session is session


@pytest.mark.asyncio
async def test_neon_uow_transactional_outbox_rollback(settings: Settings) -> None:
    """Verify that uncommitted transactions or exceptions roll back both domain state and outbox events."""
    slug = f"test-rb-{uuid.uuid4().hex[:8]}"
    with pytest.raises(RuntimeError, match="Simulated crash"):
        async with SqlAlchemyUnitOfWork() as uow:
            proj = uow.projects.add(
                Project(
                    name="Rollback Test",
                    slug=slug,
                )
            )
            await uow.session.flush()

            uow.outbox.enqueue(
                OutboxEventCreate(
                    aggregate_type="project",
                    aggregate_id=proj.id,
                    event_type="project.created",
                    payload={"slug": slug},
                )
            )
            msg = "Simulated crash"
            raise RuntimeError(msg)

    # Verify in a new session that nothing was persisted to Neon
    async with SqlAlchemyUnitOfWork() as verify_uow:
        found = await verify_uow.projects.get_by_slug(slug)
        assert found is None


@pytest.mark.asyncio
async def test_neon_uow_transactional_outbox_commit(settings: Settings) -> None:
    """Verify that uow.commit() atomically persists both domain state and outbox event, then cleans up."""
    slug = f"test-commit-{uuid.uuid4().hex[:8]}"
    proj_id: uuid.UUID | None = None
    outbox_id: uuid.UUID | None = None

    async with SqlAlchemyUnitOfWork() as uow:
        proj = uow.projects.add(
            Project(
                name="Commit Test",
                slug=slug,
            )
        )
        await uow.session.flush()
        proj_id = proj.id

        outbox_event = uow.outbox.enqueue(
            OutboxEventCreate(
                aggregate_type="project",
                aggregate_id=proj.id,
                event_type="project.created",
                payload={"slug": slug},
            )
        )
        await uow.session.flush()
        outbox_id = outbox_event.id

        await uow.commit()

    assert proj_id is not None
    assert outbox_id is not None

    # Verify both exist in a new transaction
    async with SqlAlchemyUnitOfWork() as verify_uow:
        persisted_proj = await verify_uow.projects.get_by_id(proj_id)
        assert persisted_proj is not None
        assert persisted_proj.slug == slug

        persisted_event = await verify_uow.outbox.get_by_id(outbox_id)
        assert persisted_event is not None
        assert persisted_event.status == "PENDING"
        assert persisted_event.attempt_count == 0
        assert persisted_event.aggregate_id == proj_id

    # Clean up fixture cleanly to maintain 0-row invariant
    engine = create_engine_instance()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM outbox_events WHERE id = :id"),
                {"id": outbox_id},
            )
            await conn.execute(
                text("DELETE FROM projects WHERE id = :id"),
                {"id": proj_id},
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_neon_uow_no_hidden_commit_on_exit(settings: Settings) -> None:
    """Verify that exiting a UnitOfWork block without calling commit() rolls back automatically."""
    slug = f"test-nocommit-{uuid.uuid4().hex[:8]}"
    async with SqlAlchemyUnitOfWork() as uow:
        uow.projects.add(
            Project(
                name="No Commit Test",
                slug=slug,
            )
        )
        # Deliberately exit without calling uow.commit()

    async with SqlAlchemyUnitOfWork() as verify_uow:
        persisted = await verify_uow.projects.get_by_slug(slug)
        assert persisted is None


@pytest.mark.asyncio
async def test_neon_project_repository_queries(settings: Settings) -> None:
    """Verify ProjectRepository add, get_by_id, get_by_slug, and list_projects."""
    slug = f"proj-repo-{uuid.uuid4().hex[:8]}"
    async with SqlAlchemyUnitOfWork() as uow:
        proj = uow.projects.add(
            Project(
                name="Repo Test Project",
                slug=slug,
            )
        )
        await uow.session.flush()

        # Query by ID
        by_id = await uow.projects.get_by_id(proj.id)
        assert by_id is not None
        assert by_id.name == "Repo Test Project"

        # Query by slug
        by_slug = await uow.projects.get_by_slug(slug)
        assert by_slug is not None
        assert by_slug.id == proj.id

        # List projects
        all_proj = await uow.projects.list_projects(limit=50)
        assert any(p.id == proj.id for p in all_proj)

        # Unique slug conflict raises IntegrityError on flush, translated to PersistenceConflictError
        with pytest.raises(IntegrityError) as exc_info:
            uow.projects.add(
                Project(
                    name="Duplicate Slug Project",
                    slug=slug,
                )
            )
            await uow.session.flush()

        translated = translate_db_error(exc_info.value)
        assert isinstance(translated, PersistenceConflictError)
        assert translated.conflict_key == "uq_projects_slug"


@pytest.mark.asyncio
async def test_neon_requirement_version_deterministic_queries(settings: Settings) -> None:
    """Verify RequirementRepository versioned schemas and trust contracts."""
    slug = f"req-test-{uuid.uuid4().hex[:8]}"
    async with SqlAlchemyUnitOfWork() as uow:
        proj = uow.projects.add(Project(name="Req Project", slug=slug))
        await uow.session.flush()

        req = uow.requirements.add_requirement(
            Requirement(
                project_id=proj.id,
                original_prompt="Build a deterministic data pipeline",
                requirement_spec={"target": "organizations"},
                status="COMPILED",
            )
        )
        await uow.session.flush()

        # Add DatasetSchema v1 and v2
        s1 = uow.requirements.add_dataset_schema(
            DatasetSchema(
                project_id=proj.id,
                requirement_id=req.id,
                version_number=1,
                schema_definition={"type": "object", "properties": {"v": {"type": "integer"}}},
            )
        )
        await uow.session.flush()

        s2 = uow.requirements.add_dataset_schema(
            DatasetSchema(
                project_id=proj.id,
                requirement_id=req.id,
                version_number=2,
                schema_definition={"type": "object", "properties": {"v": {"type": "string"}}},
            )
        )
        await uow.session.flush()

        # Add TrustContract v1 (for s1) and v2 (for s2)
        tc1 = uow.requirements.add_trust_contract(
            TrustContract(
                project_id=proj.id,
                requirement_id=req.id,
                dataset_schema_id=s1.id,
                version_number=1,
                contract_definition={"strictness": "moderate"},
            )
        )
        await uow.session.flush()

        tc2 = uow.requirements.add_trust_contract(
            TrustContract(
                project_id=proj.id,
                requirement_id=req.id,
                dataset_schema_id=s2.id,
                version_number=2,
                contract_definition={"strictness": "strict"},
            )
        )
        await uow.session.flush()

        # Verify deterministic version retrievals
        fetched_s1 = await uow.requirements.get_dataset_schema_by_version(req.id, 1)
        assert fetched_s1 is not None
        assert fetched_s1.id == s1.id

        latest_s = await uow.requirements.get_latest_dataset_schema(req.id)
        assert latest_s is not None
        assert latest_s.id == s2.id
        assert latest_s.version_number == 2

        fetched_tc1 = await uow.requirements.get_trust_contract_by_version(req.id, 1)
        assert fetched_tc1 is not None
        assert fetched_tc1.id == tc1.id

        latest_tc = await uow.requirements.get_latest_trust_contract(req.id)
        assert latest_tc is not None
        assert latest_tc.id == tc2.id
        assert latest_tc.version_number == 2


@pytest.mark.asyncio
async def test_neon_workflow_provenance_and_version_queries(settings: Settings) -> None:
    """Verify WorkflowRepository versions, runs, step runs, and events."""
    slug = f"wf-test-{uuid.uuid4().hex[:8]}"
    async with SqlAlchemyUnitOfWork() as uow:
        proj = uow.projects.add(Project(name="WF Project", slug=slug))
        await uow.session.flush()

        req = uow.requirements.add_requirement(
            Requirement(
                project_id=proj.id,
                original_prompt="Extraction pipeline",
                requirement_spec={"type": "pipeline"},
                status="COMPILED",
            )
        )
        await uow.session.flush()

        schema = uow.requirements.add_dataset_schema(
            DatasetSchema(
                project_id=proj.id,
                requirement_id=req.id,
                version_number=1,
                schema_definition={"fields": []},
            )
        )
        await uow.session.flush()

        contract = uow.requirements.add_trust_contract(
            TrustContract(
                project_id=proj.id,
                requirement_id=req.id,
                dataset_schema_id=schema.id,
                version_number=1,
                contract_definition={"require_evidence": True},
            )
        )
        await uow.session.flush()

        wf = uow.workflows.add_workflow(
            Workflow(
                project_id=proj.id,
                requirement_id=req.id,
                name="Extraction Workflow",
                status="ACTIVE",
            )
        )
        await uow.session.flush()

        # Version 1 and Version 2
        wv1 = uow.workflows.add_workflow_version(
            WorkflowVersion(
                workflow_id=wf.id,
                version_number=1,
                dataset_schema_id=schema.id,
                trust_contract_id=contract.id,
                plan_dag={"nodes": ["scrape", "extract"]},
            )
        )
        await uow.session.flush()

        wv2 = uow.workflows.add_workflow_version(
            WorkflowVersion(
                workflow_id=wf.id,
                version_number=2,
                dataset_schema_id=schema.id,
                trust_contract_id=contract.id,
                plan_dag={"nodes": ["scrape", "extract", "validate"]},
            )
        )
        await uow.session.flush()

        fetched_wv1 = await uow.workflows.get_workflow_version_by_number(wf.id, 1)
        assert fetched_wv1 is not None
        assert fetched_wv1.id == wv1.id

        latest_wv = await uow.workflows.get_latest_workflow_version(wf.id)
        assert latest_wv is not None
        assert latest_wv.id == wv2.id
        assert latest_wv.version_number == 2

        # Workflow Run
        w_run = uow.workflows.add_workflow_run(
            WorkflowRun(
                project_id=proj.id,
                workflow_version_id=wv2.id,
                status="RUNNING",
                run_mode="LIVE",
            )
        )
        await uow.session.flush()

        # Step Run
        step = uow.workflows.add_step_run(
            StepRun(
                workflow_run_id=w_run.id,
                node_id="scrape_step",
                operator_type="DISCOVER",
                attempt=1,
                status="READY",
            )
        )
        await uow.session.flush()

        found_step = await uow.workflows.get_step_run_by_node(w_run.id, "scrape_step")
        assert found_step is not None
        assert found_step.id == step.id

        # Workflow Event
        event = uow.workflows.add_workflow_event(
            WorkflowEvent(
                workflow_run_id=w_run.id,
                sequence_number=1,
                event_type="STEP_COMPLETED",
                payload={"records_scraped": 42},
            )
        )
        await uow.session.flush()

        events = await uow.workflows.list_workflow_events(w_run.id)
        assert len(events) == 1
        assert events[0].id == event.id


@pytest.mark.asyncio
async def test_neon_source_and_raw_document_provenance(settings: Settings) -> None:
    """Verify SourceRepository source and raw_document queries."""
    slug = f"src-test-{uuid.uuid4().hex[:8]}"
    url = f"https://example.com/data/{uuid.uuid4().hex[:6]}"
    c_hash = f"sha256_{uuid.uuid4().hex}"

    async with SqlAlchemyUnitOfWork() as uow:
        proj = uow.projects.add(Project(name="Source Project", slug=slug))
        await uow.session.flush()

        src = uow.sources.add_source(
            Source(
                project_id=proj.id,
                canonical_url=url,
                domain="example.com",
                source_type="WEB_PAGE",
                source_metadata={"trust": 1},
            )
        )
        await uow.session.flush()

        by_url = await uow.sources.get_source_by_canonical_url(proj.id, url)
        assert by_url is not None
        assert by_url.id == src.id

        doc = uow.sources.add_raw_document(
            RawDocument(
                project_id=proj.id,
                source_id=src.id,
                retrieved_at=datetime.now(UTC),
                final_url=url,
                http_status=200,
                content_hash=c_hash,
                retrieval_metadata={"status_code": 200},
            )
        )
        await uow.session.flush()

        matching_docs = await uow.sources.find_by_content_hash(proj.id, c_hash)
        assert len(matching_docs) == 1
        assert matching_docs[0].id == doc.id

        docs = await uow.sources.list_raw_documents_for_source(src.id)
        assert len(docs) == 1
        assert docs[0].id == doc.id


@pytest.mark.asyncio
async def test_neon_claim_and_evidence_anchor_persistence(settings: Settings) -> None:
    """Verify ClaimRepository unresolved & resolved claims and evidence anchors."""
    slug = f"clm-test-{uuid.uuid4().hex[:8]}"
    c_hash = f"claim_hash_{uuid.uuid4().hex}"
    doc_url = f"https://api.example.com/{uuid.uuid4().hex[:6]}"

    async with SqlAlchemyUnitOfWork() as uow:
        proj = uow.projects.add(Project(name="Claim Project", slug=slug))
        await uow.session.flush()

        req = uow.requirements.add_requirement(
            Requirement(
                project_id=proj.id,
                original_prompt="Claims test",
                requirement_spec={"type": "claims"},
                status="COMPILED",
            )
        )
        await uow.session.flush()

        schema = uow.requirements.add_dataset_schema(
            DatasetSchema(
                project_id=proj.id,
                requirement_id=req.id,
                version_number=1,
                schema_definition={"fields": []},
            )
        )
        await uow.session.flush()

        contract = uow.requirements.add_trust_contract(
            TrustContract(
                project_id=proj.id,
                requirement_id=req.id,
                dataset_schema_id=schema.id,
                version_number=1,
                contract_definition={"require_evidence": True},
            )
        )
        await uow.session.flush()

        wf = uow.workflows.add_workflow(
            Workflow(
                project_id=proj.id,
                requirement_id=req.id,
                name="Claim WF",
                status="ACTIVE",
            )
        )
        await uow.session.flush()

        wv = uow.workflows.add_workflow_version(
            WorkflowVersion(
                workflow_id=wf.id,
                version_number=1,
                dataset_schema_id=schema.id,
                trust_contract_id=contract.id,
                plan_dag={"nodes": []},
            )
        )
        await uow.session.flush()

        run = uow.workflows.add_workflow_run(
            WorkflowRun(
                project_id=proj.id,
                workflow_version_id=wv.id,
                status="RUNNING",
                run_mode="LIVE",
            )
        )
        await uow.session.flush()

        src = uow.sources.add_source(
            Source(
                project_id=proj.id,
                canonical_url=doc_url,
                domain="api.example.com",
                source_type="API",
                source_metadata={},
            )
        )
        await uow.session.flush()

        doc = uow.sources.add_raw_document(
            RawDocument(
                project_id=proj.id,
                workflow_run_id=run.id,
                source_id=src.id,
                retrieved_at=datetime.now(UTC),
                final_url=doc_url,
                http_status=200,
                content_hash=f"hash_{uuid.uuid4().hex}",
                retrieval_metadata={"json": True},
            )
        )
        await uow.session.flush()

        ent = uow.entities.add_entity(
            Entity(
                project_id=proj.id,
                entity_type="organization",
                canonical_name="Target Org",
                stable_entity_key=f"org_{uuid.uuid4().hex[:6]}",
            )
        )
        await uow.session.flush()

        # Unresolved claim (entity_id=None)
        claim_unresolved = uow.claims.add_claim(
            Claim(
                project_id=proj.id,
                workflow_run_id=run.id,
                source_id=src.id,
                raw_document_id=doc.id,
                entity_id=None,
                field_key="employee_count",
                raw_value="150",
                validation_flags=["raw_span_match"],
                claim_hash=f"unres_{c_hash}",
            )
        )
        await uow.session.flush()

        assert claim_unresolved.entity_id is None
        assert claim_unresolved.source_id == src.id
        assert claim_unresolved.raw_document_id == doc.id

        # Resolved claim (entity_id=ent.id)
        claim_resolved = uow.claims.add_claim(
            Claim(
                project_id=proj.id,
                workflow_run_id=run.id,
                source_id=src.id,
                raw_document_id=doc.id,
                entity_id=ent.id,
                field_key="employee_count",
                raw_value="150",
                validation_flags=["resolved_match"],
                claim_hash=c_hash,
            )
        )
        await uow.session.flush()

        # Evidence anchor
        anchor = uow.claims.add_evidence_anchor(
            EvidenceAnchor(
                claim_id=claim_resolved.id,
                raw_document_id=doc.id,
                anchor_type="TEXT_SPAN",
                locator={"start": 10, "end": 25},
                quoted_text="150 employees",
                verification_status="EXACT",
            )
        )
        await uow.session.flush()

        anchors = await uow.claims.list_evidence_anchors_for_claim(claim_resolved.id)
        assert len(anchors) == 1
        assert anchors[0].id == anchor.id
        assert anchors[0].quoted_text == "150 employees"

        claims_by_field = await uow.claims.list_claims_for_entity_field(
            project_id=proj.id,
            entity_id=ent.id,
            field_key="employee_count",
        )
        assert len(claims_by_field) == 1
        assert claims_by_field[0].id == claim_resolved.id


@pytest.mark.asyncio
async def test_neon_entity_repository_canonical_pair_ordering(settings: Settings) -> None:
    """Verify EntityRepository enforces canonical order (source < target) and rejects self-matches."""
    slug = f"ent-test-{uuid.uuid4().hex[:8]}"
    async with SqlAlchemyUnitOfWork() as uow:
        proj = uow.projects.add(Project(name="Entity Project", slug=slug))
        await uow.session.flush()

        ent1 = uow.entities.add_entity(
            Entity(
                project_id=proj.id,
                entity_type="organization",
                canonical_name="Alpha Corp",
                stable_entity_key=f"org_{uuid.uuid4().hex[:6]}",
            )
        )
        ent2 = uow.entities.add_entity(
            Entity(
                project_id=proj.id,
                entity_type="organization",
                canonical_name="Beta Corp",
                stable_entity_key=f"org_{uuid.uuid4().hex[:6]}",
            )
        )
        await uow.session.flush()

        # Invert the order deliberately: pass larger UUID first
        id_larger = max(ent1.id, ent2.id)
        id_smaller = min(ent1.id, ent2.id)

        match = uow.entities.add_entity_match(
            project_id=proj.id,
            entity_a_id=id_larger,
            entity_b_id=id_smaller,
            decision="AUTO_MERGE",
            score=Decimal("0.98"),
        )
        await uow.session.flush()

        # Assert canonical order in DB
        assert match.source_entity_id == id_smaller
        assert match.target_entity_id == id_larger

        # Self-match rejection
        with pytest.raises(PersistenceIntegrityError, match="between an entity and itself"):
            uow.entities.add_entity_match(
                project_id=proj.id,
                entity_a_id=ent1.id,
                entity_b_id=ent1.id,
                decision="AUTO_MERGE",
            )


@pytest.mark.asyncio
async def test_neon_dataset_repository_versioning_and_canonical_records(
    settings: Settings,
) -> None:
    """Verify DatasetRepository versioning, canonical values, conflicts, and records."""
    slug = f"ds-test-{uuid.uuid4().hex[:8]}"
    async with SqlAlchemyUnitOfWork() as uow:
        proj = uow.projects.add(Project(name="Dataset Project", slug=slug))
        await uow.session.flush()

        req = uow.requirements.add_requirement(
            Requirement(
                project_id=proj.id,
                original_prompt="Dataset Pipeline",
                requirement_spec={"type": "dataset"},
                status="COMPILED",
            )
        )
        await uow.session.flush()

        schema = uow.requirements.add_dataset_schema(
            DatasetSchema(
                project_id=proj.id,
                requirement_id=req.id,
                version_number=1,
                schema_definition={"fields": []},
            )
        )
        await uow.session.flush()

        contract = uow.requirements.add_trust_contract(
            TrustContract(
                project_id=proj.id,
                requirement_id=req.id,
                dataset_schema_id=schema.id,
                version_number=1,
                contract_definition={"require_evidence": True},
            )
        )
        await uow.session.flush()

        wf = uow.workflows.add_workflow(
            Workflow(
                project_id=proj.id,
                requirement_id=req.id,
                name="Dataset WF",
                status="ACTIVE",
            )
        )
        await uow.session.flush()

        wv = uow.workflows.add_workflow_version(
            WorkflowVersion(
                workflow_id=wf.id,
                version_number=1,
                dataset_schema_id=schema.id,
                trust_contract_id=contract.id,
                plan_dag={"nodes": []},
            )
        )
        await uow.session.flush()

        run = uow.workflows.add_workflow_run(
            WorkflowRun(
                project_id=proj.id,
                workflow_version_id=wv.id,
                status="RUNNING",
                run_mode="LIVE",
            )
        )
        await uow.session.flush()

        ds = uow.datasets.add_dataset(
            Dataset(
                project_id=proj.id,
                workflow_id=wf.id,
                name="Organizations Dataset",
                slug=f"org-ds-{uuid.uuid4().hex[:6]}",
            )
        )
        await uow.session.flush()

        # Add versions 1 and 2
        v1 = uow.datasets.add_dataset_version(
            DatasetVersion(
                project_id=proj.id,
                dataset_id=ds.id,
                dataset_schema_id=schema.id,
                workflow_run_id=run.id,
                version_number=1,
                record_count=0,
                status="DRAFT",
            )
        )
        await uow.session.flush()

        v2 = uow.datasets.add_dataset_version(
            DatasetVersion(
                project_id=proj.id,
                dataset_id=ds.id,
                dataset_schema_id=schema.id,
                workflow_run_id=run.id,
                version_number=2,
                record_count=10,
                status="FINALIZED",
            )
        )
        await uow.session.flush()

        fetched_v1 = await uow.datasets.get_dataset_version_by_number(ds.id, 1)
        assert fetched_v1 is not None
        assert fetched_v1.id == v1.id

        latest_v = await uow.datasets.get_latest_dataset_version(ds.id)
        assert latest_v is not None
        assert latest_v.id == v2.id
        assert latest_v.version_number == 2

        ent = uow.entities.add_entity(
            Entity(
                project_id=proj.id,
                entity_type="organization",
                canonical_name="Acme Inc",
                stable_entity_key=f"org_{uuid.uuid4().hex[:6]}",
            )
        )
        await uow.session.flush()

        # Canonical Value
        cv = uow.datasets.add_canonical_value(
            CanonicalValue(
                project_id=proj.id,
                dataset_version_id=v2.id,
                entity_id=ent.id,
                field_key="revenue",
                value="1000000",
                trust_status="VERIFIED",
            )
        )
        await uow.session.flush()

        cvs = await uow.datasets.list_canonical_values(v2.id, ent.id)
        assert len(cvs) == 1
        assert cvs[0].id == cv.id

        # Conflict
        cf = uow.datasets.add_conflict(
            Conflict(
                project_id=proj.id,
                dataset_version_id=v2.id,
                entity_id=ent.id,
                field_key="revenue",
                conflict_type="VALUE_MISMATCH",
                status="OPEN",
                details={"discrepancy": "Source A says 1M, Source B says 2M"},
            )
        )
        await uow.session.flush()

        cfs = await uow.datasets.list_conflicts(v2.id, ent.id)
        assert len(cfs) == 1
        assert cfs[0].id == cf.id

        # Dataset Version Record
        rec = uow.datasets.add_dataset_version_record(
            DatasetVersionRecord(
                project_id=proj.id,
                dataset_version_id=v2.id,
                entity_id=ent.id,
                record_data={"name": "Acme Inc", "revenue": 1000000},
                trust_summary={"overall_trust": "VERIFIED"},
                record_hash=f"hash_{uuid.uuid4().hex}",
            )
        )
        await uow.session.flush()

        recs = await uow.datasets.list_dataset_version_records(v2.id)
        assert len(recs) == 1
        assert recs[0].id == rec.id


@pytest.mark.asyncio
async def test_neon_persistence_fixture_cleanup_guarantee(settings: Settings) -> None:
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
