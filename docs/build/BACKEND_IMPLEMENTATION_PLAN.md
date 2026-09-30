# Backend implementation plan

Read in full: the master request, PRD, backend engineering specification, and frontend UX/UI specification. The initial backend has 21 modeled business tables, two applied migrations, repositories/UoW, health routes, an idle worker, and a branch-specific compiler with uncommitted Groq/Gemini improvements. Baseline offline tests: 149 passed, 38 deselected.

Preserve existing migrations, compiler envelopes/adapters, user changes, and frontend. Implement in this order, validating each subsystem:

1. Foundation: clock, sanitized errors, configuration, compiler regression fixes, additive persistence constraints.
2. Typed planner/validator and durable Postgres queue with leases, fencing, retry, cancellation, ordered events, and outbox.
3. Safe public acquisition with fixture replay; raw artifacts persisted before extraction.
4. Deterministic and constrained LLM extraction, verified anchors, typed normalization, conservative identity, conflict-preserving trust.
5. Immutable dataset materialization, scoped APIs, ProofCell, SSE, review, export, refresh/diff.
6. Offline/security/database/E2E tests, CI, demo rehearsal, documentation, lint/types/build and secret checks.

No frontend redesign, automatic commits, or additional distributed infrastructure. Live features remain explicitly configured. A final report will distinguish verified behavior from external and optional limitations.

Execution completed through API/worker/evidence/export. Validation expanded to live permitted captures, a 195-test offline suite, PostgreSQL queue/outbox recovery, complete synthetic review/refresh E2E, captured-history E2E and budget-limited partial output. Final dependency-locked integration and latency checks are recorded in the implementation report. Existing frontend lint/types/tests/build were preserved and verified.
