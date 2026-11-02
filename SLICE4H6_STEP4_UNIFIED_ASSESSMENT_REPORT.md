# SLICE 4H.6 — STEP 4 REPORT: UNIFIED DECISION-PERFORMANCE ASSESSMENT

**Verdict: GREEN.** Scope honored: Step 4 ONLY. The Step 2 temporal helpers and Step 3 classifiers were consumed as immutable primitives — zero modifications to them. No routes, intents, frontend, tables, columns, events, workers, writes, scores, or forecasts were added.

---

## A. Objective

Compose the separate 4H.6 primitives into ONE read-only intelligence object answering exactly one question: **"What do we actually know about what happened after this decision?"** — never "was this a good decision?"

## B. Implementation

`decision_performance_assessment()` — `backend/app/intelligence/company_operating_engine.py:8442` (same class; no new module/engine). Accepts the governance `access` envelope and passes it through to the 4H.5 chain for artifact-level visibility.

## C. The Nine Ratified Sections

| Section | Content | Provenance |
|---|---|---|
| `decision` | id/kind/title/state, approved/executed timestamps, recorded `expected_improvement` verbatim, anchor_basis | CompanyDecision row |
| `observed` | outcome_record (outcome_kind + effectiveness + `actual_outcome_compare` verbatim + evidence-refs presence), action outcomes, execution/evidence counts, lesson — each recorded or explicitly unknown (`no_outcome_recorded`) | decision row + 4H.5 chain output |
| `measured` | per linked metric: canonical metric identity + link provenance, classified measurement (Step 3 primitive output, untouched), attribution alongside | Steps 2+3 composition |
| `attributed` | per-metric level/basis/reason + SUPPORTED/ASSOCIATED/UNKNOWN summary counts | Step 3 classifier |
| `assessed` | evidence COUNTS only (`outcome_recorded`, `linked_metrics_count`, `derived_measurements_count`, unknown counts, attribution summary) — descriptive facts, explicitly "not a quality score" | computed |
| `unknown` | first-class aggregated items `{section, subject, reason}` — measurement gaps, attribution silence, unrecorded outcome, no-linked-metrics | computed |
| `temporal_basis` | decision anchor + basis; per-measurement L24 bases embedded in each measured item | Step 2 |
| `execution_chain` | 4H.5 chain CONSUMED VERBATIM (minus its volatile `generated_at`) — never duplicated | `execution_chain()` |
| `honesty` | static envelope: advisory/read-only/no-scores/no-ranking/no-forecasting/no-recommendations/no-learning/no-people-scoring/temporal≠causality/unknown≠zero/chain-consumed-not-duplicated/deterministic | static |

## D. Moat-Rule Compliance

- **No score anywhere**: no decision score, quality verdict, success probability, winner field. `assessed` carries counts only.
- **Truth/attribution separation preserved**: measured items carry BOTH blocks independently (a derived delta can sit next to ASSOCIATED attribution).
- **Unknown is structural**: an epistemic section with reasons, not an error bucket. Notable honest property proven by tests: a linked metric's attribution can never be UNKNOWN inside the unified view *because inclusion itself is canonical-link evidence* (≥ ASSOCIATED) — while a decision with no linked metrics reports `no_linked_canonical_metrics`.
- **Chain consumed, not duplicated**: test asserts `assessment["execution_chain"] == execution_chain(...) minus generated_at`. The volatile timestamp strip is required by the determinism gate; the chain function itself is untouched (its own route keeps it).
- **L20**: recorded effectiveness/compare payloads surface byte-verbatim (tests seed 0.7 / a full compare dict and assert identity).

## E. Tests

`backend/tests/test_4h6_step4_engine.py` — **15 passed**:

1. nine-section contract + unknown decision ⇒ None
2. identity/expectation verbatim
3. outcome-record truth flip (unknown → recorded)
4. derived measured item with observation-id basis + SUPPORTED attribution
5. no-linked-metrics honest empty state
6. unknown aggregation incl. per-metric levels (SUPPORTED vs ASSOCIATED by link kind)
7. assessed = counts, not scores
8. chain consumed verbatim not duplicated
9. full-assessment byte-identical determinism
10–11. L20 verbatim effectiveness; safety envelope + forbidden-field scan
12–15. no-writes/no-events, tenant isolation, no-LLM source scan, compare payload verbatim

Combined 4H.6 suites: **49 passed** (Steps 2+3+4). Predecessor regressions previously re-run green (4H.5 10/10; 4H.4 suite included in combined runs).

## F. Audits

| Gate | Result |
|---|---|
| Read-only AST audit (all EIGHT 4H.6 functions): no session mutations, no DML constructors | GREEN |
| Schema gate vs Phase-E baseline | GREEN — zero delta |
| Candidate 4H.6 event rows | 0 |
| Baseline immutability | hash verified unchanged; snapshot to separate file `SLICE4H6_SCHEMA_POST_STEP4.json` |
| Determinism | byte-identical repeated assessments |
| Tenant isolation | sibling org ⇒ None |

## G. Deviations & Test-Side Notes

Product code needed no corrections during this step. Two TEST fixtures were corrected against true semantics: (1) a metric with a recorded baseline yields ASSOCIATED (temporal context), not UNKNOWN; (2) an unlinked metric is correctly NOT measured by the unified view — linkage is the inclusion criterion. Both corrections deepened the assertions rather than weakening them.

## H. Final Verdict

**STEP 4 = GREEN.** 4H.6 now has its coherent company-intelligence object: one decision in, one provenance-backed truth packet out — with every gap stated as unknown and zero manufactured certainty.

**STOP.** Step 5 (outcome cohorts / longitudinal read) not started, per run authorization.
