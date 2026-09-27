# Phase 2C Build Report — Persistence Application Layer
## Repositories + Async Unit of Work + Transactional Outbox Foundation

**Date**: 2026-09-27  
**Status**: **PASS (Verification Clean)**  
**Engineering Lead**: Antigravity AI  
**Scope**: Phase 2C — Repositories, Unit of Work, Transactional Outbox, Error Sanitization  
**Database Migration HEAD**: `9727a73ca3e4`  
**Git Checkpoint Baseline**: `e0f999ef7fdba8c071a2f9b07244a0edf2466ac6` (Phase 2B Checkpoint)  

---

## 1. Executive Summary & Architecture Realignment

Phase 2C constructs the clean, decoupled persistence application layer for ProofGrid atop the verified Neon PostgreSQL database (Alembic HEAD `9727a73ca3e4`).

The design adheres strictly to ProofGrid architectural doctrine:
1. **Unidirectional Dependency Flow**:  
   `Application -> UnitOfWork -> Repositories -> AsyncSession -> SQLAlchemy ORM -> PostgreSQL`
2. **Single Shared AsyncSession per UnitOfWork**:  
   All repositories instantiated during a `UnitOfWork` session receive and share the exact same `AsyncSession`. No repository creates its own connection, session, or transaction.
3. **No Independent Commit or Rollback in Repositories**:  
   Repositories stage changes (`self._session.add()`) or execute query statements (`select(...)`), but NEVER call `commit()`, `rollback()`, or `begin()`. Static AST analysis across all repository files continuously enforces this invariant.
4. **Cohesive Aggregate Repositories (8 Repositories)**:  
   Rather than proliferating 21 generic CRUD tables, the 21 relational business models are partitioned into 8 cohesive aggregate repositories mirroring the core problem domains.
5. **Atomic Transactional Outbox**:  
   Business entity mutations and `outbox_events` are enqueued within the same `UnitOfWork` transaction. Either both commit atomically or neither does.
6. **Append-Only Immutability**:  
   Append-only tables (`claims`, `evidence_anchors`, `raw_documents`, `workflow_versions`, `workflow_events`, `dataset_versions`, `dataset_version_records`) expose no `update_*` or `delete_*` APIs.
7. **Strict Domain Layer Independence**:  
   Domain models in `backend/app/domain/` remain pure Python/Pydantic data structures with zero imports of SQLAlchemy, ORM entities, or database session classes.
8. **Credential & DSN Sanitization**:  
   All persistence exceptions are scrubbed of connection strings, passwords, and sensitive connection tokens before propagating.

---

## 2. Repository Layer Design & Partitioning

The 21 business tables are partitioned across 8 cohesive repositories under `backend/app/persistence/repositories/`:

| Repository Class | File | Covered Business Tables | Key Persistence Operations & Invariants |
| :--- | :--- | :--- | :--- |
| `ProjectRepository` | `project.py` | `projects` | `add`, `get_by_id`, `get_by_slug`, `list_projects`. Enforces tenant slug uniqueness via database constraints. |
| `RequirementRepository` | `requirement.py` | `requirements`, `dataset_schemas`, `trust_contracts` | Versioned schema and trust contract management: `get_dataset_schema_by_version`, `get_latest_dataset_schema`, `get_trust_contract_by_version`, `get_latest_trust_contract`. Deterministic version retrieval. |
| `WorkflowRepository` | `workflow.py` | `workflows`, `workflow_versions`, `workflow_runs`, `step_runs`, `workflow_events` | Immutable version tracking (`plan_dag`), run execution tracking, node-level step run lookups (`get_step_run_by_node`), and sequential audit events (`list_workflow_events`). |
| `SourceRepository` | `source.py` | `sources`, `raw_documents` | Attributed provenance sources, URL lookups (`get_source_by_canonical_url`), content-hash diagnostics (`find_by_content_hash`), and immutable snapshot history. Multiple documents with identical `content_hash` are permitted. |
| `ClaimRepository` | `claim.py` | `claims`, `evidence_anchors` | Append-only Claim Ledger operations: `add_claim`, `get_claim`, `list_claims_for_entity_field`, `list_claims_for_source`, `list_claims_for_raw_document`, `list_claims_for_run`, `add_evidence_anchor`, `list_evidence_anchors_for_claim`. Zero update/delete APIs. |
| `EntityRepository` | `entity.py` | `entities`, `entity_matches` | Entity lookup by `stable_entity_key`. Pairwise entity resolution with **automatic canonical UUID pair ordering** (`source_entity_id < target_entity_id`) and self-match rejection (`A == B` raises `PersistenceIntegrityError`). |
| `DatasetRepository` | `dataset.py` | `datasets`, `dataset_versions`, `canonical_values`, `conflicts`, `dataset_version_records` | Dataset logical identity, immutable dataset versions (`DRAFT`, `FINALIZING`, `FINALIZED`, `FAILED`), dataset-version scoped `canonical_values`, dataset-version scoped `conflicts`, and materialized `dataset_version_records`. |
| `OutboxRepository` | `outbox.py` | `outbox_events` | Pure persistence primitives: `enqueue` (via `OutboxEventCreate` with default `PENDING` status, `attempt_count=0`), `get_by_id`, and administrative bounded read-only query `list_by_status`. Zero worker semantics, no row locking, no leases, and no queue consumption. |

---

## 3. Async Unit of Work Design & Lifecycle

The Unit of Work is implemented in `backend/app/persistence/unit_of_work.py` via `AbstractUnitOfWork` and `SqlAlchemyUnitOfWork`.

### Lifecycle State Machine:
1. **Entry (`__aenter__`)**:
   - Opens an `AsyncSession` from the injected session factory (or default singleton factory).
   - Starts an explicit transaction via `await session.begin()`.
   - Binds the single session instance across all 8 lazy repository instances.
   - Guarded against double entry or reuse of a closed instance.
2. **Execution**:
   - Application services interact with repositories through `uow.projects`, `uow.claims`, etc.
   - Operations stage state in the session's unit-of-work buffer.
3. **Commit (`uow.commit()`)**:
   - Explicit invocation required.
   - Flushes and commits the transaction atomically.
   - Sets internal `_committed = True`. Repeated commit calls raise `PersistenceError`.
4. **Exit (`__aexit__`)**:
   - **Unhandled Exception**: Automatically invokes `await self.rollback()`, translates any `SQLAlchemyError` into a typed `PersistenceError` (scrubbing secrets), and re-raises.
   - **No Exception but Uncommitted**: Automatically invokes `await self.rollback()` to prevent hidden or dangling commits.
   - **Session Closure**: Always executes `await self._session.close()` in a `finally` block.

---

## 4. Error Translation & Security Invariants

Implemented in `backend/app/persistence/errors.py`:

### Exception Hierarchy:
```
PersistenceError
├── PersistenceNotFoundError
├── PersistenceConflictError (unique constraint violations, e.g. uq_projects_slug)
├── PersistenceIntegrityError (foreign key, check constraint, or pair order violations)
└── PersistenceConnectionError (connectivity failures, pool exhaustion)
```

### Security & Credential Masking:
- `sanitize_error_message(msg: str) -> str`: Regular expressions systematically mask connection DSNs (`postgresql://user:***@host:port/db`), passwords (`password=***`, `pwd=***`), and authentication tokens from error strings.
- `translate_db_error(exc: SQLAlchemyError) -> PersistenceError`: Inspects PostgreSQL driver error codes (`23505` unique violation, `23503` foreign key violation, `23514` check constraint violation) and constraint names from raw DBAPI exceptions, producing clean typed exceptions while strictly sanitizing the error text.

---

## 5. Verification & Testing Matrix

### Gate 1: AST Analysis & Offline Unit Tests
**File**: `backend/tests/unit/test_persistence_unit_of_work.py`  
**Result**: **14 passed in 0.34s** (0 warnings, 0 errors)
- `test_uow_shared_session_invariant`: All 8 repositories hold identical `session` object identity.
- `test_uow_access_before_enter_raises`: Accessing repositories before context entry raises `PersistenceError`.
- `test_uow_commit_calls_session_commit`: Explicit commit delegates to underlying session commit.
- `test_uow_commit_twice_raises`: Double commit calls are rejected.
- `test_uow_auto_rollback_on_unhandled_exception`: Exceptions trigger automatic rollback.
- `test_uow_auto_rollback_when_exit_without_commit`: Exiting context without commit triggers rollback.
- `test_uow_cannot_be_reused_after_close`: Re-entering a closed UoW raises `PersistenceError`.
- `test_error_sanitization_masks_credentials`: Passwords, DSNs, and tokens are scrubbed from error strings.
- `test_translate_integrity_error_categorization`: Translates unique, FK, and check constraints into typed persistence exceptions.
- `test_entity_pair_canonicalization_order`: Enforces `source < target` and self-match rejection.
- `test_repositories_never_commit_or_rollback_independently`: AST analysis scans every repository Python file to guarantee zero calls to `session.commit()` or `session.rollback()`.
- `test_append_only_repositories_lack_update_or_delete_apis`: Validates that `ClaimRepository` and `SourceRepository` expose no mutating APIs (`update_*`, `delete_*`, `modify_*`, `replace_*`).
- `test_domain_layer_strict_independence`: Verifies that `backend/app/domain` imports zero persistence or SQLAlchemy modules.
- `test_outbox_event_create_defaults`: Validates that `OutboxEventCreate` initializes with `PENDING` status and `attempt_count=0`.

### Gate 2: Live Neon PostgreSQL Integration Tests
**File**: `backend/tests/integration/test_persistence_neon.py`  
**Result**: **12 passed in 15.76s against Neon PostgreSQL cloud** (Alembic HEAD `9727a73ca3e4`)
- `test_neon_uow_shared_session_instance`: Live session sharing across 8 repositories.
- `test_neon_uow_transactional_outbox_rollback`: Domain insert + outbox event rolled back atomically on exception; 0 rows remain.
- `test_neon_uow_transactional_outbox_commit`: Domain insert + outbox event committed atomically; verified in separate session; cleaned up cleanly.
- `test_neon_uow_no_hidden_commit_on_exit`: Uncommitted context exit rolls back; 0 rows remain.
- `test_neon_project_repository_queries`: Project add, get_by_id, get_by_slug, list_projects, and unique constraint conflict translation.
- `test_neon_requirement_version_deterministic_queries`: Multi-version dataset schemas and trust contracts; version-specific and latest retrievals.
- `test_neon_workflow_provenance_and_version_queries`: Versioned workflows, execution runs, step runs by node ID, and workflow events.
- `test_neon_source_and_raw_document_provenance`: Source URL lookups and raw document content-hash queries.
- `test_neon_claim_and_evidence_anchor_persistence`: Unresolved claims (`entity_id=None`), resolved claims (`entity_id=UUID`), and text-span evidence anchors.
- `test_neon_entity_repository_canonical_pair_ordering`: Inverted UUID pairs automatically stored in canonical `source < target` order; self-match rejected.
- `test_neon_dataset_repository_versioning_and_canonical_records`: Dataset version transitions, canonical values, conflicts, and materialized records.
- `test_neon_persistence_fixture_cleanup_guarantee`: Validates that all 21 business tables are completely clean (0 rows) at test completion.

### Gate 3: Combined Integration Suite
**Command**: `make test-db`  
**Result**: **32 passed, 54 deselected, 1 warning in 48.34s**  
All 20 Phase 2A/2B database integration tests + all 12 Phase 2C persistence integration tests pass concurrently against live Neon.

### Gate 4: Full Project Verification Gate
**Command**: `make check`  
**Result**: **ALL PHASE 1 GATES PASSED (Verification Clean)**
- Backend lint: `ruff check app worker tests` -> 0 errors.
- Backend format: `ruff format --check app worker tests` -> 45 files formatted.
- Backend typecheck: `mypy app worker tests` -> Success: no issues found in 45 source files (strict mode).
- Backend unit tests: `pytest` -> 54 passed in 0.66s.
- Frontend lint: `pnpm --filter @proofgrid/web lint` -> Clean.
- Frontend typecheck: `pnpm --filter @proofgrid/web typecheck` -> Clean.
- Frontend unit tests: `vitest run` -> 2 passed.
- Frontend build: `next build` -> Optimized production build clean.

### Gate 5: Database & Tenancy Audits
- `make db-current`: `9727a73ca3e4 (head)`
- `make db-schema-check`: 22 tables (21 business tables + `alembic_version`), 48 foreign keys, 13 unique constraints, 187 check constraints, 80 indexes.
- Business table row audit: **All 21 business tables contain exactly 0 rows**.
- Live health check endpoints:
  - `GET /health/live` -> `200 OK`
  - `GET /health/ready` -> `200 OK` (`database.status: healthy`)
- Git diff whitespace audit: `git diff --check` -> Clean (zero whitespace or conflict markers).
- Tracked secret audit: Zero `.env`, credentials, or tokens tracked.

---

## 6. Deferred Work & Canonical Phase Boundaries

In compliance with instructions, Phase 2C strictly isolates the persistence application layer. The following areas are deliberately deferred to their canonical phases:
1. **Requirement Compiler (LLM Integration)**: User prompt parsing, schema extraction, and trust contract synthesis belong to **Phase 3 — Requirement Compiler**.
2. **Deterministic Workflow Planner**: DAG topological planning and operator compilation belong to **Phase 4 — Workflow Planner**.
3. **Queue Consumers & Background Workers**: Transactional outbox polling, row claiming (`FOR UPDATE SKIP LOCKED`), leases, worker dispatching, extraction execution, and reconciliation belong to **Phase 5 — Workflow Execution**.
4. **API Application Services & Endpoints**: FastAPI product route handlers for requirements, workflows, and datasets belong to their respective feature phases.
5. **Frontend API Integration**: Next.js client integration with live persistence endpoints belongs to later product phases.
