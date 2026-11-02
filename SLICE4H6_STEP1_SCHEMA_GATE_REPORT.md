# SLICE 4H.6 — STEP 1 SCHEMA-GATE REPORT

**Status:** GREEN — schema gate passed. Implementation authorized to proceed to Step 2 in a subsequent run.
**Date:** 2026-08-21
**Scope honored:** Step 1 ONLY (proof of derivability + zero-schema-delta). No engine, route, intent, frontend, model, or migration code was written.

---

## A. Authority & Scope

- Governing document: `SLICE4H6_IMPLEMENTATION_CONTRACT.md` **v0.2 RATIFIED 2026-08-21** (verbatim ratification recorded in contract header).
- Boundary under ratification: ZERO new tables, columns, events, states, permission codes, workers, engine modules, or writes.
- This step proves that every field of the unified read model is derivable from existing canonical sources before any implementation code exists.

## B. Baseline & Method

- Reference artifact: `SLICE4H6_SCHEMA_BASELINE.json`, captured at Phase E via `backend/scripts/schema_snapshot_4h6.py`.
- Method: (1) re-read ratified contract; (2) reconfirm §0 anchors against live source; (3) inspect every candidate source model/engine function for the fields the read model needs; (4) build a derivability matrix; (5) re-run the snapshot and diff **schema keys only** (`public_table_count`, `company_actions_columns`, `candidate_4h6_event_rows`) against baseline; data-row counts treated as informational.

## C. Canonical Source Inventory (anchors reconfirmed)

| Source | Location | Fields consumed by 4H.6 |
|---|---|---|
| `CompanyDecision` | company_operating.py :390 | id/kind/title/state/scope, outcome_kind :416, outcome_evidence_json :417, effectiveness :418, actual_outcome_compare :426, timestamps |
| `CompanyActionOutcome` | company_actions.py :144 | effectiveness :159 (Float, default 0.5), measured_at :163, evidence_json, uq action_id :168 |
| `OUTCOME_KINDS` | company_operating.py :140 | `successful \| partial \| unsuccessful` |
| Reconciliation writer | company_operating_engine.py :2433 | `{predicted, observed, effectiveness_observed, prediction_confidence, aligned, reviewed_at}` → `actual_outcome_compare` JSON |
| `CompanyStateHistory` | company_operating.py :280 | delta_json, risks_json :333, captured_at |
| `CompanyCausalEdge` | company_operating.py :450 | source/target type+id, kind (outcome edge kinds :161), confidence, evidence_ref, source_event_id |
| `CompanyDecisionQuality` | company_operating.py :653 | stage scores; `prediction_alignment=None` ⇒ "not yet measurable" precedent |
| `CompanyDecisionTrack` | company_operating.py :704 | append-only PREDICTION cohorts (untouched by 4H.6) |
| `BusinessMetric` | business_performance.py :101 | key/name/unit/**direction** (up_is_good/down_is_good) |
| `BusinessMetricObservation` | business_performance.py :147 | value, observed_at, unit, **label :171 = `actual\|forecast\|plan\|target\|estimated\|other`**, source, provenance, uq_bmo_exact_once :160 |
| `BusinessPerformanceLink` | business_performance.py :434 | target_type includes **`decision`**, kind ∈ `linked_to\|strongly_associated_with\|evidence_indicates\|likely_contributor`, weight, evidence_count, reasoning |
| Events | business_performance.py :423-425 | `company.decision.recorded`, `company.action.executed`, `company.outcome.recorded` |
| Caller access | company_context.py :172/:221 | `CallerAccess`, `resolve_caller_access` |

**New findings this step (strengthen the contract):**
1. `BusinessMetricObservation.label` canonically separates actual from forecast/plan/target/estimated values — L27 (No-Forecasting) compliance is a **column filter**, not an invention.
2. `BusinessDriver` docstring ("never presented as causation — always as a deterministic, evidence-backed association") is existing house precedent matching L22.
3. `BusinessPerformanceLink.target_type="decision"` with an explicit evidence-kind vocabulary gives SUPPORTED/ASSOCIATED attribution a canonical basis.

## D. Derivability Matrix (unified read-model field → canonical source)

| Read-model field | Derived from | Level |
|---|---|---|
| decision | `CompanyDecision` row (id, kind, title, state, scope) | recorded |
| observed | lineage rows (`CompanyAction` chain cols), `CompanyActionEvent` counts, `outcome_kind`+`outcome_evidence_json`, `CompanyStateHistory.delta_json` | recorded |
| measured | `BusinessMetric` × `BusinessMetricObservation` pairs where `label='actual'`, bracketing the temporal window | recorded (+derived deltas) |
| attributed | `CompanyCausalEdge` paths into/out of the decision node + `BusinessPerformanceLink(target_type='decision')` + observation provenance | classified (see F) |
| assessed | `actual_outcome_compare` (writer :2433 shape), recorded `effectiveness` (decision :418 / outcome :159), `CompanyDecisionQuality` stages | recorded |
| unknown | absence derivations: no observations / no links / no outcome row / `prediction_alignment IS NULL` | unknown |
| temporal_basis | decided/approved/executed/measured_at columns + observation `observed_at` pair | derived (L24 structure) |
| execution_chain | `execution_chain()` engine fn (4H.5, pure read) | recorded |
| honesty flags | composed statically in code from the above | static |

Every field maps to an existing column or an existing pure function. No field requires new persistence.

## E. Numerical Truth Levels (L20/L21)

- **recorded**: `effectiveness` (both locations), `outcome_kind`, observation `value`s, `actual_outcome_compare` sub-fields — surfaced verbatim, never recomputed (L20).
- **derived**: only arithmetic over ≥2 observations with `label='actual'` (deltas, % change, direction-aware sign via `BusinessMetric.direction`); each response carries its basis (observation ids/timestamps). Single-observation or zero-observation cases resolve to `unknown` with reason — never 0, never interpolated (L21).
- **unknown**: explicit `{value: null, level: "unknown", reason}` blocks; house precedent exists (`prediction_alignment=None` ⇒ "not yet measurable").

## F. Attribution Levels (L22)

- **SUPPORTED**: a `CompanyCausalEdge` path connects decision→…→outcome/metric node, OR a `BusinessPerformanceLink` targets the decision with kind ∈ {`evidence_indicates`, `likely_contributor`}.
- **ASSOCIATED**: temporal sequence only, or link kinds {`linked_to`, `strongly_associated_with`} without causal-edge support.
- **UNKNOWN**: neither. Temporal sequence is never labeled causality.

## G. Temporal Windows (L24) — derivable without new tables

Anchor = first available of executed_at / measured_at / decided_at (existing columns). Baseline = latest `label='actual'` observation at or before anchor−ε; comparison = earliest/latest such observation after anchor within a bounded constant window. Window constants live in code. All inputs are existing timestamped rows.

## H. Cohorts on Read (Q2)

Outcome cohorts are computed per-request via GROUP BY over `CompanyDecision` + outcomes. `CompanyDecisionTrack` semantics untouched — its writer (`update_tracks`) remains prediction-only and append-only (L25).

## I. 4H.5 Execution-Chain Consumption

`execution_chain(db, organization_id, decision_id, access)` is a pure async read returning a dict (verified signature + docstring). It is embedded as-is; lineage columns are indexed; no mutation path exists in the function.

## J. No-Write Proof

All listed sources are consumed via SELECT-only queries. `company_operating_engine.py` contains no event-publish calls in its derivation functions (verified during 4H.5 audit; unchanged since — Phase D zero-drift). New 4H.6 functions will be pure query composers.

## K. No-New-Event Proof

Candidate 4H.6 event names: **0 rows** in `company_events` (live probe). Event catalog unchanged. A read layer emits nothing.

## L. No-LLM Proof

Import scan of `company_operating_engine.py`: zero LLM/client/http imports. All derivations are SQL + deterministic arithmetic.

## M. No-People-Scoring Proof (L28)

Ontology mapping holds: decision→quality, action→effectiveness, outcome→result, metric→measurement. `assignee_id`/`recorded_by` exist upstream but no 4H.6 surface emits person-keyed effectiveness or quality. `CompanyDecisionQuality` docstring already fixes quality as "attribute of the DECISION, never of a person."

## N. Live Schema vs Baseline

```
SCHEMA GATE: GREEN - zero delta
tables: 437 | company_actions cols: 53 | candidate 4h6 event rows: 0
informational (data growth from Phase-F acceptance fixtures, not drift):
  quality 268→296 · tracks 94→104 · outcomes 26→28 · observations 132→135 · lineage actions 6→8
```

## O. Deviations & Notes

1. **Baseline-file hygiene incident (resolved):** `schema_snapshot_4h6.py` overwrites `SLICE4H6_SCHEMA_BASELINE.json` on every run; the Step-1 re-run clobbered the Phase-E artifact. The file has been restored to the true Phase-E captures (row counts 268/94/26/132/6; schema keys were identical either way). Recommendation for Step 2+: make the script refuse to overwrite without `--force`, or write timestamped snapshots. Not fixed now (out of Step-1 scope; noted here per no-silent-fix rule).
2. Data-row growth between Phase E and now is fully attributable to the six Phase-F acceptance suites' fixture seeding. Schema gate unaffected.
3. No unrelated drift found. No contract contradiction found.

## P. Verdict

**GREEN.** Every unified read-model field is derivable from canonical sources; all truth/attribution levels have canonical bases; temporal windows need no new table; cohorts derive on read; 4H.5 chain consumes cleanly; zero writes/events/LLM/people-scoring; live schema matches the ratified baseline exactly.

**STOP — Step 1 complete. Step 2 (temporal measurement helpers) NOT started, per run authorization.**
