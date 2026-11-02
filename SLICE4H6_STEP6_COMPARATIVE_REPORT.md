# SLICE 4H.6 — STEP 6 REPORT: Comparative Read

**Scope:** Step 6 ONLY — side-by-side comparison of a bounded set of decisions, composed from Steps 2–5 primitives. **Verdict: GREEN.**

## A. Scope Honored
- Zero new tables, columns, events, states, permission codes, workers, or write paths.
- Zero duplicated logic: every per-decision fact is a verbatim Step 4 `decision_performance_assessment` result; every longitudinal figure is a verbatim Step 5 `decision_performance_cohort` subset for the kinds actually compared.
- COMPARE ≠ RANK (L23): the payload contains no winner/rank/score/probability/recommendation/forecast/learning/person-evaluation field — enforced by test (`test_compare_not_rank_no_forbidden_fields`), including receiver-aware key scanning with honesty-flag self-collision handling.

## B. Implementation
`CompanyOperatingEngine.decision_performance_comparison(db, *, organization_id, decision_ids)` + class attr `MAX_COMPARE_DECISIONS = 5`.

**Input discipline**
- Dedupe preserving caller order; `<2` unique → rejected `at_least_two_unique_decisions_required`; `>MAX` → rejected `too_many_decisions` with `received` echoed — **never silently truncated**.
- Per id: tenant-scoped Step 4 assessment; unresolved ids land in `comparison.not_found` (missing **and** foreign-org ids alike). `<2` resolvable → rejected `fewer_than_two_resolvable_decisions` with the not-found list.

**Payload blocks**
| Block | Content |
|---|---|
| `comparison` | decision_ids (order preserved), requested/compared/not_found/max_decisions, `compare_not_rank: true`, `derived_on_read: true` |
| `columns` | compact neutral card per decision: title/kind/state, anchor+anchor_basis, outcome{kind,truth}, recorded effectiveness verbatim, execution counts (actions/evidence/artifacts/outcomes via `observed.action_outcomes`), measured counts, attribution summary, unknowns count + reason histogram |
| `contrasts` | neutral with/without partitions of factual evidence only: outcome-record presence, derived-measurement presence, SUPPORTED-attribution presence — partitions provably cover exactly the compared set |
| `longitudinal_context` | per compared kind: Step 5 cohort's decision_count / recorded_outcomes.by_kind / effectiveness_aggregate / attribution_summary, byte-equal to a direct cohort call |
| `assessments` | full embedded Step 4 assessments keyed by decision_id (provenance-complete) |
| `honesty` | compare_not_rank, no_winner_field, no_scores, no_probability, no_recommendations, no_forecasting, no_learning, no_people_scoring, chronology_is_not_causality, deterministic_composition |

One engine-side correction during self-review: the card originally read chain `outcomes`; the canonical source is `observed.action_outcomes` (the 4H.5 chain dict carries actions/evidence/artifacts/lesson) — fixed before first run.

## C. Tests — 17/17 GREEN (`tests/test_4h6_step6_engine.py`)
1 composition equality vs direct Step 4 calls · 2 recorded facts verbatim + absent-not-zero + unknown truth · 3 derived measurement + SUPPORTED attribution flow-through incl. delta basis ids · 4 temporal basis per decision · 5 bound of five accepted · 6 over-bound rejected, never truncated · 7 single-unique rejection + dedupe · 8 missing ids reported without blocking valid pair · 9 fewer-than-two-resolvable honest rejection · 10 **tenant isolation inside an otherwise-valid comparison** (foreign id → not_found, own two still compared) · 11 longitudinal context == direct Step 5 cohort output · 12 contrasts are neutral partitions covering exactly the compared set · 13 forbidden-field/key/vocabulary scan · 14 CompanyDecisionTrack row-level + stats untouched, no track keys in payload · 15 no writes/events · 16 determinism · 17 no-LLM source inspection.

Three initial failures were fixture/test-expectation issues, not product defects: (a) a seeded decision *with* an `unsuccessful` outcome correctly classified truth=recorded — test now also covers the no-outcome column; (b) zero-linked-metrics decisions carry all-zero attribution counters plus the canonical `no_linked_canonical_metrics` unknown reason — assertion aligned to the real contract signal; (c) banned-token self-collisions (fixture id containing "rank"; honesty flag names) — scanner adjusted, product vocabulary clean.

## D. Audits
| Audit | Result |
|---|---|
| AST read-only audit (receiver-aware; all TEN 4H.6 functions incl. sync classifiers) | GREEN — only flagged item was local `set.add` data assembly (false positive class documented since Step 2) |
| Schema gate structural keys (table count, company_actions columns, candidate_4h6_event_rows) | GREEN — identical to Phase-E baseline; candidate event rows = 0 |
| Row-count deltas vs Phase-E baseline | Append-only growth only (+quality/+tracks/+outcomes/+observations/+lineage) from cumulative persistent-DB test fixtures since Phase E; runtime non-mutation proven by test 15 and event-row count 0 |
| Baseline immutability | Hash verified unchanged; snapshot written to separate `SLICE4H6_SCHEMA_POST_STEP6.json` |

## E. Boundary
Stopped after this report per authorization. Step 7 (brain routes + narrow intents + collision guards) NOT started.

**Cumulative 4H.6: 79 tests green (16+18+15+13+17). Predecessor regressions: 25 green (4H.5 10, 4H.4, 4G.6).**
