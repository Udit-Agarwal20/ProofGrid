# ProofGrid backend

FastAPI modular monolith with a separate PostgreSQL queue worker. Neon/PostgreSQL owns requirements, plans, raw evidence, claims, review decisions and dataset snapshots. No external task broker is needed.

## Start the synthetic conflict demo

From the repository root:

```sh
cd backend
uv sync --frozen --extra dev
# Keep your existing backend/.env. For a new setup, copy ../.env.example and set both database URLs.
.venv/bin/alembic upgrade head
cd ..
AI_PROVIDER=fixture ACQUISITION_MODE=FIXTURE FIXTURE_SET=synthetic make run-api
```

In a second terminal:

```sh
AI_PROVIDER=fixture ACQUISITION_MODE=FIXTURE FIXTURE_SET=synthetic make run-worker
```

In a third terminal:

```sh
cd backend
.venv/bin/python scripts/demo.py
```

The demo prints the run, dataset version and export URL. Interactive API documentation: `http://127.0.0.1:8000/docs`. Readiness requires a working database. `worker/main.py --once` checks startup configuration and exits without consuming a job.

`DATABASE_URL` is the pooled runtime connection. `DATABASE_DIRECT_URL` is the direct migration/admin connection. Keep both server-side. `DEMO_PROJECT_ID` selects the server-controlled workspace. To require a bearer token, set `AUTH_ENABLED=true` and a strong `API_AUTH_TOKEN`; clients pass `Authorization: Bearer ...`.

## Fixture and live modes

`FIXTURE_SET=synthetic` replays explicitly artificial JSON/HTML sources. Nimbus has competing $4.5M/$5M funding assertions; Veda has independent agreeing sources. The demo pins reference date `2026-09-30`. These are not real company facts.

`FIXTURE_SET=captured` replays actual Sarvam and Neysa company announcements captured on 2026-09-30 through production robots/HTTP checks. Original event dates remain intact. For the historical Sarvam example use reference date `2024-09-30` and add a `country` location field during schema editing. Missing headquarters remain missing. The captured E2E demonstrates that negotiation. Neysa's CMS publication date is not a defensible funding date and is left out. `scripts/capture_funding_sources.py` explicitly refreshes the two snapshots.

Live acquisition requires `ACQUISITION_MODE=LIVE`. Set `AI_PROVIDER=groq` and `GROQ_API_KEY`, or `gemini` and `GEMINI_API_KEY`. Planning/extraction share that configured provider; legacy `PLANNER_MODEL`, `EXTRACTOR_MODEL` and `LLM_PROVIDER` placeholders do not select separate adapters. Discovery uses `SEARCH_PROVIDER=brave` with `SEARCH_API_KEY`; explicit confirmed source URLs can work without discovery. `FIRST_PARTY_DOMAINS` is a server-controlled attribution allowlist. `ALLOWED_SOURCE_DOMAINS` can restrict all acquisition. No silent model fallback occurs.

HTTP pins checked public IP addresses while preserving TLS SNI, rechecks redirects and robots, and bounds time/body size. Authentication, CAPTCHA and paywall gates are refused. Browser collection is unavailable. Qdrant, Pathway and n8n remain optional extension placeholders, with no cloud projection implemented. Index requests remain durable for a future configured consumer; database correctness does not depend on them.

## Validation

```sh
make check            # offline Ruff, formatting, strict mypy and unit/contract/security tests
make test-compiler
make test-security
make test-db          # explicit PostgreSQL integration environment
make test-e2e         # actual DB; no public web/search/LLM dependency
make test-groq-live   # opt-in; consumes API quota
make test-llm-live    # opt-in Gemini smoke
make build            # existing frontend production build
```

Disposable local database, when Docker is installed:

```sh
docker compose up -d --wait postgres
export DATABASE_URL=postgresql://proofgrid:proofgrid_local@127.0.0.1:5433/proofgrid
export DATABASE_DIRECT_URL="$DATABASE_URL"
export TEST_DATABASE_URL="$DATABASE_URL"
make db-upgrade
make test-db
make test-e2e
```

New queue/E2E tests create and drop only their own uniquely named schemas. Legacy database tests roll back their transactions and assume the target's public business tables are empty: use a dedicated integration database. CI provisions PostgreSQL 16 without external API keys.

## API and execution boundaries

Compile → edit schema/trust → confirm → plan → run → records/proof/review/export → rerun/diff. `PATCH /v1/requirements/{id}` accepts an edited typed specification and creates a schema version, requiring `expected_version`. An edit invalidates confirmation. Workflow versions pin specification, schema, trust policy and plan. Run creation requires a client UUID idempotency key. Review choices affect later snapshots while preserving disagreement. Version-pinned exports contain CSV/JSON and evidence companions, with CSV formula escaping.

SSE persists ordered sequence numbers and replays with `Last-Event-ID`. Worker/attempt fencing rejects expired leases and cancelled-run writes. Retries persist atomically. Runtime budgets reserve pages, search and model calls before effects; USD figures are conservative estimates, not billing totals.

Quotes resolve against stored raw bytes or the named deterministic representation `html_visible_text:v1`, with offsets, JSON pointers or DOM selectors. Unanchored claims cannot earn VERIFIED/SUPPORTED. Claims are append-only in PostgreSQL. Exact name/domain identity can merge; uncertain matches require review. Money uses Decimal and preserves currency without invented FX conversion.

## Retention and operations

`RAW_RETENTION_DAYS` expires only unreferenced artifact bodies. Artifacts referenced by preserved claims remain available. `EXPORT_RETENTION_DAYS` expires regeneratable manifests. Preview cleanup with `cd backend && .venv/bin/python scripts/retention.py`; add `--apply` to apply a bounded batch for the configured workspace. Cleanup is not automatically scheduled.

`scripts/check_secrets.py` scans Git candidate files for configured secret values without printing them. See `../docs/build/BACKEND_IMPLEMENTATION_REPORT.md` for verified scope, exact results and remaining limitations.
