.PHONY: help dev-api dev-worker dev-web test lint typecheck build check install

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
	@echo "  make check       Run full Phase 1 verification gate"

install:
	cd backend && uv pip install -e ".[dev]"
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
	cd backend && $(VENV_BIN)/mypy app worker tests
	pnpm --filter @proofgrid/web typecheck

build:
	pnpm --filter @proofgrid/web build

check: lint typecheck test build
	@echo ""
	@echo "=================================================="
	@echo "ALL PHASE 1 GATES PASSED (Verification Clean)"
	@echo "=================================================="
