# SLICE 4H.6 — STEP 3 REPORT: TRUTH & ATTRIBUTION CLASSIFICATION

**Verdict: GREEN.** Scope honored: Step 3 ONLY. No routes, intents, frontend, tables, columns, events, workers, new engine/module, or writes were added.

---

## A. Objective

Classify — never create — facts: attach canonical numerical-truth levels (`recorded | derived | unknown`) and attribution levels (`SUPPORTED | ASSOCIATED | UNKNOWN`) to the Step 2 measurement foundation, using only repository evidence that already exists.

## B. Implementation Surface

`backend/app/intelligence/company_operating_engine.py`, same class as Step 2 (no new module/engine):

- `classify_measurement_truth()` :8247 — pure function over a Step 2 window result; no I/O.
- `classify_attribution()` :8304 — reads only `CompanyCausalEdge` hops touching the decision node (`("decision", decision_id)` convention, bounded by `MAX_CAUSAL_EDGES`) and `BusinessPerformanceLink(target_type="decision")` rows (bounded by `MAX_LINKED_METRICS`).
- `decision_metric_classification()` :8389 — Step 3 composition: `measured` + `attributed` + honesty envelope.

## C. Numerical Truth (L21) — exactly three levels

- **derived**: both sides recorded → `value`/`percentage_delta` with `basis = {baseline_observation_id, comparison_observation_id}` citing both source observations. Never presented as recorded.
- **unknown**: missing side(s) → explicit reason (`baseline_observation_missing` / `comparison_observation_missing` / `no_actual_observation_pair`); value stays `null`. Unknown is not zero (test-asserted).
- **recorded**: preserved at the observation level inside each side block (`truth_level: "recorded"`, verbatim values — L20 test proves 82.4 surfaces exactly as seeded, never recomputed).
- No fourth category exists anywhere in the response surface.

## D. Attribution (L22) — exactly three levels

| Evidence found | Level | Reason |
|---|---|---|
| Causal edge touching decision node, or link kind ∈ {`evidence_indicates`, `likely_contributor`} | **SUPPORTED** | basis cites edge/link ids |
| Link kind ∈ {`linked_to`, `strongly_associated_with`} | **ASSOCIATED** | `association_link_only` |
| Temporal co-presence only (recorded observation inside anchored window, no canonical links) | **ASSOCIATED** | `temporal_context_only` |
| Nothing | **UNKNOWN** | `no_canonical_attribution_basis` |

Chronology never upgrades: the temporal-only test asserts level stays below SUPPORTED.

## E. Independence Matrix (L21 × L22)

The dedicated matrix test produces a derived measurement (+6 from observations 80→86) alongside `attributed.level == "ASSOCIATED"` — proving "we know WHAT changed and by how much, but not WHY" is a first-class representable state. The two dimensions share no code path and no collapsed field.

## F. Anti-Collapse Guarantees (L23/L28)

No scores, no confidence numbers, no winner fields. The classification response carries zero numeric judgment fields; `honesty.no_confidence_number` / `no_people_scoring` are static flags. Negative audit scans output for `employee_score/person_score/manager_score/people_score/effectiveness_score/ranking/"winner"` — none present. Ontology intact: decision→quality, action→effectiveness, outcome→result, metric→measurement, person→nothing.

## G. Reuse, No Duplication

Step 3 duplicates nothing: `decision_metric_classification` calls the Step 2 helpers directly (`decision_metric_measurement` → anchor + window), inherits rejection semantics (ambiguity passes through unchanged — tested), and reuses existing constants/bounds. Attribution reads the existing 4H.1 causal graph and existing BPL associations — no parallel linkage system.

## H. Tests

`backend/tests/test_4h6_step3_engine.py` — **18 passed**:

1–9 truth: derived-with-basis, missing-comparison unknown (baseline stays recorded), missing-baseline unknown, forecast/plan/estimated exclusion (parametrized), no interpolation/fill, determinism byte-identical, L20 verbatim values
10–14 attribution: causal-edge SUPPORTED (edge id cited), evidence-link SUPPORTED (link id cited), association-link never upgrades, temporal-only ASSOCIATED + L21/L22 independence matrix, empty basis UNKNOWN
15–19 safety: no writes/no events, no-LLM source scan, tenant isolation (zero leaked basis ids across orgs; UNKNOWN without temporal context), people-scoring prohibition, ambiguity passthrough

Combined with Step 2 suite: **35 passed**. Predecessor regression: `tests/test_4h5_engine.py` **10/10 unchanged**.

## I. Audits

| Gate | Result |
|---|---|
| Read-only AST audit (all seven 4H.6 functions): no session mutations, no DML constructors | GREEN |
| No-LLM (source inspection tests + module import scan) | GREEN |
| Schema gate vs Phase-E baseline (tables / company_actions columns / candidate events) | GREEN — zero delta |
| Candidate 4H.6 event rows | 0 |
| Baseline immutability | hash verified unchanged; post-run snapshot written to separate file `SLICE4H6_SCHEMA_POST_STEP3.json` via `schema_probe_4h6.py` |
| Tenant isolation | unit-proven both directions |
| Determinism | byte-identical repeated classifications |

## J. Deviations

None. (One test-side fix during development: the tenant-isolation test initially mis-asserted that `has_temporal_context=True` must yield UNKNOWN; corrected to assert non-leakage of basis ids plus UNKNOWN when the flag is absent. Product code unchanged.)

## K. Final Verdict

**STEP 3 = GREEN.** The system can now say exactly how truthful each number is and exactly what evidence supports each claimed relationship — and can say "unknown" on either dimension without embarrassment.

**STOP.** Step 4 (unified assessment) not started, per run authorization.
