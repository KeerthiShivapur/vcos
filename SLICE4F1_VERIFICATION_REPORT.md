# Slice 4F.1 Verification Report — Universal People Intelligence Foundation

**Status: COMPLETE** — all 22 slice tests, the full backend regression suite
(760 tests), and the live API acceptance script (21 checks) pass with zero
failures. Backend-only slice per the roadmap decision (the People Intelligence
UI is introduced in the later 4F slices once the model is mature, and is
ultimately unified into the Universal Virtual Company OS workspace). Commit +
tag at the end of this slice.

## What this slice delivers

4F.1 is the canonical People Intelligence FOUNDATION for the Universal Virtual
Company OS: every person in an organization gets ONE governed identity and a
complete, reconstructable career — membership windows, role windows, reporting
windows — plus identity resolution that never silently merges, the living org
chart and people graph, unit surfaces, governed brain-question intents, and
exact-once event journaling from the canonical employee lifecycle. All of it
is governed by the same RBAC/scopes already in the schema.

```
person  (the canonical employee record — rule: identity != employment != role)
  |-> person_identities        strong keys per source; a conflicting key on
  |                             another person is REFUSED (409), never merged;
  |                             re-linking on the same person is an idempotent
  |                             refresh; resolution admits ambiguity honestly
  |-> person_memberships       temporal windows: every status change closes
  |                             the previous window (never deleted) and the
  |                             employee status mirrors it; history is always
  |                             reconstructable AT ANY MOMENT (/at)
  |-> person_role_assignments  temporal windows; assigning a new primary role
  |                             demotes the previous primary; the open primary
  |                             mirrors the employee designation
  |-> reporting_relationships  temporal windows (reports_to / matrix_manager /
  |                             project_manager / …); the open reports_to
  |                             window mirrors Employee.manager_id
  |-> people_timelines         append-only, exact-once per (org, person,
                               event_id): durable replay never double-writes
```

Certified surfaces:

```
/brain/people                governed directory (search, profiles, history)
/brain/people/{id}/at        temporal reconstruction of a person's world
/brain/people/{id}/roles     role windows (assign / change / remove)
/brain/people/{id}/membership    membership windows (open/close + mirror)
/brain/people/{id}/reporting     reporting windows (set / clear)
/brain/people/{id}/reporting-line   the chain of managers above a person
/brain/people/{id}/related   deterministic why-are-these-people-related
/brain/people/{id}/identities     link / resolve / history of strong keys
/brain/org/chart             the living org chart (built from open windows)
/brain/org/graph             people graph nodes + edges
/brain/org/units             unit member enumeration + unit summaries
brain intents                "who works in X" -> unit members,
                             "who reports to X" -> direct reports,
                             "org chart" -> the living chart
events                       employee.created / manager.changed /
                             employee.status.changed / employee.transferred /
                             employee.promoted / employee.offboarded /
                             user.created / user.status.updated /
                             team.member.added / team.member.removed
                             -> canonical sync + exact-once journaling
```

Governance is built into every surface: scoped readers see exactly their
scope (team members + leads, sub-team members, ancestor-manager chains) and
NEVER reveal invisible subordinates (downward-only visibility), and every
write needs `employees:manage` while every read needs `brain:read`.

## Implementation (diffs from 95f09e2)

Backend (new):

- `backend/app/models/people_intelligence.py` — `PersonIdentity`,
  `PersonMembership`, `PersonRoleAssignment`, `ReportingRelationship`
  (temporal windows with validity indexes) and `PeopleTimeline`
  (append-only, `uq_people_timeline_event` for exact-once), plus the
  `IDENTITY_SOURCES` / `MEMBERSHIP_STATUSES` / `RELATIONSHIP_TYPES` /
  `ROLE_TYPES` enumerations.
- `backend/app/models/__init__.py` — model registration (create_all at
  bootstrap).
- `backend/app/people/people_engine.py` — the `PeopleEngine` singleton:
  identity link/resolve, `ensure_person` canonical sync, membership/role/
  reporting window management with employee mirrors, exact-once `journal`,
  `visible_person_ids` governance, directory/search/profile/history/
  as-of/reporting-line/related/org-chart/people-graph/unit surfaces.
- `backend/app/api/v1/brain.py` — the `/brain/people` and `/brain/org`
  REST surface (19 routes, all gated, writes committed by the routes).
- `backend/app/events/handlers.py` — 13 people handlers bridging the
  canonical employee lifecycle events into the people engine, exact-once
  via `event_id`, never committing (the EventBus owns the transaction).
- `backend/app/knowledge/intelligence_engine.py` — the `people` intent with
  deterministic routing (unit members / direct reports / reporting line /
  org chart / directory fallback), governance-scoped.
- `backend/tests/test_4f1_people_intelligence.py` — 22 tests.
- `backend/scripts/accept_slice4f1.py` — 21 live acceptance checks.

Frontend (new): none — backend-only slice (see roadmap decision above). All
contracts (models, API responses, event payloads, governance semantics) are
designed as production-grade contracts so the later People Intelligence UI can
be added without redesigning the kernel.

## Design decisions locked by tests

- **One canonical person.** Identity keys, membership, roles and reporting
  are separate governed facts with their own windows; nothing is derived then
  thrown away — state moves forward and history is retained.
- **Identity resolution never merges.** A strong key already linked to
  another person is refused (409); re-linking the same key to the same person
  is an idempotent refresh; retired mappings can be re-linked consciously.
- **Temporal everything.** A new membership/role/reporting window CLOSES the
  previous open window (with a `valid_to`); the closed window survives and
  `/at` reconstructs the person's world at any moment in the past.
- **Mirrors stay consistent.** The open reports_to window mirrors
  `Employee.manager_id`; the open primary role mirrors `Employee.designation`;
  membership maps employee statuses through one `_STATUS_TO_EMPLOYEE` table.
- **Exact-once under replay.** Every durable event applies to the timeline
  exactly once (unique (org, person, event_id)), so replays and retries never
  double-write.
- **Governance before data.** Access is resolved via the existing RBAC/scopes
  BEFORE any data is assembled; scoped callers see only their scope plus the
  ancestor-manager chain of visible people, and invisible subordinates are
  never revealed on any surface (directory, chart, graph, units, questions).
- **No permission sprawl.** Writes reuse the existing `employees:manage`;
  reads reuse `brain:read`; no new permission strings were minted.
- **Same canonical model, no silo.** People surfaces read Employee/Team/
  Department/BusinessUnit and the new temporal rows — they are views over one
  model, never duplicated intelligence.

## Verification

Backend unit tests:

```
22 passed  (tests/test_4f1_people_intelligence.py)
```

Live acceptance (`backend/scripts/accept_slice4f1.py` against the restarted
running backend on :8999):

```
21 passed, 0 failed   (exit 0)  — canonical birth, temporal windows, /at
reconstruction, identity resolution + 409 refusal, role demotion + mirror,
reporting line, org chart, related strengths, graph, units, governed brain
questions, exact-once promotion/offboarding journaling, scoped-governance,
writes need employees:manage (403/200), tenant isolation
```

Full backend regression (all suites, `backend/tests`):

```
760 passed in 2861.48s (0:47:41)   — zero failures
```

Frontend: out of scope for this slice (backend-only; see roadmap decision).

## Post-acceptance state

- The running backend on :8999 is the verified 4F.1 code (restarted to load
  the new tables/routes; the dev event queue, which had accumulated ~2M
  historical rows and stuck transactions, was drained and unblocked as part
  of acceptance).
- Commit + tag `vcos-slice-4f1-complete` created.
- **STOP**: next slice is 4F.2 (Skills & Expertise Intelligence) per the
  roadmap decision.