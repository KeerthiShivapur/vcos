# Slice 4H.2 Verification Report — Universal Organizational Decision Intelligence

**Date:** 2026-08-19
**Slice:** 4H.2 — Universal Organizational Decision Intelligence: first-class decision object (`CompanyDecision`), advisory evaluate → recommend pipeline, alternatives + why-not reasoning, precedent compounding, contradiction surfacing, temporal as-of, exact-once replay of 8 new `company.decision.*` events, brain intent routing (`decision_reason` / `decision_alternatives`), and the Decision Intelligence frontend tab — all law-checked against the RATIFIED `SLICE4H2_IMPLEMENTATION_CONTRACT.md`. Slice 4H.2 adds NO second approval path: pre-approval states are never executable (409, zero false events).

## Acceptance results

| Script / check | Result |
|---|---|
| `backend/scripts/accept_slice4h2.py` (live, 19 checks) | 19 passed, 0 failed (exit 0) |
| Backend slice-4H.2 pytest (`tests/test_4h2_engine.py`, 9 tests) | 9 passed |
| Baseline regression on final code (4G.7 + 4H.1 engine/governance/surfaces + 4H.2, 51 tests) | 51 passed (4:36) |
| Prior full-suite signals (see below) | 42/42 (4G.7 + 4H.1) Green under full `pytest -q` |
| 4H.1 live regression (`accept_slice4h1.py`) | 16 passed, 0 failed |
| 4G.7 live regression (`accept_slice4g7.py`) | 14 passed, 0 failed |
| Frontend `npx tsc --noEmit` | passed (exit 0) |

All runs executed against the live stack (uvicorn `http://localhost:8999`, Postgres `vcos2`). The full `pytest -q` suite (126 `tests/test_*.py`) is **1094 passed, 0 failed (1:19:47)**. That run was launched before the two late verification fixes below; modules imported after the edits ran on final code, and both fixes are each verified individually on final code by the 51-test baseline and the 19-check acceptance.

## Coverage exercised by `accept_slice4h2.py` (maps to contract §15 tests 1–15 + invariants)

1. **Decision capture (test 1)** — advisory evaluate returns kind, title, rationale, evidence_count, state `evaluated`, `evidence_written=1`; the row lives in the one canonical `CompanyDecision` store (no second table).
2. **Advisory recommend + reads (tests 2–4)** — recommend transitions to `recommended`; detail reads 1 evidence, 2 alternatives, exactly one `chosen`, 1 why-not row; prediction surface exposes `confidence_band: "not_recorded"`, `not_yet_measurable: False`, and the quality surface shows 2 stage snapshots — never a naked number.
3. **Why-not write is exact-once (test 3)** — changed once, replays no-op (`changed=False`), writing a `why_not` onto the chosen alternative is rejected (400).
4. **Pre-approval law (test 12 backward-compat)** — `execute` and `outcome` on a `recommended` decision return 409 with `detail.rejected=True`, and `company.action.executed` + `company.outcome.recorded` event counts stay 0 (no false events).
5. **Governed 4H.1 loop closes (tests 4–6)** — the existing approve path is unchanged; after execute + outcome, the outcome quality stage `outcome_recorded` composes, `kind:hire` cohort track measures ≥1 decision, the prediction surface reconciles `actual_outcome_compare.aligned=True`, and the lesson is visible on the company memory surface.
6. **Bounded shapes (tests 7, 14)** — 50 evidence rows cap at 40, 8 alternatives cap at 5, precedent recall capped at `limit`; identical parameterized schema across scopes.
7. **Temporal as-of (test 13)** — `as_of` strictly excludes late evidence (`evidence_count=0`); `include_partial` keeps the count 0 but lists the late evidence under `evidence_incomplete` (no backward leakage).
8. **Tenant isolation (test 11)** — a second organization sees `total=0` decisions and 404 on the first org's decision id.
9. **Exact-once replay (test 12)** — re-publishing evaluate + recommend with the SAME `decision_id` writes 0 new evidence and leaves all 8 `company.decision.*` event counts and the list total byte-identical.
10. **Brain intent routing (test 7)** — `/brain/knowledge/query` routes `decision_reason` / `decision_alternatives` and pins the answers to the latest decision.
11. **Pagination + filters (test 14)** — `limit`/`page` honored, `state` filter applied, rows bounded.
12. **Impact (test 8)** — `GET /decisions/{id}/impact` is bounded (`direct ≤ depth`) and reports observed impact 0 for a not-yet-measured decision (honest, not a fake 0).
13. **Determinism (tests 12, 13)** — re-querying the list and detail returns identical surfaces modulo `generated_at`.
14. **Contradiction surface shape (test 10)** — the surface is bounded and reports `contradictions_open` in quality.
15. **All-eight-events ledger (test 12)** — every 4H.2 event lands and stays stable under re-drain.
16. **What-if advisory-only (test 9)** — per-alternative what-if returns `advisory_only: True` with every scenario `not_a_prediction: True` and bounded consequences; decision count and evaluate/recommend event counts are unchanged — nothing executed.
17. **Contradiction honesty vs a recorded lesson (test 10)** — after an unsuccessful governed outcome records a lesson containing the decision's metric key, a matching recommendation surfaces `evidence_is_conflicting: True` with both sides (side_a = the recommendation, side_b = the lesson memory id), and quality reports `contradictions_open ≥ 1`.

Suite-wide invariants (a–c) are enforced throughout: responses carry `advisory_only` / `not_a_prediction` flags, cited facts carry decision/evidence/lesson ids (no opacity, no blame on persons — outcomes cite decision + evidence ids only), every confidence-like figure is accompanied by its evidence/contradiction context.

## Determinism / honesty guarantee

- All 4H.2 surfaces are deterministic compositions of recorded rows — no LLM calls in evaluate/recommend/track/contradiction paths. What-if reuses the existing bounded `what_if()` engine per alternative (`not_a_prediction`, `advisory_only`); it never creates, executes, or mutates anything.
- Contradiction surfacing returns both sides with provenance (never silently selects a side); precedence linking, contradiction writing, quality snapshots, and track rollups are exact-once on natural keys so replays converge to identical list lengths.
- 4H.2 adds no second approval path: execute/outcome rejections for `proposed / evaluated / recommended / declined / assessed` happen before any event is published.

## Notable fixes during verification

- **`OUTCOME_KINDS` NameError in `update_tracks`** — surfaced by the unit cycle; added `OUTCOME_KINDS` to the `app.models.company_operating` import block.
- **Alternatives seeding on evaluate** — alternatives were re-written/re-emitted on replay; now seeded only `if created and payload.get("alternatives")`, so replay never mutates alternative/why-not rows or re-publishes `alternatives.recorded` / `why_not.recorded` / `precedents.linked`.
- **Recommend guard** — the early-return past-state set was missing `"recommended"`, which re-emitted `company.decision.recommended` on replay; added to the guard.
- **Contradiction detector dead-code bug (live-found)** — `record_decision_lesson` stores the lesson text in `memory.outcome` and the outcome kind in `memory.outcome_type`, but `_detect_contradictions` only checked `mem.outcome` against `("unsuccessful","partial")` — so contradictions against decision-derived lessons could never fire. The detector now checks both `outcome_type` and `outcome`. This is exactly the case contract §15 test 10 demands; the new acceptance check 17 proves it live.
- **Outcome handler `NameError` (live-found)** — `record_outcome` only bound `result` inside the `predicted_outcome is not None` branch, so recording an outcome on a decision without a prediction crashed the event worker. `result` is now built unconditionally via `_decision_payload(row)`.
- **Acceptance script**: 409 rejections assert through `detail.rejected` (FastAPI detail dict); quality stages asserted as a superset; replay must reuse the SAME `decision_id`; as-of partial reports `evidence_incomplete`; the as-of/quality check reads the stable post-drain surface instead of the outcome response's inline compare (which races the global queue); decision approves persist via the event worker, so the governed execute step drains before proceeding.
- **Environment**: leftover event-queue jobs from a force-killed server session caused connection-pool meltdown on restart; cleared `background_jobs` (terminal `failed`/`retry` rows) and restarted. Probe scripts must not use PowerShell 7-only `-SkipHttpErrorCheck` (5.1 rejects it); server health is confirmed by a 401 on `/api/v1/auth/me`.

## Architecture notes

- **Routes (28)** appended to `app/api/v1/brain.py`: evaluate/recommend, detail, alternatives, why-not, prediction, quality, precedents/search, contradictions, impact, tracks, what-if, outcome/execute 4H.1-compatible guarded writes; 409s use the `{rejected, decision_id, state, reason}` detail shape. Outcome/execute include an inline queue drain.
- **Engine** `app/intelligence/company_operating_engine.py`: the whole 4H.2 block (evaluate through contradictions). Bounded reads everywhere (`MAX_DECISION_EVIDENCE=40`, `MAX_*` caps, top-N precedents). Deterministic precedent ranking from context-signature + outcome-of-record + evidence weight; contradiction rows unique on `(org, decision_id, contradiction_key)`.
- **Intent routing** `app/knowledge/intelligence_engine.py`: 54 `_INTENT_RULES`, 6 4H.2 branches in `_company_operating_query` mapping answers to `decision_reason` / `decision_alternatives` / `company_operating` / `company_universal` with `scope`.
- **Events** `app/events/event_models.py`: 8 `company.decision.*` catalog entries; internally-produced rows (alternatives/why-not/precedents/contradictions/quality/tracks) publish their audit event only when a row was actually written (replays converge).
- **Frontend** `lib/api.ts` (~30 4H.2 helpers + `CompanyDecisionRow4H2` / `CompanyEvidenceIn` / `CompanyAlternativeIn` types) and `app/(app)/execution/company-tab.tsx` (Decision Intelligence panel: prediction/quality/alternatives/why-not/precedents/contradictions/impact; evaluate + advisory recommend; `tsc` clean).
- **Tests** `tests/test_4h2_engine.py` — 9 unit tests (SQLite) covering evaluate/recommend/reads, why-not exact-once, pre-approval 409, governed loop closure, as-of, replay convergence, tenant isolation, brain routing.

## Repository state

- HEAD `cd653b8` + the verification fixes above (uncommitted working tree at report time).
- Slice 4H.2 is complete; the next slice is not started.