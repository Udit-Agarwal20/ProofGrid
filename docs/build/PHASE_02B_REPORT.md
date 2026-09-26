# Phase 2B Build Report — Core Database Schema & ORM Models (Corrected Pass)

**Date**: 2026-09-27  
**Status**: **PASS**  
**Engineering Lead**: Antigravity AI  
**Scope**: Phase 2B — Core Relational Database Schema & ORM Models (Neon PostgreSQL)  
**Migration Baseline**: `21242d5d8505`  
**Migration HEAD**: `9727a73ca3e4`  

---

## 1. Goal & Architecture Realignment

Phase 2B establishes the complete relational persistence model for ProofGrid against Neon PostgreSQL. Following architectural review, a focused correction pass realigned the schema with ProofGrid's core doctrine:

1. **Dataset Schema Versioning**: `dataset_schemas` supports immutable version history per requirement (`UNIQUE(requirement_id, version_number)`).
2. **Trust Contract Versioning**: `trust_contracts` preserves contract evolution per requirement (`UNIQUE(requirement_id, version_number)`).
3. **Workflow Version Reproducibility**: `workflow_versions` explicitly references the exact `dataset_schema_id` and `trust_contract_id` used when the PlanDAG was compiled (`ON DELETE RESTRICT`).
4. **Dataset-Version Scoped Canonical Values**: Canonical values represent accepted truth for a *specific dataset version*, keyed by `UNIQUE(dataset_version_id, entity_id, field_key)` with explicit `project_id` and pointer to `selected_claim_id`.
5. **Dataset-Version Scoped Conflicts**: Disagreements and competing assertions are scoped to a dataset version (`UNIQUE(dataset_version_id, entity_id, field_key)`), allowing resolutions in future versions to preserve historical disputes.
6. **Standardized Terminology**: Consolidated on `field_key` across claims, canonical values, and conflicts.
7. **Claim Ledger vs Canonical Field Trust**: Removed arbitrary numeric probabilities (`confidence_score`, `verification_score`) and duplicate trust enums from `claims`. Claims store factual extraction/validation metadata (`extraction_method`, `validation_flags`, `claim_hash`), while canonical categorical trust (`VERIFIED`, `SUPPORTED`, `SINGLE_SOURCE`, `CONFLICTING`, `NEEDS_REVIEW`, `MISSING`) is evaluated on `canonical_values`.
8. **Raw Document Provenance**: Removed `content_hash` uniqueness from `raw_documents`. Identical bytes from separate sources or at different times constitute distinct provenance events. Retained non-unique B-tree index `(project_id, content_hash)`.
9. **Materialized Record Identity**: Enforced one row per entity per dataset version (`UNIQUE(dataset_version_id, entity_id)`).
10. **Entity Match Pair Invariant**: Enforced database-level canonical pair ordering `source_entity_id < target_entity_id` to strictly prevent self-matches and reversed candidate pairs `(B, A)`.
11. **Developer Introspection Sanitization**: Removed all connection strings and host details from `make db-schema-check`.
12. **Index Audit**: Removed redundant indexes where composite unique constraints provide leading-column coverage.

Strict Phase Boundary: This phase does **NOT** implement repositories, business services, workflow execution, extraction, trust computation, outbox workers, or business API endpoints.

---

## 2. ORM Model Inventory (21 Business Tables)

All models are defined under `backend/app/db/models/` using SQLAlchemy 2.0 mapped-column syntax, strictly separated from Pydantic domain models in `backend/app/domain/`:

| Table Name | Model Class | Column Count | Primary Key | Parent / Tenancy Foreign Keys (ON DELETE RESTRICT) |
| :--- | :--- | :--- | :--- | :--- |
| `projects` | `Project` | 6 | `id` (UUID) | Root Tenancy Boundary |
| `requirements` | `Requirement` | 8 | `id` (UUID) | `project_id -> projects.id` |
| `dataset_schemas` | `DatasetSchema` | 7 | `id` (UUID) | `project_id -> projects.id`, `requirement_id -> requirements.id` |
| `trust_contracts` | `TrustContract` | 8 | `id` (UUID) | `project_id -> projects.id`, `requirement_id -> requirements.id`, `dataset_schema_id -> dataset_schemas.id` |
| `workflows` | `Workflow` | 7 | `id` (UUID) | `project_id -> projects.id`, `requirement_id -> requirements.id` |
| `workflow_versions` | `WorkflowVersion` | 8 | `id` (UUID) | `workflow_id -> workflows.id`, `dataset_schema_id -> dataset_schemas.id`, `trust_contract_id -> trust_contracts.id` |
| `workflow_runs` | `WorkflowRun` | 11 | `id` (UUID) | `project_id -> projects.id`, `workflow_version_id -> workflow_versions.id` |
| `step_runs` | `StepRun` | 11 | `id` (UUID) | `workflow_run_id -> workflow_runs.id` |
| `workflow_events` | `WorkflowEvent` | 6 | `id` (UUID) | `workflow_run_id -> workflow_runs.id` |
| `sources` | `Source` | 7 | `id` (UUID) | `project_id -> projects.id` |
| `raw_documents` | `RawDocument` | 12 | `id` (UUID) | `project_id -> projects.id`, `source_id -> sources.id`, `workflow_run_id -> workflow_runs.id` |
| `claims` | `Claim` | 13 | `id` (UUID) | `project_id -> projects.id`, `raw_document_id -> raw_documents.id`, `source_id -> sources.id`, `workflow_run_id -> workflow_runs.id`, `entity_id -> entities.id` |
| `evidence_anchors` | `EvidenceAnchor` | 9 | `id` (UUID) | `claim_id -> claims.id`, `raw_document_id -> raw_documents.id` |
| `entities` | `Entity` | 8 | `id` (UUID) | `project_id -> projects.id` |
| `entity_matches` | `EntityMatch` | 9 | `id` (UUID) | `project_id -> projects.id`, `source_entity_id -> entities.id`, `target_entity_id -> entities.id` |
| `datasets` | `Dataset` | 7 | `id` (UUID) | `project_id -> projects.id`, `workflow_id -> workflows.id` |
| `dataset_versions` | `DatasetVersion` | 9 | `id` (UUID) | `project_id -> projects.id`, `dataset_id -> datasets.id`, `dataset_schema_id -> dataset_schemas.id`, `workflow_run_id -> workflow_runs.id` |
| `canonical_values` | `CanonicalValue` | 9 | `id` (UUID) | `project_id -> projects.id`, `dataset_version_id -> dataset_versions.id`, `entity_id -> entities.id`, `selected_claim_id -> claims.id` |
| `conflicts` | `Conflict` | 10 | `id` (UUID) | `project_id -> projects.id`, `dataset_version_id -> dataset_versions.id`, `entity_id -> entities.id`, `resolved_claim_id -> claims.id` |
| `dataset_version_records` | `DatasetVersionRecord` | 8 | `id` (UUID) | `project_id -> projects.id`, `dataset_version_id -> dataset_versions.id`, `entity_id -> entities.id` |
| `outbox_events` | `OutboxEvent` | 11 | `id` (UUID) | `project_id -> projects.id` |

---

## 3. Database Catalog Inventory (PostgreSQL Inspection)

Verified via live catalog queries on Neon development database:
- **Public Tables**: **22** (21 business tables + `alembic_version`)
- **Primary Keys**: **22**
- **Foreign Keys**: **48** (all enforcing `ON DELETE RESTRICT`)
- **Unique Constraints**: **13**
- **Check Constraints**: **187**
- **Indexes**: **80** (35 PK/unique indexes + 45 foreign key, query, and queue indexes)

### Index Audit: Before vs After

| Category | Initial Pass | Corrected Pass | Rationale |
| :--- | :--- | :--- | :--- |
| Redundant Single-Column FK Indexes | 6 | 0 | Removed redundant indexes where composite unique constraint has FK as leading column (e.g., `ix_dataset_schemas_requirement_id`, `ix_workflow_versions_workflow_id`, `ix_dataset_versions_dataset_id`, `ix_dataset_version_records_version_id`). |
| Duplicate Unique Indexes | 1 | 0 | Removed `ix_workflow_events_run_sequence` which duplicated `uq_workflow_events_run_sequence`. |
| Composite Execution Indexes | 1 | 1 | Preserved `ix_workflow_runs_version_status_created` and removed redundant standalone `ix_workflow_runs_version_id` and `ix_workflow_runs_created_at`. |
| Multi-Tenant `project_id` Indexes | 6 | 13 | Added explicit tenant lookup indexes on `dataset_schemas`, `trust_contracts`, `dataset_versions`, `canonical_values`, `conflicts`, `dataset_version_records`, and `outbox_events`. |
| Provenance Indexes | 1 | 2 | Removed `ux_raw_documents_content_hash`; added `ix_raw_documents_project_content_hash` and `ix_claims_project_id`. |
| Reproducibility FK Indexes | 0 | 4 | Added indexes for `workflow_versions.dataset_schema_id`, `workflow_versions.trust_contract_id`, `canonical_values.selected_claim_id`, `conflicts.resolved_claim_id`. |
| **Total Indexes in Catalog** | **76** | **80** | Every single index is tied to a concrete access pattern or foreign key traversal. |

---

## 4. Migration Cycle Verification (Neon PostgreSQL)

Migration `9727a73ca3e4_core_schema_phase2b.py` was verified through a complete downgrade/re-upgrade cycle:
1. **Initial Downgrade**: Downgraded Neon database to Phase 2A baseline (`21242d5d8505`). All business tables removed.
2. **Migration Update**: Corrected `9727a73ca3e4_core_schema_phase2b.py` in-place without creating a premature Phase 2C migration.
3. **Upgrade to HEAD**: `alembic upgrade head` applied the corrected schema cleanly.
4. **Downgrade Verification**: `alembic downgrade 21242d5d8505` cleanly dropped all 21 tables in reverse topological dependency order.
5. **Re-Upgrade to HEAD**: `alembic upgrade head` restored all tables, constraints, and indexes. Current revision confirmed: `9727a73ca3e4 (head)`.

---

## 5. Verification Results

### Offline Gates (`make check`)
- **Ruff check**: All checks passed across `app`, `worker`, `tests`.
- **Ruff format**: 30 files verified, 0 formatting issues.
- **Web lint**: ESLint passed with 0 warnings or errors.
- **Mypy**: `Success: no issues found in 30 source files` (strict mode).
- **Web typecheck**: TypeScript type-check passed (`tsc --noEmit`).
- **Offline pytest**: **40/40 passed** (10 domain contracts + 12 schema contracts + 7 config + 4 correlation + 5 health + 2 worker).
- **Web tests**: Vitest passed 2/2 tokens tests.
- **Web build**: Production Next.js build compiled successfully (all 4 routes static).

### Live Neon Integration Tests (`make test-db`)
**20/20 live integration tests passed**:
- `test_real_neon_pooled_connectivity` — **PASSED**
- `test_real_neon_direct_connectivity` — **PASSED**
- `test_async_engine_lifecycle` — **PASSED**
- `test_async_session_creation_and_cleanup` — **PASSED**
- `test_transaction_rollback_behavior` — **PASSED**
- `test_health_checker_success_against_neon` — **PASSED**
- `test_health_checker_graceful_failure_simulation` — **PASSED**
- `test_alembic_current_revision_is_phase2b_head` — **PASSED**
- `test_neon_table_inventory` — **PASSED**
- `test_neon_critical_constraints_and_indexes` — **PASSED** (asserts all 10 critical FKs and required indexes in live catalog)
- `test_minimal_relational_fixture_insertion_and_rollback` — **PASSED**
- `test_neon_foreign_key_violation_rejected` — **PASSED**
- `test_neon_unique_constraint_violation_rejected` — **PASSED**
- `test_neon_check_constraint_violation_rejected` — **PASSED**
- `test_neon_entity_match_pair_order_and_no_self_match` — **PASSED** (verifies self-match and inverted order rejection)
- `test_neon_raw_document_independent_provenance_identical_content_hash` — **PASSED** (verifies multiple sources with identical content hash)
- `test_neon_canonical_values_dataset_version_scoped` — **PASSED** (verifies v1 and v2 coexist for same entity & field)
- `test_neon_schema_version_reproducibility_coexistence` — **PASSED** (verifies Requirement -> Schema v1/v2 -> Trust v1/v2 -> Workflow v1/v2 -> DatasetVersion 1/2 coexist under same logical entities without mutating v1)
- `test_neon_claim_provenance_and_nullable_entity` — **PASSED** (verifies claim references source, raw_document, entity and allows initial NULL entity_id for pre-resolution extraction)
- `test_neon_fixture_cleanup_guarantee` — **PASSED** (verified 0 rows across all 21 tables)

### Introspection Output (`make db-schema-check`)
```text
============================================================
ProofGrid Schema Introspection (Safe / Sanitized)
============================================================
Provider: PostgreSQL / Neon
Database connectivity: OK
Alembic Current Revision: 9727a73ca3e4

Public Tables (22 total):
  [✓] alembic_version
  [✓] canonical_values
  [✓] claims
  [✓] conflicts
  [✓] dataset_schemas
  [✓] dataset_version_records
  [✓] dataset_versions
  [✓] datasets
  [✓] entities
  [✓] entity_matches
  [✓] evidence_anchors
  [✓] outbox_events
  [✓] projects
  [✓] raw_documents
  [✓] requirements
  [✓] sources
  [✓] step_runs
  [✓] trust_contracts
  [✓] workflow_events
  [✓] workflow_runs
  [✓] workflow_versions
  [✓] workflows

Constraint & Index Inventory across public schema:
  Primary Keys:       22
  Foreign Keys:       48
  Unique Constraints: 13
  Check Constraints:  187
  Indexes:            80

[SUCCESS] Schema verification passed cleanly against live database.
```

### Live Health Check Endpoints
- `GET /health/live` -> HTTP 200 `{'status': 'ok', 'service': 'proofgrid-api', 'version': '0.1.0'}`
- `GET /health/ready` -> HTTP 200 `{'status': 'ok', 'ready': True, 'database': {'status': 'healthy'}}`

---

## 6. Secret Safety
- Confirmed zero credentials, DSN strings, passwords, or tokens are tracked in git or printed in logs/tools.
- `make db-schema-check` outputs only sanitized metadata.
- `.env` and `backend/.env` remain strictly gitignored.
