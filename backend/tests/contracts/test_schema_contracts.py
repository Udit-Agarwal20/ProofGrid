"""Schema contract tests for ProofGrid relational models.

Offline tests asserting SQLAlchemy metadata constraints, table inventory,
primary keys, foreign keys, unique constraints, check constraints, domain independence,
and schema security invariants.
"""

import os
import pkgutil
from importlib import import_module

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

import app.db.models as models  # noqa: F401
from app.db.base import Base
from app.domain.enums import TrustStatus

EXPECTED_BUSINESS_TABLES = {
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


def test_expected_table_inventory() -> None:
    """Verify metadata contains exactly the 21 expected business tables."""
    registered_tables = set(Base.metadata.tables.keys())
    assert registered_tables == EXPECTED_BUSINESS_TABLES, (
        f"Mismatch in table inventory. Diff: {registered_tables ^ EXPECTED_BUSINESS_TABLES}"
    )
    assert len(registered_tables) == 21


def test_table_primary_keys() -> None:
    """Verify every table has a single UUID primary key named 'id'."""
    for table_name, table in Base.metadata.tables.items():
        pk_cols = list(table.primary_key.columns)
        assert len(pk_cols) == 1, f"Table {table_name} must have exactly 1 PK column"
        pk = pk_cols[0]
        assert pk.name == "id", f"Table {table_name} PK must be named 'id'"
        assert isinstance(pk.type, UUID), f"Table {table_name} PK must be UUID type"


def test_foreign_key_delete_policies() -> None:
    """Verify that foreign keys strictly use RESTRICT to prevent accidental provenance deletion."""
    for table_name, table in Base.metadata.tables.items():
        for fk in table.foreign_keys:
            assert fk.ondelete == "RESTRICT", (
                f"Foreign key {fk} on table {table_name} has ondelete={fk.ondelete}; "
                "must be 'RESTRICT' to preserve historical evidence."
            )


def test_required_reproducibility_and_versioning_foreign_keys() -> None:
    """Verify all 10 critical reproducibility, provenance, and versioning foreign keys."""
    # 1. trust_contracts.dataset_schema_id -> dataset_schemas.id (NOT NULL)
    tc_table = Base.metadata.tables["trust_contracts"]
    tc_fks = {fk.parent.name: fk.target_fullname for fk in tc_table.foreign_keys}
    assert tc_fks.get("dataset_schema_id") == "dataset_schemas.id"
    assert tc_table.columns["dataset_schema_id"].nullable is False

    # 2. workflow_versions.dataset_schema_id -> dataset_schemas.id (NOT NULL)
    # 3. workflow_versions.trust_contract_id -> trust_contracts.id (NOT NULL)
    wv_table = Base.metadata.tables["workflow_versions"]
    wv_fks = {fk.parent.name: fk.target_fullname for fk in wv_table.foreign_keys}
    assert wv_fks.get("dataset_schema_id") == "dataset_schemas.id"
    assert wv_table.columns["dataset_schema_id"].nullable is False
    assert wv_fks.get("trust_contract_id") == "trust_contracts.id"
    assert wv_table.columns["trust_contract_id"].nullable is False
    assert wv_fks.get("workflow_id") == "workflows.id"

    # 4. datasets.workflow_id -> workflows.id (nullable)
    d_table = Base.metadata.tables["datasets"]
    d_fks = {fk.parent.name: fk.target_fullname for fk in d_table.foreign_keys}
    assert d_fks.get("workflow_id") == "workflows.id"
    assert d_table.columns["workflow_id"].nullable is True
    # Confirm datasets table does NOT have schema_id (stable identity)
    assert "schema_id" not in d_table.columns

    # 5. dataset_versions.dataset_schema_id -> dataset_schemas.id (NOT NULL)
    # 6. dataset_versions.workflow_run_id -> workflow_runs.id (nullable)
    dv_table = Base.metadata.tables["dataset_versions"]
    dv_fks = {fk.parent.name: fk.target_fullname for fk in dv_table.foreign_keys}
    assert dv_fks.get("dataset_schema_id") == "dataset_schemas.id"
    assert dv_table.columns["dataset_schema_id"].nullable is False
    assert dv_fks.get("workflow_run_id") == "workflow_runs.id"
    assert dv_table.columns["workflow_run_id"].nullable is True

    # 7. claims.source_id -> sources.id (NOT NULL)
    # 8. claims.entity_id -> entities.id (nullable)
    claims_table = Base.metadata.tables["claims"]
    claims_fks = {fk.parent.name: fk.target_fullname for fk in claims_table.foreign_keys}
    assert claims_fks.get("source_id") == "sources.id"
    assert claims_table.columns["source_id"].nullable is False
    assert claims_fks.get("entity_id") == "entities.id"
    assert claims_table.columns["entity_id"].nullable is True
    assert claims_fks.get("raw_document_id") == "raw_documents.id"
    assert claims_table.columns["raw_document_id"].nullable is False
    assert claims_fks.get("workflow_run_id") == "workflow_runs.id"
    assert claims_fks.get("project_id") == "projects.id"

    # 9. canonical_values.dataset_version_id -> dataset_versions.id (NOT NULL)
    cv_table = Base.metadata.tables["canonical_values"]
    cv_fks = {fk.parent.name: fk.target_fullname for fk in cv_table.foreign_keys}
    assert cv_fks.get("dataset_version_id") == "dataset_versions.id"
    assert cv_table.columns["dataset_version_id"].nullable is False
    assert cv_fks.get("entity_id") == "entities.id"
    assert cv_fks.get("project_id") == "projects.id"
    assert cv_fks.get("selected_claim_id") == "claims.id"

    # 10. conflicts.dataset_version_id -> dataset_versions.id (NOT NULL)
    conf_table = Base.metadata.tables["conflicts"]
    conf_fks = {fk.parent.name: fk.target_fullname for fk in conf_table.foreign_keys}
    assert conf_fks.get("dataset_version_id") == "dataset_versions.id"
    assert conf_table.columns["dataset_version_id"].nullable is False
    assert conf_fks.get("entity_id") == "entities.id"
    assert conf_fks.get("project_id") == "projects.id"
    assert conf_fks.get("resolved_claim_id") == "claims.id"

    dvr_fks = {
        fk.parent.name: fk.target_fullname
        for fk in Base.metadata.tables["dataset_version_records"].foreign_keys
    }
    assert dvr_fks.get("dataset_version_id") == "dataset_versions.id"
    assert dvr_fks.get("entity_id") == "entities.id"
    assert dvr_fks.get("project_id") == "projects.id"


def test_critical_unique_constraints() -> None:
    """Verify expected unique constraints are present with deterministic naming."""
    table_uqs = {}
    for table_name, table in Base.metadata.tables.items():
        table_uqs[table_name] = {
            uq.name: [c.name for c in uq.columns]
            for uq in table.constraints
            if isinstance(uq, UniqueConstraint)
        }

    # 1. projects slug
    assert "slug" in [col.name for col in Base.metadata.tables["projects"].columns if col.unique]

    # 2. dataset_schemas (requirement_id, version_number)
    ds_uqs = table_uqs["dataset_schemas"]
    assert "uq_dataset_schemas_requirement_version" in ds_uqs
    assert ds_uqs["uq_dataset_schemas_requirement_version"] == [
        "requirement_id",
        "version_number",
    ]

    # 3. trust_contracts (requirement_id, version_number)
    tc_uqs = table_uqs["trust_contracts"]
    assert "uq_trust_contracts_requirement_version" in tc_uqs
    assert tc_uqs["uq_trust_contracts_requirement_version"] == [
        "requirement_id",
        "version_number",
    ]

    # 4. workflow_versions (workflow_id, version_number)
    wv_uqs = table_uqs["workflow_versions"]
    assert "uq_workflow_versions_workflow_version" in wv_uqs
    assert wv_uqs["uq_workflow_versions_workflow_version"] == [
        "workflow_id",
        "version_number",
    ]

    # 5. step_runs idempotency (workflow_run_id, node_id, attempt)
    sr_uqs = table_uqs["step_runs"]
    assert "ux_step_idempotency" in sr_uqs
    assert sr_uqs["ux_step_idempotency"] == ["workflow_run_id", "node_id", "attempt"]

    # 6. workflow_events (workflow_run_id, sequence_number)
    we_uqs = table_uqs["workflow_events"]
    assert "uq_workflow_events_run_sequence" in we_uqs
    assert we_uqs["uq_workflow_events_run_sequence"] == [
        "workflow_run_id",
        "sequence_number",
    ]

    # 7. sources (project_id, canonical_url)
    src_uqs = table_uqs["sources"]
    assert "uq_sources_project_canonical_url" in src_uqs
    assert src_uqs["uq_sources_project_canonical_url"] == ["project_id", "canonical_url"]

    # 8. raw_documents content hash must NOT be unique across sources
    rd_uqs = table_uqs["raw_documents"]
    for uq_name, cols in rd_uqs.items():
        assert "content_hash" not in cols, (
            f"raw_documents must not enforce uniqueness on content_hash ({uq_name}: {cols}) "
            "because identical bytes from separate sources are independent provenance events."
        )

    # 9. canonical_values (dataset_version_id, entity_id, field_key)
    cv_uqs = table_uqs["canonical_values"]
    assert "uq_canonical_values_version_entity_field" in cv_uqs
    assert cv_uqs["uq_canonical_values_version_entity_field"] == [
        "dataset_version_id",
        "entity_id",
        "field_key",
    ]

    # 10. conflicts (dataset_version_id, entity_id, field_key)
    conf_uqs = table_uqs["conflicts"]
    assert "uq_conflicts_version_entity_field" in conf_uqs
    assert conf_uqs["uq_conflicts_version_entity_field"] == [
        "dataset_version_id",
        "entity_id",
        "field_key",
    ]

    # 11. datasets (project_id, slug)
    d_uqs = table_uqs["datasets"]
    assert "uq_datasets_project_slug" in d_uqs
    assert d_uqs["uq_datasets_project_slug"] == ["project_id", "slug"]

    # 12. dataset_versions (dataset_id, version_number)
    dv_uqs = table_uqs["dataset_versions"]
    assert "uq_dataset_versions_dataset_version" in dv_uqs
    assert dv_uqs["uq_dataset_versions_dataset_version"] == [
        "dataset_id",
        "version_number",
    ]

    # 13. dataset_version_records (dataset_version_id, entity_id)
    dvr_uqs = table_uqs["dataset_version_records"]
    assert "uq_dataset_version_records_version_entity" in dvr_uqs
    assert dvr_uqs["uq_dataset_version_records_version_entity"] == [
        "dataset_version_id",
        "entity_id",
    ]

    # 14. entity_matches (project_id, source_entity_id, target_entity_id)
    em_uqs = table_uqs["entity_matches"]
    assert "uq_entity_matches_pair" in em_uqs
    assert em_uqs["uq_entity_matches_pair"] == [
        "project_id",
        "source_entity_id",
        "target_entity_id",
    ]


def test_critical_check_constraints() -> None:
    """Verify invariants enforced by database check constraints."""
    check_names = set()
    for table in Base.metadata.tables.values():
        for c in table.constraints:
            if isinstance(c, CheckConstraint):
                check_names.add(c.name)

    expected_checks = {
        "ck_requirements_status",
        "ck_dataset_schemas_version_number",
        "ck_trust_contracts_version_number",
        "ck_workflows_status",
        "ck_workflow_versions_version_number",
        "ck_workflow_runs_status",
        "ck_workflow_runs_run_mode",
        "ck_step_runs_attempt",
        "ck_step_runs_status",
        "ck_step_runs_operator_type",
        "ck_workflow_events_sequence_number",
        "ck_sources_source_type",
        "ck_raw_documents_size_bytes",
        "ck_evidence_anchors_type",
        "ck_evidence_anchors_status",
        "ck_entity_matches_canonical_pair_order",
        "ck_entity_matches_decision",
        "ck_canonical_values_trust_status",
        "ck_conflicts_status",
        "ck_conflicts_type",
        "ck_dataset_versions_version_number",
        "ck_dataset_versions_record_count",
        "ck_dataset_versions_status",
        "ck_outbox_events_attempt_count",
        "ck_outbox_events_status",
    }
    for ck in expected_checks:
        assert ck in check_names, f"Missing check constraint: {ck}"


def test_claims_trust_and_confidence_absence() -> None:
    """Claims must not store arbitrary numerical confidence or duplicate trust states."""
    claims_table = Base.metadata.tables["claims"]
    col_names = set(claims_table.columns.keys())

    assert "field_key" in col_names, "claims must use 'field_key', not 'attribute_name'"
    assert "attribute_name" not in col_names

    # Claims must NOT have trust_status or numeric confidence scores
    assert "trust_status" not in col_names, (
        "claims must not pretend to store final canonical trust status"
    )
    assert "confidence_score" not in col_names, (
        "claims must not store arbitrary numerical confidence"
    )
    assert "verification_score" not in col_names, (
        "claims must not store arbitrary numerical verification score"
    )

    # Claims store factual extraction/normalization details
    assert "extraction_method" in col_names
    assert "claim_hash" in col_names
    assert "validation_flags" in col_names


def test_canonical_values_trust_status_matches_domain_enum() -> None:
    """Verify canonical_values.trust_status check constraint matches domain TrustStatus exactly."""
    cv_table = Base.metadata.tables["canonical_values"]
    ck = next(
        c
        for c in cv_table.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_canonical_values_trust_status"
    )
    sql_text = str(ck.sqltext)

    for status in TrustStatus:
        assert f"'{status.value}'" in sql_text, (
            f"Canonical check missing domain TrustStatus: {status.value}"
        )


def test_raw_documents_provenance_independence() -> None:
    """raw_documents content_hash is indexed for dedup/cache, but NOT unique."""
    rd_table = Base.metadata.tables["raw_documents"]
    index_map: dict[str, list[str]] = {
        str(idx.name): [c.name for c in idx.columns] for idx in rd_table.indexes
    }

    assert "ix_raw_documents_project_content_hash" in index_map
    assert index_map["ix_raw_documents_project_content_hash"] == ["project_id", "content_hash"]

    # Verify no unique index on content_hash alone
    for idx in rd_table.indexes:
        if idx.unique:
            assert "content_hash" not in [c.name for c in idx.columns]


def test_critical_indexes() -> None:
    """Verify indexes needed for query patterns, queues, and foreign key traversals."""
    index_names = set()
    for table in Base.metadata.tables.values():
        for idx in table.indexes:
            index_names.add(idx.name)

    expected_indexes = {
        "ix_step_runs_ready",
        "ix_step_runs_run_status",
        "ix_claims_entity_field",
        "ix_claims_raw_document_id",
        "ix_claims_source_id",
        "ix_claims_workflow_run_id",
        "ix_evidence_anchors_claim_id",
        "ux_entities_project_stable_key",
        "ix_outbox_events_status_available",
        "ix_workflow_versions_dataset_schema_id",
        "ix_workflow_versions_trust_contract_id",
        "ix_trust_contracts_dataset_schema_id",
        "ix_dataset_versions_schema_id",
        "ix_datasets_workflow_id",
        "ix_canonical_values_project_id",
        "ix_conflicts_project_id",
        "ix_dataset_version_records_project_id",
        "ix_dataset_versions_project_id",
        "ix_raw_documents_project_content_hash",
    }
    for idx_name in expected_indexes:
        assert idx_name in index_names, f"Missing expected index: {idx_name}"


def test_jsonb_data_types() -> None:
    """Verify dynamic documents are mapped to PostgreSQL JSONB."""
    expected_jsonb = [
        ("requirements", "requirement_spec"),
        ("dataset_schemas", "schema_definition"),
        ("trust_contracts", "contract_definition"),
        ("workflow_versions", "plan_dag"),
        ("workflow_versions", "planner_metadata"),
        ("workflow_runs", "budget_snapshot"),
        ("workflow_runs", "metrics"),
        ("workflow_events", "payload"),
        ("sources", "metadata"),
        ("raw_documents", "retrieval_metadata"),
        ("claims", "raw_value"),
        ("claims", "validation_flags"),
        ("evidence_anchors", "locator"),
        ("entities", "attributes"),
        ("entity_matches", "signals"),
        ("entity_matches", "reason"),
        ("canonical_values", "value"),
        ("canonical_values", "provenance_summary"),
        ("conflicts", "details"),
        ("dataset_versions", "diff_summary"),
        ("dataset_version_records", "record_data"),
        ("dataset_version_records", "trust_summary"),
        ("outbox_events", "payload"),
    ]
    for table_name, col_name in expected_jsonb:
        table = Base.metadata.tables[table_name]
        col = table.columns[col_name]
        assert isinstance(col.type, JSONB), f"{table_name}.{col_name} must be JSONB"


def test_domain_layer_independent_of_sqlalchemy() -> None:
    """Verify that backend/app/domain/ contains zero imports of SQLAlchemy."""
    domain_pkg = import_module("app.domain")
    assert domain_pkg.__file__ is not None
    for _, module_name, _ in pkgutil.iter_modules(domain_pkg.__path__):
        full_name = f"app.domain.{module_name}"
        mod = import_module(full_name)
        for attr_name, attr_val in mod.__dict__.items():
            attr_mod = getattr(attr_val, "__module__", "")
            assert not str(attr_mod).startswith("sqlalchemy"), (
                f"Domain module {full_name} leaks SQLAlchemy via {attr_name}: {attr_val}"
            )

    domain_dir = os.path.dirname(domain_pkg.__file__)
    for filename in os.listdir(domain_dir):
        if filename.endswith(".py"):
            with open(os.path.join(domain_dir, filename)) as f:
                content = f.read()
                assert "sqlalchemy" not in content.lower(), (
                    f"Domain file {filename} contains reference to sqlalchemy"
                )
