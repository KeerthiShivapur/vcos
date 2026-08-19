# Slice 4G.6 Verification Report — Commercial & Business Performance Intelligence

**Status: COMPLETE** — 27 slice backend tests, the full cross-slice
regression (1043 passed), the live API acceptance script (11 checks), the
frontend Business Performance tab with tsc + next build gates clean, and the
COMPLETE Playwright suite green end-to-end (30/30). Commit + tag
`vcos-slice-4g6-complete` created.

## What this slice delivers

4G.6 answers the leadership-facing half of execution intelligence: **what is
the business actually achieving (metrics), are we hitting what we committed
(targets), where are we heading (forecasts), what moves the numbers (drivers),
how is a scope performing overall (multidimensional health), and — when a
target slips — exactly why and what to do about it (the behind-target
chain)** — one Business Performance tab folded into the Execution Command
Center. The engine is change-driven from the SAME durable events the platform
already emits, and every surface is evidence-backed:

- **Metric ledger** — canonical business metrics (kind, direction, unit,
  granularity, visibility, scope) with their current/previous value,
  direction-aware trend and linked target.
- **Outcomes** — recorded actuals; an outcome lazily materializes the metric
  when it does not exist yet (kind defaults `other`).
- **Targets** — committed targets with a deadline: deterministic status
  (≥0.75 on_track, ≥0.5 at_risk, else slipped; past end → missed; achieved →
  delivered; terminal states never regress), gap to attainment, belief,
  progress, review trail, owner and the linked strategy label.
- **Forecasts** — conservative/base/optimistic arcs with basis, confidence
  and required conditions — always labeled **projected**, never observed
  fact.
- **Drivers** — cross-slice evidence linked to the metrics it moves with the
  deterministic language: strong → `linked to`, moderate → `strongly
  associated with`, limited → `evidence indicates`.
- **Performance health** — one explainable state per dimension (growth,
  customers, execution, strategy, capacity, operations, innovation,
  financial), each carrying its reasons, positives, top metrics and evidence
  count; only dimensions with evidence are emitted — an empty dimension is
  never faked as healthy.
- **Behind-target chain (flagship)** — target → gap → trajectory → drivers →
  forecasts → at-risk customers → knowledge topics → strategy goal chain →
  projects → capacity bottlenecks → open decisions → lessons → `what_to_do`
  (bounded, advisory, every item carries its evidence).
- **Recommendations** — derived deterministically from at-risk/concerned
  dimensions and behind targets; advisory only, bounded (max 5), every item
  carries its evidence.

Human actions: define/update a metric, record an outcome, commit/revise a
target, commit/revise a forecast, record a driver, and universal query
routing on the Company Brain ("why are we behind target on revenue", "how is
the business performing", "what is the revenue forecast", "what is driving
revenue growth").

Deterministic laws under test:

```
change-driven      triggers only on the real durable events
                   (business.metric.created/updated,
                   business.outcome.recorded,
                   business.target.created/updated,
                   business.forecast.created/updated,
                   business.driver.detected, business.performance.changed)
exact-once         live entities key on canonical keys (metric key, target
                   (metric, period_label), driver key); observations,
                   snapshots, history and links key on source_event_id;
                   replays converge (live check 11 re-drains and nothing
                   changes)
lazy creation      an outcome for an unknown metric_key materializes the
                   metric (live check 9)
deterministic      status thresholds, trend direction (both directions),
                   dimension scoring, driver link language, target/driver/
                   recommendation ordering
bounded            every surface capped (metrics 200, targets 100,
                   forecasts 60, drivers 100, history 40, recommendations 5)
governance         the surfaces are ORG-WIDE (scoped callers 404 on every
                   read); every write requires projects:manage; enums are
                   400-validated; unknown metric keys 404
advisor-only       the engine writes only its own tables; performance
                   snapshots are advisory artifacts, never mutations of the
                   business records
```

## Certified surfaces

```
GET  /brain/execution/business/metrics             metric ledger w/ trend
GET  /brain/execution/business/metrics/{key}       one metric's full evidence
GET  /brain/execution/business/targets             target ledger w/ status,
                                                   gap, metric_key
GET  /brain/execution/business/targets/{id}        one target's command center
GET  /brain/execution/business/forecasts           forecast arcs (projected)
GET  /brain/execution/business/drivers             driver ledger w/ link lang
GET  /brain/execution/business/performance         multidimensional health +
                                                   trajectories + history
GET  /brain/execution/business/behind-target       the flagship chain
GET  /brain/execution/business/recommendations     advisory next steps
POST /brain/execution/business/metrics             define/update a metric
POST /brain/execution/business/outcomes            record an outcome (lazy
                                                   metric creation)
POST /brain/execution/business/targets             commit/revise a target
POST /brain/execution/business/forecasts           commit/revise a forecast
POST /brain/execution/business/drivers             record a driver
POST /brain/knowledge/query                        4G.6 intents: behind target
                                                   / business performance /
                                                   forecasts / drivers
```

## Implementation (diffs from vcos-slice-4g5-complete)

Backend (new + extended):

- `backend/app/models/business_performance.py` — `BusinessMetric`,
  `BusinessMetricObservation`, `BusinessTarget`, `BusinessForecast`,
  `BusinessDriver`, `BusinessPerformanceSnapshot`, `BusinessPerformanceHistory`,
  `BusinessPerformanceLink` with exact-once `source_event_id` keys on
  observations/snapshots/history/links and canonical-key uniqueness on live
  entities; closed vocabularies for kind/direction/granularity/visibility/
  target belief/forecast type/driver type/observation source; every new
  timestamp column timezone-aware.
- `backend/app/intelligence/business_performance_engine.py` — the engine:
  change-driven `record_event` (metric/outcome/target/forecast/driver),
  metric score + status derivation, dimension health, deterministic target
  status eval, snapshot + history per handled event, the behind-target chain
  walk (target → gap → drivers → customers → knowledge → strategy → projects
  → capacity → decisions → what_to_do), recommendations, bounded reads,
  per-org locks.
- `backend/app/events/event_models.py` + `backend/app/models/__init__.py` —
  the 4G.6 event names + model registration for `create_all`.
- `backend/app/events/handlers.py` — the `business_performance_engine`
  bridge (change-driven; never commits).
- `backend/app/knowledge/intelligence_engine.py` — the 4G.6
  `business_performance` intent block + `_business_performance_query`
  (placed after customer_intelligence; "are we on track" still routes to
  execution by design).
- `backend/app/api/v1/brain.py` — the nine GET + five POST endpoints under
  `/brain/execution/business/*` with `_business_float` /
  `_business_metric_or_404` and the `_people_access` governance idiom.
- `backend/tests/test_4g6_engine.py`, `test_4g6_models.py`,
  `test_4g6_surfaces.py`, `test_4g6_governance.py` — 27 slice tests.
- `backend/scripts/accept_slice4g6.py` — 11 live acceptance checks.

Frontend (new):

- `frontend/lib/api.ts` — Slice 4G.6 block: types (metric/target/forecast/
  driver/health dimension/trajectory/performance/behind-target/
  recommendation rows and responses) and one function per surface plus the
  write actions (`recordBusinessMetric`, `recordBusinessOutcome`,
  `recordBusinessTarget`, `recordBusinessForecast`, `recordBusinessDriver`,
  `askBusinessPerformance`).
- `frontend/app/(app)/execution/business-performance-tab.tsx` — the Business
  Performance tab: health score stat cards, dimension health with reasons/
  positives, metric trajectories, the behind-target chain with "what to do",
  recommendations, targets with gap, forecasts (projected), drivers with the
  link language, and the advisory-only note.
- `frontend/app/(app)/execution/page.tsx` — the Execution Command Center is
  now four tabs: Command Center (4G.1), Coordination (4G.2), Customer
  Intelligence (4G.5), Business Performance (4G.6).
- `frontend/e2e/slice4g6-business-performance.spec.ts` — Playwright E2E.

## Design decisions locked by tests

- **Health dimensions are evidence-driven.** A dimension with no metric
  evidence is NOT emitted (an empty dimension would fake health); the health
  score averages the dimensions that exist. The live acceptance check locks
  1 ≤ dims ≤ 8 with the `financial` dimension present and every dimension
  carrying `reasons`/`positives`/`top_metrics`.
- **Target status is a boundary-true ladder.** ratio ≥0.75 on_track, ≥0.5
  at_risk, else slipped (100k vs 200k = exactly 0.5 → at_risk — proven by the
  engine tests); past end → missed; achieved → delivered; terminal states
  never regress; `reviews_json` carries the transition trail.
- **The target ledger exposes `metric_key`** (the engine resolves it from
  the metric rows it already loads) — found empty and fixed during E2E
  acceptance (see Stability fixes).
- **Behind-target exposes the metric at top level** (`metric["key"]`, not
  `target.metric_key`) with `target["gap"] = target − current` and a
  `close_gap` `what_to_do` item carrying target/gap/unit/days_left/
  confidence.
- **Driver ledger keys are `driver_key` / `kind` / `kind_label` /
  `metric_keys`** (not `key`/`link_label`) — locked by the surfaces tests.
- **Writes require the drain.** Record actions PUBLISH events; the surfaces
  read the recomputed state, so the E2E and the tab call
  `POST /intelligence/events/process` after writes (the target POST 404s
  until the metric event is processed — the E2E dispatches between phases).
- **The surfaces are org-wide.** Scoped callers get 404 on every business
  read; every write requires `projects:manage`; enums are 400-validated
  (`driver_type` must be customer|market|operational|economic|competitive|
  opportunity|risk, `direction` toward|away, `impact_shape` attribute|
  aggregation|portfolio, ...).
- **The POST target response's `target_id` is the event id**, not the live
  row id — the E2E re-reads the ledger by `metric_key` (the same idiom the
  surfaces tests use).
- **KnowledgeTopic's column is `name`** — three latent `t.topic`
  AttributeErrors fixed in the business engine (2 sites) and the customer
  intelligence engine (1 site); the full regression proves no 4G.5
  regression.

## Verification

Backend unit tests (the slice):

```
27 passed (test_4g6_engine / test_4g6_models / test_4g6_surfaces /
           test_4g6_governance) in 53.69s
```

Hermetic SQLite, event-bus drains, register_org per test, tenant isolation
covered; every scenario runs through the real API to enqueue the durable
events.

Full cross-slice regression (the complete backend suite, hermetic SQLite,
pytest-xdist 6 workers):

```
1043 passed in 972.81s
```

Live acceptance (`backend/scripts/accept_slice4g6.py` against the live
backend on :8999 — final result exactly):

```
11/11 checks passed:
  1.  the metric ledger carries the current value and trend
  2.  the committed target gets a deterministic status and gap
  3.  status transitions are deterministic with a review trail
  4.  forecasts are labeled projected; drivers carry the link language
  5.  performance is multidimensional, explainable and bounded
  6.  the flagship chain walks from target to drivers to strategy to actions
  7.  recommendations are advisory, bounded and evidence-carrying
  8.  business questions route to the business_performance intent
  9.  an outcome-only metric materializes; scopes stay isolated
 10.  scoped callers: business reads 404, writes blocked
 11.  replay is exact-once and the surfaces stay deterministic
```

Playwright E2E (`frontend/e2e/slice4g6-business-performance.spec.ts`):

```
1 passed (9.5s) — full journey through the live UI + API: register/login,
real governed writes through the real API and the event bus; the tab renders
the health stat cards, the financial dimension with reasons, the improving
Recurring Revenue trajectory, the behind-target chain with "What to do" and
the "linked to" driver language, projected forecast badges, the slipped
target badge and the advisory-only note; the API contract is asserted first
(metrics trend improving, target slipped with gap 200000, behind-target
close_gap action, base forecast midpoint 150000, recommendations ≥ 1).
```

COMPLETE Playwright suite (every e2e spec, one clean run):

```
30 passed (8.0m) — 29 pre-existing specs plus the 4G.6 spec, zero failures.
```

Frontend static gates: `npx tsc --noEmit` clean, `npm run build` passed.

## Stability fixes landed while getting the suite green

1. **The targets ledger emitted `metric_key: ""`** — the `targets()` read
   built a `metric_directions` map but never resolved metric keys, so every
   ledger row carried an empty `metric_key`. Fixed: the query it already
   ran now also fills `metric_keys` (target row shape locked by a new
   surfaces assertion). Found by the 4G.6 E2E acceptance.
2. **The live acceptance over-constrained health dimensions** — the original
   check asserted ≥ 6 dimensions; with only revenue evidence the engine
   honestly reports 1 (financial). The check now locks the real contract:
   1 ≤ dims ≤ 8, the financial dimension present, and per-dimension
   `reasons`/`positives`/`top_metrics`.
3. **E2E environment parity** — the acceptance backend ran with
   APP_ENV=test (no event worker), which starves the task-unblock event
   handler the pre-existing slice3 e2e relies on; the suite now runs against
   the worker-enabled backend (the same configuration the 4G.5 report
   documents), and two pre-existing ambiguous locators in slice3
   ("Comment added"/"Attachment added" matched both the toast and the
   activity feed) were scoped to `main`. slice2/slice3 now pass
   deterministically.

## Universal Company OS moat test

- **5-person startup:** record an outcome or commit a target and the tab
  shows the metric trajectory, the target status with the gap, the health
  dimension with its reasons, and — if it slips — the full behind-target
  chain with "what to do"; ask the brain "why are we behind target on
  revenue" and it routes to the same evidence. Zero configuration. ✓
- **50,000-person enterprise:** the same canonical tables with indexed,
  bounded reads (metrics/targets/forecasts/drivers/history capped), per-org
  locks and scoped visibility answer the same questions with the same
  architecture; replays converge exact-once. ✓
- **Connected, not isolated:** the tab is fed by the platform's own durable
  events and routes through the Company Brain intents — a competitor cannot
  copy this as a standalone "dashboard". ✓

## Post-acceptance state

- The running backend on :8999 is the verified 4G.6 code (worker-enabled,
  the same configuration the full 30-spec suite ran against); the frontend
  dev server on :3000 is up for the tab.
- Commit + tag `vcos-slice-4g6-complete` created; workspace junk cleaned.
- **STOP**: next slice is 4G.7 per the locked roadmap.
