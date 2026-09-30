# ProofGrid backend implementation report

Verification date: 2026-09-30. No commit was created.

## 1. Backend status — PARTIAL

The complete fixture product journey is implemented and exercised against PostgreSQL, including raw acquisition replay, verified evidence, preserved conflicts, review, immutable refresh and export. **The overall mission remains PARTIAL because the measured remote-database read latency exceeds the requested targets.** Gemini live acceptance also remains unavailable because of upstream HTTP 503 responses. Optional cloud/browser extensions are not implemented. This is a functional hackathon backend, not a claim of production readiness or arbitrary-web completeness.

## 2. Executive summary

Replaced the idle worker and health-only API with a coherent requirement-to-provable-dataset system. PostgreSQL owns truth, models emit constrained proposals, and fixed code executes the plan. The synthetic conflict demo and actual captured historical announcements pass through the same downstream pipeline. Invalid/unsupported evidence never earns verified trust. Existing user changes were preserved.

## 3. Documents read

Read the complete master request plus all three DOCX source specifications through their paragraphs and tables:

- `docs/source-of-truth/ProofGrid_PRD_Code_Cubicle_6_0.docx`
- `docs/source-of-truth/ProofGrid_Backend_Engineering_Spec_Code_Cubicle_6_0.docx`
- `docs/source-of-truth/ProofGrid_Frontend_UX_UI_Design_Spec_Code_Cubicle_6_0.docx`

Document contents were treated as product/engineering reference, subordinate to the explicit master request. Significant conflicts are recorded in `BACKEND_CONFLICT_REGISTER.md`.

## 4. Repository state at start

Existing SQLAlchemy models described 21 business tables, with two baseline/core migrations, repositories/UoW, health routes and an idle worker. A branch-specific compiler and uncommitted provider/compiler improvements already existed. The worktree was dirty, including untracked frontend work. Initial offline baseline: **149 passed, 38 deselected**. No user changes were reset or committed.

## 5. Architecture

FastAPI application/API layer, pure domain contracts and validators, provider/acquisition adapters, project-scoped persistence, and a separate PostgreSQL worker. Short row-locked transactions own state transitions and output writes; remote acquisition/model calls execute outside those queue transactions. Ordered events and outbox rows commit with authoritative data. There is no Redis, Celery, Kafka or new microservice framework.

## 6. Files/modules changed

Major additions: `app/api`, `application/acquisition`, `application/planning`, `application/extraction`, `application/execution`, `application/datasets`, `persistence/queries`, and `persistence/repositories/workspace.py`. Added domain clock/identity/normalization/states/response contracts; raw fixture sets; export model; additive migration; E2E/security/queue/compiler/extraction tests; capture/demo/retention/secret-check scripts; dependency lock and disposable PostgreSQL Compose configuration. Updated compiler validation/fixtures, provider safety, worker, logging, configuration, Makefile, CI and backend README. The final Git status includes both new work and the user's earlier changes; it is not a claim that every dirty file originated in this task.

## 7. Database and Alembic

Revision chain: `21242d5d8505` → `9727a73ca3e4` → **`b73a8d401e20`**. The additive revision is applied to the configured Neon database and exercised in isolated test schemas. There are **22 business tables** plus `alembic_version`. Added lease/output/error support, stored raw bodies, compiler metadata, version-pinned exports, unique run/node/document/claim/version constraints and read/lease indexes. PostgreSQL rejects claim UPDATE/DELETE via an append-only trigger. Pooled runtime and direct migration connections were verified.

## 8. Requirement Compiler

COMPILED and NEEDS_CLARIFICATION branches remain separate, with deterministic XOR enforcement and mandatory human confirmation. Clarification does not fabricate a RequirementSpec. A–H fixture corpus passes: golden funding, subjective recency, fintech revenue, Germany manufacturers, explicit Singapore dates, malicious instructions with legitimate Japan intent, unresolved reference and contradictory IPO/founding dates. Relative dates use an injected reference date with calendar-aware month subtraction. Filters must have fields and valid typed values/operators. At most three material clarification questions are allowed. No automatic repair loop was introduced; invalid proposals fail validation.

## 9. Provider adapters

Fixture, Groq and Gemini adapters exist behind the structured-generation protocol. No tools, browser privileges, shell or SQL are supplied to the models. Provider errors and malformed-output messages are sanitized; API-created clients are closed. Groq live strict-schema smoke passed. Gemini was corrected to use JSON Schema input rather than the SDK converter that rejected boolean literals, but its subsequent live calls returned HTTP 503. The normal suite uses mocks/fixtures. There is no silent fallback.

## 10. Planner

Fixture and structured-provider planners produce a stored PlanDAG tied to a confirmed schema/trust snapshot. The preview includes plan, validation metadata and schema hash. Plans support discovery, HTTP, extraction, normalization, verification, resolution, reconciliation, materialization and optional export/index requests. Live general-purpose planning has not been certified across arbitrary prompts.

## 11. Plan validation

Rejects cycles, missing/duplicate nodes, incompatible stage edges, unknown parameters, model-generated execution fields, unsafe literal URLs, unsupported browser collection and budgets that exceed confirmation. Processing stages are constrained to one each. Evidence and conflict-preservation invariants cannot be turned off by user policy edits. Runtime reservations independently enforce budgets.

## 12. Worker and queue

Durable `SKIP LOCKED` claims, run-before-step lock order, attempt/worker fencing, lease heartbeats, expiry recovery, bounded exponential retries, cancellation and idempotent persistence. Failure propagation handles DAG nodes in arbitrary listing order. Run creation enforces idempotency and three concurrent workspace runs by default. Outbox dispatch retries with stable event IDs, backoff and dead-letter state, without altering authoritative dataset correctness. Unknown/unconfigured projection events remain pending.

## 13. Acquisition

Bounded public HTTP and Brave Search adapters; explicit source hints can work without search. Missing discovery configuration is surfaced. Two actual first-party announcements were successfully fetched through the production policy and saved with capture timestamps/hashes: [Sarvam](https://www.sarvam.ai/blogs/announcing-series-a) and [Neysa](https://neysa.ai/press-release/neysa-raises-20-million-in-seed-funding-to-accelerate-generative-ai-adoption-for-enterprises/). Browser acquisition is rejected as unconfigured. Source failures are isolated and reported.

## 14. SSRF and security

Rejects credentials in URLs, non-HTTP schemes, unsafe ports, private/reserved/multicast/loopback/metadata addresses, alternate numeric IP forms and unsafe DNS answers. Connections pin checked IPs and retain original TLS SNI/Host; redirects are revalidated and get destination robots checks. TLS verification remains enabled; environment proxy trust is disabled. Bodies, timeouts, concurrency and query/page budgets are bounded. Auth gates, CAPTCHA and paywall markers stop collection. Project scope is enforced in read/write paths; SQL values remain parameterized. These controls passed the implemented adversarial tests, not an external security audit.

## 15. Extraction

Deterministic JSON/API objects, JSON-LD, semantic HTML tables and a narrow fundraising-headline/dateline parser. A schema-only LLM fallback proposes claims and quotes when deterministic parsing has no result. The generic engine does not promise reliable extraction from every layout. The Sarvam captured source yields its actual historical amount/date; Neysa's ambiguous CMS date remains missing.

## 16. Evidence Anchor Verification

Raw documents persist before extraction. JSON pointers, named JSON-LD script pointers, exact/normalized text spans and exact DOM selectors resolve against stored representations. HTML visible-text offsets explicitly name `html_visible_text:v1`. Literal raw-value presence and structured value/type equality are checked. Invalid or hallucinated evidence stays unanchored and cannot become high-trust canonical evidence.

## 17. Normalization

Raw and normalized values coexist. Decimal monetary parsing supports explicit currencies/scales without fabricated FX. Float monetary inputs are rejected. Dates retain available precision; locations/names/URLs/lists/booleans use deterministic normalization and comparison. Currency differences preserve disagreement.

## 18. Entity resolution

Exact normalized name plus domain supports stable identity. Missing-domain observations are scoped to their source; identical names on distinct domains are not automatically combined. Multiple contradictory domains in one observation are flagged. Similar names, shared-domain ambiguity and parent/subsidiary signals create inspectable review cases; contradictory identifiers veto merging. Human merge decisions affect later snapshots. This is conservative prototype resolution, not a global corporate registry.

## 19. Reconciliation and conflicts

All claims remain stored. Canonical cells retain supporting/competing claim IDs and explain selection. Material disagreement produces CONFLICTING even when a first-party value is preferred. Review selects a later display value only; disagreement and historical values remain. E2E verifies both $4.5M/$5M claims before and after review/refresh.

## 20. Trust engine

VERIFIED, SUPPORTED, SINGLE_SOURCE, CONFLICTING, NEEDS_REVIEW and MISSING are derived from verified anchors, eligible sources, source independence, contract thresholds and disagreement. Same registrable domains, duplicate content and near-duplicate source bodies do not count as independent support. First-party attribution is server/fixture controlled. Freshness currently uses observation/capture time; general publication-age inference is not implemented.

## 21. Datasets and versions

Durable version allocation under a dataset advisory lock, unique version per run, immutable materialized records and canonical provenance. Schema/trust edits produce new versions and require confirmation. Required-field policy can exclude incomplete rows without deleting their evidence. Refresh reruns create new versions and stable entities. Diff reports added, missing, value/trust/conflict/evidence changes, comparing evidence fingerprints rather than freshly allocated claim IDs.

## 22. APIs

`/health/live`, `/health/ready`; `/v1/requirements/compile`, requirement read/edit/confirm, schema/trust reads and trust edit, plan generation; workflow list/version reads; run create/list/status/cancel; SSE; dataset list/get/version list/get; paginated records with typed filtering/sort/search; ProofCell; review queue/decisions; version diff; export create/read/download. Public responses are Pydantic projections rather than ORM objects. Lists have hard caps. The default is a server-injected single workspace with optional bearer authentication, not enterprise RBAC.

## 23. SSE

Ordered persisted sequence numbers, `Last-Event-ID`/cursor replay and 500 ms polling. Stream reads use short separate sessions; disconnects cannot alter workflow execution. The golden E2E verifies replay excludes already received events. Sub-second database-to-client propagation is a design target, not a certified WAN measurement.

## 24. Export

Explicit version-pinned CSV/JSON ZIP bundles include stable entity IDs, evidence cells/claims and a manifest. CSV formula-leading text is escaped. Evidence reads are batched and omit full raw bodies. Export metadata is idempotent and regeneratable; optional cloud object storage is unnecessary for the demo.

## 25. Fixture/demo mode

Synthetic fixtures are plainly labeled at raw-source/run/proof levels and supply intentional credible-shape conflicts plus independent agreement. Captured public fixtures retain real historical dates and clearly identify capture acquisition. Both execute the same downstream stages. The synthetic demo pins 2026-09-30; the captured historical E2E uses 2024-09-30 and an explicitly added country field, leaving unsupported headquarters/founders missing. No final rows are injected.

## 26. Tests added

A–H compiler cases, typed plan/policy checks, SSRF/redirect/DNS pinning/robots tests, redaction/auth/OpenAPI boundaries, evidence/normalizer/trust/entity cases, captured source goldens, isolated PostgreSQL queue/recovery/outbox tests, and three complete worker/API scenarios. Existing compiler/provider/repository tests were preserved and extended where the additive schema required it.

## 27. Exact test results

- Latest offline `make check`: **195 passed, 42 deselected**, one upstream Starlette TestClient deprecation warning; no public network/model dependency.
- Database regression before the final combined run: **33 passed in 101.27 s**.
- Three fixture E2E scenarios: **3 passed in 316.79 s** against isolated schemas on the explicit Neon integration database; no public web/search/LLM calls.
- Final byte-preserving replay regression: **2 passed, 1 deselected in 137.34 s** (budget-limited and captured cases); persisted capture/proof hashes match.
- Groq/Gemini opt-in live tests: **1 passed, 2 failed**; Groq passed, Gemini failures were upstream HTTP 503.
- Existing frontend tests: **2 passed**.
- Final dependency-locked `pytest -q -m integration`: **39 passed, 194 deselected in 507.78 s**, including all three E2E cases, queue/outbox recovery, compiler persistence and database constraints.

## 28. Type/lint/build

Ruff and formatting pass. Strict mypy passes across **111 source files**, including worker/tests/scripts. Existing `apps/web` ESLint, TypeScript, Vitest and Next production build pass. `uv.lock` is created and `uv sync --frozen --extra dev` completed. No frontend code/design changes were made.

## 29. Performance decisions and measurements

Materialized records, scoped indexes, immutable version reads, bounded pages/claims/documents, batched export evidence and reduced ProofCell round trips. Full raw bodies are excluded from ProofCell SQL projections and fetched only for stages that need them. PostgreSQL pools and per-domain/global HTTP semaphores bound resource use.

Measured 20 API requests each from this machine to the explicit remote Neon test database, using an ASGI client and warm connection pool:

| Read | p50 | p95 | Requested p95 |
| --- | ---: | ---: | ---: |
| Grid | 615.9 ms | 1,245.2 ms | ≤300 ms |
| ProofCell | 481.0 ms | 1,316.2 ms | ≤350 ms |

**Targets are not met in this environment.** These measurements include database network/transaction time and application processing. They are not a production load benchmark. Deploy the API near the database and remeasure before certifying those targets; no fabricated latency claim or cache-only result is substituted.

## 30. Security findings

Fixed TLS SNI type incompatibility found during actual capture, destination-robots handling, stale worker fencing/lock-order risk, byte-preserving captured-fixture replay, empty bearer-token acceptance, provider malformed-output text leakage, request validation input echo, and same-name cross-source identity overmerging. Default logs omit exception bodies and redact credentials. A configured-secret scan found zero matches among Git candidate files. No arbitrary code/SQL execution or browser authority was added. Remaining boundaries include single-workspace authentication and narrow parsing/source-policy coverage.

## 31. Secrets/configuration needed

Existing Neon pooled/direct and Groq credentials were used without printing them. No new secret is required for the fixture demo. Brave live discovery needs `SEARCH_API_KEY`; live providers need their explicit configured key/model. A deployment should set the allowed source/first-party domains and an API bearer token when needed. Docker is required only for the provided disposable local-Postgres option; Docker was not installed on this host.

## 32. External features not live-tested

Brave Search (no configured discovery credential), Qdrant, browser acquisition, Pathway, n8n/webhooks, object storage and a deployed API environment. LLM extraction/general planning were tested with constrained mocks and deterministic downstream checks; only the requirement provider had a live Groq smoke. Gemini live remained unavailable. The GitHub workflow was authored for local PostgreSQL but was not run on GitHub from this task.

## 33. Known limitations

Remote read latency above target; narrow deterministic article coverage; no claim of arbitrary-web completeness; missing funding dates are excluded from dated datasets; no browser/CAPTCHA/paywall bypass; no automatic periodic refresh; optional cloud projections absent; first-party classification requires explicit configuration; freshness uses retrieval time; list/demo outputs capped at 500 records. Referenced raw evidence is retained even beyond the raw cleanup window. Cleanup is manual and bounded. Money across currencies is never silently converted.

## 34. Remaining work

- **P0:** No known failing security/functional gate in the verified fixture path. All 39 final integration tests passed.
- **P1:** Deploy near Neon and meet the measured grid/ProofCell targets; enable/test Brave discovery for a broader live demo; reverify Gemini when service capacity recovers; expand selected-source parsers and provenance-aware source publication dates.
- **P2:** Optional Qdrant consumer, approved browser adapters, scheduled refresh/cleanup, broader corpus/scale/load testing and deployment observability. These do not replace PostgreSQL truth.

## 35. Exact local commands

See `backend/README.md` for full setup, fixture/captured differences and disposable database commands. With existing database configuration:

```sh
cd backend
uv sync --frozen --extra dev
.venv/bin/alembic upgrade head
cd ..
make check
make test-db
make test-e2e
AI_PROVIDER=fixture ACQUISITION_MODE=FIXTURE FIXTURE_SET=synthetic make run-api
# Separate terminal:
AI_PROVIDER=fixture ACQUISITION_MODE=FIXTURE FIXTURE_SET=synthetic make run-worker
# Third terminal:
cd backend && .venv/bin/python scripts/demo.py
```

`make test-compiler`, `make test-security`, `make build` and `backend/.venv/bin/python backend/scripts/check_secrets.py` provide focused checks.

## 36. Git status

Changes remain uncommitted: 34 modified tracked entries and 46 untracked entries (Git collapses untracked directories). Modified/new backend, tests, migration, docs, configuration, Makefile/CI and Compose files are present, alongside preserved earlier user changes and untracked frontend work. `git diff --check` passes. The task did not reset history, create a commit or push.

## 37. Secret confirmation

No commit was made. No configured secret value was found in the scanned Git candidate files. Environment files remain ignored; no key values are included in this report. This is a precise scan result, not a claim that a universal secret detector examined every possible secret format.

## 38. Frontend confirmation

No frontend redesign or frontend source change was performed. Existing lint/types/tests/build were verified.

## 39. Infrastructure confirmation

No unjustified infrastructure was added. The only new local service definition is disposable PostgreSQL for tests; Neon remains the authoritative deployment database. Optional cloud consumers are explicitly absent.

## 40. Demo readiness assessment

- **Local demo:** Functional with configured PostgreSQL, API and worker; use the pinned synthetic demo script.
- **Fixture hackathon demo:** Functionally verified, including conflicts, proof, review, refresh and export. Expect the documented remote-database latency on this machine.
- **Permitted live demo:** Limited to configured explicit sources/narrow extraction or supplied discovery/model credentials. Two public source captures succeeded; broad live discovery and full live-pipeline reliability are not certified. Overall mission status remains PARTIAL until the performance gap is closed.
