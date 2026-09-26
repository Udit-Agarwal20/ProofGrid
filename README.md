# ProofGrid

> Turn natural-language business data requirements into structured, source-backed, traceable datasets.

## Architecture Doctrine

```
LLM plans.
Code executes.
Evidence proves.
PostgreSQL owns truth.
```

> **Security Note**: Do not add secrets to the repository. Use environment variables via `.env` (derived from `.env.example`).

---

## Local Prerequisites

- **Python**: `>= 3.12`
- **uv**: Package installer and virtual environment manager (`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node.js**: `>= 20.x` (recommended `v22+` or `v24+`)
- **pnpm**: `>= 9.x` (`corepack enable` or `npm install -g pnpm`)
- **Make**: Standard POSIX make utility

---

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd code-cubical

# Install both backend and frontend dependencies
make install
```

Or manually:
```bash
# Backend setup
cd backend
uv venv
uv pip install -e ".[dev]"
cd ..

# Frontend setup
pnpm install
```

---

## Running the Application

### 1. Start the API
```bash
make dev-api
# API server runs at http://localhost:8000
# Health check: http://localhost:8000/health/live
```

### 2. Start the Worker (Phase 1 Standby)
```bash
make dev-worker
```

### 3. Start the Web Frontend
```bash
make dev-web
# Web application runs at http://localhost:3000
```

### 4. Database Operations (Phase 2A Neon Foundation)
```bash
make db-check      # Ping Neon database and report latency (no secrets exposed)
make db-current    # Show current Alembic migration revision
make db-upgrade    # Apply Alembic migrations to HEAD
make db-downgrade  # Rollback latest Alembic migration
```

---

## Verification & Quality Gates

Run the offline verification gate (CI-compatible, deterministic, offline):

```bash
make check
```

Run live database integration tests against Neon:

```bash
make test-db
```

Or run individual verification checks:

```bash
make test        # Run backend pytest (unit + contracts) and frontend vitest
make test-db     # Run live Neon PostgreSQL integration tests
make lint        # Run ruff check and next lint
make typecheck   # Run mypy (strict) and tsc --noEmit
make build       # Run next production build
```

---

## Project Structure

```
.
├── apps/
│   └── web/                 # Next.js 15 App Router web workbench (Tailwind + Forensic Ledger tokens)
├── backend/
│   ├── app/
│   │   ├── api/             # API routes and endpoints
│   │   ├── core/            # Config, structured logging, correlation middleware
│   │   ├── domain/          # Pydantic v2 domain contracts and canonical enums
│   │   └── main.py          # FastAPI application entrypoint
│   ├── worker/
│   │   └── main.py          # Graceful background worker entrypoint
│   ├── tests/
│   │   ├── unit/            # Unit tests for config, correlation, health, worker
│   │   ├── contracts/       # Serialization and validation tests for domain models
│   │   └── fixtures/        # Sample JSON schema contract fixtures
│   └── pyproject.toml       # Backend Python dependencies and tooling configs
├── docs/
│   ├── source-of-truth/     # Upstream PRD, TRD, and UX/UI specifications
│   ├── architecture/        # Architecture docs, system maps, conflict register, decision log
│   └── build/               # Phase completion reports and verification logs
├── .github/
│   └── workflows/ci.yml     # Minimal CI workflow for lint, test, and typecheck
├── .env.example             # Placeholder environment variable specification
├── Makefile                 # Unified development and gate verification commands
└── README.md                # Project documentation and engineering doctrine
```
