# SLICE 4H.6 — STEP 7 REPORT: Brain Routes + Intents + Collision Guards

**Scope:** Step 7 ONLY — expose the existing deterministic Step 4/5/6 read models through the Brain. **Verdict: GREEN.**

## A. Scope Honored
- No new intelligence engine, no new permission codes, no writes, no events, no schema/state changes.
- Routes reuse the exact 4H.5 governance chain verbatim: `require_permission("brain:read")` → `_people_access` → org-wide gate (`scoped → 404 "scope not found"` before any engine work).
- The Brain routes users to canonical evidence; it never generates a performance interpretation (no LLM on any 4H.6 path — source-inspected in Steps 5/6; routes/intents add none).

## B. Routes (`api/v1/brain.py`, appended after the 4H.5 block)
| Route | Surface | Rejection semantics |
|---|---|---|
| `GET /execution/company/decisions/{id}/performance` | Step 4 assessment | unknown/foreign id → `404 decision not found` |
| `GET /execution/company/performance/cohort?kind=&state=` | Step 5 cohort (empty cohort is a valid 200) | — |
| `POST /execution/company/decisions/compare` (`BrainDecisionCompareIn`) | Step 6 comparison | engine `rejected` dicts → `409` with full detail; **over-bound is a 409, never silent truncation** |

## C. Intents (`knowledge/intelligence_engine.py`)
Three ratified names from contract §8, placed at rule indices 3–5: after the 4H.5 lineage intents (plan/chain keep first claim on shared decision phrasing), before generic execution/recommendations.

| Intent | Phrases (narrow) | Handler |
|---|---|---|
| `company_decision_performance` | "how did the/that/this decision perform", "did the/that decision perform", "performance of the/that decision" | anchor resolve → assessment |
| `company_measured_change` | "did the/that/this decision improve …", "measured change from/after the decision", "metric change after the decision" | anchor resolve → assessment (measured section carries derived deltas + basis ids) |
| `company_decision_comparison` | "compare the outcomes of these/the decisions", "compare these/our decisions", "outcome comparison" | anchor-kind-scoped Step 5 cohort + explicit `canonical_route` pointer to POST compare; `honesty.compare_not_rank`; no verdict |

Determinism note: intent responses omit `generated_at` deliberately — underlying payloads are byte-deterministic (L19/L20); answers are reproducible.

**Product finding fixed during implementation:** the ratified phrase family "did the decision improve \<metric\>" was pre-captured by the generic `recommendations` rule's bare `"improve"` keyword (index 28). Resolution follows the established 4H.5 precedent: route the SPECIFIC phrases before the generic meaning. Only questions containing the exact long 4H.6 phrases change routing; every bare-"improve" question still reaches `recommendations`.

Also: `_resolve_decision_anchor` now returns the resolved row's `kind` (additive key; both return paths) so the comparison intent can scope its longitudinal context to comparable decisions. Existing consumers unaffected.

## D. Tests — 13/13 GREEN (`tests/test_4h6_step7_brain.py`)
Route happy paths (assessment recorded facts verbatim; cohort filters + shape; comparison neutral + order-preserving) · 404 unknown AND foreign ids (by public id and by raw pk) · all three rejection reasons as 409 with honest detail · foreign id inside valid pair proceeds with `not_found` · scoped caller 404 on all three routes · HTTP determinism · intent resolution ×3 with anchor assertions · HTTP collision guards (8 protected phrasings keep their original intents or at minimum never land on 4H.6) · **rule-level proof**: no earlier rule pre-captures any 4H.6 question, full scan resolves them to 4H.6, no 4H.6 keyword is a substring of any protected phrase, and protected phrases never resolve to a 4H.6 rule · intent queries write nothing (table+event stats identical).

Two fixture-side collisions were found and fixed during testing (product rules were correct): test vocabulary containing "bottleneck" (owned by `capacity`) and questions routed through the then-tail-placed block; fixtures now use unowned tokens ("vendor invoicing overhaul") verified programmatically.

## E. Audits
| Audit | Result |
|---|---|
| AST read-only audit — 3 new brain routes | GREEN |
| AST read-only audit — all TEN 4H.6 engine functions (re-run) | GREEN |
| Schema gate structural keys vs Phase-E baseline | GREEN — zero structural delta; `candidate_4h6_event_rows = 0` |
| Baseline immutability | hash verified; snapshot → separate `SLICE4H6_SCHEMA_POST_STEP7.json` |

## F. Regressions
| Suite | Result |
|---|---|
| Predecessor matrix (4H.1, 4H.2, 4H.3, 4H.4, 4H.5 incl. its intent-collision suite, 4G.6) | 58 passed |
| Cumulative 4H.6 steps 2–6 | 79 passed |

**Cumulative 4H.6: 92 tests green (16+18+15+13+17+13).**

## G. Boundary
Stopped after this report per authorization. Step 8 (minimal frontend window) NOT started.
