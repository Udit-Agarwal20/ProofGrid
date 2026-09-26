# ProofGrid: System Map & Architectural Topology

> **Comprehensive Component Map**: Defines every logical component, data boundary, responsibility, input/output contract, and operational constraints for the ProofGrid prototype.

---

## 1. ASCII Architecture Diagram

```
+--------------------------------------------------------------------------------------------------+
|                                    PROOFGRID FRONTEND (Next.js)                                  |
|  [Ask Brief] -> [Schema Studio] -> [Trust Contract] -> [Plan Preview] -> [Monitor] -> [Workbench] |
|                                                                    ^           |                 |
|                                                                    | SSE       | ProofCell / REST|
+--------------------------------------------------------------------|-----------|-----------------+
                                                                     |           v
+--------------------------------------------------------------------------------------------------+
|                                  FASTAPI CORE API SERVICE                                        |
|  /v1/requirements/compile   |  /v1/requirements/{id}/plan  |  /v1/workflows/{id}/runs            |
|  /v1/datasets/.../records   |  /v1/records/.../proof/{f}   |  /v1/runs/{id}/events (SSE)         |
+--------------------------------------------------------------------------------------------------+
             |                                                                 ^
             v                                                                 |
+------------------------------------+               +---------------------------------------------+
|    COMPILATION & PLANNING (API)    |               |               POSTGRESQL (Supabase)         |
|  - Requirement Compiler (LLM)      |               |  - requirements      - workflow_runs        |
|  - Schema Proposal & Negotiation   |               |  - trust_contracts   - step_runs (Queue)    |
|  - Trust Contract Engine           | ------------> |  - workflows         - run_events           |
|  - Workflow Planner (LLM)          |               |  - raw_documents     - sources              |
|  - Deterministic Plan Validator    |               |  - evidence_anchors  - claims (Ledger)      |
+------------------------------------+               |  - entities          - conflicts            |
                                                     |  - canonical_values  - dataset_version_recs |
                                                     |  - dataset_versions  - outbox_events        |
                                                     +---------------------------------------------+
                                                                     |                  ^
                                    SELECT FOR UPDATE SKIP LOCKED    |                  | Outbox Dispatch
                                                                     v                  v
+--------------------------------------------------------------------------------------------------+
|                                     PYTHON WORKER PROCESS                                        |
|                                                                                                  |
|   +------------------------------------------------------------------------------------------+   |
|   | 1. ACQUISITION LAYER                                                                     |   |
|   |    - Source Discovery (SearchProvider: Brave/Tavily/Exa/Fixture)                         |   |
|   |    - Safe Acquisition (SSRF guard, redirects, robots.txt, domain semaphore)             |   |
|   |    - HTTP Collector (HTTPX + Trafilatura)                                                |   |
|   |    - Browser Fallback (Playwright Chromium, isolated context, non-critical)              |   |
|   |    - Raw Document Store (Supabase Object Storage / SHA-256 content deduplication)        |   |
|   +------------------------------------------------------------------------------------------+   |
|                                            | RawDocuments                                        |
|                                            v                                                     |
|   +------------------------------------------------------------------------------------------+   |
|   | 2. EXTRACTION & EVIDENCE VERIFICATION                                                    |   |
|   |    - Structured Extraction (Ladder: JSON-LD/selectors -> Heuristics -> LLM fallback)    |   |
|   |    - Evidence Anchor Verification (Text spans, JSON pointers, DOM selectors, API paths)  |   |
|   +------------------------------------------------------------------------------------------+   |
|                                            | ClaimDrafts                                         |
|                                            v                                                     |
|   +------------------------------------------------------------------------------------------+   |
|   | 3. QUALITY, NORMALIZATION & IDENTITY                                                     |   |
|   |    - Field Normalization (Typed FieldPolicy: Currency/FX, ISO Date, URLs, Names)         |   |
|   |    - Deterministic Validation (Pydantic, range checks, cross-field plausibility)         |   |
|   |    - Entity Resolution (Blocking + RapidFuzz + Qdrant candidates -> auto/review/veto)   |   |
|   +------------------------------------------------------------------------------------------+   |
|                                            | Normalized Claims                                   |
|                                            v                                                     |
|   +------------------------------------------------------------------------------------------+   |
|   | 4. RECONCILIATION & TRUST STATE                                                          |   |
|   |    - Claim Ledger (Append-only persistence of all field assertions)                      |   |
|   |    - Conflict Engine (Material disagreement detection, preservation of competing claims) |   |
|   |    - Trust-State Engine (Assigns VERIFIED / SUPPORTED / SINGLE_SOURCE / CONFLICTING)     |   |
|   |    - Canonical Record Builder (Derives display value while retaining all evidence links) |   |
|   +------------------------------------------------------------------------------------------+   |
|                                            | Canonical Records                                   |
|                                            v                                                     |
|   +------------------------------------------------------------------------------------------+   |
|   | 5. MATERIALIZATION & EXPORT                                                              |   |
|   |    - Materialized Read Model (dataset_version_records denormalized JSONB)                |   |
|   |    - Dataset Versioning & Diff Engine (ADDED, CHANGED, UNCHANGED, MISSING_LATEST)        |   |
|   |    - Export Engine (ZIP bundle: dataset.csv, claims.csv, sources.csv, manifest.json)     |   |
|   +------------------------------------------------------------------------------------------+   |
+--------------------------------------------------------------------------------------------------+
            |                                                      |
            v                                                      v
+-------------------------------+                     +--------------------------------------------+
|     QDRANT VECTOR DATABASE    |                     |       EXTERNAL EXTENSIONS (OPTIONAL)       |
|  - Entity Semantic Embeddings |                     |  - Pathway (Incremental stream feed)       |
|  - Non-authoritative Index    |                     |  - n8n (Completion webhooks / notifications|
+-------------------------------+                     +--------------------------------------------+
```

---

## 2. Detailed Component Inventory

### 1. Frontend
- **Responsibility**: Analytical user workbench providing the 6-stage interaction journey (Ask, Interpret, Trust, Plan, Run, Prove). Renders the dense dataset grid, the interactive ProofCell Evidence Drawer, live SSE run monitor, version diffs, and review queue.
- **Input**: User natural language prompts, UI configuration clicks, API responses, SSE event stream.
- **Output**: JSON payloads to API routes (`/v1/requirements/compile`, `/v1/workflows/{id}/runs`, etc.).
- **Dependencies**: Next.js App Router, React 19, Tailwind CSS, Radix UI Primitives, TanStack Table v9, Phosphor Icons.
- **AI Involved**: No. The frontend is strictly deterministic UI.
- **MUST NOT DO**: Must not make direct LLM or search provider API calls, must not connect directly to PostgreSQL/Supabase service roles, must not use default unstyled shadcn/ui or glowing AI card templates, must not invent fake confidence scores.

### 2. API (FastAPI Core Service)
- **Responsibility**: Stateless HTTP interface exposing typed REST endpoints, request authentication/authorization, schema exchange via OpenAPI, workflow run triggering, dataset querying, ProofCell payload hydration, and SSE streaming.
- **Input**: Client HTTP requests, database records.
- **Output**: Typed JSON responses, `text/event-stream` SSE events.
- **Dependencies**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 Async, psycopg3.
- **AI Involved**: No direct inference; orchestrates calls to the Requirement Compiler and Planner.
- **MUST NOT DO**: Must not run long-running crawling or browser execution inside request handlers, must not hold long-lived in-memory workflow state, must not leak server secrets or raw LLM prompts to the client.

### 3. Requirement Compiler
- **Responsibility**: Interprets the user's free-form business data request into a typed, structured `RequirementSpec` and a proposed set of schema fields.
- **Input**: User natural language prompt string + current system UTC timestamp.
- **Output**: `RequirementSpec` (entity type, goal, geography, filters, date range, fields with `origin='user'|'ai_inferred'`).
- **Dependencies**: `ModelGateway` (structured output capable LLM), Pydantic validator.
- **AI Involved**: **Yes** (LLM semantic parsing).
- **MUST NOT DO**: Must not execute external tools, must not fetch web pages, must not write directly to the database, must not proceed without user confirmation.

### 4. Schema Proposal & Negotiation
- **Responsibility**: Allows the user to inspect, modify, add, rename, or delete fields generated by the compiler before any execution starts. Enforces field provenance tags (`user_specified` vs `ai_inferred`).
- **Input**: Compiled `RequirementSpec`, user modifications.
- **Output**: Persisted `dataset_schemas` record with a deterministic `schema_hash`.
- **Dependencies**: FastAPI router, Pydantic models.
- **AI Involved**: No. Purely deterministic schema validation and state storage.
- **MUST NOT DO**: Must not allow filters to reference non-existent columns; must not discard origin tags.

### 5. Trust Contract Engine
- **Responsibility**: Converts user quality preferences into an immutable technical policy object (`TrustContract`) that governs budget limits, corroboration thresholds, evidence strictness, and conflict rules.
- **Input**: User selection (presets like Balanced/Strict/Exploratory or explicit controls).
- **Output**: Validated `TrustContract` model snapshotted into `workflow_versions`.
- **Dependencies**: Pydantic v2.
- **AI Involved**: No.
- **MUST NOT DO**: Must not allow user UI settings to override hard system safety ceilings (e.g. max page caps).

### 6. Workflow Planner
- **Responsibility**: Generates a declarative execution graph (`PlanDAG`) tailored to the `RequirementSpec` and `TrustContract` using exclusively pre-registered operators.
- **Input**: `RequirementSpec`, `TrustContract`, operator capabilities metadata.
- **Output**: `PlanDAG` containing a list of `PlanNode` definitions, dependency edges, and estimated cost/effort ranges.
- **Dependencies**: `ModelGateway` (LLM structured output).
- **AI Involved**: **Yes** (LLM DAG composition).
- **MUST NOT DO**: Must not invent novel operator names, must not emit executable code (Python/SQL/bash), must not consume raw scraped text, must not emit cyclic dependencies.

### 7. PlanDAG
- **Responsibility**: Immutable declarative specification of the execution plan. Defines nodes, dependencies, operator types, parameters, criticality, and budget allocations.
- **Input**: Planner output.
- **Output**: Validated DAG data structure consumed by the executor.
- **Dependencies**: Pydantic schema.
- **AI Involved**: No (data contract).
- **MUST NOT DO**: Must not contain unbudgeted nodes or dynamic self-modifying nodes.

### 8. Plan Validator
- **Responsibility**: Deterministic gatekeeper that inspects the proposed `PlanDAG` prior to execution. Verifies acyclicity (Kahn's topological sort), operator registry validity, typed I/O edge compatibility, and verifies that estimated pages/calls/costs do not exceed the `TrustContract`.
- **Input**: Raw `PlanDAG`, `TrustContract`.
- **Output**: `ValidatedPlan` or throws `PLAN_BUDGET_EXCEEDED` / `PLAN_INVALID`.
- **Dependencies**: Graph validation algorithms, Operator Registry.
- **AI Involved**: No (strictly deterministic code).
- **MUST NOT DO**: Must not "best-effort execute" an invalid or over-budget plan.

### 9. Workflow Executor
- **Responsibility**: Coordinates workflow lifecycle. Expands `PlanNode` definitions into database `step_runs`, manages step readiness based on upstream dependencies, handles retries, heartbeats, and determines terminal status (`COMPLETED`, `PARTIAL`, `FAILED`).
- **Input**: `ValidatedPlan`, `workflow_runs` row.
- **Output**: State transitions, updated run counters, final run status.
- **Dependencies**: PostgreSQL transactions, Step State Machine.
- **AI Involved**: No.
- **MUST NOT DO**: Must not run steps synchronously in-process; must not fail an entire run if non-critical steps fail.

### 10. Worker (`proofgrid-worker`)
- **Responsibility**: Background process that polls for `READY` steps using PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED`, claims a lease, executes the operator implementation, updates progress heartbeats, and commits results.
- **Input**: Leased `step_runs` row and input artifacts.
- **Output**: Persisted step outputs, claims, documents, and `run_events`.
- **Dependencies**: Python asyncio runtime, DB connection pool, Operator implementations.
- **AI Involved**: No (worker itself is deterministic; invokes LLM adapters only when executing `EXTRACT`).
- **MUST NOT DO**: Must not hold in-memory-only state that cannot survive process restart; must not serve client web requests.

### 11. Source Discovery
- **Responsibility**: Finds candidate URLs matching the requirement without scraping page contents.
- **Input**: Query template from `RequirementSpec`.
- **Output**: List of `CandidateSource` objects (URL, title, snippet, discovery metadata).
- **Dependencies**: `SearchProvider` interface (`Brave`, `Tavily`, `Exa`, or pre-seeded fixture adapter).
- **AI Involved**: No (calls search APIs or fixture data).
- **MUST NOT DO**: Must not treat search engine snippets as verified evidence claims.

### 12. Safe Acquisition Layer
- **Responsibility**: Enforces security, policy, and network boundaries before any external network connection is established.
- **Input**: Candidate URL from discovery.
- **Output**: `SourcePolicyDecision` (allowed/blocked, reason code, rate limit token).
- **Dependencies**: SSRF validator (IP resolution, private range filter), robots.txt parser, per-domain concurrency semaphores.
- **AI Involved**: No.
- **MUST NOT DO**: Must not allow requests to loopback (`127.0.0.1`), private RFC1918, link-local, or cloud metadata endpoints (`169.254.169.254`). Must not bypass robots.txt, CAPTCHAs, or paywalls.

### 13. HTTP Collector
- **Responsibility**: Primary, low-cost static page acquisition. Performs async streaming HTTP requests, validates redirect targets, enforces byte limits, and captures raw HTML/JSON.
- **Input**: Validated HTTP/HTTPS URL.
- **Output**: Raw document payload, HTTP status, headers, retrieved timestamp.
- **Dependencies**: `httpx` async client.
- **AI Involved**: No.
- **MUST NOT DO**: Must not follow uncontrolled redirect chains (>5); must not read bodies larger than configured max bytes (5MB default).

### 14. Playwright Browser Fallback
- **Responsibility**: Isolated, rendered browser execution used strictly as a non-critical fallback for approved JS-heavy sites where static HTTP fails.
- **Input**: Approved URL, execution script.
- **Output**: Rendered DOM HTML snapshot.
- **Dependencies**: Playwright (headless Chromium).
- **AI Involved**: No.
- **MUST NOT DO**: Must not be used as an open-ended autonomous agent; must not persist cookies/sessions; must not download files or execute unknown external scripts.

### 15. Raw Document Store
- **Responsibility**: Immutable, content-addressed storage of retrieved raw artifacts and cleaned text representations.
- **Input**: Acquired document bytes.
- **Output**: `RawDocument` record in PostgreSQL with SHA-256 hashes and object storage URIs.
- **Dependencies**: Supabase Storage / S3-compatible bucket, PostgreSQL.
- **AI Involved**: No.
- **MUST NOT DO**: Must not store large raw HTML/PDF blobs in PostgreSQL relational table rows.

### 16. Structured Extraction
- **Responsibility**: Extracts candidate fields from source documents using a fallback ladder: (1) Structured data/JSON-LD, (2) Deterministic CSS/XPath selectors, (3) Regex/heuristics, (4) LLM structured output.
- **Input**: Cleaned document text / DOM + `DatasetSchema`.
- **Output**: List of `ClaimDraft` objects (field key, raw value, candidate evidence quote).
- **Dependencies**: `Trafilatura`, `BeautifulSoup`, `ModelGateway`.
- **AI Involved**: **Yes**, only at ladder level 4 (LLM extraction).
- **MUST NOT DO**: Must not give LLM extraction tools to write to DB, access web, or call APIs; must not treat LLM output as fact without verification.

### 17. Evidence Anchor Verification
- **Responsibility**: Technical invariant verifier. Deterministically validates that a claim's evidence anchor can be resolved against the stored `RawDocument` representation across all supported anchor types:
  - `TEXT_SPAN`: Verifies that the exact quoted span is present in document text.
  - `NORMALIZED_TEXT_SPAN`: Verifies that the quoted span is present after the documented normalization procedure (whitespace folding, Unicode normalization).
  - `JSON_POINTER`: Resolves the JSON pointer path in structured JSON payloads and validates against the stored raw value.
  - `DOM_SELECTOR / DOM_PATH`: Validates a stable element locator plus supporting text in the stored DOM snapshot.
  - `STRUCTURED_FIELD`: Compares canonical keys/paths against structured tables or feeds.
  - `API_RESPONSE_POINTER`: Resolves field path in recorded API response payloads.
- **Input**: Proposed anchor payload (quote, pointer, selector, or path) and stored `RawDocument` representation (text, JSON, or DOM).
- **Output**: `EvidenceAnchor` object containing anchor type, status (`VERIFIED` vs `UNRESOLVED/UNANCHORED`), resolution metadata (offsets, pointer, selector), and matching confidence flag.
- **Dependencies**: Deterministic text normalization, JSON pointer evaluation, DOM selector parser.
- **AI Involved**: No. Strictly deterministic code.
- **MUST NOT DO**: Must not accept quotes or pointers that fail deterministic resolution against the stored document; must not allow claims with unverified anchors to qualify for strong trust (`VERIFIED` or `SUPPORTED`).

### 18. Normalization
- **Responsibility**: Transforms raw strings into standardized typed representations according to a `FieldPolicy` registry (Money with ISO currency and Decimal amount, ISO 8601 dates, canonical URLs, standardized company names). Retains the raw value alongside the normalized value.
- **Input**: `ClaimDraft` raw values.
- **Output**: Normalized typed claim values.
- **Dependencies**: `FieldPolicy` registry, `Frankfurter` FX provider (cached).
- **AI Involved**: No.
- **MUST NOT DO**: Must not discard raw strings; must not use floating-point numbers for money; must not guess dates without context.

### 19. Validation
- **Responsibility**: Deterministic schema, domain, and cross-field validation. Checks type adherence, value ranges, and relational sanity (e.g. funding date <= article publication date).
- **Input**: Normalized claims.
- **Output**: Validated claims with attached `validation_flags`.
- **Dependencies**: Pydantic v2.
- **AI Involved**: No.
- **MUST NOT DO**: Must not silently drop invalid claims (they must be flagged and stored for audit).

### 20. Entity Resolution & Deduplication
- **Responsibility**: Determines whether records from different sources refer to the same real-world entity. Uses blocking (country + name prefix), lexical similarity (`RapidFuzz`), semantic candidate retrieval (`Qdrant`), and hard-contradiction vetoes.
- **Input**: Validated claims across sources.
- **Output**: `EntityMatch` decisions (`AUTO_MERGE`, `REVIEW`, `KEEP_SEPARATE`) and stable `entity_id` assignments.
- **Dependencies**: `RapidFuzz`, `Qdrant` (candidate generator only), PostgreSQL `pg_trgm`.
- **AI Involved**: No decision AI. Uses vector embeddings for candidate indexing only; merge logic is deterministic code.
- **MUST NOT DO**: Must not merge entities when hard identifiers contradict; must not delete historical entity IDs on merge (creates merge pointer).

### 21. Claim Ledger
- **Responsibility**: Append-only relational repository storing every assertion made by every source about every field.
- **Input**: Validated, anchored, normalized claims.
- **Output**: Immutable `claims` rows.
- **Dependencies**: PostgreSQL `claims` table.
- **AI Involved**: No.
- **MUST NOT DO**: Must not update or overwrite existing claims when a new source arrives.

### 22. Conflict Engine
- **Responsibility**: Identifies material disagreements among valid claims for the same entity and field after normalization. Groups agreeing claims into source independence clusters and flags unresolved disputes.
- **Input**: Set of claims for an entity field.
- **Output**: Grouped claims, conflict status (`CONFLICTING` vs clean), `conflicts` records.
- **Dependencies**: Materiality comparator rules in `FieldPolicy`.
- **AI Involved**: No.
- **MUST NOT DO**: Must not treat trivial formatting or punctuation differences as material conflicts; must never delete losing claims to "clean up" the table.

### 23. Trust-State Engine
- **Responsibility**: Computes categorical trust status for each field based on verifiable facts (anchor verified, independent source count, first-party match, absence of unresolved conflict).
- **Input**: Claim groups, `TrustContract` rules.
- **Output**: Categorical status: `VERIFIED`, `SUPPORTED`, `SINGLE_SOURCE`, `CONFLICTING`, `NEEDS_REVIEW`, `MISSING`.
- **Dependencies**: Deterministic status derivation rules.
- **AI Involved**: No.
- **MUST NOT DO**: Must not generate uncalibrated numeric probabilities (e.g. "93% confidence").

### 24. Canonical Record Builder
- **Responsibility**: Selects the canonical display value for each entity field according to Trust Contract policy, while linking to all supporting and conflicting claim IDs.
- **Input**: Resolved claims, trust states, entity metadata.
- **Output**: `canonical_values` rows.
- **Dependencies**: PostgreSQL.
- **AI Involved**: No.
- **MUST NOT DO**: Must not sever links to underlying evidence claims.

### 25. Materialized Dataset Read Model
- **Responsibility**: Stores a pre-pivoted, denormalized JSONB representation of the dataset for a specific version (`dataset_version_records`), enabling sub-300ms table queries, pagination, filtering, and sorting.
- **Input**: Canonical values and trust states for a finalized version.
- **Output**: Queryable rows in `dataset_version_records`.
- **Dependencies**: PostgreSQL, GIN indexes.
- **AI Involved**: No.
- **MUST NOT DO**: Must not replace the authoritative write tables; must be completely rebuildable from `claims` and `canonical_values`.

### 26. Dataset Versioning & Diff Engine
- **Responsibility**: Freezes a run's output into an immutable `DatasetVersion` and computes differential comparisons against prior runs.
- **Input**: Two `DatasetVersion` IDs.
- **Output**: Version diff classification (`ADDED`, `CHANGED`, `UNCHANGED`, `MISSING_LATEST`, `EVIDENCE_CHANGED`, `CONFLICT_CHANGED`).
- **Dependencies**: SHA-256 row and claim-set hashing.
- **AI Involved**: No.
- **MUST NOT DO**: Must not interpret `MISSING_LATEST` as an assertion that the entity no longer exists in reality.

### 27. PostgreSQL (Supabase)
- **Responsibility**: Authoritative single source of truth for the entire platform. Manages ACID transactions, durable step queue (`SKIP LOCKED`), relational provenance graph, and denormalized read model.
- **Input**: Relational queries, transactional commands.
- **Output**: Stored persistent data.
- **Dependencies**: Supabase-managed PostgreSQL 15+.
- **AI Involved**: No.
- **MUST NOT DO**: Must not be bypassed by secondary indexes.

### 28. Object Storage (Supabase Storage / S3)
- **Responsibility**: Persistent store for large immutable files (raw HTML, text representations, generated export ZIP archives).
- **Input**: Byte streams, content hashes.
- **Output**: Storage URIs, retrieved bytes.
- **Dependencies**: Supabase Storage API / S3 API.
- **AI Involved**: No.
- **MUST NOT DO**: Must not store public unauthenticated sensitive data.

### 29. Qdrant (Secondary Vector Index)
- **Responsibility**: Accelerates semantic similarity search across entities and generates candidate matches for entity resolution.
- **Input**: Entity name + description embedding vectors and metadata payload.
- **Output**: Top-k matching entity IDs.
- **Dependencies**: Qdrant Cloud or local instance.
- **AI Involved**: Consumes model embeddings; vector distance search.
- **MUST NOT DO**: Must not become an authoritative store for provenance or workflow state; failure must not prevent PostgreSQL dataset finalization.

### 30. SSE Event Stream
- **Responsibility**: Unidirectional real-time progress broadcast from worker to browser. Replays missed events from `run_events` table on client reconnect using `Last-Event-ID`.
- **Input**: `run_events` rows inserted by workers.
- **Output**: Server-Sent Events HTTP stream (`text/event-stream`).
- **Dependencies**: FastAPI SSE response, `run_events` table.
- **AI Involved**: No.
- **MUST NOT DO**: Must not use complex bi-directional WebSockets when one-way streaming is sufficient.

### 31. Export Engine
- **Responsibility**: Generates standalone, self-contained evidence bundles for external consumption.
- **Input**: `DatasetVersion` ID.
- **Output**: ZIP archive containing `dataset.csv`, `claims.csv`, `sources.csv`, `conflicts.csv`, and `manifest.json`.
- **Dependencies**: Python `zipfile`, `csv` libraries, Object Storage.
- **AI Involved**: No.
- **MUST NOT DO**: Must not export a bare CSV without evidence references.

### 32. Optional Pathway Integration (Extension)
- **Responsibility**: Optional streaming engine that listens to live sources and emits changed observations into the same ingestion contract.
- **Input**: Live stream data.
- **Output**: Standardized `RawDocument` / observation events.
- **Dependencies**: Pathway framework.
- **AI Involved**: No.
- **MUST NOT DO**: Must not be a blocking dependency for the core one-shot hackathon workflow; must not bypass the Trust Contract or Claim Ledger.

### 33. Optional n8n Integration (Extension)
- **Responsibility**: External workflow automation trigger. Receives signed webhooks upon run completion or material diff to update Google Sheets, Slack, or CRM systems.
- **Input**: ProofGrid signed webhook payload (`dataset.version.material_change`).
- **Output**: Downstream SaaS actions.
- **Dependencies**: n8n instance / webhook URL.
- **AI Involved**: No.
- **MUST NOT DO**: Must not run inside the core execution loop; failure of n8n must not fail the ProofGrid workflow run.
