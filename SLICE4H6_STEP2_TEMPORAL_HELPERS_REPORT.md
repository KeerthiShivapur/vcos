# SLICE 4H.6 — STEP 2 REPORT: TEMPORAL MEASUREMENT HELPERS

**Verdict: GREEN.** Scope honored: Step 2 ONLY. No routes, intents, frontend, tables, columns, events, workers, or writes were added.

---

## A. Objective

Establish a deterministic, read-only temporal foundation for decision-anchored measurement: given one decision and one canonical metric, derive the explicit BEFORE/AFTER observation pair with its full temporal basis — without inventing timestamps, consuming non-actual observations, or persisting anything.

## B. Canonical Temporal Sources

| Source | Used for |
|---|---|
| `CompanyDecision.executed_at / approved_at / created_at` (company_operating.py) | anchor selection, in strict precedence order |
| `BusinessMetricObservation` (value, observed_at, **label**, unit, source_event_id) | baseline/comparison candidates; exact-once via `uq_bmo_exact_once` |
| `BusinessMetric` (key, label, kind, **direction**, unit) | canonical metric identity + direction metadata |
| `BusinessPerformanceLink(target_type="decision")` | existing decision↔metric associations (no new linkage system) |

## C. Decision Anchor Semantics (`_decision_anchor_dt`, engine :7939)

Precedence: `executed_at` → `approved_at` → `created_at`. The response always names the exact column used (`anchor_basis`). If a row carries no timing at all, basis is `"unknown"` — never a guessed time. Unknown decision ⇒ `None`.

## D. Baseline Semantics

Baseline = **latest** `label='actual'` observation with `observed_at <= anchor`. Deterministic tie-break by `(observed_at ASC, id ASC)`. Not "first ever" — selection follows the explicit rule recorded in `temporal_basis.selection_rule`.

## E. Comparison Semantics

Comparison = **earliest** `label='actual'` observation with `anchor < observed_at <= cutoff`. The nearest-after rule is deterministic and documented in-band; both Aug 11 vs Aug 20 style ambiguities are resolved by the declared rule, never silently.

## F. Window Semantics (L24)

Every measurement exposes exactly:

```json
"temporal_basis": {
  "anchor": "...", "baseline_as_of": "<= anchor",
  "comparison_as_of": "anchor + window_days",
  "window_days": 90,
  "selection_rule": {"baseline": "...", "comparison": "..."}
}
```

Window is the bounded class constant `PERF_WINDOW_DAYS = 90` (:7935), clamped to `[1, 3650]` when overridden. No hidden temporal basis anywhere.

## G. Observation-Label Filtering (L27)

Eligibility filter is the canonical column: only `label='actual'` rows are queried for measurement. Non-actual rows are aggregated per-label into `excluded_observations` (e.g. `{"forecast": 1}`) — preserved and visible, never silently consumed, never reclassified. Enforced by parametrized tests for `forecast`/`plan`/`estimated`.

## H. Recorded/Unknown Boundary (L21)

Each side resolves to either `{observation_id, value, observed_at, label, truth_level: "recorded"}` or `{value: null, truth_level: "unknown", reason}` with reasons `no_actual_observation_at_or_before_anchor` / `no_actual_observation_after_anchor_within_window`. Unknown is never zero, never baseline-substituted, never interpolated (gap test proves no fabricated midpoint).

## I. Derived Arithmetic Boundary (Q3/L21)

`delta` exists ONLY when both sides are recorded: `{value, percentage_delta, direction, delta_sign, truth_level: "derived", basis: [baseline_id, comparison_id]}`. Percentage is omitted (`percentage_unknown_reason: "baseline_value_zero"`) when baseline is 0 — never divided through, never fudged.

## J. Direction Handling

`BusinessMetric.direction` is surfaced verbatim on the metric block and on any delta. Tests prove `up_is_good`/`down_is_good` pass through and that NO judgment vocabulary ("improved", "favorable", "good") appears in responses. Direction ≠ verdict.

## K. 4H.5 Lineage Consumption

No new lineage. Decision↔metric association reads existing `BusinessPerformanceLink` rows only (`decision_linked_metrics`, :7969); the decision anchor reads existing lifecycle columns; ambiguity (multiple linked metrics, no explicit target) is REJECTED with the link list — never silently resolved.

## L. Determinism

Responses contain no `generated_at` and no randomness. Test proves two invocations over identical canonical rows are byte-identical (`a == b`).

## M. No-LLM Proof

Source-inspection test scans all four public helpers + anchor helper for banned tokens (`openai/anthropic/llm/completion/chat/httpx/aiohttp/requests`) — GREEN. The engine module imports no LLM clients.

## N. No-Write Proof

1. AST/source audit of the five new functions: zero `.add(/.delete(/.commit(/insert(/update(/flush` calls — GREEN.
2. Behavioral test: full table-count + `max(updated_at)` snapshot before/after helper calls is identical — GREEN.
3. Live probe run performed zero writes (read-only asyncpg queries).

## O. Tests

`backend/tests/test_4h6_step2_engine.py` — **16 passed**:

1. actual→actual recorded + derived delta + basis citation
2. missing baseline ⇒ unknown (not zero)
3. missing comparison ⇒ unknown (not zero)
4–6. forecast/plan/estimated excluded but counted
7. derived basis cites both observation ids (covered in 1)
8. no interpolation across gaps
9. direction preserved, never judged (both directions)
10. determinism byte-identical
11. no writes + no events (counts + max(updated_at))
12. (merged into 11)
13. no-LLM source inspection
14. anchor precedence executed>approved>created; unknown decision ⇒ None
15. unparseable anchor rejected, never invented
16. linked-metric resolution: single auto-select / multi reject / explicit key / tenant isolation
17. percentage unknown when baseline zero

## P. Schema / Event Regression

- New read-only probe `scripts/schema_probe_4h6.py` (never touches the Phase-E baseline; post-run snapshots go to `SLICE4H6_SCHEMA_POST_STEP2.json`).
- Baseline file hash verified UNCHANGED across the audit run.
- Schema keys (`public_table_count`, `company_actions_columns`, `candidate_4h6_event_rows`): **zero delta — GREEN**.
- Candidate 4H.6 event rows: **0**. Informational data-row growth (quality 268→296 etc.) remains the previously documented Phase-F acceptance fixture seeding — not produced by Step 2 (unit tests run against isolated test databases).

## Q. Final Verdict

**STEP 2 = GREEN.** The temporal foundation answers exactly one question — what counts as BEFORE, AFTER, and the window connecting them — deterministically, honestly labeled, and without creating or modifying any persistent state.

**STOP.** Steps 3+ not started, per run authorization.
