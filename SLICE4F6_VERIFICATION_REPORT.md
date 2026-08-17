# Slice 4F.6 Verification Report — Organizational Capability & Capacity Intelligence

**Status: COMPLETE** — 22 slice backend tests, the FULL cross-slice regression
(878 tests), the live API acceptance script (15 checks), and the Playwright
E2E (evidence-backed → capacity-explicit → explainable → advisory-only → one
governed UI surface) pass with zero failures. Commit + tag
`vcos-slice-4f6-complete` created.

## What this slice delivers

4F.6 answers **WHAT the organization can actually deliver, and how much is
free** as a canonical, evidence-derived, explainable capability intelligence
— lifecycle (emerging → established → strong → strategic, and back down to
declining/dormant with preserved monthly history), a real capacity model
(**capacity = potential − committed − reserved**, derived from the freed
evidence, never from fake hours), demand (current active projects only),
concentration and single-point dependency findings, capability gaps and
taxonomy adjacency. It is fused with the work events already in the Company
Brain: capability records are DISCOVERED change-driven from the same durable
events the platform already emits — there is no scan, no guesswork, and
nothing is invented.

```
OrgCapability              canonical org capability row per canonical skill:
                           lifecycle, confidence, expert/strong-expert and
                           evidence counts, corroborated kinds, outcome
                           ratio, capacity = potential - committed -
                           reserved + state, demand (active projects only),
                           concentration shares, owner/team/knowledge
                           counts, deterministic factors + one human
                           explain, exact-once via source_event_id
CapabilityProjectLink      which active projects demand a capability
                           (unique org+skill+project; project-anchored
                           evidence only)
CapabilityHistory          monthly archive: previous vs current month
                           points + lifecycle, so decline is measurable
CapabilitySignal           advisory findings (concentration /
                           single_point_dependency / capacity_constraint /
                           capability_gap / emerging_without_capacity /
                           capacity_without_expertise / declining /
                           expertise_without_capacity) — analysis NEVER
                           changes the organization
```

Deterministic laws under test:

```
discovery                  a capability row is created only by an applied
                           expertise-feeding event (task.completed etc.
                           via expertise.updated) — never by a scan; a
                           fresh org starts with zero rows
lifecycle                  deterministic evidence bands: unknown ->
                           emerging -> established -> strong -> strategic,
                           declining when activity falls below recent
                           history, dormant below it — with monthly
                           history preserved on transitions
capacity                   = potential (experts with evidence) - committed
                           (experts engaged on active projects) - reserved
                           (inactive/recently-left experts); every preview
                           and detail asserts the identity, never fake hours
demand                     counts DISTINCT active projects only (a closed
                           project closes its demand)
explainability             every capability answers WHY: confidence,
                           corroborated kinds, outcome ratio, factors dict,
                           human-readable explain; the detail endpoint
                           never hides factors
adjacency                  taxonomy neighborhood (parent/children/related)
                           plus capabilities sharing experts, bounded reads
idempotent                 one capability row per org+skill with
                           exact-once event wiring — replays converge
bounded                    every read is an indexed lookup with caps
                           (500 overview rows, 10 top experts, 40 adjacency,
                           50 initiative skills, etc.)
governance                 brain:read for capability surfaces;
                           employees:manage to acknowledge signals;
                           org-wide surfaces require org-wide visibility
                           (scoped callers get 404 or leak-free
                           project-anchored rows, never member counts);
                           tenant isolation holds
advisory-only              analysis writes ONLY capability tables
                           (signals are acknowledge-only; a cleared
                           finding auto-resolves) — never operating
                           entities, projects, people or teams
change-driven              the 4F.6 bridge in handlers.py feeds
                           expertise.updated, task.*, project.*, decision.*,
                           approval.*, ownership.*, skill.*, team.member.*,
                           employee.transferred into the capability engine
```

## Certified surfaces

```
/brain/capabilities/overview                 one-glance capability center:
                                             lifecycle distribution,
                                             strong / emerging /
                                             constrained / concentration
                                             risks / gaps + the full
                                             evidence-ordered list
/brain/capabilities/{skill_id}               full detail: lifecycle,
                                             capacity model, demand,
                                             concentration, owners/teams/
                                             projects/knowledge counts,
                                             experts with scores and
                                             evidence, history (monthly),
                                             evidence by kind, signals,
                                             adjacency, factors + explain
/brain/capabilities/signals                  advisory findings (open or
                                             acknowledged) by severity
/brain/capabilities/signals/{id}/acknowledge governed, explicit,
                                             persistent acknowledgement
/brain/capabilities/projects/{id}            capabilities evidenced on one
                                             project — leak-free for scoped
                                             callers
/brain/capabilities/initiative               "can we take this on?" —
                                             deterministic, evidence-backed
                                             readiness per required
                                             capability (ready / partial /
                                             gap) + one verdict; never a
                                             forecast, never a guarantee
brain NL intents                             capability_strength /
                                             capability_emerging /
                                             capability_declining /
                                             capability_constraint /
                                             capability_concentration /
                                             capability_gaps ("what are we
                                             really good at", "which
                                             emerging capabilities are we
                                             getting good at", "are we
                                             capacity constrained anywhere")
```

## Implementation (diffs from vcos-slice-4f5-complete)

Backend (new + extended):

- `backend/app/models/org_capability_intelligence.py` — the four canonical
  tables (`OrgCapability`, `CapabilityProjectLink`, `CapabilityHistory`,
  `CapabilitySignal`), JSON-typed deterministic factors, and the
  `source_event_id` exact-once wiring.
- `backend/app/intelligence/org_capability_engine.py` — the engine:
  per-org `asyncio.Lock`, `record_event` → `refresh_person` /
  `refresh_capability` (month-keyed points + monthly history archiving,
  lifecycle derivation, capacity = potential − committed − reserved,
  distinct-active-project demand, concentration shares, counts,
  factors/explain), bounded `_reconcile_signals` with auto-resolve of
  cleared findings, and the governed surfaces `overview`, `capability_detail`
  (with taxonomy + shared-expert adjacency), `signals`,
  `acknowledge_signal`, `project_capabilities` (leak-free),
  `initiative_gap` (canonical-taxonomy resolution, ready/partial/gap).
- `backend/app/models/__init__.py` — capability tables registered so
  `create_all` builds them live.
- `backend/app/events/handlers.py` — the 4F.6 bridge
  `handle_org_capability` over expertise.updated, task.*, project.*,
  decision.*, approval.*, ownership.*, skill.*, team.member.*,
  employee.transferred.
- `backend/app/events/event_bus.py` — a failure-path debug log
  (handler traceback) carried over into this slice's debugging workflow.
- `backend/app/api/v1/brain.py` — the governed `/brain/capabilities/*`
  surface (6 endpoints).
- `backend/app/knowledge/intelligence_engine.py` — capability intents
  answering from the canonical tables (capability_* family placed before
  the bare expertise catch-alls so "which emerging capabilities ..."
  routes deterministically).
- `backend/tests/test_4f6_discovery.py`, `test_4f6_capacity.py`,
  `test_4f6_lifecycle.py`, `test_4f6_signals.py`,
  `test_4f6_governance.py` — 22 slice tests.
- `backend/scripts/accept_slice4f6.py` — 15 live acceptance checks.

Frontend (new):

- `frontend/lib/api.ts` — Slice 4F.6 block: types (`CapabilityBrief`,
  `CapabilityOverview`, `CapabilitySignalRow`, `CapabilitySignalsResponse`,
  `CapabilityDetail`, `CapabilityInitiativeResponse`, …) and one function
  per surface. (The initiative function passes the question as an object —
  `api()` stringifies bodies itself; a pre-stringified body double-encodes
  and the backend rejects it with a 422 — caught by the E2E.)
- `frontend/app/(app)/capabilities/page.tsx` — the Capability Center:
  stat cards (capabilities, strong/strategic, in demand, open signals),
  lifecycle distribution, strong / emerging / constrained / concentration
  risks / gaps panels, CEO readiness ("can we take this on?") with the
  deterministic verdict and per-capability readiness, open signals with
  Acknowledge (governed, `employees:manage`), and the full capability list
  whose rows open an evidence-backed detail panel (capacity model, demand,
  concentration, experts, teams, projects, history, adjacency, factors).
- `frontend/components/sidebar/Sidebar.tsx` — "Capability Center" entry in
  the Knowledge group (`brain:read`).
- `frontend/e2e/slice4f6-capability.spec.ts` — Playwright E2E.

## Design decisions locked by tests

- **Discovered, never scanned.** `task.created` alone creates NO capability;
  `task.completed` chains `expertise.updated` and produces the cap
  row — tests seed capability through completed work exactly as the live
  platform does.
- **Capacity is derived from freed evidence, in the open.** The E2E and
  acceptance pin `capacity_available == potential − committed − reserved`
  on preview and detail; there are no availability "hours".
- **Demand = current active projects, distinctly.** `.distinct()` on
  project ids keeps demand honest — several project-anchored evidence
  events count as ONE project in demand (verified live: demand 3 vs 1).
- **Lifecycle bands are deterministic.** 1 expert × evidence →
  emerging; 2 experts + enough evidence → established (the E2E pins this);
  strength tests reach strong; declining/knowledge work is preserved in
  `CapabilityHistory` month rows.
- **Explainable, not a black box.** Preview and detail both carry `explain`;
  detail carries `factors` (experts, strong_experts, evidence, kinds,
  outcome_ratio, avg/max score, days since last evidence, capacity parts,
  demand, teams/owners/knowledge, month_points) — the discovery test
  asserts the breakdown is never hidden.
- **Analysis is advisory, period.** Signals reconcile per capability from
  evidence; acknowledging changes NOTHING in the org; the governance test
  and check 10/15 assert persistence and read-path zero-mutation.
- **Scoped callers never reach org-wide capability surfaces.** Shear
  visibility → 404; scoped access gets project-anchored surfaces without
  member counts, and the initiative answer is filtered to visible skills.
- **One event, one row, forever.** `source_event_id` exact-once wiring
  makes replays and concurrent workers converge; the per-org lock keeps
  check-then-insert races out of the single-process deployment.
- **The brain routes capability questions deterministically.** Emerging
  and declining rules sit BEFORE the strength catch-all so "which emerging
  capabilities are we getting good at" cannot fall into "what are we good
  at"; both slice tests and the live check pin the routing.

## Verification

Backend unit tests (the slice):

```
22 passed  (test_4f6_discovery / capacity / lifecycle / signals / governance)
```

Hermetic SQLite, event-bus drains, register_org per test, tenant isolation
covered.

Full cross-slice regression (the complete backend suite, hermetic SQLite,
pytest-xdist 6 workers):

```
878 passed in 1086.64s (0:18:06)
```

(The 856-test 4F.5 baseline is included; 4F.6 adds 22 collected tests.)

Live acceptance (`backend/scripts/accept_slice4f6.py` against the live
backend on :8999 — final result exactly):

```
15/15 checks passed:
 1. a fresh org starts with zero capability rows
 2. a task completion creates the capability, emerging with 1 expert
 3. detail explains every number and never hides factors
 4. a second expert with evidence moves the lifecycle forward
 5. tasks inside a project create demand (active projects only)
 6. capacity = potential - committed - reserved (no fake hours)
 7. the project surface names the demand-capabilities
 8. a single-expert capability in demand is concentrated
 9. concentration and single-point signals surface from evidence
10. acknowledging a signal is explicit and persistent
11. completing the project closes its demand
12. the CEO readiness answer is deterministic and evidence-backed
13. capability brain questions route deterministically
14. scoped callers never reach org-wide capability surfaces
15. read paths never fabricate capabilities or enqueue signals
```

Playwright E2E (`frontend/e2e/slice4f6-capability.spec.ts`):

```
1 passed (warm) — full governed trail through the live UI + API:
seeding through the live event bus (5 project-anchored Kubernetes completions
+ 1 side task), overview contract (lifecycle established, 2 experts, 6+
evidence, capacity identity, demand ≥ 1, concentration share ≥ 60%),
detail contract (explain + factors, Ada + Bob experts, capacity identity,
projects), signals (concentration raised, acknowledged and persisted), CEO
readiness (Kubernetes "ready", verdict names required capabilities), brain
/knowledge/query routing to capability_strength, and the Capability Center
UI: stat cards, lifecycle distribution, CEO readiness question + verdict,
open signals with UI Acknowledge (count drops to zero), and a capability
row opening the detail panel (Capacity model, experts, "why we believe
this"). slice4f5-collaboration.spec also re-run green (shared-component
regression after api.ts/Sidebar changes).
```

Frontend static check: `npx tsc --noEmit` clean (repo gate: tsc/next build;
ESLint is not configured).

## Universal Company OS moat test

- **5-person startup:** "what can we actually deliver and how much is free"
  — one screen, no configuration: capabilities are discovered from the same
  completed work the team already does; every number is explained, capacity
  is honest, advisory signals are explicit and acknowledge-only. ✓
- **50,000-person enterprise:** the same canonical tables, indexed bounded
  reads, per-org locks, tenant isolation and visibility gating answer "is
  this capability ready for the new initiative" with the SAME architecture
  (initiative readiness caps at 50 skills, adjacency at 40, history caps).
- **Connected, not isolated:** the capability engine consumes the 4F.1–4F.6
  event stream through one bridge (expertise, tasks, projects, decisions,
  approvals, ownership, skills, teams), rolls monthly history for decline
  detection, feeds Company Brain intents, and is advisory by design — a
  competitor cannot copy this as a standalone skills list. ✓

## Post-acceptance state

- The running backend on :8999 is the verified 4F.6 code (the live
  acceptance and E2E ran against it end-to-end).
- Commit + tag `vcos-slice-4f6-complete` created.
- **STOP**: next slice is 4F.7 per the locked roadmap.