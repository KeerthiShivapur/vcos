# Slice 4H.1 - Implementation Contract (RATIFIED - official working spec)

**Status: RATIFIED on 2026-08-19.** This document is the official working
specification for the 4H.1 implementation. It was reviewed and approved
as-is by the author before any code existed; no 4H.1 code has been written
yet. Implementation starts from this document, and any deviation must be
recorded in the verification report with its reason.

**Working name (locked):** 4H.1 - Universal Company / Organizational
Intelligence.

**Objective (from the strategy brief):** make VCOS understand the company as
one continuously connected living system - people + customers + work +
projects + strategy + resources + knowledge + decisions + execution +
outcomes - and use that unified state to help the company operate. 4E-4G
built the organs; 4H makes them behave like one organism.

**Anti-clone position (from the brief):** this is NOT "add another AI
feature", NOT "a better ServiceNow", NOT another module. The moat is a
different abstraction level: a system of organizational intelligence, not a
system of workflows. VCOS learns how a particular company actually works.

---

## 0. Mandatory first step: analyze the codebase, extend it, never parallel-build

Permanent law: **one canonical architecture, one canonical model, one event
fabric, one governance model** - for 5 people and for 50,000+ people. A new
slice may add tables; it never adds parallel systems. The analysis below was
done for this contract; the implementer must re-verify it before coding.

### What already exists (the canonical 4E-4G stack)

| Layer | Location | Role |
|---|---|---|
| Event fabric | `backend/app/events/event_models.py` | `EVENT_CATALOG` canonical event names |
| Event bridges | `backend/app/events/handlers.py` | change-driven engine bridges (46 refs), never commit |
| Engines | `backend/app/intelligence/{execution,coordination,strategic_execution,resource_allocation,customer_intelligence,business_performance,company_operating,expertise,people_decision,work_collaboration}_engine.py` | read-composition, exact-once keys, bounded reads, per-org locks, advisory-only |
| 4G.7 engine | `backend/app/intelligence/company_operating_engine.py` | state/health/root_cause/impact/recommendations/what_if/changes/memory |
| 4G.7 models | `backend/app/models/company_operating.py` | `CompanyDecision`, `CompanyHealthHistory` (exact-once `source_event_id`) |
| Brain routes | `backend/app/api/v1/brain.py` | `/brain/execution/company/*`; `_people_access` governance; scoped-caller 404; `BrainCompanyWhatIfIn` nested-`payload` merge |
| Intent router | `backend/app/knowledge/intelligence_engine.py` | ordered deterministic keyword table; `company_operating` block routes FIRST (~lines 291-307) |
| Memory pipeline | `backend/app/memory/formation.py` + `memory_store/service/context_service` | 4D.3 change-driven `CompanyMemory` formation: dedupe, evidence lineage, governance inheritance - already canonical-shaped |
| Tests | `backend/tests/test_4g7_engine.py` | hermetic SQLite, real API, event-bus drains, per-test `register_org` |
| Live acceptance | `backend/scripts/accept_slice4g7.py` | 14 checks against the live :8999 backend |
| Frontend | `frontend/app/(app)/execution/company-tab.tsx`, `frontend/lib/api.ts`, `frontend/e2e/slice4g7-company.spec.ts` | Company tab, 4G.7 API block, E2E |

### The overlap 4H.1 must NOT create a third copy of

`backend/app/autonomy/*` (Phase 18/19 blueprint-era: awareness_engine,
health_engine, prediction_engine, recommendation_engine, simulation_engine,
digital_twin_sync, learning_loop, decision_support, planning_engine,
strategy_engine, optimization_engine, executive_briefing,
knowledge_evolution, workflow_intelligence) with its own tables
(`CompanyState`, `OrganizationHealth`, `DigitalTwin`, `Prediction`,
`SimulationRun`, ...) and manual-trigger routes
(`backend/app/api/v1/autonomy.py`: `/autonomy/state`, `/autonomy/observe`).
This layer is NOT event-driven and predates the change-driven canonical
architecture.

**Disposition (locked):**
1. 4H.1 extends the canonical engine family - specifically
   `company_operating_engine` - and NEVER adds routes, handlers or tables
   under `app/autonomy/*`, `app/api/v1/autonomy.py`, `company_state.py`,
   `digital_twin.py`, `prediction.py`, `simulation.py`, `recommendation.py`
   or `organization_health.py`.
2. Persistent state extends `app/models/company_operating.py`; the memory
   surface reuses `CompanyMemory` through `app/memory/*`.
3. Consolidation/retirement of the autonomy layer is a SEPARATE decision,
   out of scope for 4H.1. 4H.1 documents overlap; it never double-writes
   the same facts into both layers.
4. `app/memory/*` is already canonical-shaped - 4H.1 memory work REUSES it.

## 1. Scope of 4H.1 (the delta over 4G.7)

Six capabilities:

1. **Temporal company state** - state/health is a time series, not a point.
   "Why did company health decline?" gets a narrative with a causal chain.
2. **Business causality graph** - cross-domain cause edges (person ->
   capability -> project -> milestone -> customer -> revenue -> objective ->
   outcome; decision -> task -> execution -> outcome -> customer impact ->
   business impact), derived deterministically from evidence the engines
   already read. Impact/root-cause walks become first-class queries over it.
3. **What-happens-if (advisory simulation)** - extends 4G.7 `what_if`:
   delay/hire/reallocate traverse dependency -> customer commitment ->
   strategy -> capacity redistribution -> other projects. Declared, never
   executed, never a prediction, bounded (5 consequences).
4. **Multi-level intelligence** - the SAME surfaces (state, health, causal
   chain, what-changed) parameterized by level: org -> business unit ->
   department -> team -> person. One canonical engine, one graph.
5. **Company memory loop** - decisions carry a prediction (expected outcome
   + confidence) at approval time; the loop closes when the observed outcome
   lands and derives a lesson; recall answers "why did we decide this six
   months ago", "was that decision good", "what has this company learned".
6. **Universal company query** - one intent block routing CEO/CTO/COO/HR/
   Sales/manager/employee questions into the same canonical layer.

NOT in scope (locked): finance (4I), HR (4J), sales (4K), meetings (4L),
documents (4M), integrations (4N), executive briefing (4O), statistical/ML
prediction (4P - deterministic-forecast-only here), autonomous execution
(4Q - 4H.1 stays advisory-only), autonomy-layer consolidation, and any
"world first" marketing claims.

## 2. Architecture

```
  COMPANY ACTIVITY (canonical events, EVENT_CATALOG)
            |
            v
  CANONICAL ENGINES 4G.1-4G.6 (unchanged, read-composed)
            |
            v
  company_operating_engine (EXTENDED - the 4H.1 engine)
   temporal state + narrative | causality graph | what-happens-if |
   multi-level state | memory loop
            |
            v
  COMPANY BRAIN intent routing (ONE block, EXTENDED)
            |
            v
  one frontend Company tab (EXTENDED, no new route)
```

Laws that cannot change: read-composition (the engine writes only its own
tables); change-driven (surfaces recompute from durable events; replays
converge exact-once); advisory-first (nothing scheduled/moved/hired by the
engine; humans decide); bounded (every list capped); same semantics for
5 -> 50,000+ (scope parameterization, not separate engines).

## 3. Canonical models (extend, don't invent) - all in `company_operating.py`

1. `CompanyHealthHistory` - ADD nullable `scope_type` + `scope_id`
   (default org) for multi-level; keep exact-once `source_event_id`;
   additive migration, existing rows untouched.
2. `CompanyDecision` - ADD nullable `predicted_outcome` (JSON),
   `prediction_confidence` (float 0..1), `actual_outcome_compare` (JSON,
   filled by the outcome write), `reviewed_at`. Existing vocabularies
   untouched.
3. NEW `CompanyCausalEdge` - derived edge table (exact-once key = source
   event; bounded recent window + cap per domain): `organization_id,
   source_type, source_id, target_type, target_id, kind` (one of
   person->capability, capability->project, project->milestone,
   milestone->customer, customer->revenue, revenue->objective,
   objective->outcome, decision->task, task->execution, execution->outcome,
   outcome->customer, customer->business, dependency->project,
   capacity->project), `confidence` (high/medium/low from evidence
   strength), `evidence_ref` (entity refs), `source_event_id`, `created_at`.
   Written ONLY by the 4H.1 engine from data the canonical engines already
   expose (CustomerProjectLink, StrategicLink, milestones, dependencies,
   commitments, business metrics/targets, decisions).
4. REUSE `CompanyMemory` via `app/memory/formation.py` for the memory
   surface - decision-loop lessons are `lesson`-labeled memories with
   evidence lineage back to the `CompanyDecision`.

No new "company state" model: `CompanyHealthHistory` IS the temporal state
table.

## 4. Event flows

New names in `EVENT_CATALOG` + handler wiring (extend the existing
`company_operating_engine` bridge; do NOT add a second bridge class):

- `company.causal_edge.refreshed` - causality graph recomputed (internal).
- `company.prediction.recorded` - a decision recorded its expected outcome
  + confidence (fired by the decision write).
- `company.memory.lesson.derived` - a closed decision loop derived its
  lesson memory (internal).

4H.1 reacts to the EXISTING 4G.1-4G.6 events via the existing bridge's
`record_event`; no new events per upstream domain.

## 5. The intelligence engine (`company_operating_engine`, extended)

Keep every existing surface byte-compatible (live 4G.7 acceptance must keep
passing unchanged). New methods:

- `temporal_state(db, *, scope_type=None, scope_id=None, from_ts=None,
  to_ts=None, limit=40)` - bounded health-trail series with per-step
  dimension scores; answers "what is happening across my company right
  now" with evidence.
- `narrative(db, *, scope_type, scope_id, window)` - WHY the score moved:
  deltas between consecutive trail rows composed with their evidence
  (capacity dropped Tue -> project slipped Wed -> customer risk Thu ->
  score down Mon); deterministic, bounded (5 steps).
- `causal_chain(db, *, entity_type, entity_id, depth=5)` - walks
  `CompanyCausalEdge` + existing impact chains; per-hop confidence +
  evidence refs.
- `what_happens_if(db, *, scenario_type, payload)` - EXTENDS `what_if`
  (delay/hire/reallocate labels byte-compatible) with company-level hops.
  Note contract unchanged: "not a prediction", "humans decide", nothing
  rescheduled.
- `multi_level_state(db, *, scope_type, scope_id)` - the SAME state/health
  computation parameterized by scope using the same canonical tables
  (department/team membership, ownership, assignments, workload); same
  response schema as org level; org stays the default.
- `memory_loop` - extend `memory`: prediction at approve-time, reconcile
  on outcome (`actual_outcome_compare`), derive lesson memory, add recall
  filters (`decision_id`, `predicted: true`, `since`).

## 6. APIs (`backend/app/api/v1/brain.py`)

All under `/brain/execution/company/*` via the existing `_people_access`
governance idiom:

- `GET /company/state` - EXTEND with optional `scope_type`/`scope_id` and
  `from`/`to`/`limit` (temporal series). Defaults stay org-level, current
  point - live acceptance stays green.
- `GET /company/narrative` - `?window=` -> the why-it-changed narrative.
- `GET /company/causal-chain` - `?subject_type=&subject_id=` (same
  parameter style as `impact`).
- `POST /company/what-happens-if` - extends the `what-if` schema
  (`scenario_type` + `payload`; the 4G.7 nested-`payload` merge rule
  applies - never silently drop nested keys).
- `POST /company/decisions` - EXTEND with optional `predicted_outcome` +
  `prediction_confidence`; response byte-compatible.
- `POST /company/decisions/{id}/outcome` - EXTEND to return
  `actual_outcome_compare` + the derived lesson memory ref.
- `GET /company/memory` - EXTEND with `predicted: true` / `decision_id` /
  `since` filters.
- `POST /brain/knowledge/query` - EXTEND the router with a NEW
  `company_universal` block placed BEFORE `company_operating` (4G.7
  keywords untouched) for multi-level / narrative / memory-recall
  questions.

## 7. Governance

- Org-wide surfaces (narrative, causal-chain, what-happens-if, temporal
  state at org level) 404 for scoped callers - the existing idiom.
- Multi-level surfaces: a caller may query ONLY scopes their governance
  assignments cover (scope_id membership check, same rule the
  execution/customer surfaces use); 404 otherwise.
- All writes (`decisions` with prediction, `outcome` with compare)
  require `projects:manage`; reads require `brain:read`.
- Every surface bounded; every write audits through the event fabric;
  replays converge exact-once.

## 8. UI (extend the existing Company tab; no new route)

`frontend/app/(app)/execution/company-tab.tsx` + `frontend/lib/api.ts`:

- Temporal health sparkline (from `/company/state` series) + a "Why did it
  change?" narrative panel (`/company/narrative`).
- Causal chain panel for a selected subject (project/customer/capability/
  person) rendered as an ordered chain with per-hop confidence.
- What-happens-if runner extending the existing what-if controls
  (delay/hire + dependency/customer/strategy consequence lists).
- Multi-level selector (Company / Business unit / Department / Team /
  Person) driving the same state cards through `scope_type`/`scope_id`.
- Memory ledger gains prediction/actual/compare columns and recall
  filters; lessons link to the decision.
- Advisory-only note unchanged.

## 9. Tests

- `backend/tests/test_4h1_engine.py` - temporal series + exact-once,
  narrative determinism, causal edge derivation + chains, what-happens-if
  bounded + advisory labels, multi-level scoping, memory loop
  (predict -> outcome -> compare -> lesson), replay convergence.
- `backend/tests/test_4h1_surfaces.py` - API contract (schemas, bounds,
  defaults unchanged for 4G.7 surfaces).
- `backend/tests/test_4h1_governance.py` - scoped 404s, scope membership,
  write permissions.
- The 4G.7 module tests MUST keep passing unmodified (byte-compatibility
  gate); the full backend regression + the full Playwright suite must stay
  green before acceptance.

## 10. Live acceptance (extend `scripts/accept_slice4g7.py`)

New checks against the live :8999 backend:

1. Temporal state: the series grows across seeded events; exact-once on
   replay.
2. Narrative: a seeded capacity->project->customer deterioration produces
   the expected causal narrative (deterministic wording).
3. Causal chain: project subject walks to customers; customer subject walks
   back; per-hop confidence + evidence refs present; bounded depth.
4. What-happens-if: delay/hire consequences include customer commitment +
   strategy hops; note keeps the honesty contract; unknown scenario
   declared.
5. Multi-level: org default unchanged; a team/person scope returns the same
   schema bounded to that scope's entities; out-of-scope caller 404s.
6. Memory loop: decision with prediction -> execute -> outcome lands
   `actual_outcome_compare` + a lesson memory with evidence lineage back to
   the decision; recall finds it.
7. Universal query: the CEO/COO/HR-style phrasings route to the
   `company_universal` intent and return the canonical layer's answer.

## 11. The mandatory moat test (from the strategy brief - permanent)

Before declaring 4H.1 complete, ALL must hold with evidence:

1. Company understanding - "What is happening across my company right now?"
   answered with evidence.
2. Causality - "Why?" traced as a chain.
3. Prediction (deterministic only) - "What is likely to happen next?" with
   uncertainty labels (4H.1: forecasts/expected-outcomes only, never ML).
4. Simulation - "What happens if we change X?" without changing the real
   system.
5. Decision memory - "Why did we make this decision six months ago?"
6. Outcome learning - "Was that decision actually good?"
7. Organizational memory - "What has this company learned?"
8. Universal scale - the same architecture serves 5 -> 50 -> 5,000 ->
   50,000+ (scope parameterization; no separate engines).
9. Governance - every answer respects tenant boundaries, role permissions,
   project scopes, employee visibility, confidentiality, auditability.
10. Moat - every month of usage makes VCOS understand this company better
    than a newly deployed competitor on day one.

## 12. Anti-module gate (from the brief - every 4H.1 feature must pass)

1. Does it create another standalone module? If yes -> rethink.
2. Does it strengthen the Living Company Model? If no -> don't build.
3. Does it connect previously disconnected organizational information?
4. Can it reason across departments?
5. Does it work for 5 -> 50,000+ employees?
6. Can it work with existing enterprise software?
7. Can it explain its reasoning and evidence?
8. Can the result become organizational memory?
9. Can the company actually act on the intelligence (within governance)?
10. Does removing it materially weaken the company's ability to operate
    through VCOS?

## 13. Deliverables checklist (what "4H.1 complete" means)

- [ ] `company_operating.py` extended (scope columns, prediction columns,
      `CompanyCausalEdge`) with additive migration.
- [ ] `company_operating_engine.py` extended; all 4G.7 surfaces unchanged.
- [ ] 3 new events in `EVENT_CATALOG` + handler wiring.
- [ ] brain.py routes (2 new, 4 extended) + `company_universal` intent block.
- [ ] Governance: scope-membership checks for multi-level reads.
- [ ] Frontend: sparkline, narrative, causal chain, what-happens-if,
      multi-level selector, memory recall - one tab, tsc clean.
- [ ] `test_4h1_engine/surfaces/governance` green; 4G.7 tests untouched and
      green; full backend regression green; full Playwright suite green.
- [ ] Live acceptance extended and green.
- [ ] The 10 moat-test items each evidenced in `SLICE4H1_VERIFICATION_REPORT.md`.
- [x] Ratification recorded - this contract was ratified as-is on 2026-08-19
      (name locked: Universal Company / Organizational Intelligence).

## 14. Out of scope (explicitly not 4H.1)

4I finance, 4J HR, 4K sales, 4L meetings, 4M documents, 4N enterprise
integrations, 4O executive briefing, 4P statistical prediction, 4Q
autonomous execution, autonomy-layer consolidation, competitor claims.
