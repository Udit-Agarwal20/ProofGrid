# ProofGrid Submission Readiness & Release Report

**Release Date:** 2026-09-30 (Submission Night — Code Cubicle 6.0)  
**Status:** **SUBMISSION READY (PASS)**  
**Target Branch:** `feature/proofgrid-frontend`  
**Application Root:** `apps/web`  
**Backend Root:** `backend`  

---

## 1. Exact Branch
- **Branch:** `feature/proofgrid-frontend`
- **Upstream Tracking:** `origin/feature/proofgrid-frontend`

---

## 2. Commit Checkpoints
- **Baseline Checkpoint Commit:** `0f337b8` (`checkpoint: complete ProofGrid frontend vertical slice`)
- **Release Hardening Commit:** `release: harden ProofGrid hackathon demo`

---

## 3. Frontend Test Results
- **Command:** `pnpm --filter @proofgrid/web test`
- **Framework:** Vitest v3.2.7 with jsdom environment
- **Result:** **34 passed across 3 test suites (100% pass)** in 1.67s.
  - `test/tokens.test.ts`: 2/2 passed (typography and trust badge tokens).
  - `test/contracts.test.ts`: 23/23 passed (API client error mappings, SSE frame parsing, query builder, canonical trust status vocabulary).
  - `test/components.test.tsx`: 9/9 passed (Brief composer, DataGrid rendering, ProofCell keyboard/mouse interaction, Review Queue, Export panel).
- **TypeScript:** `pnpm --filter @proofgrid/web typecheck` → **0 errors** (`tsc --noEmit`).
- **ESLint:** `pnpm --filter @proofgrid/web lint` → **0 warnings, 0 errors** (`next lint`).

---

## 4. Backend Focused Test Results
- **Contract Integrity Tests:**
  - `backend/.venv/bin/pytest backend/tests/contracts/test_schema_contracts.py`
  - **12 passed in 0.06s** (verifies primary keys, foreign key delete policies, critical unique constraints, canonical trust status enum alignment, raw document provenance independence).
- **Golden Journey E2E Tests:**
  - `backend/.venv/bin/pytest -m integration backend/tests/e2e/test_fixture_backend.py`
  - **3 passed in 303.92s** (full pipeline over real PostgreSQL: compilation, confirmation, planning, worker execution, ProofCell extraction, conflict resolution, export, diff).

---

## 5. Build Result
- **Command:** `pnpm --filter @proofgrid/web build`
- **Result:** **Compiled successfully**.
  - `Route (app) /`: 138 B (First load JS: 132 kB)
  - `Route (app) /_not-found`: 980 B (First load JS: 106 kB)
  - `Route (app) /[...path]`: 137 B (First load JS: 132 kB)
  - Zero hydration errors, zero route bundle warnings.

---

## 6. Database Health
- **Engine:** Neon PostgreSQL (remote pooled instance over SSL)
- **Status:** **HEALTHY**
- **Health Endpoint:** `GET http://127.0.0.1:8000/health/ready`
  ```json
  {
    "status": "ok",
    "service": "proofgrid-api",
    "version": "0.1.0",
    "environment": "local",
    "ready": true,
    "database": {
      "status": "healthy",
      "latency_ms": 1617.03
    }
  }
  ```

---

## 7. Runtime Configuration Mode (Non-Secret)
Configured in git-ignored `backend/.env` and `apps/web/.env.local`:
- `AI_PROVIDER=fixture` (Zero-latency, 100% deterministic compilation)
- `SEARCH_PROVIDER=fixture` (Bounded raw fixture acquisition)
- `ACQUISITION_MODE=FIXTURE` (Hermetic public source replay)
- `FIXTURE_SET=synthetic` (Indian AI funding demo showcase)
- `CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]` (Allows both origins)
- `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`

---

## 8. Three Required Processes

To demonstrate the full platform, all three processes must be active:

| Process | Working Directory | Command | Purpose |
| :--- | :--- | :--- | :--- |
| **1. API Server** | `backend` | `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend` | FastAPI REST & SSE backend |
| **2. Queue Worker** | `backend` | `.venv/bin/python worker/main.py` | Durable PostgreSQL job processor |
| **3. Web App** | root / `apps/web`| `pnpm --filter @proofgrid/web dev --hostname 127.0.0.1 --port 3000` | Next.js 15 Forensic Ledger UI |

---

## 9. Golden Demo Rehearsal Result
A live rehearsal was executed in an automated Chromium session:

| Stage | Expected Behavior | Actual Verified Result | Status |
| :--- | :--- | :--- | :---: |
| **Ask** | Natural-language query input | Pre-populated via "Indian AI funding" chip | **PASS** |
| **Compile** | Prompt → RequirementSpec | Returned `cf851ec7...` with 11 fields, ambiguities & assumptions | **PASS** |
| **Interpretation** | Studio with editable proposed fields | Rendered schema editor, constraints, and brief context | **PASS** |
| **Trust Contract** | Presets & policy controls | Switched between Balanced/Strict; budgets configured | **PASS** |
| **Plan DAG** | Validated 8-stage execution graph | Plan verified with dependencies (Discover → Materialize) | **PASS** |
| **Run Execution** | Launch workflow run | Run created; worker picked up task within 500ms | **PASS** |
| **SSE Stream** | Real-time step progress | Connected; streamed steps 01→08; 20 events received | **PASS** |
| **Terminal State** | Completion & dataset resolution | Run reached `COMPLETED`; "Open dataset" button appeared | **PASS** |
| **Dataset Grid** | Forensic Ledger data table | Rendered Nimbus AI Demo & Veda AI Demo with 12 columns | **PASS** |
| **ProofCell Click** | Click `#cell-1-2` (Funding Amount) | Opened slide-over Proof Drawer with zero lag | **PASS** |
| **Evidence Display** | Competing claims side-by-side | Displayed $4.5M (first-party) vs $5.0M (news report quote) | **PASS** |
| **Conflict & Review** | Human resolution preference | Reviewer selected $5M preference; saved successfully | **PASS** |
| **Export ZIP** | Download evidence bundle | Downloaded 79.6KB ZIP with `dataset.csv`, `evidence.json`, `manifest.json` | **PASS** |

---

## 10. Browser Quality Gate
- **Console Errors:** **0 errors, 0 warnings** during full rehearsal.
- **Network Requests:** All fetch requests returned HTTP 200 OK.
- **Hydration / React Warnings:** 0 warnings detected.

---

## 11. Export Bundle Verification
Contents of `proofgrid-*.zip`:
- `dataset.csv` (641 bytes): Complete tabular export with entity IDs and normalized values.
- `evidence.json` (78,859 bytes): Full provenance companion containing claims, selectors, and content hashes.
- `manifest.json` (101 bytes): Cryptographic dataset version link and record count.

---

## 12. Remaining Known Limitations
1. **Live Browser Crawling:** Unconfigured in demo mode (uses hermetic high-fidelity fixtures for 100% demo reliability).
2. **Neon Latency:** Remote database queries over SSL have ~1.2s–1.6s baseline latency.
3. **Qdrant Vector Engine:** Disabled for hackathon slice (deterministic entity resolution is used).

---

## 13. Exact Demo Startup Commands

Run each in a dedicated terminal window:

```bash
# Terminal 1 — Backend Core API
cd /Users/uditagarwal/Desktop/code-cubical/backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir .

# Terminal 2 — PostgreSQL Durable Queue Worker
cd /Users/uditagarwal/Desktop/code-cubical/backend
.venv/bin/python worker/main.py

# Terminal 3 — Forensic Ledger Frontend
cd /Users/uditagarwal/Desktop/code-cubical
pnpm --filter @proofgrid/web dev --hostname 127.0.0.1 --port 3000
```

---

## 14. Exact Golden Prompt

```text
Find Indian AI startups that raised more than $1M in the last 12 months. Include company, website, founders, headquarters, funding round, funding amount, investors, funding date, and original evidence.
```

---

## 15. 3-Minute Demo Script

- **0:00 – 0:25 (The Problem & Doctrine):**
  > *"Modern AI data extraction hallucinates numbers and gives untraceable answers. ProofGrid is built on a different doctrine: LLM plans, code executes, evidence proves, PostgreSQL owns truth. We turn a question into a dataset you can prove."*

- **0:25 – 0:50 (The Brief Composer):**
  > *"I begin at the Ask screen. I click our research brief: 'Find Indian AI startups that raised more than $1M in the last 12 months with founders, round, amount, and original evidence.' I click 'Compile request'."*

- **0:50 – 1:15 (The Interpretation Studio & Trust Contract):**
  > *"ProofGrid doesn't just guess what I want. It compiles a formal RequirementSpec. Notice it flagged ambiguities: 'What does Indian startup mean? Headquartered in India, or founded by Indian founders abroad?' On the right, I can edit the proposed schema. In Stage 2, I inspect the Trust Contract: requiring verified evidence anchors, preferring first-party sources, and preserving conflicts."*

- **1:15 – 1:40 (The Plan DAG & Live Execution):**
  > *"I click 'Confirm contract & build plan'. The backend compiles a deterministic 8-operator execution graph. I click 'Run workflow'. Look at the real-time execution ledger: over SSE, our durable PostgreSQL worker executes Discovery, Fetch, Extraction, Normalization, Entity Resolution, and Reconciliation live."*

- **1:40 – 2:10 (The ProofGrid & Trust Badges):**
  > *"Our dataset is ready. Notice the canonical trust grammar: Verified (check), Supported (approximate), and Conflicting (exclamation mark). There are no fake confidence percentages here."*

- **2:10 – 2:40 (The ProofCell & Preserved Disagreement):**
  > *"Look at Nimbus AI Demo's funding amount: it's marked CONFLICTING. I click the cell to open the Proof Drawer. Here is the magic: ProofGrid preserves the disagreement. The company's press release claims $4.5 million with a direct JSON locator. But the tech journal reported $5.0 million with a DOM selector quote. As an analyst, I can inspect the raw hash, open the source URL, and set a future display preference without destroying the historical record."*

- **2:40 – 3:00 (Export & Conclusion):**
  > *"Finally, I click Export. ProofGrid generates a ZIP bundle containing not just a CSV, but an evidence companion JSON and cryptographic manifest. Every single value has a traceable source. That is ProofGrid."*

---

## 16. Emergency Recovery Steps

If any service encounters an issue during live judging:

1. **Port Already Bound:**
   ```bash
   kill -9 $(lsof -t -i :8000) 2>/dev/null || true
   kill -9 $(lsof -t -i :3000) 2>/dev/null || true
   ```
2. **Worker Stuck or Stopped:**
   Restart the worker in Terminal 2:
   ```bash
   cd backend && .venv/bin/python worker/main.py
   ```
3. **Reset to Clean Known Dataset:**
   Open the pre-existing verified dataset in the browser:
   `http://localhost:3000/datasets/4d7a410d-3e2a-4951-9156-f8f8caef15fa`
