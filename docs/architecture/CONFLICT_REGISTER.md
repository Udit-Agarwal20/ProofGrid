# ProofGrid: Conflict & Ambiguity Register

> **Cross-Document Analysis**: A rigorous comparison of the four source-of-truth documents:
> 1. Product Requirements Document (`PRD v1.0`)
> 2. Technical Requirements Document (`TRD v1.0`)
> 3. Frontend UX/UI Design Specification (`Frontend Spec v1.0`)
> 4. Backend Engineering & Data Pipeline Specification (`Backend Spec v1.0`)
>
> All conflicts, discrepancies, terminology variations, and differing implementation scopes have been documented below with recommended resolutions. None of these conflicts are fatal blockers, but explicit alignment is required.

---

### Conflict 1: API Route Hierarchy and Naming
- **Document A says (TRD Section 20.1)**:
  - `POST /v1/interpret`
  - `POST /v1/workflows`
  - `POST /v1/workflows/{id}/plan`
  - `GET /v1/entities/{id}/claims`
  - `POST /v1/dataset-versions/{id}/exports`
- **Document B says (Backend Spec Section 23 & Appendix B)**:
  - `POST /v1/requirements/compile`
  - `PATCH /v1/requirements/{id}`
  - `POST /v1/requirements/{id}/trust-contract`
  - `POST /v1/requirements/{id}/plan`
  - `GET /v1/datasets/{dataset_id}/versions/{version_id}/records/{entity_id}/proof/{field_key}`
  - `POST /v1/exports`
- **Impact**: Inconsistent endpoint naming between TRD and Backend Spec would create breaking client-server contract mismatches and frontend client generation confusion.
- **Recommended interpretation**: **Adopt Backend Spec Section 23**. It provides clean, RESTful resource boundaries, explicitly separates requirement compilation from schema negotiation (`PATCH`), and scopes proof retrieval to specific versioned records (`/records/{eid}/proof/{field_key}`).
- **Blocking?**: **NO** (Standardized on Backend Spec).

---

### Conflict 2: Frontend Route Hierarchy
- **Document A says (TRD Section 21)**:
  - Routes: `/`, `/workflows/new/interpret`, `/workflows/{id}/trust`, `/workflows/{id}/plan`, `/runs/{id}`, `/datasets/{id}`, `/entities/{id}`, `/datasets/{id}/diff`.
- **Document B says (Frontend Spec Section 4 & 16)**:
  - Routes: `/ask`, `/datasets`, `/datasets/[datasetId]`, `/datasets/[datasetId]/diff`, `/workflows`, `/workflows/[workflowId]`, `/runs/[runId]`, `/review`, `/sources`, `/exports`.
- **Impact**: Differences in Next.js folder routing (`app/ask/page.tsx` vs `app/workflows/new/interpret/page.tsx`).
- **Recommended interpretation**: **Adopt Frontend Spec Section 4 & 16**. The `/ask` route represents the clean brief composer, while `/datasets/[datasetId]` acts as the persistent analytical workbench. The intermediate interpretation and trust steps are handled via staged client views or clean sub-routes (`/ask/interpret`, `/ask/trust`, `/ask/plan`).
- **Blocking?**: **NO**.

---

### Conflict 3: UI Component Architecture (shadcn/ui vs. Radix Primitives)
- **Document A says (TRD Section 4)**:
  - Stack selection: `"Tailwind + shadcn/ui (fast consistent interface without locking table behavior)"`.
- **Document B says (Frontend Spec Section 15 & 19)**:
  - Anti-template rule: *"Do not install shadcn/ui and keep its default appearance. If any generated primitive code is used, treat it as behavior scaffolding only and restyle fully to ProofGrid tokens. DO NOT copy shadcn/Linear/Notion styling literally. Radix UI Primitives is the accessible unstyled behavior layer."*
- **Impact**: Risk of AI coding assistants importing generic shadcn components with black-and-white rounded card styling, violating the "Forensic Ledger" visual design.
- **Recommended interpretation**: **Enforce Frontend Spec Section 19 strictly**. Use Radix UI Primitives as unstyled headless building blocks, customized with the ProofGrid Forensic Ledger color tokens (`--canvas: #F4F1EA`, `--ink: #151A17`, `--copper: #B85732`) and IBM Plex typography.
- **Blocking?**: **NO**.

---

### Conflict 4: Run and Step State Machine Enums
- **Document A says (TRD Appendix A)**:
  - `RunState`: `QUEUED`, `PLANNING`, `READY`, `RUNNING`, `PARTIAL`, `COMPLETED`, `FAILED`, `CANCELLED`.
  - `StepState`: `PENDING`, `READY`, `RUNNING`, `COMPLETED`, `SKIPPED`, `FAILED_RETRYABLE`, `FAILED_FINAL`, `CANCELLED`.
- **Document B says (Backend Spec Appendix C)**:
  - `RunStatus`: `CREATED`, `QUEUED`, `RUNNING`, `PARTIAL`, `COMPLETE`, `FAILED`, `CANCEL_REQUESTED`, `CANCELLED`.
  - `StepStatus`: `PENDING`, `READY`, `LEASED`, `RUNNING`, `RETRY_WAIT`, `SUCCEEDED`, `FAILED`, `SKIPPED`, `CANCELLED`.
- **Impact**: Database schema constraints and frontend badge display logic will break if state names mismatch (e.g. `COMPLETED` vs `COMPLETE`, `COMPLETED` vs `SUCCEEDED`).
- **Recommended interpretation**:
  - For `StepStatus`: **Adopt Backend Spec** (`PENDING`, `READY`, `LEASED`, `RUNNING`, `RETRY_WAIT`, `SUCCEEDED`, `FAILED`, `SKIPPED`, `CANCELLED`) because `LEASED` is functionally necessary for PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` worker claims, and `RETRY_WAIT` is needed for backoff.
  - For `RunStatus`: Standardize on `COMPLETED` (spelled out) as used in PRD, TRD, and Frontend Spec to describe successful terminal runs.
- **Blocking?**: **NO**.

---

### Conflict 5: Trust Contract Budget Defaults
- **Document A says (PRD Table / Section 6.2 & TRD Section 6.2)**:
  - `max_pages = 120`, `max_browser_pages = 5`, `max_llm_calls = 40-50`, `max_run_seconds = 180`.
- **Document B says (Backend Spec Section 5.2)**:
  - `max_pages = 60`, `max_browser_pages = 6`, `max_llm_calls = 80`, `max_estimated_cost_usd = Decimal('3.00')`.
- **Impact**: Plan validation rejection thresholds and default user slider positions.
- **Recommended interpretation**: **Adopt Backend Spec defaults** for the live hackathon demo. Capping `max_pages` at 60 guarantees the demo workflow completes within the target 90-second window, while `max_llm_calls = 80` accommodates extraction across up to 40 entities.
- **Blocking?**: **NO**.

---

### Conflict 6: RequirementSpec Field Data Types
- **Document A says (TRD Section 6.1)**:
  - `value_type: Literal['string', 'number', 'money', 'date', 'url', 'string_list', 'boolean']`
- **Document B says (Backend Spec Section 5.1 & 16)**:
  - `data_type: Literal['text', 'url', 'money', 'date', 'location', 'entity_ref', 'entity_list', 'number', 'boolean']`
- **Impact**: Field normalization and validation dispatch logic.
- **Recommended interpretation**: **Adopt Backend Spec Section 5.1**. Distinguishing `location` and `entity_ref` (references to other entities like Founders or Investors) is critical for startup funding data modeling, and `text` is more standard than `string`.
- **Blocking?**: **NO**.

---

### Conflict 7: Database Table Inventory and Model Names
- **Document A says (TRD Section 17.1)**:
  - Tables: `workflow_events`, `canonical_fields`, `entity_matches`, `llm_calls`.
- **Document B says (Backend Spec Section 6.2)**:
  - Tables: `run_events`, `canonical_values`, `dataset_version_records`, `entity_match_candidates`, `model_calls`, `evidence_anchors`, `projects`, `outbox_events`.
- **Impact**: SQLAlchemy ORM models, foreign key relationships, and Alembic migrations.
- **Recommended interpretation**: **Adopt Backend Spec Section 6.2**. It introduces three critical architectural improvements:
  1. `evidence_anchors`: Separates the verifiable quote/span from the claim itself.
  2. `dataset_version_records`: Stores the materialized denormalized read model for fast UI queries.
  3. `outbox_events`: Provides transactional guarantees for updating Qdrant and webhooks.
- **Blocking?**: **NO**.

---

### Conflict 8: Evidence Anchor Verification Status Enum
- **Document A says (TRD Section 12.2)**:
  - Returns `AnchorResult(verified=True, start=idx, end=idx+len(q))` with `anchor_method in ['exact', 'fuzzy']`.
- **Document B says (Backend Spec Section 15.3 & Appendix C)**:
  - Defines `EvidenceStatus` enum: `EXACT`, `NORMALIZED`, `JSON_POINTER`, `DOM_SELECTOR`, `UNANCHORED`.
- **Impact**: How evidence anchors are stored and classified.
- **Recommended interpretation**: **Adopt Backend Spec Section 15.3**. Distinguishing between verbatim substring matches (`EXACT`), whitespace-folded matches (`NORMALIZED`), structured JSON pointers (`JSON_POINTER`), and selector hits (`DOM_SELECTOR`) provides richer provenance in the ProofCell drawer.
- **Blocking?**: **NO**.

---

### Conflict 9: Multi-Tenancy vs. Single-Workspace Demo
- **Document A says (PRD Section 12.3 & TRD Section 2.2)**:
  - Explicit non-goal: *"Enterprise multi-tenant billing/admin controls during the hackathon."*
- **Document B says (Backend Spec Section 7 & Appendix D)**:
  - Introduces `projects` table and `AUTH_ENABLED` toggle supporting `DEMO_SINGLE_WORKSPACE` (injects hardcoded demo project ID) vs `AUTHENTICATED` (Supabase JWT auth).
- **Impact**: Complexity of request authentication and database foreign keys.
- **Recommended interpretation**: Implement database schema with a `project_id` column, but default to `AUTH_ENABLED=false` (`DEMO_SINGLE_WORKSPACE`) for the hackathon MVP. This keeps the demo frictionless while preserving multi-tenant database readiness.
- **Blocking?**: **NO**.

---

### Conflict 10: Search Discovery Provider Selection
- **Document A says (TRD Section 4 & 11.1)**:
  - Mentions `Brave` or `Tavily` search adapter.
- **Document B says (Backend Spec Section 2 & 12)**:
  - Mentions `Exa`, `Tavily`, `Brave`, or `mock/fixture`.
- **Impact**: Third-party API keys and client libraries.
- **Recommended interpretation**: Implement a clean `SearchProvider` protocol. Support `Tavily` and `Brave` as live providers, and a `FixtureSearchProvider` that returns pre-cached candidate URLs for offline and rehearsal demo runs.
- **Blocking?**: **NO**.

---

### Summary of Conflict Audit
- **Major Blocking Architectural Conflicts**: **0**
- **Terminology & Schema Alignments Required**: **10** (all resolved above in favor of Backend Engineering Spec v1.0 and Frontend UX Spec v1.0).
- **Development Status**: **Clear to proceed to Acceptance Gates.**
