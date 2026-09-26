# ProofGrid: Engineering Acceptance Gates

> **Strict Machine-Verifiable Verification Protocol**: Development cannot advance past a milestone without satisfying the measurable pass conditions defined for each gate. These gates ensure architectural integrity, zero regression, and demo-day reliability.

---

## 1. Foundation Gate (Phase 1)
- [x] **Typecheck**: `mypy app worker tests` passes with zero errors under strict mode.
- [x] **Linter**: `ruff check .` and `ruff format --check .` pass with zero violations.
- [x] **Frontend Tooling**: `pnpm build` in `apps/web` builds an empty shell without TypeScript or CSS errors.
- [x] **Domain Schema Serialization**: Automated unit tests verify that `RequirementSpec`, `FieldSpec`, `TrustContract`, `PlanDAG`, `PlanNode`, `EvidenceAnchor`, `EvidenceType`, `Claim`, and `Entity` serialize to and deserialize from valid JSON Schema fixtures.
- [x] **Config Hardening**: Application fails fast on boot if essential environment variables are missing or misconfigured.
- [x] **Phase 1 Scope Enforcement**: Verified zero implementation code for database migrations, Supabase/Qdrant connections, LLM API calls, web acquisition/scrapers, extraction, entity resolution, Claim Ledger persistence, ProofCell business logic, or full application screens.

---

## 2. Database Gate (Phase 2)
- [ ] **Clean Migration**: `alembic upgrade head` applies cleanly against a fresh, empty PostgreSQL database.
- [ ] **Reversible Migration**: `alembic downgrade -1` rolls back the latest migration cleanly, and re-applying `upgrade head` succeeds.
- [ ] **Constraints & Indexes**: All 18 core tables and explicit unique indexes exist (including `ux_step_idempotency`, `ix_step_runs_ready`, `ux_raw_documents_content_hash`).
- [ ] **Foreign Key Cascades**: Foreign keys to provenance objects (`raw_documents`, `claims`, `entities`) use `RESTRICT` to prevent accidental deletion of historical evidence.
- [ ] **Transaction Rollback**: An integration test asserts that a failed step insert rolls back cleanly without leaving partial run state.

---

## 3. Requirement Compiler Gate (Phase 3)
- [ ] **Schema Conformance**: 100% of curated evaluation prompts produce a valid `RequirementSpec` matching the Pydantic schema on the first attempt or within a single automated repair retry.
- [ ] **Demo Vertical Compilation**: Compiling the golden prompt (*"Find Indian AI startups that raised more than $1M in the last 12 months..."*) yields all required fields (`company_name`, `website`, `founders`, `headquarters`, `funding_round`, `funding_amount`, `currency`, `investors`, `funding_date`).
- [ ] **AI-Inferred Tagging**: Any field inferred by the model that was not explicitly present in the user prompt has `origin='ai_inferred'`.
- [ ] **Deterministic Date Resolution**: Expressions like *"last 12 months"* resolve to explicit ISO 8601 calendar bounds relative to the execution timestamp.
- [ ] **Schema Negotiation**: `PATCH /v1/requirements/{id}` allows adding, deleting, and renaming fields, recalculating a matching `schema_hash`.

---

## 4. Planner Gate (Phase 4)
- [ ] **Topological Validity**: The generated `PlanDAG` passes Kahn's algorithm; cyclic dependencies are strictly rejected.
- [ ] **Operator Registry Conformance**: 100% of operators in the plan belong to the registered enum (`DISCOVER`, `FETCH_HTTP`, `FETCH_BROWSER`, `EXTRACT`, `NORMALIZE`, `VALIDATE`, `ENTITY_RESOLVE`, `RECONCILE`, `MATERIALIZE`, `INDEX`, `EXPORT`).
- [ ] **Budget Gate**: Any proposed plan where `expected_pages > max_pages` or `expected_browser_pages > max_browser_pages` is rejected with `PLAN_BUDGET_EXCEEDED` before execution.
- [ ] **Deterministic Plan Validator**: Unit tests assert that fabricated plans with cycles, missing dependencies, or incompatible artifact edges fail validation.

---

## 5. Workflow Engine Gate (Phase 5)
- [ ] **SKIP LOCKED Concurrency**: A concurrency test running 2 simultaneous worker processes claiming 20 queue steps results in **0 duplicate executions** and **0 lock deadlocks**.
- [ ] **Worker Death Recovery**: An integration test simulating a worker process crash (`kill -9`) verifies that after the lease expires (e.g., 60 seconds), the sweeper returns the step to `READY` state.
- [ ] **Idempotent Step Execution**: Re-executing an operator with identical input parameters produces identical output hashes without duplicating database rows.
- [ ] **Cooperative Cancellation**: Invoking `POST /v1/runs/{id}/cancel` halts queued steps from being claimed and marks the run status as `CANCELLED`.

---

## 6. Acquisition Gate (Phase 6)
- [ ] **SSRF Defense Suite**: The safe URL validator rejects 100% of test attack vectors: `http://127.0.0.1`, `http://localhost`, `http://169.254.169.254`, `http://10.0.0.1`, `http://[::1]`, and HTTP redirects pointing to private addresses.
- [ ] **Robots.txt Policy**: Collector respects disallowed paths for a simulated domain and records `ROBOTS_DISALLOW` without crashing.
- [ ] **Byte & Timeout Limits**: Oversized responses (>5MB) and hanging socket connections are aborted within configured limits.
- [ ] **Content-Addressed Storage**: Fetching an identical webpage twice results in a single stored binary in object storage, verified by SHA-256 hash match.
- [ ] **Two Working Public Source Patterns**: Successfully collects live HTML from at least two real public startup news/feed domains.

---

## 7. Evidence Gate (Phase 7)
- [ ] **Evidence Anchor Deterministic Resolution**: 100% of claims accepted into `VERIFIED` or `SUPPORTED` trust states have their evidence anchor deterministically resolved against the stored `RawDocument` representation across supported types:
  - `TEXT_SPAN` / `NORMALIZED_TEXT_SPAN`: Quoted span is verified present in document text after the documented normalization procedure.
  - `JSON_POINTER` / `API_RESPONSE_POINTER`: JSON pointer / field path resolves in the structured payload and matches the raw value.
  - `DOM_SELECTOR / DOM_PATH`: Stable element locator and supporting text validate against the stored DOM snapshot.
  - `STRUCTURED_FIELD`: Canonical key/path resolves accurately against structured tables or feeds.
- [ ] **Hallucination Rejection**: Automated unit tests inject LLM responses containing plausible but fabricated text quotes, invalid JSON pointers, or missing DOM selectors; the verifier detects that resolution fails, marks the anchor as `UNANCHORED`, and strictly blocks the claim from `VERIFIED` or `SUPPORTED` status.
- [ ] **Exact Character Offsets & Paths**: Verified text anchors record valid `evidence_start` and `evidence_end` character indices matching the source text span; structured anchors record resolved JSON-pointer or DOM selector paths for ProofCell inspection.

---

## 8. Data Quality Gate (Phase 8)
- [ ] **Currency Normalization**: Test fixtures for `$4.5M`, `USD 1 million`, `₹12 crore`, `Rs 25 lakh`, and `€2.5M` parse accurately into Decimal amounts and ISO currency codes, retaining original strings.
- [ ] **Exchange Rate Reproducibility**: Derived USD conversions record the exact FX rate and rate date used from the cached `Frankfurter` provider.
- [ ] **Date Normalization**: Ambiguous dates parse with explicit precision metadata (`YYYY`, `YYYY-MM`, or `YYYY-MM-DD`).
- [ ] **Entity Deduplication Precision**: 100% of labeled identical startup pairs in the evaluation corpus are auto-merged; 0% of labeled distinct companies with similar names are falsely merged.
- [ ] **Contradiction Veto**: Competing claims with verified distinct primary domains are blocked from auto-merging and flagged for human review.

---

## 9. Backend API Gate (Phase 9 & 10)
- [ ] **OpenAPI Schema Generation**: The FastAPI application generates a complete `openapi.json` without validation errors.
- [ ] **TypeScript Client Generation**: TypeScript interfaces generated from the OpenAPI schema compile without errors in `apps/web`.
- [ ] **Read Model Query Performance**: `GET /v1/datasets/{id}/versions/{vid}/records` returns 100 paginated records in **<300ms p95** using the denormalized `dataset_version_records` table.
- [ ] **ProofCell Payload Latency**: `GET /.../records/{eid}/proof/{field_key}` returns canonical value, trust status, and all supporting/conflicting claims in **<350ms p95** with zero LLM calls.
- [ ] **SSE Replay & Resume**: Client connecting with `Last-Event-ID` receives all missed historical events in order before receiving live events.

---

## 10. Frontend Gate (Phase 11 & 12)
- [ ] **Responsive Density**: ProofGrid table renders smoothly without layout breakage or horizontal collapse at both **1366x768** and **1440x900** viewports.
- [ ] **Anti-AI-Slop Compliance**: Interface uses the "Forensic Ledger" palette (`--canvas: #F4F1EA`, `--ink: #151A17`, `--copper: #B85732`) and IBM Plex typography. Zero purple/blue glowing aurora gradients, zero glassmorphism cards, zero AI sparkle icons.
- [ ] **ProofCell Drawer Interaction**: Clicking any evidence-bearing cell opens the Evidence Drawer in **<100ms UI response time**, displaying the verbatim source quote in IBM Plex Serif.
- [ ] **Conflict Surfacing**: Conflicted cells visibly render the `!` symbol and amber badge; it is impossible to suppress the conflict badge from the UI.
- [ ] **Comprehensive State Handling**: Every screen deterministically handles Loading (skeletons), Error (contextual error banners), Empty (actionable brief suggestions), and Partial (amber partial run badge) states.

---

## 11. End-to-End Gate (Phase 13)
- [ ] **Golden Vertical Completion**: Executing the prompt *"Find Indian AI startups that raised more than $1M in the last 12 months"* from the UI completes end-to-end and materializes at least 20 verified startup records.
- [ ] **Runtime Budget**: The complete golden vertical workflow completes in **<90 seconds** under controlled demo conditions.
- [ ] **Conflict Demonstration**: The resulting dataset contains at least one visibly flagged `CONFLICTING` cell with multiple competing claims in the Evidence Drawer.
- [ ] **Entity Deduplication Demonstration**: The dataset contains at least one successfully merged entity whose aliases and cross-source evidence are inspectable.
- [ ] **Export Integrity**: Exported ZIP file contains `dataset.csv`, `claims.csv`, `sources.csv`, and `manifest.json`; every record ID in `dataset.csv` maps to claims in `claims.csv`.

---

## 12. Security Gate (Phase 14)
- [ ] **Zero Secret Leakage**: No API keys, database credentials, or service-role keys are present in frontend bundles, network request payloads, or application logs.
- [ ] **Prompt Injection Defense**: An end-to-end test processes a malicious HTML document containing prompt injection instructions; the system extracts data without executing tools, modifying database state, or following injected instructions.
- [ ] **Stored XSS Sanitization**: Evidence quotes containing `<script>` tags or malicious HTML are safely rendered as plain text in the Evidence Drawer.
- [ ] **Strict Egress / Robots Policy**: Outbound crawlers identify with a named ProofGrid user-agent and do not attempt CAPTCHA bypass or paywall circumvention.

---

## 13. Demo Reliability Gate (Phase 14)
- [ ] **Secondary Dependency Resilience**: When Qdrant is completely offline, the core workflow, ProofGrid table, and Evidence Drawer function with 100% correctness (`index_status=PENDING`).
- [ ] **Honest Fixture Mode**: Setting `ACQUISITION_MODE=FIXTURE` allows the entire downstream pipeline (extraction, normalization, entity resolution, conflict detection, materialization) to execute offline on pre-cached documents with visible `"Cached Fixture"` UI labeling.
- [ ] **10 Consecutive Rehearsals**: The complete live user journey (Ask → Schema → Trust → Plan → Run → Prove → Export) executes successfully 10 times consecutively from a clean database state without manual intervention.

---

## 14. Release Gate (Competition Submission)
- [ ] **Code Freeze**: All application code, prompts, model aliases, and database migrations are frozen 6 hours prior to presentation.
- [ ] **Production Build**: Production Docker container builds and Next.js static production bundle pass without warnings.
- [ ] **Pitch Timing**: Live on-stage workflow demo completes comfortably within the 90-second presentation allocation.
- [ ] **Backup Artifacts**: Recorded 90-second golden path video and pre-materialized showcase dataset are available locally for instant venue failure recovery.
