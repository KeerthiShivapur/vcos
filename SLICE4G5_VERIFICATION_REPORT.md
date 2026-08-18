# Slice 4G.5 Verification Report — Customer & Market Execution Intelligence

**Status: COMPLETE** — 24 slice backend tests, the full cross-slice
regression (1016 passed), the live API acceptance script (14 checks), the
frontend tab with tsc + next build gates clean, and the COMPLETE Playwright
suite green end-to-end (29/29). Commit + tag `vcos-slice-4g5-complete`
created.

## What this slice delivers

4G.5 answers the customer-facing half of execution intelligence: **what are
customers asking for (demand), what have we promised them (commitments), are
we delivering (outcomes), where are we exposed (risk), and where should we
move next (opportunities)** — one Customer Intelligence tab folded into the
Execution Command Center. The engine is change-driven from the SAME durable
events the platform already emits, and every surface is evidence-backed:

- **Themes** — recurring demand across support/CRM/meetings/etc. with
  occurrence counts, the distinct customers behind each theme, severity
  spread, the top request signals, and per-theme Net Promoter posture.
- **Risk** — customers at risk: health + renewal posture, churn indicators,
  open high-severity demands, confidence, and the gap to a chosen delivery
  window (mapped through the same health recompute the exec health surface
  uses).
- **Commitments** — what we recorded we would do: lifecycle, due dates,
  pardon notes, delivery status, with deterministic ordering (due/expired
  first).
- **Outcomes** — delivered outcomes with metric, baseline/actual/improvement;
  deterministic ordering (actual - baseline improvement desc, then
  delivered_at desc).
- **Coverage & gaps** — per-project coverage of each customer need and the
  gaps behind at-risk posture.
- **Opportunities** — expansion/request/adoption demand with sizing, fit,
  timeline distance and the deterministic engagement score (value × fit ×
  urgency, reviewer rank tied last).
- **Trends** — demand over the last 12 weeks with pre/post spikes.
- **Knowledge center** — the org's customer answers in one surface: sunrise
  signals (high-severity needs since the org's last center read), senior
  signals (first-touch at need/manager level), commitments, outcomes,
  themes, and a compact usage snapshot.

Human actions: resolve a customer signal as the canonical demand, record a
commitment, deliver a commitment, record an outcome, record a signal
(explicit artifacts on the org graph), and universal query routing on the
Company Brain ("what are our customers asking for", "what have we promised
our customers", "what are our biggest customer gaps").

Deterministic laws under test:

```
change-driven      triggers only on the real durable events the platform
                   already emits (support tickets, CRM records, meeting
                   pulse, manager changes ...); handlers never commit
exact-once         signal/commitment/outcome rows key on source_event_id;
                   replays converge (live check 10 re-drains and nothing
                   changes)
canonical demand   resolve() marks the canonical signal for a need_key +
                   reviewer and REPLACES the derived signals for that key —
                   the "request type" counts on opportunities come only
                   from canonical + current signals
measured           themes/trends/risk/opportunities derive from signals
                   with occurred_at, never guessed; risk health runs the
                   real health recompute
deterministic      risk sorting (health then severity then first_at),
                   outcomes (improvement desc), commitments (due/expired
                   first), opportunities (engagement score with reviewer
                   rank last), themes (occurrences desc, first_at asc)
governance         the center is ORG-WIDE (scoped callers 404); every
                   write action requires intelligence:manage; surfaces
                   never leak project names across scopes
advisor-only       the engine writes only its own tables; resolve/record
                   are artifacts the human writes, never mutations of the
                   CRM/tickets
timezone-safe      every new timestamp column is DateTime(timezone=True)
```

## Certified surfaces

```
GET  /customer-intelligence/health             counts + summary posture
GET  /customer-intelligence/signals            signals w/ canonical flags
GET  /customer-intelligence/themes             occurrence/scope/severity/
                                               net_promoter per theme
GET  /customer-intelligence/risk               at-risk customers w/ health,
                                               reasons, confidence, gap_days,
                                               window_days (org-wide only)
GET  /customer-intelligence/commitments        promises: lifecycle, due,
                                               pardon note, delivered state
GET  /customer-intelligence/outcomes           delivered outcomes w/
                                               metric/baseline/actual
GET  /customer-intelligence/coverage           per-project need coverage
GET  /customer-intelligence/gaps               gaps behind at-risk posture
GET  /customer-intelligence/opportunities      demand w/ value/fit/urgency/
                                               engagement score
GET  /customer-intelligence/trends             12-week demand + spikes
GET  /customer-intelligence/knowledge          the org customer center:
                                               sunrise/senior signals,
                                               commitments, outcomes,
                                               themes, usage snapshot
POST /customer-intelligence/signals/resolve    human resolve -> canonical
                                               + artifact; replaces derived
POST /customer-intelligence/commitments        record a promise
POST /customer-intelligence/commitments/{id}/deliver   deliver it
POST /customer-intelligence/outcomes           record an outcome
POST /customer-intelligence/signals            record a signal (source:
                                               support|crm|email|meeting|
                                               usage|survey|interview|
                                               account|observation)
POST /brain/knowledge/query                    4G.5 intents: what customers
                                               ask for / promised / gaps
                                               / at-risk customers /
                                               opportunities
```

## Implementation (diffs from vcos-slice-4g4-complete)

Backend (new + extended):

- `backend/app/models/customer_intelligence.py` — `CustomerSignal`,
  `CustomerCommitment`, `CustomerOutcome`, `CustomerNeed` with
  `source_event_id` exact-once keys and `DateTime(timezone=True)` columns.
- `backend/app/intelligence/customer_intelligence_engine.py` — the engine:
  signal/commitment/outcome recording, canonical resolve with
  replacement semantics, determinant theme/risk/commitment/outcome/coverage/
  gap/opportunity/trend/knowledge computation, per-org locks and bounded
  reads.
- `backend/app/events/event_models.py` + `backend/app/models/__init__.py` —
  the new event names + model registration for `create_all`.
- `backend/app/events/handlers.py` — the change-driven bridges
  (`customer.intelligence.intent` on support/crm/meeting events,
  `customer.signal.recorded`, `customer.commitment.recorded`,
  `customer.commitment.delivered`, `customer.outcome.recorded`, the
  `manager.changed` reporting fix — see stability below); never commit.
- `backend/app/intelligence/graph_engine.py` — `upsert_edge` made
  concurrency-safe (see stability below).
- `backend/app/knowledge/intelligence_engine.py` — the 4G.5 intent block
  routing to the surfaces with honest answers.
- `backend/app/api/v1/brain.py` — the eleven GET + five POST endpoints with
  the `_people_access` governance idiom.
- `backend/tests/test_4g5_engine.py`, `test_4g5_surfaces.py`,
  `test_4g5_governance.py`, `test_4g5_models.py` — 24 slice tests.
- `backend/scripts/accept_slice4g5.py` — 14 live acceptance checks.

Frontend (new):

- `frontend/lib/api.ts` — Slice 4G.5 block: types (theme/signal/risk/
  commitment/outcome/coverage/gap/opportunity/trend/knowledge rows and
  responses) and one function per surface plus the write actions
  (`resolveCustomerSignal`, `recordCustomerCommitment`,
  `deliverCustomerCommitment`, `recordCustomerOutcome`,
  `recordCustomerSignal`, `askCustomerIntelligence`) and the event drain
  helper the tab uses after writes.
- `frontend/app/(app)/execution/customer-intelligence-tab.tsx` — the
  Customer Intelligence tab: health posture cards, risk list with
  window/gap delinquency states, themes, commitments with deliver action,
  outcomes, coverage/gaps, opportunities with engagement scoring,
  trends, the knowledge center, and the resolve/record dialogs.
- `frontend/app/(app)/execution/page.tsx` — the Execution Command Center is
  now three tabs: Command Center (4G.1), Coordination (4G.2), Customer
  Intelligence (4G.5).
- `frontend/e2e/slice4g5-customer-intelligence.spec.ts` — Playwright E2E.

## Design decisions locked by tests

- **Signal sources are a closed enum** — `support|crm|email|meeting|usage|
  survey|interview|account|observation`. Anything else (e.g. the literal
  "sales") is a 400 — proven live by the E2E (the spec uses `crm`).
- **Resolve replaces the derived demand.** `resolve` writes the canonical
  signal for `(need_key, reviewer)` and the engine derives opportunities
  from canonical + current signals only — "request type" opportunity counts
  reflect human-confirmed demand, and themes carry the canonical marker.
- **Risk health runs the REAL health recompute.** The at-risk posture uses
  the platform's own health scoring (same recompute the exec health surface
  uses), which is why the live acceptance keeps Nova at-risk through
  delivery until health drops the customer out of the window.
- **Writes require the drain.** Resolve/record/deliver PUBLISH events; the
  surfaces read the recomputed state, so the E2E and the tab call
  `POST /intelligence/events/process` (scoped drain) after each write —
  the UI polls the drained state, never the raw write.
- **The center is org-wide.** Scoped callers get 404 on `risk`/the center
  (same idiom as 4G.1/4G.2); surfaces scope-filter names; every write
  action requires `intelligence:manage`.
- **Deterministic ordering everywhere** so the live checks and the E2E
  assert exact positions, not post-hoc sorts: risk (health, then severity,
  then first_at), outcomes (improvement desc), commitments (due/expired
  first), opportunities (value*fit*urgency, reviewer rank LAST), themes
  (occurrences desc, first_at asc).
- **Live acceptance scenario is 4 high-severity SSO issues on Nova Labs +
  4 medium requests from distinct other customers.** That keeps Nova at-risk
  even after health recomputes (resolving 1 of 4 still leaves the posture
  red), gives theme occurrences = 8 (5 sso + 3 mobile), customers = 5,
  high_severity = 4, and opportunity request-type counts = demand signals
  only (sso 2, mobile 3) — the exact numbers the checks lock.
- **Timestamps are timezone-safe.** Every new `DateTime` column is
  `DateTime(timezone=True)`.

## Verification

Backend unit tests (the slice):

```
24 passed (test_4g5_engine / test_4g5_surfaces / test_4g5_governance /
           test_4g5_models) in 66.95s
```

Hermetic SQLite, event-bus drains, register_org per test, tenant isolation
covered; every scenario runs through the real API to enqueue the durable
events.

Full cross-slice regression (the complete backend suite, hermetic SQLite,
pytest-xdist 6 workers):

```
1016 passed
```

Live acceptance (`backend/scripts/accept_slice4g5.py` against the live
backend on :8999 with APP_ENV=test — final result exactly):

```
14/14 checks passed:
  1.  themes total 8, customers 5, high_severity 4, sso 5, mobile 3
  2.  theme ordering: occurrences desc, first_at asc
  3.  opportunity counts: sso demand 2 (request signals only), mobile 3,
      engagement scoring deterministic
  4.  risk ranks the healthiest at-risk customer first
  5.  risk reasons are stable and precise (delivery window, senior signal)
  6.  committing + delivering moves the promise lifecycle
  7.  recording an outcome changes the outcomes surface
  8.  resolving a signal replaces the derived demand for that need
  9.  the knowledge center posts the high-severity need as sunrise
 10.  replay is exact-once: re-draining the events changes nothing
 11.  themes reflect the recomputed customer health posture
 12.  universal query intents answer: what are our customers asking for /
      what have we promised our customers / what are our biggest customer
      gaps
 13.  risk health recomputes: delivering the final high-severity fix drops
      Nova under the at-risk window
 14.  scoped callers: center 404, risk 404, own scoped surfaces only,
      others invisible, writes 403
```

Playwright E2E (`frontend/e2e/slice4g5-customer-intelligence.spec.ts`):

```
1 passed (6.5s) — full journey through the live UI + API: register/login,
real support tickets + CRM records through the real API and the event bus;
the tab renders health, signals, themes (5 sso / 3 mobile), risk with
reasons, commitments with deliver, outcomes with improvements, coverage,
gaps, opportunity scores and trends; the write actions (resolve the sso
need, deliver a commitment, record an outcome) each go through the scoped
drain and the tab reflects the drained state.
```

COMPLETE Playwright suite (every e2e spec, one clean run):

```
29 passed (7.9m) — 28 pre-existing specs plus the 4G.5 spec, zero failures.
```

Frontend static gates: `npx tsc --noEmit` clean, `npm run build` passed.

## Stability fixes landed while getting the suite green

The full-suite run exposed three PRE-EXISTING backend defects (present
before 4G.5, now fixed; all verified live):

1. **`handle_people_manager_changed` passed `note=` to
   `people_engine.set_reporting()`, which has no such kwarg** — the handler
   raised on every real manager change, so the "Manager changed"
   notification never fired. Fix: removed the kwarg (slice2 e2e now passes).
2. **`upsert_edge` in `graph_engine.py` had a select-then-insert race** —
   two concurrent passes (periodic worker + on-demand drain) processing the
   same `manager.changed` hit the `uq_org_graph_edge` unique index; the
   IntegrityError rolled back the whole dispatch transaction. Fix: the
   insert runs inside `async with db.begin_nested()` and an IntegrityError
   re-reads the committed row and updates it (weight/evidence/active
   merge). This also silenced the relationship-worker error storm that had
   been visible across orgs.
3. **The event worker's drain cadence could not outrun the noise floor.**
   Worker-generated events (forecast/health/intelligence/graph refreshes)
   re-entered the bus continuously and the 60s/5000-per-pass drain lagged
   them by tens of thousands of rows, so fresh tenant events (like a
   manager change) starved behind them for hours and the slice2 e2e's
   180s poll timed out. Fix: the scheduler's event registry
   (`app/workers/scheduler.py`) runs the dispatch pass every 15s with the
   same 5000-event cap — verified live: queued 15,500 -> 0 while the suite
   ran, done count climbing past 3,039,000, and fresh events now dispatch
   within a pass. No bus semantics changed.

## Universal Company OS moat test

- **5-person startup:** support tickets and CRM records land on the tab as
  demand themes with distinct customers, an at-risk health posture with
  named reasons, your own promises with a deliver button and measured
  outcomes — all zero configuration, all evidence-backed. ✓
- **50,000-person enterprise:** the same canonical tables with indexed,
  bounded reads (themes/risk/opportunities capped), per-org locks and
  scoped visibility answer the same questions with the same architecture;
  replays converge exact-once. ✓
- **Connected, not isolated:** the tab is fed by the platform's own durable
  events and routes through the Company Brain intents — a competitor
  cannot copy this as a standalone "customer dashboard". ✓

## Post-acceptance state

- The running backend on :8999 is the verified 4G.5 code (live acceptance,
  e2e, and the full 29-spec suite ran against it end-to-end); the live
  Postgres 4G.5 tables were built by `create_all` on startup and the
  scheduler/engine fixes are live (queue verifiably draining during the
  run).
- Commit + tag `vcos-slice-4g5-complete` created; workspace junk cleaned
  (`backend/_tmp_probe.py` removed).
- **STOP**: next slice is 4G.6 per the locked roadmap.