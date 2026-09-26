# Phase 2A Build Report — Database Connection & Persistence Foundation

**Date**: 2026-09-27  
**Status**: **PASS**  
**Engineering Lead**: Antigravity AI  
**Scope**: Phase 2A — Database Connection & Persistence Foundation (Neon PostgreSQL)

---

## 1. Goal

The objective of Phase 2A is to establish a safe, robust, strongly typed PostgreSQL persistence foundation connecting to the live Neon development database. This phase verifies database connectivity, async engine lifecycle, session management, health checking, and baseline Alembic migrations without creating any ProofGrid business tables (which belong strictly to Phase 2B).

At completion of Phase 2A:
- SQLAlchemy 2.0 AsyncEngine and session lifecycle are established.
- psycopg 3 async driver is operational.
- Dual-connection model is implemented: pooled runtime connection for FastAPI (`DATABASE_URL`) and direct unpooled connection for Alembic DDL (`DATABASE_DIRECT_URL`).
- Alembic migration environment is initialized with an empty baseline migration (`21242d5d8505_baseline_phase2a`).
- Migration reversibility (`downgrade base` -> `upgrade head`) is tested and verified, with the final state at HEAD.
- Process liveness (`/health/live`) remains strictly independent of PostgreSQL.
- Service readiness (`/health/ready`) queries live database health when configured and degrades gracefully (HTTP 503) on failure.
- Offline tests (`make check`) remain 100% deterministic and runnable without network access.
- Live Neon integration tests (`make test-db`) execute and pass against the real Neon instance.
- No business tables exist in PostgreSQL (only `alembic_version`).
- No secrets, credentials, or unredacted connection strings are logged, tested, or committed.

---

## 2. Architecture Implemented

A clean, modular persistence layer was established inside `backend/app/db/`:

```
code-cubical/
├── backend/
│   ├── alembic/
│   │   ├── versions/
│   │   │   └── 21242d5d8505_baseline_phase2a.py  # Empty Phase 2A baseline migration
│   │   ├── env.py                                # Loads DATABASE_DIRECT_URL via typed settings
│   │   └── script.py.mako                        # Async migration template
│   ├── alembic.ini                               # Config file with dynamic/empty sqlalchemy.url
│   ├── app/
│   │   ├── core/
│   │   │   └── config.py                         # SecretStr database settings, normalization & safe redaction
│   │   ├── db/
│   │   │   ├── __init__.py                       # Public persistence exports
│   │   │   ├── base.py                           # SQLAlchemy 2.0 DeclarativeBase (no business models)
│   │   │   ├── engine.py                         # Centralized AsyncEngine management with conservative pooling
│   │   │   ├── session.py                        # Request-scoped AsyncSession dependency & lifecycle
│   │   │   └── health.py                         # Bounded SELECT 1 health check with sanitized output
│   │   └── main.py                               # Health endpoints (/health/live, /health/ready) & engine disposal
│   ├── tests/
│   │   ├── integration/
│   │   │   └── test_database.py                  # Live Neon integration tests (pooled, direct, sessions, rollback)
│   │   └── unit/
│   │       ├── test_config.py                    # Unit tests for SecretStr masking & URL normalization
│   │       └── test_health.py                    # Unit tests for liveness independence & readiness 503 simulation
│   └── pyproject.toml                            # Dependencies: sqlalchemy[asyncio], psycopg[binary], alembic
├── docs/
│   ├── architecture/
│   │   └── DECISION_LOG.md                       # ADR-019 recorded
│   └── build/
│       └── PHASE_02A_REPORT.md                   # This report
├── .env.example                                  # Updated with DATABASE_URL & DATABASE_DIRECT_URL placeholders
├── Makefile                                      # Added db-check, db-current, db-upgrade, db-downgrade, test-db
└── README.md                                     # Documented new database developer commands
```

---

## 3. Neon Provider Architecture Decision (ADR-019)

As formally recorded in `docs/architecture/DECISION_LOG.md` (ADR-019), the ProofGrid prototype persistence provider was changed from Supabase PostgreSQL to Neon PostgreSQL:

- **Authoritative Source of Truth**: PostgreSQL remains the sole authoritative system of record.
- **FastAPI Core**: FastAPI remains the backend application framework.
- **Dual-Connection Contract**:
  - `DATABASE_URL`: Neon pooled runtime connection (PgBouncer in transaction mode) for API query handling and worker operations.
  - `DATABASE_DIRECT_URL`: Neon direct/unpooled connection for Alembic DDL migrations and administrative operations.
  - `DATABASE_URL_UNPOOLED`: Supported as an optional alias for `DATABASE_DIRECT_URL`.
- **Low Coupling**: Core persistence relies strictly on standard PostgreSQL, SQLAlchemy 2.0, and `psycopg` 3. No proprietary vendor SDKs are imported.
- **Feature Decoupling**: Object storage and authentication configurations are intentionally deferred and decoupled from database hosting.
- **Progress Reporting**: Server-Sent Events (SSE) from FastAPI are used instead of proprietary WebSocket channels (e.g. Supabase Realtime).

---

## 4. Dependencies Added and Rationale

The following production dependencies were added to `backend/pyproject.toml`:

- `sqlalchemy[asyncio]` (`>=2.0.36`): The standard Python SQL toolkit and Object Relational Mapper with async I/O support (`greenlet`).
- `psycopg[binary]` (`>=3.2.0`): The modern, high-performance PostgreSQL driver for Python with native asynchronous support and binary C extensions.
- `alembic` (`>=1.14.0`): Database migration tool for SQLAlchemy with async engine support.

---

## 5. Configuration Contract & Secret Safety

`backend/app/core/config.py` enforces strict credential protection:
- `DATABASE_URL`, `DATABASE_DIRECT_URL`, and `DATABASE_URL_UNPOOLED` are typed as `pydantic.SecretStr`.
- `repr(settings)` displays `SecretStr('**********')` and never outputs the password.
- `normalize_database_url`: Ensures the scheme is mapped to `postgresql+psycopg://` while preserving `sslmode=require` and query parameters.
- `redact_database_url`: Utilizes SQLAlchemy's `make_url().render_as_string(hide_password=True)` to mask passwords (`user:***@host/db`) for all logging and diagnostic output.
- In case of an unparseable URL, `redact_database_url` returns `<redacted-unparseable-url>` to prevent leaking malformed secrets.

---

## 6. Database Engine & Session Design

### Engine Design (`backend/app/db/engine.py`)
- Centralized singleton AsyncEngine initialized via `create_engine_instance()`.
- Conservative connection pooling parameters optimized for Neon transaction-pooled PgBouncer:
  - `pool_pre_ping=True`: Verifies connection liveness before checkout, preventing stale socket errors.
  - `pool_recycle=300`: Recycles connections every 5 minutes to accommodate cloud firewall and serverless idle timeouts.
  - `pool_size=10`: Prudent connection pool limit for serverless instances.
  - `max_overflow=5`: Bounded surge capacity.
  - `echo=False`: Disables SQL parameter logging to protect sensitive data.
- Graceful shutdown: `dispose_async_engine()` cleans up connection pools during FastAPI lifespan shutdown.

### Session Lifecycle (`backend/app/db/session.py`)
- Factory: `async_sessionmaker[AsyncSession]` bound to the singleton engine with `autocommit=False`, `autoflush=False`, `expire_on_commit=False`.
- Dependency: `get_db_session()` yields an `AsyncSession` per request.
- Automatic rollback: Catches unhandled exceptions, issues `await session.rollback()`, and closes the session in a `finally` block.
- Transaction boundaries: Explicit commits are deferred to business workflows, avoiding hidden repository-level auto-commits.

---

## 7. Alembic Migration Design & Baseline Execution

- **Directory**: `backend/alembic/` with root `backend/alembic.ini`.
- **Credential Protection**: `alembic.ini` contains `sqlalchemy.url = ` (blank). The migration engine dynamically connects via `DATABASE_DIRECT_URL` in `alembic/env.py`.
- **Baseline Migration**: `21242d5d8505_baseline_phase2a.py`.
  - `upgrade()`: `pass`
  - `downgrade()`: `pass`
  - Creates only Alembic's internal `alembic_version` tracking table. Zero business tables created.
- **Reversibility Verification**:
  1. `alembic current` -> initial empty state
  2. `alembic upgrade head` -> applied revision `21242d5d8505`
  3. `alembic current` -> `21242d5d8505 (head)`
  4. `alembic downgrade base` -> rolled back revision cleanly
  5. `alembic upgrade head` -> restored to `21242d5d8505 (head)`
- **Current Database Revision**: `21242d5d8505 (head)`.

---

## 8. Health & Readiness Endpoint Behavior

### Process Liveness: `GET /health/live`
- Verifies process execution and API identity (`status="ok"`, `service="proofgrid-api"`, `version="0.1.0"`).
- Pure process check; 100% decoupled from database connectivity.
- Remains HTTP 200 even during total database failure.

### Service Readiness: `GET /health/ready`
- Evaluates operational readiness of configured dependencies.
- If `DATABASE_URL` is configured:
  - Invokes `check_database_health(timeout_seconds=10.0)` which executes `SELECT 1`.
  - If healthy: returns `200 OK` with latency metadata (`{"status": "ok", "ready": true, "database": {"status": "healthy", "latency_ms": ...}}`).
  - If unhealthy: returns `503 Service Unavailable` with sanitized error details (`{"status": "degraded", "ready": false, "database": {"status": "unhealthy", "error": ...}}`). Zero credentials leaked.
- If `DATABASE_URL` is not configured (e.g. offline CI):
  - Returns `200 OK` with `{"database": {"status": "unconfigured"}}`, preserving Phase 1 deterministic compatibility.

---

## 9. Verification Commands Executed & Exact Results

### 1. Developer Commands in `Makefile`
- `make db-check`: Runs standalone database ping and reports latency.
- `make db-current`: Displays current Alembic revision.
- `make db-upgrade`: Applies pending migrations to HEAD.
- `make db-downgrade`: Rolls back the latest migration.
- `make test-db`: Executes live Neon integration tests (`pytest -m integration`).
- `make check`: Executes offline unit/contract verification gate (`pytest -m "not integration"`, lint, typecheck, build).

### 2. Offline Verification Gate (`make check`)
```text
cd backend && .venv/bin/ruff check app worker tests
All checks passed!
cd backend && .venv/bin/ruff format --check app worker tests
21 files already formatted
pnpm --filter @proofgrid/web lint
$ next lint
✔ No ESLint warnings or errors
cd backend && .venv/bin/mypy app worker tests
Success: no issues found in 21 source files
pnpm --filter @proofgrid/web typecheck
$ tsc --noEmit
cd backend && .venv/bin/pytest
collected 35 items / 8 deselected / 27 selected

tests/contracts/test_domain_serialization.py::test_requirement_spec_roundtrip PASSED [  3%]
tests/contracts/test_domain_serialization.py::test_trust_contract_roundtrip PASSED [  7%]
tests/contracts/test_domain_serialization.py::test_plan_dag_roundtrip PASSED [ 11%]
tests/contracts/test_domain_serialization.py::test_claim_roundtrip PASSED [ 14%]
tests/contracts/test_domain_serialization.py::test_dataset_schema_roundtrip PASSED [ 18%]
tests/contracts/test_domain_serialization.py::test_field_spec_rejects_invalid_keys PASSED [ 22%]
tests/contracts/test_domain_serialization.py::test_plan_node_rejects_arbitrary_code_parameters PASSED [ 25%]
tests/contracts/test_domain_serialization.py::test_plan_node_rejects_unknown_operators PASSED [ 29%]
tests/contracts/test_domain_serialization.py::test_evidence_anchor_rejects_inverted_span PASSED [ 33%]
tests/contracts/test_domain_serialization.py::test_trust_contract_rejects_negative_budget PASSED [ 37%]
tests/unit/test_config.py::test_settings_default_values PASSED           [ 40%]
tests/unit/test_config.py::test_database_url_redaction_safety PASSED     [ 44%]
tests/unit/test_config.py::test_settings_env_override PASSED             [ 48%]
tests/unit/test_config.py::test_settings_invalid_port_rejection PASSED   [ 51%]
tests/unit/test_config.py::test_settings_invalid_env_rejection PASSED    [ 55%]
tests/unit/test_config.py::test_get_settings_cached PASSED               [ 59%]
tests/unit/test_correlation.py::test_is_valid_correlation_id PASSED      [ 62%]
tests/unit/test_correlation.py::test_correlation_id_generated_when_missing PASSED [ 66%]
tests/unit/test_correlation.py::test_correlation_id_propagated_when_valid PASSED [ 70%]
tests/unit/test_correlation.py::test_correlation_id_replaced_when_invalid PASSED [ 74%]
tests/unit/test_health.py::test_health_live PASSED                       [ 77%]
tests/unit/test_health.py::test_health_live_independent_of_database PASSED [ 81%]
tests/unit/test_health.py::test_health_ready_when_db_healthy PASSED      [ 85%]
tests/unit/test_health.py::test_health_ready_when_db_unhealthy PASSED    [ 88%]
tests/unit/test_health.py::test_health_ready_when_db_unconfigured PASSED [ 92%]
tests/unit/test_worker.py::test_worker_startup_and_run_once PASSED       [ 96%]
tests/unit/test_worker.py::test_worker_signal_shutdown PASSED            [100%]

================= 27 passed, 8 deselected, 1 warning in 0.43s ==================
pnpm --filter @proofgrid/web test
$ vitest run
 ✓ test/tokens.test.ts (2 tests) 2ms
 Test Files  1 passed (1)
      Tests  2 passed (2)
pnpm --filter @proofgrid/web build
$ next build
 ✓ Compiled successfully
 ✓ Generating static pages (4/4)
Route (app)                              Size     First Load JS
┌ ○ /                                    137 B           105 kB
└ ○ /_not-found                          980 B           106 kB
+ First Load JS shared by all            105 kB

==================================================
ALL PHASE 1 GATES PASSED (Verification Clean)
==================================================
```

### 3. Real Neon Integration Tests (`make test-db`)
```text
cd backend && .venv/bin/pytest -m integration
============================= test session starts ==============================
collected 35 items / 27 deselected / 8 selected

tests/integration/test_database.py::test_real_neon_pooled_connectivity PASSED [ 12%]
tests/integration/test_database.py::test_real_neon_direct_connectivity PASSED [ 25%]
tests/integration/test_database.py::test_async_engine_lifecycle PASSED   [ 37%]
tests/integration/test_database.py::test_async_session_creation_and_cleanup PASSED [ 50%]
tests/integration/test_database.py::test_transaction_rollback_behavior PASSED [ 62%]
tests/integration/test_database.py::test_health_checker_success_against_neon PASSED [ 75%]
tests/integration/test_database.py::test_health_checker_graceful_failure_simulation PASSED [ 87%]
tests/integration/test_database.py::test_alembic_current_revision_is_head PASSED [100%]

================= 8 passed, 27 deselected, 1 warning in 17.10s =================
```

### 4. Live Server Endpoints & Failure Simulation
- `GET /health/live`: `200 OK`, `{"status": "ok", "service": "proofgrid-api", "version": "0.1.0"}`
- `GET /health/ready` (with live Neon): `200 OK`, `{"status": "ok", "service": "proofgrid-api", "version": "0.1.0", "environment": "local", "ready": true, "database": {"status": "healthy", "latency_ms": 2681.28}}`
- Logged connection target: `"target": "postgresql+psycopg://neondb_owner:***@...-pooler...neon.tech/neondb?..."`
- Simulated DB Failure:
  - `/health/live`: `200 OK` (independent)
  - `/health/ready`: `503 Service Unavailable`, `{"status": "degraded", "service": "proofgrid-api", "version": "0.1.0", "environment": "local", "ready": false, "database": {"status": "unhealthy", "error": "Database connection error: OperationalError"}}` (zero credentials exposed).

### 5. Standalone Worker Verification
- `python worker/main.py --once`: Status 0, emitted clean JSON logs and exited cleanly without touching the database.

---

## 10. Security & Secret Verification

- Verified via `git check-ignore -v .env backend/.env`: both files are strictly ignored by `.gitignore`.
- Verified via `git status --short`: clean working directory, no `.env` or untracked secret files.
- Confirmed zero secret exposure in:
  - Application logs (`engine.py`, `main.py`)
  - Health check error responses (`health.py`)
  - Exception messages (`OperationalError`, `ConnectionRefusedError`)
  - `alembic.ini` (contains no credentials)
  - `alembic/env.py` (reads typed settings, raises without displaying URL)
  - Tests (`test_config.py`, `test_database.py`)
  - Reports and commit history.

---

## 11. Known Limitations

- **Cross-Region Latency**: The Neon development database resides in `ap-southeast-1` (AWS Singapore). Initial connection establishment from cold compute takes ~4-7 seconds, while warm query round-trips take ~2-3 seconds. The health check timeout is set to 10.0 seconds to prevent premature timeouts during cold starts.
- **PgBouncer Transaction Pooling Constraints**: Prepared statements across transactions and session-level settings (`SET search_path`) must not be used in runtime application code.
- **No Business Schema**: As required by Phase 2A, zero domain business tables exist. The public schema contains solely `alembic_version`.

---

## 12. Things Intentionally NOT Implemented in Phase 2A

- No ProofGrid business tables (e.g. `raw_documents`, `claims`, `entities`, `datasets`).
- No business ORM models or repository query methods.
- No Neon Auth, Object Storage, Edge Functions, or AI Gateway integrations.
- No LLM calls, workflow planner execution, or worker job queues.

---

## 13. Phase 2B Prerequisites

With Phase 2A complete and verified:
1. ProofGrid core domain entity ORM models mapped to `Base` (`RawDocument`, `Claim`, `Entity`, `ProofCell`, `DatasetVersion`, `OutboxEvent`).
2. Schema migration adding all 18 core tables, unique indexes (`ux_step_idempotency`, `ux_raw_documents_content_hash`), and foreign key constraints (`ON DELETE RESTRICT`).
3. Repository layer with unit and integration tests.
