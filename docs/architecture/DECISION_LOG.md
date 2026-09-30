# ProofGrid: Architecture Decision Log (ADR)

> **Architectural Decision Records**: Captures all foundational architectural, technical, data model, and security decisions established across the ProofGrid Product Requirements Document (PRD), Technical Requirements Document (TRD), and Backend Engineering Specification.

---

### ADR-001: Modular Monolith and Separate Worker Process for MVP
- **Decision**: Build ProofGrid as a single backend Python codebase producing two runnable processes: a stateless FastAPI web API and an asynchronous background worker (`proofgrid-worker`).
- **Reason**: Avoids distributed microservice overhead, cross-service networking latency, and complex deployment topologies during a hackathon, while cleanly separating interactive request latency (<300ms) from long-running crawling and extraction tasks.
- **Alternatives considered**:
  - *Full microservices architecture* (crawler service, extraction service, dedup service): Rejected due to high operational complexity and coordination overhead.
  - *Single monolithic process running background threads*: Rejected because heavy CPU parsing and browser rendering could block the async event loop and degrade interactive API responsiveness.
- **Consequences**: Fast local development, shared domain models between API and worker, straightforward containerized deployment (e.g. Railway/Render/Docker).
- **Status**: **Accepted**.

---

### ADR-002: PostgreSQL as the Single Authoritative Source of Truth
- **Decision**: Use Supabase PostgreSQL as the sole system of record for all requirements, workflows, runs, steps, raw documents, evidence anchors, entities, claims, conflicts, and dataset versions.
- **Reason**: The core value proposition of ProofGrid is a relational graph of provenance, claims, and versioned datasets. Relational databases provide ACID transaction guarantees, complex multi-table joins, and reliable audit integrity that document or graph databases cannot match.
- **Alternatives considered**:
  - *MongoDB / Document Store*: Rejected because unstructured document updates encourage overwriting historical evidence and lack strong transactional constraints.
  - *Graph Database (Neo4j)*: Rejected as architectural novelty; relational tables with foreign keys model provenance graphs effectively without specialized query infrastructure.
- **Consequences**: High data consistency, straightforward migrations via Alembic, relational guarantees for the Claim Ledger.
- **Status**: **Accepted**.

---

### ADR-003: LLM Planner with Deterministic Code Executor
- **Decision**: Constrain the LLM to semantic planning (interpreting natural language and composing declarative DAGs from a fixed operator vocabulary) and bounded extraction. Deterministic software owns all execution, scheduling, retries, budgeting, and database persistence.
- **Reason**: Unconstrained autonomous agent loops are non-deterministic, prone to runaway token/page costs, difficult to debug, and fragile. Separating semantic intent from deterministic execution ensures inspectability and repeatability.
- **Alternatives considered**:
  - *Autonomous Multi-Agent Swarm (e.g. CrewAI / AutoGen)*: Rejected because autonomous agents make unpredictable tool calls, loop infinitely on errors, and fail to provide deterministic audit trails.
  - *Hardcoded Pipeline without LLM Planning*: Rejected because it eliminates the user promise of compiling dynamic natural-language questions into novel datasets.
- **Consequences**: Plans can be validated before any expensive execution begins; budgets are strictly enforced by software.
- **Status**: **Accepted**.

---

### ADR-004: Typed RequirementSpec with Human-in-the-Loop Checkpoint
- **Decision**: Natural-language prompts are compiled into a strongly typed `RequirementSpec` (entity type, fields, filters, date bounds). Users must inspect and confirm the schema before any data collection begins.
- **Reason**: Prevents ambiguous or incorrect AI assumptions from wasting crawl budgets or generating unwanted datasets. AI-inferred fields are explicitly distinguished from user-specified fields.
- **Alternatives considered**:
  - *Immediate Black-Box Execution*: Prompt immediately triggers scraping. Rejected because users lose control over what data is collected and cannot enforce field requirements.
- **Consequences**: Introduces an explicit "Interpret & Schema Negotiation" stage in the UI, enhancing perceived intelligence and user control.
- **Status**: **Accepted**.

---

### ADR-005: Claim Ledger Separate from Materialized Dataset Read Model (CQRS-Lite)
- **Decision**: Store all raw source assertions in an append-only `claims` table. Separately materialize a denormalized JSONB read model (`dataset_version_records`) upon workflow finalization.
- **Reason**: Traditional scrapers overwrite values when a new source arrives, destroying provenance and concealing disagreement. ProofGrid's Claim Ledger preserves all claims forever, while the materialized read model ensures table pagination and filtering remain sub-300ms.
- **Alternatives considered**:
  - *Single Normalized Table*: Joining `entities`, `canonical_values`, `claims`, and `sources` on every table render creates massive query latency on large datasets.
  - *Raw JSON-only Storage*: Storing claims directly inside entity JSON blobs prevents cross-source SQL analysis and conflict indexing.
- **Consequences**: Canonical values can change across versions without altering source claims; reads are decoupled from write-side provenance tracking.
- **Status**: **Accepted**.

---

### ADR-006: Field-Level Provenance and ProofCell UI
- **Decision**: Provenance is tracked and displayed at the individual field level rather than at the row or document level. Every evidence-backed cell renders as a `ProofCell` linking to underlying claims.
- **Reason**: In business data intelligence, different fields in a single company row often originate from completely different sources (e.g. website from Company Registry, funding amount from TechCrunch, investors from a venture press release). Row-level provenance fails to reflect reality.
- **Alternatives considered**:
  - *Row-Level Source Links*: Displaying 3-4 links per row. Rejected because it forces the user to manually read all sources to find which link supported which number.
- **Consequences**: Requires fine-grained claim schemas; enables the killer demo feature (clicking a cell opens the exact highlighted excerpt in the Evidence Drawer).
- **Status**: **Accepted**.

---

### ADR-007: Deterministic Evidence Anchor Verification
- **Decision**: An extracted claim cannot contribute to a strong trust tier (`VERIFIED` or `SUPPORTED`) unless its evidence anchor can be deterministically resolved against the stored `RawDocument` representation across supported anchor types:
  - `TEXT_SPAN` / `NORMALIZED_TEXT_SPAN`: Quoted text must be present after the documented normalization procedure.
  - `JSON_POINTER` / `API_RESPONSE_POINTER`: JSON pointer / field path must resolve in the structured payload and match the raw value.
  - `DOM_SELECTOR / DOM_PATH`: Stable element locator plus supporting text must validate against the stored DOM snapshot.
  - `STRUCTURED_FIELD`: Canonical key/path must compare accurately against structured tables or feeds.
- **Reason**: LLMs frequently hallucinate plausible-looking quotes or fabricate figures. Code—not the LLM—must verify that the source document actually contained the supporting material, whether textual, structured, or DOM-based.
- **Alternatives considered**:
  - *Trusting LLM-Extracted Quotes Directly*: Storing whatever quote the LLM returns. Rejected because models hallucinate non-existent evidence passages.
  - *Text-Only String Matching*: Restricting anchors to verbatim raw text strings. Rejected because modern web and API sources require structured JSON pointers and DOM element locators.
  - *Embedding Cosine Similarity*: Measuring vector distance between quote and document. Rejected because it permits semantic drift without guaranteeing literal presence.
- **Consequences**: 100% elimination of hallucinated evidence in verified records; robust support for both unstructured web prose and structured APIs; provides exact character offsets or paths for ProofCell UI highlighting.
- **Status**: **Accepted**.

---

### ADR-008: Deterministic-First Extraction Ladder
- **Decision**: Data extraction follows an explicit priority ladder: (1) Structured data (JSON-LD / microdata), (2) Tested CSS/XPath selectors, (3) Regex/heuristics, (4) Schema-constrained LLM fallback over cleaned text.
- **Reason**: Calling an LLM on every raw HTML page is slow, expensive, and unnecessary when pages provide structured schema.org markup or consistent selector patterns.
- **Alternatives considered**:
  - *LLM-Only Extraction*: Sending every page directly to an LLM. Rejected due to runaway token costs and rate-limit bottlenecks.
  - *Pure Selector Scraping*: Hand-crafting selectors for every website. Rejected because it breaks when encountering novel domains.
- **Consequences**: Drastically reduces LLM API spend, speeds up pipeline execution, and reserves AI for unstructured prose.
- **Status**: **Accepted**.

---

### ADR-009: Playwright as Isolated Browser Fallback (Never Primary Control Plane)
- **Decision**: Static HTTP (`httpx` + `Trafilatura`) is the primary acquisition path. Headless Chromium (`Playwright`) is strictly a fallback for approved, JavaScript-rendered sites where static fetch yields no content.
- **Reason**: Headless browsers consume significant CPU/RAM, suffer from high latency (3–10s per page), and introduce flakiness. Static HTTP fetch is 10x faster and 100x cheaper.
- **Alternatives considered**:
  - *Browser-First Crawling*: Rendering every URL in Playwright. Rejected because it would crash lightweight worker containers and blow through the 90-second demo window.
- **Consequences**: The golden demo path runs reliably over static HTTP; Playwright is isolated in the worker process and invoked only when allowlisted.
- **Status**: **Accepted**.

---

### ADR-010: No General Autonomous Browser Agent in the Golden Path
- **Decision**: ProofGrid will not feature an autonomous browser agent clicking random UI elements, solving CAPTCHAs, or guessing navigation paths across unknown websites.
- **Reason**: Autonomous browser agents are notoriously unreliable in live demonstrations, frequently triggering bot detection, getting stuck on cookie banners, or blowing budgets.
- **Alternatives considered**:
  - *Autonomous Agentic Scraping (e.g. Browser-Use / Stagehand)*: Rejected for the core pipeline due to unpredictability and high failure rates on stage.
- **Consequences**: Bulletproof demo repeatability; clear alignment with ethical crawling policies and robots.txt.
- **Status**: **Accepted**.

---

### ADR-011: Qdrant as a Secondary Semantic Index Only
- **Decision**: Qdrant is utilized strictly for auxiliary capabilities: vector semantic search across entities and semantic candidate generation for entity resolution. PostgreSQL remains authoritative for all metadata and provenance.
- **Reason**: Vector databases lack ACID transactions, complex relational integrity, and durable workflow state management. If Qdrant experiences downtime, the core platform must continue operating seamlessly.
- **Alternatives considered**:
  - *Vector-First Database Architecture*: Storing datasets and claims inside vector payloads. Rejected because vector payload updates are eventually consistent and lack relational foreign-key safety.
  - *pgvector inside PostgreSQL*: Considered as an alternative. Qdrant is selected to fulfill sponsor integration while keeping it cleanly decoupled.
- **Consequences**: Graceful degradation: If Qdrant is unavailable, workflows complete with `index_status=PENDING` and PostgreSQL datasets remain 100% functional.
- **Status**: **Accepted**.

---

### ADR-012: PostgreSQL-Backed Queue with `SKIP LOCKED` for MVP
- **Decision**: Use a PostgreSQL `step_runs` table with `SELECT ... FOR UPDATE SKIP LOCKED` and step leases as the background task queue, rather than deploying Redis and Celery.
- **Reason**: Workflow state is already persisted in PostgreSQL. Using `SKIP LOCKED` eliminates the operational overhead of managing Redis/RabbitMQ clusters, provides ACID transactional status updates, and handles multiple concurrent workers safely.
- **Alternatives considered**:
  - *Celery + Redis*: Standard Python stack, but introduces a second stateful service that can get out of sync with PostgreSQL during transaction rollbacks.
  - *Temporal*: Excellent durable execution engine, but excessively complex for a hackathon prototype build.
- **Consequences**: Zero additional infrastructure dependencies; trivial deployment; easy future migration to Temporal if enterprise scale warrants it.
- **Status**: **Accepted**.

---

### ADR-013: Categorical Trust States Instead of Fake Confidence Probabilities
- **Decision**: Expose deterministic categorical trust states (`VERIFIED`, `SUPPORTED`, `SINGLE_SOURCE`, `CONFLICTING`, `NEEDS_REVIEW`, `MISSING`) derived from observable evidence signals, rather than uncalibrated percentage scores (e.g. "93% confident").
- **Reason**: Without a large labeled calibration corpus, machine learning confidence scores are fabricated numbers that erode trust with technical evaluators. Categorical states explain *why* data is trusted based on concrete rules.
- **Alternatives considered**:
  - *LLM Self-Assessed Confidence*: Asking the model "How confident are you from 0 to 100?". Rejected because LLMs are notoriously overconfident and uncalibrated.
- **Consequences**: Honest, inspectable trust signals; clear visual grammar in the ProofGrid table.
- **Status**: **Accepted**.

---

### ADR-014: Transactional Outbox for External Side Effects
- **Decision**: Asynchronous external side-effects (indexing entities into Qdrant, dispatching n8n webhooks) are written to an `outbox_events` table inside the same transaction that finalizes the dataset, then dispatched asynchronously.
- **Reason**: Direct network calls to secondary services during a database transaction risk split-brain inconsistency if the external service fails or the transaction rolls back.
- **Alternatives considered**:
  - *Direct Synchronous Calls*: Calling Qdrant upsert inside the finalization handler. Rejected because Qdrant failure would crash the database commit.
- **Consequences**: Guarantees at-least-once delivery; makes worker retries idempotent; protects PostgreSQL as the sole system of record.
- **Status**: **Accepted**.

---

### ADR-015: Pathway and n8n as Optional External Extensions
- **Decision**: Pathway (incremental live refresh) and n8n (downstream workflow automation) are treated as strictly optional edge integrations. The core platform must function completely without them.
- **Reason**: Integrating sponsor tools into the synchronous golden path creates fragile single points of failure. Decoupling them preserves core stability while enabling high-impact live demos if time permits.
- **Alternatives considered**:
  - *Pathway as Core Execution Engine*: Rejected because batch workflow compilation and claim-level provenance require standard relational transactions.
- **Consequences**: Zero risk to the main pitch; high upside if bonus integrations are demonstrated.
- **Status**: **Accepted**.

---

### ADR-016: Honest Fixture Mode as Transparent Demo Resilience Fallback
- **Decision**: Provide an `ACQUISITION_MODE=FIXTURE` configuration that replays pre-cached raw documents through the entire downstream extraction, anchor verification, normalization, deduplication, conflict detection, and materialization pipeline.
- **Reason**: Live venue WiFi during hackathon presentations is notoriously volatile. Mocking the final dataset is dishonest; replaying real raw documents through live downstream processing is reliable and honest.
- **Alternatives considered**:
  - *Static JSON Mocking*: Returning pre-baked database rows. Rejected as fragile and transparently fake.
  - *Pure Live Scraping with No Fallback*: High risk of presentation failure due to network throttling or target site rate limits.
- **Consequences**: Zero-risk stage presentation; the UI transparently displays `"Cached Fixture Evidence"`, demonstrating engineering maturity.
- **Status**: **Accepted**.

---

### ADR-017: Backend Module Resolution for Standalone Worker Execution
- **Decision**: Embed deterministic `sys.path` backend root resolution at the head of `backend/worker/main.py`.
- **Reason**: When running worker scripts directly via `python worker/main.py`, Python sets `sys.path[0]` to `backend/worker/`, causing imports from `app.*` to fail unless manually prefixed with `PYTHONPATH=.`. Auto-resolving the backend directory guarantees consistent execution across CLI, Makefile targets, and systemd/container entrypoints.
- **Alternatives considered**:
  - *Require `PYTHONPATH=.` in all invocation commands*: Fragile for developers and CI environments.
  - *Require `python -m worker.main` exclusively*: Good, but standard script execution `python worker/main.py` should also work out of the box.
- **Consequences**: Boring, reliable worker startup from any shell context.
- **Status**: **Accepted**.

---

### ADR-018: Explicit Build Script Approval in pnpm v11+
- **Decision**: Explicitly approve required native tool build scripts (`esbuild`, `sharp`, `unrs-resolver`) via pnpm configuration.
- **Reason**: pnpm v11+ disables arbitrary postinstall execution by default to prevent supply-chain attacks. Approving only the explicit build tools required for Next.js and SWC maintains security without breaking production compilation.
- **Alternatives considered**:
  - *Disable all security controls*: High supply-chain vulnerability risk.
- **Consequences**: Deterministic, secure CI and local builds.
- **Status**: **Accepted**.

---

### ADR-019: Neon PostgreSQL as Persistence Provider with Dual-Connection Architecture
- **Decision**: Adopt Neon PostgreSQL as the primary managed persistence provider for the ProofGrid prototype, replacing Supabase PostgreSQL, while maintaining a strict dual-connection architecture:
  1. `DATABASE_URL`: Neon pooled runtime connection (PgBouncer in transaction mode) for FastAPI application queries and worker operations.
  2. `DATABASE_DIRECT_URL`: Neon direct/unpooled connection for Alembic migrations, DDL statements, and administrative schema operations (with `DATABASE_URL_UNPOOLED` supported as a secondary alias).
- **Reason**:
  - ProofGrid requires standard, robust PostgreSQL with ACID transactions, JSONB, and standard client library support.
  - Neon provides instantaneous database branching, managed serverless compute, and explicit separation between pooled transaction endpoints and direct administrative endpoints.
  - ProofGrid does not rely on Supabase-specific proprietary features (Supabase Realtime, Edge Functions, or auto-generated PostgREST APIs), as progress reporting uses custom Server-Sent Events (SSE) from FastAPI and domain models are governed directly by Pydantic and SQLAlchemy.
  - Low vendor coupling: The application layer targets standard PostgreSQL through SQLAlchemy 2.0 and `psycopg` 3 without proprietary SDK dependencies.
  - Object storage and authentication configurations are intentionally deferred and decoupled from the database provider.
- **Alternatives considered**:
  - *Supabase PostgreSQL*: Feature-rich but bundles unneeded proprietary layers (Realtime, PostgREST) and lacks native database branching for lightweight migration preview environments.
  - *Local PostgreSQL Docker exclusively*: Useful for offline development, but Neon provides hosted development parity for team collaboration.
- **Consequences**:
  - Runtime code must honor transaction-pooling constraints (e.g. no session-level advisory variables or persistent `SET search_path` across transactions).
  - Migrations must strictly execute over `DATABASE_DIRECT_URL` to avoid PgBouncer DDL limitations.
- **Status**: **Accepted**.

---

### ADR-020: Adopt Google Gemini Developer API for Live Requirement Compiler Structured Generation
- **Decision**: Adopt the Google Gemini Developer API via the official `google-genai` Python SDK as the primary live `StructuredGenerationProvider` implementation for the ProofGrid Requirement Compiler, with `gemini-3.8-flash` as the initial configuration-driven model.
- **Reason**:
  - High performance and cost-efficiency for structured JSON synthesis with strict schema adherence.
  - Native support for schema-enforced structured outputs (`response_mime_type="application/json"`).
  - Low latency for interactive requirement negotiation (<2s typical response time).
  - Clean asynchronous SDK lifecycle (`client.aio`) without requiring third-party wrappers or thread executors.
- **Alternatives considered**:
  - *OpenAI Structured Outputs (GPT-4o)*: Excellent structured output support, but requires higher per-token costs for high-iteration interactive sessions.
  - *Anthropic Claude 3.5 Sonnet*: Strong reasoning, but native JSON schema enforcement requires tool use / function calling mechanisms rather than native constrained decoding.
  - *Local LLMs (Ollama / vLLM)*: Zero cloud dependency, but imposes severe local hardware requirements (Apple Silicon / NVIDIA GPU) that impair team portability.
- **Consequences**:
  - `FixtureProvider` remains the canonical, default offline provider for unit tests, CI pipelines, and environments without an API key.
  - The Requirement Compiler application layer remains strictly vendor-independent, interacting only through the `StructuredGenerationProvider` protocol.
  - Schema compatibility: Gemini Developer API structured output requires a local schema transformation to remove unsupported keywords (`additionalProperties`, `title`, `$schema`) while preserving all required properties, types, and enums.
  - ProofGrid deterministic validation remains the final, authoritative gate; model outputs are never trusted without independent Pydantic and domain validation.
  - Strict tool isolation: Zero external tools, zero Google Search grounding, and zero code execution are permitted during requirement compilation.
  - The model name is strictly configuration-driven (`GEMINI_MODEL`, defaulting to `gemini-3.8-flash`) and replaceable without modifying compiler code.
  - Additional providers (e.g. OpenAI, Anthropic) can be added in future phases without altering domain or compiler contracts.
- **Privacy & Compliance Note**:
  - Gemini Developer API data handling is suitable for non-sensitive hackathon development prompts, but private or enterprise production workloads require a deliberate provider/privacy review before deployment.
- **Status**: **Accepted** (Live operational testing experienced upstream HTTP 503 capacity errors; preserved alongside alternate live providers).

---

### ADR-021: Groq Cloud Provider Integration for Structured Generation (openai/gpt-oss-120b)
- **Decision**: Add Groq Cloud (`groq>=1.7.0,<2.0.0`) via `AsyncGroq` as an explicit, production-grade implementation of `StructuredGenerationProvider`, using `openai/gpt-oss-120b` with mandatory `strict: True` JSON Schema constrained decoding. Provider selection is explicit (`AI_PROVIDER=groq`), with zero automatic runtime fallback.
- **Reason**:
  - Live Gemini acceptance was temporarily blocked by repeated upstream capacity constraints (HTTP 503 `UNAVAILABLE`).
  - Groq Cloud delivers ultra-fast token generation (~2-3s wall-clock latency) and native strict JSON Schema constrained decoding.
  - Maintains strict vendor independence: `GroqProvider` implements the identical `StructuredGenerationProvider` contract as `FixtureProvider` and `GeminiProvider`.
  - Offline isolation is preserved: `AI_PROVIDER=fixture` remains the default committed configuration; all CI test suites make zero network calls.
- **Alternatives considered**:
  - *Runtime automatic fallback (Gemini -> Groq)*: Rejected. Fallback chains introduce nondeterministic behavior and hide billing/capacity failures across providers.
  - *OpenAI SDK with custom base_url*: Rejected. Official `groq` SDK is preferred for clean error handling, bounded async lifecycle, and accurate usage metrics.
- **Consequences**:
  - `transform_schema_for_groq_strict` applies a Groq-local JSON Schema adaptation (enforces `additionalProperties: false`, lists all properties in `required`, strips unsupported regex lookarounds, and explicitly types untyped leaf nodes).
  - Pydantic models in ProofGrid are NOT duplicated or weakened.
  - Architecture remains: Groq strict decoding -> Pydantic validation -> ProofGrid deterministic validation.
  - Zero tools, zero PlanDAG, zero acquisition execution.
- **Status**: **Accepted**.

### ADR-022: Durable bounded execution and reproducible evidence snapshots
- **Decision**: Keep FastAPI plus a separate worker and use PostgreSQL row locks (`SKIP LOCKED`), attempt-fenced leases, atomic operator writes and a transactional outbox. Lock runs before steps everywhere. No distributed broker was introduced.
- **Reason**: Three concurrent demo runs do not justify additional coordination infrastructure. Retries must not duplicate facts or allow expired workers to publish results.
- **Consequences**: The queue serializes short state changes per run, while acquisition remains outside transactions. Schema/trust/plan snapshots and run idempotency keys are durable. Dataset version allocation is protected by transaction-scoped advisory locks. Claims reject UPDATE/DELETE in the database. Review selections apply to later snapshots; historical displayed values stay unchanged.
- **Status**: Accepted; database concurrency/recovery and fixture E2E verified.

### ADR-023: Honest fixture provenance and constrained live acquisition
- **Decision**: Ship two raw-source fixture sets: explicitly synthetic conflict scenarios and actual captured historical public company announcements. Both traverse the same worker, extraction, verification, normalization, identity, trust and materialization stages.
- **Reason**: A reliable conflict demo must not misrepresent fabricated assertions as live facts. A publication timestamp must not silently become a funding date.
- **Consequences**: Every raw observation records acquisition method, capture time and hash. Runtime HTTP validates DNS, pins public IPs, preserves TLS SNI, checks every redirect and robots policy, and bounds response size/time. Browser collection and optional cloud projections remain disabled extensions. Gemini uses `response_json_schema` to avoid SDK conversion errors for boolean constants; local Pydantic/domain validation remains authoritative.
- **Status**: Accepted; two public captures and offline captured extraction verified. Groq live smoke passed; Gemini live acceptance remains affected by upstream HTTP 503.
