.PHONY: help dev-api dev-worker dev-web test lint typecheck build check install db-check db-current db-upgrade db-downgrade db-schema-check test-db test-compiler test-llm-live test-groq-live eval-compiler-live

VENV_BIN := .venv/bin

help:
	@echo "ProofGrid Development Commands:"
	@echo "  make install     Install backend and frontend dependencies"
	@echo "  make dev-api     Start FastAPI backend server"
	@echo "  make dev-worker  Start ProofGrid worker process"
	@echo "  make dev-web     Start Next.js frontend dev server"
	@echo "  make test        Run backend and frontend tests"
	@echo "  make lint        Run backend and frontend linters"
	@echo "  make typecheck   Run backend and frontend type checkers"
	@echo "  make build       Build frontend for production"
	@echo "  make check       Run offline backend verification gate"

install:
	cd backend && uv sync --frozen --extra dev
	pnpm install

dev-api:
	cd backend && $(VENV_BIN)/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dev-worker:
	cd backend && $(VENV_BIN)/python worker/main.py

dev-web:
	pnpm --filter @proofgrid/web dev

test:
	cd backend && $(VENV_BIN)/pytest
	pnpm --filter @proofgrid/web test

lint:
	cd backend && $(VENV_BIN)/ruff check app worker tests
	cd backend && $(VENV_BIN)/ruff format --check app worker tests
	pnpm --filter @proofgrid/web lint

typecheck:
	cd backend && $(VENV_BIN)/mypy app worker tests scripts
	pnpm --filter @proofgrid/web typecheck

build:
	pnpm --filter @proofgrid/web build

db-check:
	cd backend && $(VENV_BIN)/python -c "import asyncio; from app.db.health import check_database_health; res = asyncio.run(check_database_health()); print(f'Database Health: {res.status.upper()} (latency: {res.latency_ms}ms)' if res.status == 'healthy' else f'Database Health: {res.status.upper()} (error: {res.error})'); exit(0 if res.status == 'healthy' else 1)"

db-current:
	cd backend && $(VENV_BIN)/alembic current

db-upgrade:
	cd backend && $(VENV_BIN)/alembic upgrade head

db-downgrade:
	cd backend && $(VENV_BIN)/alembic downgrade -1

db-schema-check:
	cd backend && $(VENV_BIN)/python scripts/db_schema_check.py

test-db:
	cd backend && $(VENV_BIN)/pytest -m integration

test-compiler:
	cd backend && $(VENV_BIN)/pytest tests/unit/test_requirement_compiler.py

test-llm-live:
	cd backend && $(VENV_BIN)/pytest -m llm_live tests/integration/test_gemini_live.py

test-groq-live:
	cd backend && $(VENV_BIN)/pytest -m llm_live tests/integration/test_groq_live.py

eval-compiler-live:
	cd backend && $(VENV_BIN)/python scripts/eval_compiler_live.py

check:
	cd backend && $(VENV_BIN)/ruff check app worker tests scripts
	cd backend && $(VENV_BIN)/ruff format --check app worker tests scripts
	cd backend && $(VENV_BIN)/mypy app worker tests scripts
	cd backend && $(VENV_BIN)/pytest

check-all: check lint typecheck test build

test-unit:
	cd backend && $(VENV_BIN)/pytest tests/unit tests/contracts

test-security:
	cd backend && $(VENV_BIN)/pytest tests/security

test-e2e:
	cd backend && $(VENV_BIN)/pytest -m integration tests/e2e

run-api: dev-api

run-worker: dev-worker
