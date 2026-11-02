# SLICE 4H.6 — STEP 8 REPORT: Minimal Frontend

**Scope:** Step 8 ONLY — presentation window onto the already-governed Steps 2–7 intelligence. **Verdict: GREEN.**

## A. Scope Honored
- Exactly the two ratified frontend files modified; zero new components/files/routes/libraries.
- No new backend anything: no engines, tables, columns, events, states, permissions, workers, LLM calls.
- No analytics dashboard product: performance is attached to the decision row inside the existing 4H.5 company experience; cohort + comparison are two minimal read-only cards beside it.
- Presentation only — every number shown is verbatim canonical data (recorded effectiveness, derived deltas citing observation ids, unknown reasons); the UI invents nothing.

## B. What Was Added
### `frontend/lib/api.ts`
Typed windows onto the three Step-7 routes: `CompanyPerformanceAssessment` (nine sections), `CompanyPerformanceCohortResponse`, `CompanyPerformanceComparisonResponse` + `getCompanyDecisionPerformance` / `getCompanyPerformanceCohort` / `compareCompanyDecisions`. Comparison rejections surface as typed errors carrying the engine's `reason`.

### `frontend/app/(app)/execution/company-tab.tsx`
1. **`PerformancePanel`** — per-decision, lazily loaded ("Outcome & performance" toggle next to "Decision intelligence"). Renders the nine sections as human concepts:
   - Decision context (title/state/anchor with named basis)
   - Observed outcome — outcome kind with **recorded** truth badge; effectiveness shown as the *recorded value*, never rescaled into a percentage score
   - Measured change — per metric: baseline → comparison values, delta, **derived-from observation ids**, baseline/comparison as-of dates + window
   - Attribution per metric — SUPPORTED / ASSOCIATED / UNKNOWN as visually distinct badges + reason text
   - Assessment — evidence counts only, captioned "evidence only · no score"
   - What remains unknown — dedicated warning block listing subject + reason
   - Honesty flags rendered as neutral chips
2. **Outcome history card** — Step 5 cohort on demand: outcome-kind histogram (successful/partial/unsuccessful/no-outcome-yet), effectiveness aggregate with its truth level and basis count, attribution totals, honesty chips. Captioned "institutional evidence, not a leaderboard".
3. **Compare decisions card** — Step 6 on demand: 2–5 comma-separated ids → dimension × decision table (outcome/truth, recorded effectiveness, execution, measured, attribution S/A/U, unknowns, anchor) + not-found line + honesty chips. Rejection reasons (over-bound etc.) surface verbatim from the 409 detail. No winner, rank, or recommendation anywhere.

## C. Acceptance Checklist (contract §23)
| Criterion | Status |
|---|---|
| Performance section attached to decision context | ✓ |
| Observed / Measured displayed | ✓ |
| Recorded / derived / unknown differentiated (badges + basis citations) | ✓ |
| Attribution supported/associated/unknown explicit | ✓ |
| Temporal basis visible (anchor basis, as-of dates, window) | ✓ |
| Unknown reasons visible | ✓ |
| Execution chain visible | ✓ (counts in panel; full chain remains the existing 4H.5 view — consumed, not rebuilt) |
| Cohort view accessible · Comparison accessible | ✓ |
| No ranking/score/winner/recommendation/people-scoring/forecasting | ✓ (anti-duplication token scan over additions: zero hits) |
| Existing 4H.5 UI intact | ✓ (all prior toggles/cards untouched) |
| Existing APIs intact | ✓ (additive only) |
| TypeScript clean | ✓ `tsc --noEmit` exit 0 |

(No frontend test runner exists in the project; tsc is the established gate.)

## D. Audits & Regressions
| Check | Result |
|---|---|
| AST read-only — 10 engine functions + 3 brain routes (re-run) | GREEN |
| Schema gate structural keys / candidate_4h6_event_rows | identical to Phase-E baseline / **0** |
| Baseline immutability | hash verified; snapshot → separate `SLICE4H6_SCHEMA_POST_STEP8.json` |
| Diff confinement (filesystem audit, whole slice) | exactly the ratified set: engine, brain.py, intelligence_engine.py, api.ts, company-tab.tsx, new tests/scripts/reports — nothing else |
| Predecessor matrix (4H.1–4H.5, 4G.6) | 58 passed |
| Cumulative 4H.6 steps 2–7 | 92 passed |

## E. Boundary
Stopped after this report per authorization. The final freeze run (live acceptance script `accept_slice4h6.py`, chunked full pytest, moat analysis, `SLICE4H6_VERIFICATION_REPORT.md`) is NOT started.
