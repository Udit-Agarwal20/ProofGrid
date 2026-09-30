# Backend conflict register

| Source A | Source B | Disagreement | Resolution and reason | Downstream impact |
| --- | --- | --- | --- | --- |
| Master request | PRD/backend spec | Neon versus Supabase database/auth/storage defaults | Neon pooled runtime plus direct migration URL; master request takes precedence | No Supabase dependency; bounded raw bodies in Postgres for the prototype |
| Existing canonical enums/migrations | Backend spec | COMPLETED versus COMPLETE run terminal state | Preserve COMPLETED, already persisted and tested | API/OpenAPI use COMPLETED consistently |
| Master request / PRD | Existing fixture compiler | Last 12 months was hardcoded to 18 months | Resolve the requested interval against explicit reference date | Regression corpus checks calendar boundaries |
| Immutable dataset history | Frontend conflict display override | Review may select a displayed claim, but must not rewrite old versions | Persist review annotation and apply decisions in subsequent versions | Historical ProofCells and exports remain reproducible |
| PRD generic engine | Fixture provider | Fixtures cannot promise arbitrary language understanding | Explicit fixture scenarios, live structured provider for general input | Demo metadata identifies fixtures; unsupported fixture prompts clarify |
| Historical public announcements | Current rolling 12-month demo | Actual captured articles describe past funding; changing event dates would fabricate current results | Separate captured historical replay with an explicit reference date from the synthetic current-date conflict demo | Raw metadata labels both modes and source dates remain intact |
| Source CMS publication timestamp | Funding event date | Neysa's CMS metadata is later than the event described; it cannot safely establish the funding date | Keep funding date missing; do not admit the record into a strict dated dataset | Captured E2E includes only the article whose event date is supported |
| Configurable evidence/conflict toggles | Master security invariants | Disabling required anchors or conflict preservation would invalidate the product promise | Confirmation/planning reject these settings | Human policy edits cannot authorize unanchored verified values or erase disagreement |
