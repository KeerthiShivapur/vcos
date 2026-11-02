# SLICE 4H.6 — VERIFICATION REPORT
## Outcome & Performance Intelligence

- **Contract**: `SLICE4H6_IMPLEMENTATION_CONTRACT.md` v0.2 (RATIFIED 2026-08-21)
- **Date of freeze run**: 2026-08-22
- **Verdict**: ✅ **VERIFIED — FROZEN**

---

## 1. What was frozen

A deterministic, READ-ONLY composition layer over existing canonical data:
per-decision unified performance assessments, an org-level longitudinal
outcome cohort, neutral bounded side-by-side comparisons — exposed through
three governed brain routes, three brain intents with collision guards,
and a typed frontend panel. Zero new tables/columns/events/states/
permission codes/writes/engine modules (L20–L28 upheld end-to-end).

Diff footprint (recency-audited): exactly the ratified file set —
`intelligence/company_operating_engine.py` (:7926–8936),
`api/v1/brain.py` (routes ~:8343–8421),
`knowledge/intelligence_engine.py` (intent rules idx 3–5 + dispatch +
handler branches), `frontend/lib/api.ts`, `frontend/app/(app)/execution/company-tab.tsx`,
six new test suites, `scripts/schema_probe_4h6.py`, reports/snapshots,
and the new `scripts/accept_slice4h6.py`. Nothing else.

## 2. Verification ring — results

| # | Gate | Result |
|---|------|--------|
| 1 | Live acceptance `backend/scripts/accept_slice4h6.py` vs running stack (:8999, APP_ENV=test) | **17 / 17 PASS** |
| 2 | Full pytest suite (chunked ×3, pytest-xdist `-n 4`) | **1223 passed / 0 failed** (419+396+408) |
| 3 | Regression matrix — predecessors (`test_4g7_engine`, `test_4h1_{engine,governance,surfaces}`, `test_4h2..4h5_engine`) | **88 passed** |
| 4 | Regression matrix — 4H.6 cumulative (`test_4h6_step2..step7`) | **92 passed** = 16+18+15+13+17+13 |
| 5 | Regression matrix — `test_4g6_models` | **4 passed** |
| 6 | Frontend gate `npx tsc --noEmit` | **exit 0** |
| 7 | AST read-only audit — TEN 4H.6 engine functions | **GREEN** |
| 8 | AST read-only audit — THREE brain routes | **GREEN** |
| 9 | Baseline immutability `SLICE4H6_SCHEMA_BASELINE.json` SHA256 | `D9DC1800…403F69` **unchanged** |
| 10 | Structural schema gate vs Phase-E baseline | **zero delta**: tables 437=437; company_actions 53 cols identical; candidate 4H.6 event names **0 rows**; row counters append-only (quality 268→353, tracks 94→144, action outcomes 26→28, observations 132→155, lineage 6→8 — cumulative test-fixture growth; none shrank). Snapshot: `SLICE4H6_SCHEMA_POST_FREEZE.json` |
| 11 | Anti-duplication banned-token scan (PerformanceEngine/AnalyticsEngine/KPIEngine/ScoringEngine/winner/rank/score/probability/forecast) across all 4H.6 additions | **clean** — hits are honesty comments and negation flags only (`forecast_excluded`, `no_*`, docstrings) |
| 12 | Runtime no-write proof (live) | GET-phase event total stable; canonical row counts stable across pure reads AND across compare/intents phase; decision detail immutable modulo its pre-existing `generated_at` |

### Live acceptance coverage (the 17 checks)
Recorded-outcome verbatim round-trip (L20) · unknown-stays-unknown never
zero-filled · derived delta citing both observation ids · explicit temporal
basis (anchor/executed_at/as-ofs/window=90) · SUPPORTED vs ASSOCIATED
attribution (never upgraded) · Track-invariant cohort histogram + derived
effectiveness mean citing both decision ids · comparison neutrality with
recursive banned-key scan · bounds REJECT never truncate (<2 unique, 6>5,
dedupe) · not_found semantics + full tenant isolation (404 / empty cohort /
cross-org compare rejected) · moat T1→T3 same decision strictly enriches
with ZERO code change · runtime read-only · byte-identical determinism
(generated_at stripped per L19) · schema gate vs baseline · intents resolve
with collision guards incl. scoped-member governance gating · honesty blocks
on every surface · frontend static parity.

## 3. Laws L20–L28 — final status

All ten laws verified live and in-suite: recorded effectiveness never
recomputed (0.8/0.55/0.7 round-trip); truth levels `recorded|derived|unknown`
with cited observation-id bases; attribution SUPPORTED (evidence_indicates)
vs ASSOCIATED (linked_to → association_link_only, temporal-only context);
COMPARE ≠ RANK (no winner/rank/score/probability keys anywhere — recursive
scan); temporal basis always explicit; cohort composition append-only with
CompanyDecisionTrack untouched (row count stable across reads); no learning,
no forecasting (canonical label vocabulary `actual|forecast|plan|target|
estimated|other`; non-actual labels excluded via `forecast_excluded`);
no people scoring anywhere.

## 4. PRE-EXISTING platform findings (out of 4H.6 scope — NOT fixed)

Discovered while standing up the live ring; **zero production code was
changed** in response (ratified confinement forbids touching these files
in this slice):

1. **VARCHAR(32) truncation on long decision public ids.**
   `company_memory.entity_id` is VARCHAR(32); CompanyDecision public ids are
   `dec:{kind}:{hex12}` — kind `commercial_action` yields 34 chars. SQLite
   (pytest dialect) does not enforce VARCHAR lengths, so the entire suite is
   blind to this; live Postgres raises `StringDataRightTruncationError`
   inside `_upsert_memory` during outcome recording, flush-poisoning the
   request session (PendingRollback → MissingGreenlet cascade → 500 on
   `POST …/outcome`). **Recommended follow-up slice**: widen to VARCHAR(64)
   and audit sibling id-bearing columns
   (`knowledge_recommendations.decision_id`, `ownership_relationships.object_id`,
   `expertise_evidence.entity_id`, …).
2. **Platform-wide drain in the outcome route.**
   `brain.py` `brain_company_record_outcome` drains
   `event_bus.process_pending(db, limit=50)` WITHOUT `organization_id`, so a
   single org's permanently-failing events re-poison every tenant's drain.
   **Recommended**: pass the caller's org id.
3. **Acceptance mitigations used (within confinement)**: acceptance seeds use
   sanctioned kinds whose ids fit 32 chars (`hire`=21, `delay_project`=30,
   `change_priority`=32); one-time hygiene closed THIS session's own stuck
   queue rows (events `processed_at` set, jobs closed) belonging solely to
   `4H6 …` acceptance organizations.

## 5. Environment & ops notes

- Server: uvicorn :8999, APP_ENV=test, workers-off; launched via
  Start-Process with logs `uvicorn-8999.out17.log/.err17.log`.
- Decision lifecycle is EVENT-SOURCED; the script drains between transitions.
- Measurement windows are FORWARD-looking from the decision anchor:
  baseline = latest actual ≤ anchor; comparison = earliest actual > anchor
  within [anchor, anchor+90d] (PERF_WINDOW_DAYS=90).
- Scoped-reader governance sequence replicated from the ratified
  `tests/_brain4d6_helpers.invite_scoped_reader` (drop default org-wide
  assignment; project-type governance scope; brain:read delegation).

## 6. Artifact index

- `backend/scripts/accept_slice4h6.py` — live acceptance (17 checks)
- `SLICE4H6_SCHEMA_POST_FREEZE.json` — freeze-run structural snapshot
- `SLICE4H6_SCHEMA_BASELINE.json` — immutable Phase-E reference
- Step reports STEP1–STEP8 (all GREEN)
- Test suites `tests/test_4h6_step{2..7}_*.py`

---

**Slice 4H.6 is COMPLETE, VERIFIED, and FROZEN.** Any further change to the
frozen surfaces requires a new ratified contract amendment.
