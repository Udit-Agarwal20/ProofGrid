# ProofGrid: Project Context & Implementation Foundation

> **Source-of-Truth Synthesis**: Built directly from the official Code Cubicle 6.0 Problem Statement (PS 01), Product Requirements Document (PRD v1.0), Technical Requirements Document (TRD v1.0), Frontend UX/UI Design Specification (v1.0), and Backend Engineering Specification (v1.0).

---

## 1. Product Purpose
**ProofGrid** is an evidence-first, AI-assisted data intelligence platform. It converts a natural-language business data requirement into a structured, source-backed, traceable, and living dataset where every important field can prove its evidence, transformations, conflicts, and historical lineage.

**The Product Pitch**: *"Turn a question into a dataset you can prove."*

**Core Thesis**: Prompt-to-table and AI scrapers are commodities. ProofGrid differentiates not by claiming "we have autonomous AI agents", but by compiling natural language into a reproducible workflow with a user-visible **Trust Contract**, an immutable **Claim Ledger**, and cell-level interactive proof (**ProofCell**).

---

## 2. Main Problem Being Solved
When business teams (analysts, founders, BD/partnerships, researchers) need dynamic web data (e.g., funding, companies, competitors, executive moves, hiring), they currently face broken paradigms:
1. **Ad-hoc Data Engineering**: Every new question requires custom scrapers, fragile CSS selectors, or manual copy-pasting.
2. **Messy & Unnormalized Web Data**: Dates, currencies (USD, INR Crores, Lakhs), company legal names, and locations vary wildly across sources.
3. **Hallucination & Lack of Proof**: AI research assistants return synthesized prose or unverified tables with zero verifiable provenance.
4. **Disagreements are Silently Destroyed**: Traditional scrapers or naive LLMs pick one arbitrary value when two credible sources disagree, concealing uncertainty.
5. **Entity Duplication**: The same company appears with legal suffixes, abbreviations, or alias domains across different sources.
6. **Ephemeral Research**: Insights become stale tomorrow, with no way to rerun the collection and understand what changed.
7. **Runaway Cost/Latency**: Autonomous browser swarms get stuck in loops, rack up API bills, or fail completely when one page breaks.

---

## 3. Target Users & Jobs-to-be-Done (JTBD)
- **Primary Persona: Research & Strategy Analyst**
  - *Context*: Needs reliable market/company intelligence for investment memos, strategic benchmarking, or executive decisions.
  - *JTBD*: *"When I need a new market dataset, help me define it, collect it, and show the exact evidence so I can use it without manually verifying every single row."*
- **Primary Persona: Founder, BD & Partnerships Lead**
  - *Context*: Needs shortlists of prospects, investors, sponsors, or partners.
  - *JTBD*: *"When I describe the targets I want, give me a clean shortlist with proof and let me refresh it next month to see who raised or joined."*
- **Secondary Persona: Recruiting / Talent Ops**
  - *Context*: Tracking hiring, leadership changes, or competitor talent.
- **Secondary Persona: Data & Operations Engineer**
  - *Context*: Wants inspectable, reproducible extraction DAGs instead of maintaining dozens of fragile one-off scraping scripts.

---

## 4. Core User Journey (The 6-Stage Flow)
1. **ASK**: User enters a plain-English request (e.g., *"Find Indian AI startups that raised more than $1M in the last 12 months..."*).
2. **INTERPRET**: System compiles the prompt into a typed `RequirementSpec` with proposed columns. User inspects, edits, renames, adds, or deletes columns (AI-inferred columns are visibly tagged).
3. **TRUST**: User reviews and customizes the **Trust Contract** (evidence rules, freshness, first-party source preference, conflict preservation, and crawl/LLM budgets).
4. **PLAN**: System compiles the requirement into a constrained `PlanDAG` using only a fixed operator registry. User previews estimated steps, pages, and budget before execution.
5. **RUN**: Deterministic executor claims steps via a transactional queue. Real-time progress is streamed via SSE (sources discovered, pages fetched, claims extracted, entities resolved, partial failures).
6. **PROVE & ACT**: User explores the materialized **ProofGrid**, filters by trust status, clicks any **ProofCell** to open the Evidence Drawer (showing verbatim source quotes, timestamp, method, and conflicting claims), and exports CSV/JSON with an evidence companion bundle.
7. **REFRESH (Living Dataset)**: User reruns the saved workflow later; the system computes a `DatasetVersion` diff showing Added, Changed, Missing, and Conflict-Changed records.

---

## 5. Product Differentiation
| Traditional AI Scraper / Chatbot | ProofGrid Advantage |
| :--- | :--- |
| Returns prose or static JSON table | Produces a persistent, versioned relational dataset |
| Hallucinates facts without receipts | **ProofCell**: Every cell links to stored immutable evidence |
| Overwrites conflicting data silently | **Claim Ledger**: Stores all assertions; flags `CONFLICTING` visibly |
| Black-box autonomous agent looping | **Constrained PlanDAG**: LLM plans, deterministic code executes |
| Fake confidence scores (e.g. "94% sure") | **Categorical Trust States**: Derived from observable evidence criteria |
| Ephemeral one-off search | **Living Dataset**: Version diffs (Added / Changed / Missing / Conflicted) |
| Breaks on one failed webpage | **Partial Success**: Resilient execution preserves valid partial results |

---

## 6. The Golden Hackathon Demo
- **Vertical Focus**: Indian AI Startup Funding Intelligence (last 12 months, >$1M).
- **Why this vertical**: Horizontally extensible engine, but narrow and deep demo. Exercises multi-source discovery, currency normalization (USD vs INR Crores), entity resolution (parent vs subsidiary, legal names), cross-source corroboration, deliberate conflict detection, and living dataset refresh.
- **The Wow Moment on Stage**:
  1. Show prompt → typed schema; delete one AI-inferred field to show human control.
  2. Inspect the Trust Contract (first-party preference, budget caps).
  3. Run workflow; view SSE live monitor handling a non-critical source failure gracefully.
  4. Open ProofGrid; click a funding cell; show the **Evidence Drawer** with the exact highlighted snippet from the source document.
  5. Open an intentionally conflicting row (e.g. Source A says $41M, Source B says $45M); demonstrate that ProofGrid **refuses to hide uncertainty** and marks it `CONFLICTING`.
  6. Execute a semantic search query (*"healthcare AI infrastructure"*).
  7. Export the dataset with its companion evidence manifest.

---

## 7. Core Architectural Concepts

### 7.1 Trust Contract
A user-visible, technically enforced policy contract snapshotted before execution.
- Rules: `require_evidence_anchor` (true/false), `minimum_independent_sources` (1–5), `prefer_first_party` (true/false), `preserve_conflicts` (true/false), `max_source_age_days`.
- Hard Budgets: `max_pages` (e.g., 60–120), `max_browser_pages` (5–6), `max_llm_calls` (40–80), `max_estimated_cost_usd`.
- Runtime Effect: Limits execution, gates canonicalization, and determines if a record reaches `VERIFIED` status.

### 7.2 Claim Ledger
The heart of the trust architecture. Claims are append-only assertions (`Source S asserted Value V for Field F of Entity E at Time T with Evidence Quote Q`).
- Claims are decoupled from the canonical displayed value.
- If two sources give different numbers, both are stored as immutable `Claim` rows.
- Canonicalization is a presentation/version derivation, not evidence destruction.

### 7.3 ProofCell
The interactive UI presentation of any evidence-bearing canonical field.
- Displays: canonical value + categorical trust badge + source count indicator + conflict alert.
- Interaction: Clicking opens the **Evidence Drawer** (<500ms, reading stored relational data, zero LLM calls).
- Drawer Contents: Canonical value, Trust status reasoning, supporting claims list, conflicting claims, verbatim source excerpt (rendered in editorial serif), retrieval timestamp, HTTP status, content hash, extraction method, and normalization audit trail.

### 7.4 Dataset Versions & Living Dataset
- Every workflow run generates an immutable `DatasetVersion`.
- Stable entity UUIDs allow comparing datasets across time.
- Changes are classified as: `ADDED`, `CHANGED`, `UNCHANGED`, `MISSING_LATEST` (collection outcome, not deletion), `EVIDENCE_CHANGED`, and `CONFLICT_CHANGED`.

---

## 8. Division of Labor: AI vs. Deterministic Software

### What AI Should Do (Semantic Boundary Only)
1. **Compile Requirements**: Parse user's free-form prompt into a typed `RequirementSpec` and proposed fields.
2. **Propose Workflow Plan**: Generate a declarative `PlanDAG` using only pre-registered operators.
3. **Structured Extraction Fallback**: When structured data (JSON-LD, microdata, CSS/XPath) is unavailable, extract schema-constrained field values and candidate evidence quotes from cleaned text.
4. **Semantic Candidate Retrieval**: Generate embeddings for entity matching and dataset semantic search.

### What Deterministic Software MUST Do (Execution & Truth)
1. **Validate & Enforce**: Pydantic schema validation, PlanDAG cycle detection, budget checks, SSRF URL security filters.
2. **Queue & Scheduling**: Transactional Postgres step queue with `SKIP LOCKED` and leases.
3. **Evidence Anchor Verification**: Deterministic verification that a claim's evidence anchor resolves against the stored `RawDocument` representation across multiple supported anchor types:
   - `TEXT_SPAN` / `NORMALIZED_TEXT_SPAN`: Verifying that the quoted span is present in document text after the documented normalization procedure.
   - `JSON_POINTER` / `API_RESPONSE_POINTER`: Resolving the JSON pointer / field path in structured JSON/API data and comparing against the stored raw value.
   - `DOM_SELECTOR / DOM_PATH`: Storing and validating a stable element locator plus supporting text where possible.
   - `STRUCTURED_FIELD`: Comparing canonical keys and paths against structured tables or feeds.
   *(A claim qualifies for strong trust only when its evidence anchor deterministically resolves against the stored RawDocument).*
4. **Normalization**: Currency parsing (Decimal, FX conversion), ISO date parsing, name cleanup.
5. **Entity Resolution**: Blocking, RapidFuzz lexical scoring, hard-contradiction vetoes, decision thresholds.
6. **Trust State Engine**: Applying deterministic rules to assign `VERIFIED`, `SUPPORTED`, `SINGLE_SOURCE`, `CONFLICTING`, `NEEDS_REVIEW`, `MISSING`.
7. **Persistence & Integrity**: Managing PostgreSQL database transactions, state machines, and outbox events.

---

## 9. Important Architectural Principles

### 9.1 Backend Principles
- **PostgreSQL Owns Truth**: The authoritative store for all requirements, workflows, runs, steps, raw documents, evidence anchors, claims, entities, conflicts, and dataset versions.
- **Bounded AI**: No autonomous LLM agent loops. The LLM produces JSON; code validates and executes.
- **Isolated Acquisition**: Static HTTP first (`httpx` + `Trafilatura`). Browser (`Playwright`) is strictly a fallback for allowlisted, JS-heavy domains.
- **Transactional Outbox**: Side-effects to Qdrant or downstream webhooks are dispatched via an `outbox_events` table after Postgres commit to prevent split-brain states.
- **CQRS-Lite Read Model**: Detailed normalized claims live in `claims`; the grid reads from denormalized `dataset_version_records` (JSONB) for sub-300ms queries.

### 9.2 UX & Design Principles ("Forensic Ledger")
- **Visual Identity**: Warm off-white canvas (`#F4F1EA`), ink typography (`#151A17`), hairline rules (`#D8D4C8`), copper brand accent (`#B85732`) for active proof/focus.
- **Anti-AI-Slop**: NO purple/blue glowing aurora gradients, NO glassmorphism, NO floating 3D balls, NO decorative AI sparkle icons, NO card-soup layouts.
- **Typography (IBM Plex)**:
  - *IBM Plex Sans*: Clean UI labels, controls, tables.
  - *IBM Plex Mono*: Machine IDs, hashes, timestamps, URLs, metrics.
  - *IBM Plex Serif*: Quoted source evidence text (editorial credibility).
- **Categorical Trust Grammar**: Trust states use symbols + labels + colors (never color alone):
  - `✓ Verified` (#2C624B)
  - `≈ Supported` (#246B68)
  - `1 Single Source` (#3E568F)
  - `! Conflicting` (#8A4D08)
  - `? Needs Review` (#6B477F)
  - `○ Missing` (#6A716C)
- **Density Over Decoration**: Analytical workbench density (36–44px table rows) with sticky headers and resizable columns.

### 9.3 Security Principles
- **Untrusted Web Content**: Scraped text is raw data, NEVER instructions. The extraction model has no DB-write, browsing, or webhook tools.
- **Strict SSRF Defense**: Deny private RFC1918, loopback, link-local, multicast, and cloud metadata (169.254.169.254) addresses. Manual validation of every redirect target.
- **Zero-Secret Leakage**: Model provider keys, DB credentials, and service role keys exist only in backend environments; never exposed to the frontend.
- **Ethical Web Collection**: Respect `robots.txt` policy; no CAPTCHA circumvention, no paywall bypass, no unauthorized credential scraping.

---

## 10. Technology Stack Selected in Source Documents
| Tier | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend Framework** | Next.js (App Router) + TypeScript | React server/client architecture, layout composition |
| **Frontend UI / Tokens** | Tailwind CSS + CSS Variables (`@theme`) | Custom design tokens (Forensic Ledger palette) |
| **UI Primitives** | Radix UI Primitives | Accessible, unstyled behavior components |
| **Data Grid** | TanStack Table v9 (+ TanStack Virtual if needed) | Headless sorting, filtering, ProofCell rendering |
| **Workflow Graph** | React Flow (lazy-loaded) | Advanced read-only DAG inspection |
| **Typography** | IBM Plex (Sans, Mono, Serif) | Editorial & technical tone |
| **Core API Service** | Python 3.12 + FastAPI + Pydantic v2 | Async HTTP, typed OpenAPI contracts |
| **Database & ORM** | PostgreSQL (Supabase) + SQLAlchemy 2 Async + Alembic | Authoritative relational data, migrations |
| **Job Queue** | Postgres-backed `step_runs` table (`SKIP LOCKED`) | Reliable multi-worker step execution without Redis |
| **Raw File Storage** | Supabase Storage (S3-compatible) | Content-addressed raw HTML, text, export zips |
| **Static Acquisition** | HTTPX + Trafilatura + BeautifulSoup | Fast HTTP streaming, robots check, main-text extraction |
| **Browser Acquisition** | Playwright (Chromium) | Isolated non-persistent context fallback |
| **Search Discovery** | Adapter (`Brave`, `Tavily`, or `Exa`) | Discovery query provider (with fixture fallback) |
| **Vector Index** | Qdrant | Non-authoritative semantic search & candidate retrieval |
| **Entity Matching** | RapidFuzz + Blocking + Embeddings | Explainable string and token deduplication |
| **Event Streaming** | Server-Sent Events (SSE) | One-way real-time execution progress updates |

---

## 11. MVP Scope vs. Optional / Future Features

### MVP Scope (Must Ship for Hackathon)
- [x] Natural language prompt → typed `RequirementSpec` with schema negotiation.
- [x] Trust Contract editor (presets + explicit constraints + budget caps).
- [x] Constrained `PlanDAG` generator and deterministic plan validator.
- [x] Safe HTTP acquisition (SSRF protection, robots check, Trafilatura text).
- [x] Deterministic-first extraction + LLM structured fallback.
- [x] **Evidence Anchor Verification** across multiple deterministic anchor types (`TEXT_SPAN`, `NORMALIZED_TEXT_SPAN`, `JSON_POINTER`, `DOM_SELECTOR / DOM_PATH`, `STRUCTURED_FIELD`, `API_RESPONSE_POINTER`).
- [x] Normalization (currency with FX, dates, URLs, company names).
- [x] Basic explainable entity resolution (blocking + RapidFuzz).
- [x] **Claim Ledger** and **Conflict Detection** Engine.
- [x] Materialized dataset table with search, sort, filter, and pagination.
- [x] **ProofCell** with interactive Evidence Drawer.
- [x] SSE live run monitor with step states and partial-failure resilience.
- [x] CSV/JSON export with evidence companion bundle.
- [x] **Honest Fixture Mode**: Full downstream pipeline replayed over real pre-cached documents for zero-risk demo resilience.

### Strong Differentiators (Ship After Core MVP is Stable)
- [ ] Qdrant hybrid semantic search across entities.
- [ ] Dataset Version Diff viewer (Added, Changed, Missing, Conflicted).
- [ ] Scripted Playwright fallback for one approved JS-heavy source.
- [ ] Review Queue UI for resolving ambiguous entity merges and conflicting claims.

### Optional / Future Integrations (Strictly Non-Blocking)
- [ ] Pathway streaming integration for incremental live refresh.
- [ ] n8n webhook dispatch on workflow completion.
- [ ] Visual snapshot (screenshot of raw page highlight).

### Explicit Non-Goals (DO NOT BUILD)
- ❌ No general-purpose autonomous browser agent wandering the open web.
- ❌ No CAPTCHA solving, paywall cracking, or unauthorized scraping.
- ❌ No Redis, Celery, RabbitMQ, Kafka, or Temporal for the MVP.
- ❌ No microservices architecture; keep modular monolith + worker.
- ❌ No graph database (Neo4j) solely for architectural vanity.
- ❌ No fake statistical confidence percentages (e.g. "97% accurate").
- ❌ No multi-tenant enterprise billing or complex RBAC.

---

## 12. Strict Phase 1 Implementation Boundary
To ensure disciplined foundation construction without premature feature creep, Phase 1 is strictly restricted:

### What Phase 1 MAY Define:
- Monorepo folder layout and workspace configuration (`backend/` and `apps/web/`).
- Python tooling (`pyproject.toml`, `uv`, `Ruff`, `mypy`).
- Pydantic v2 domain schemas and enums (`RequirementSpec`, `FieldSpec`, `TrustContract`, `PlanDAG`, `PlanNode`, `EvidenceAnchor`, `EvidenceType`, `Claim`, `Entity`, `DatasetSchema`).
- Automated JSON Schema serialization/deserialization tests.
- Application shells (bare FastAPI app instance, bare Next.js 15 App Router scaffold).
- Environment configuration and validation (`pydantic-settings`).
- Structured logging setup (`structlog`).
- Basic test infrastructure (`pytest`, `vitest`).
- Frontend design-token foundation (`Forensic Ledger` CSS variables in `@theme` and IBM Plex typography config).

### What Phase 1 MUST NOT Implement:
- ❌ Actual workflow planning logic or LLM planning prompts.
- ❌ Database schema migrations or SQLAlchemy table creation (Phase 2).
- ❌ Supabase integration or database connections.
- ❌ Qdrant vector database integration.
- ❌ LLM API calls or provider gateway execution.
- ❌ Web acquisition, HTTP crawlers, or scraping logic.
- ❌ Data extraction or parsing engines.
- ❌ Entity resolution or deduplication algorithms.
- ❌ Claim Ledger persistence or transaction logic.
- ❌ ProofCell business logic or drawer hydration.
- ❌ Real application screens beyond a minimal static shell.
- ❌ External API integrations (search providers, FX rates, webhooks).
