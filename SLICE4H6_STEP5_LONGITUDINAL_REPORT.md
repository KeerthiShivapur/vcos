# SLICE 4H.6 — STEP 5 REPORT: OUTCOME COHORT / LONGITUDINAL READ

**Verdict: GREEN.** Scope honored: Step 5 ONLY. Cohorts derived entirely ON READ through the Steps 2–4 primitives. `CompanyDecisionTrack` untouched, unqueried, unimitated. No recommendations, rankings, scores, forecasts, learning, people judgments, writes, schema changes, or events.

---

## A. Objective

Turn accumulated canonical decision/outcome evidence into a longitudinal institutional read — "what does the record show across decisions?" — without creating a competing history system and without crossing into the learning layer (4H.7).

## B. Implementation

`decision_performance_cohort()` — `backend/app/intelligence/company_operating_engine.py:8610` (same class). Optional canonical filters (`kind`, `state`); bounded at `MAX_COHORT_DECISIONS = 25`; deterministic ordering (`created_at ASC, id ASC`). Per decision it composes the **Step 4 unified assessment** — literal reuse; zero duplicated measurement/attribution logic.

## C. Cohort Surface

| Block | Content | Truth discipline |
|---|---|---|
| `cohort` | filters, count, bound + `bounded` flag, `derived_on_read: true` | factual |
| `decisions` | compact per-decision facts: id/kind/state/outcome_kind/effectiveness/anchor(+basis) | recorded |
| `recorded_outcomes` | by_kind histogram over the canonical vocab, with/without outcome record | recorded counts |
| `effectiveness_aggregate` | ≥2 recorded values → derived mean **citing contributing decision ids**; exactly 1 → recorded passthrough; 0 → unknown with reason | L20/L21/Q3 |
| `measurement_coverage` | decisions-with-linked-metrics, derived items, unknown items (sums of Step 4 assessed counts) | reuse |
| `attribution_summary` | cohort-wide SUPPORTED/ASSOCIATED/UNKNOWN totals | L22 |
| `temporal_coverage` | earliest/latest anchors + anchor_bases histogram | L24 |
| `unknown_aggregate` | total unknown items + reason histogram across the cohort | first-class |
| `honesty` | incl. `patterns_not_recommendations`, `no_learning`, `compare_not_rank`, `track_infrastructure_untouched` | envelope |

Allowed example (what this surface can now answer): *"Across N approved decisions of this kind, X have recorded successful outcomes, Y partial, Z unsuccessful; average recorded effectiveness is a derived mean over these specific recorded values."* It cannot and does not say what to do next.

## D. Track-Infrastructure Invariant

Test seeds real `CompanyDecisionTrack` rows, snapshots them plus table stats, runs cohort reads, and asserts byte-identical state afterwards. The cohort output contains no track fields. Prediction-history semantics remain exclusively 4H.2's.

## E. Tests

`backend/tests/test_4h6_step5_engine.py` — **13 passed**:

1–2 distribution + honest gaps; kind/state filters
3 effectiveness aggregate truth levels (unknown / recorded / derived-with-basis)
4 measurement+attribution aggregation via linked metric
5 temporal coverage extremes + basis histogram
6 unknown reasons aggregated across assessments
7 track infrastructure untouched (row-level + stats identity)
8 bounds enforced with exposure
9 determinism byte-identical
10 tenant isolation (empty sibling cohort)
11 no writes/no events
12 no-LLM source scan
13 patterns-not-recommendations vocabulary scan

**Cumulative 4H.6: 62 passed** (Steps 2+3+4+5). Predecessor regressions re-run green: **25 passed** (4H.5 engine 10, 4H.4 engine suite, 4G.6 models).

## F. Audits

| Gate | Result |
|---|---|
| Read-only AST audit (all NINE 4H.6 functions) | GREEN |
| Schema gate vs Phase-E baseline | GREEN — zero delta |
| Candidate 4H.6 event rows | 0 |
| Baseline immutability | hash verified; post-run snapshot to separate file `SLICE4H6_SCHEMA_POST_STEP5.json` |
| Determinism / tenant isolation / bounded reads | GREEN |

## G. Deviations & Notes

Two test-side corrections during this step (product code unchanged): fixture emails made collision-proof against the persistent test DB, and one test was found reading an empty org due to its own double-registration — fixed to use the seeded org. A debug replica confirmed the cohort engine behaved correctly throughout.

Operational note for later steps: the cohort performs one bounded assessment per decision (≤25 × bounded sub-reads). Acceptable for read endpoints today; if larger cohorts are ever ratified, batch the per-metric queries in Step 4's composition rather than duplicating logic here.

## H. Final Verdict

**STEP 5 = GREEN.** The company's historical operating evidence is now readable as one provenance-connected longitudinal layer — compounding institutional memory that stops exactly where learning begins.

**STOP.** Step 6 (comparative read) not started, per run authorization.
