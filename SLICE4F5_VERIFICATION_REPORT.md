# Slice 4F.5 Verification Report — Work Collaboration Intelligence

**Status: COMPLETE** — 38 slice backend tests, the FULL cross-slice
regression (856 tests), the live API acceptance script (48 checks), and the
Playwright E2E (evidence-backed → explainable → advisory-only → one governed
UI surface) pass with zero failures. Commit + tag `vcos-slice-4f5-complete`
created.

## What this slice delivers

4F.5 answers **WHO works with WHOM, and how well** as a canonical,
evidence-derived, explainable governed graph — person ↔ person, unit ↔ unit
(team/department), and project collaboration — fused with the work events
already in the Company Brain. Nothing is guessed: every relationship is
built from applied evidence items (`task.created`, `task.completed`,
`task.blocked`, `decision.made`, `meeting.ended`, messages), every strength
is an explained formula, and every finding is advisory.

```
CollaborationEvidence       one applied evidence item: (org, event_name,
                            person_a/b, outcome, points, project, source,
                            detail); idempotency law = one item per
                            (event_id, person_a, person_b, scope)
CollaborationRelationship   canonical pair: counters (shared_tasks /
                            decisions / meetings, meaningful_messages,
                            successful/failed interactions), strength,
                            confidence, health_state (strong / healthy /
                            strengthening / emerging / weakening / dormant /
                            at_risk / blocked), quality, monthly points
                            (prev vs current), provenance (source_type,
                            last_source_id/title), recent evidence, unique
                            (person_a, person_b, scope) index — replay-safe
CollaborationUnitPair       team/department ↔ team/department rollups
CollaborationPersonRollup / OrgRollup   O(1) strength accumulators for
                            per-person and org concentration context
CollaborationSignal         advisory findings (gap / slowdown /
                            negative_shift / concentration) — analysis
                            NEVER changes people, teams or projects
CollaborationProjectView    per-project evidence share, top pairs and a
                            potential dependency-concentration advisory
```

Deterministic laws under test:

```
evidence-first        a relationship only exists with applied evidence; a
                      pair with zero evidence after required cross-unit
                      project work reads as a GAP advisory, never a verdict
idempotent            one evidence item per (event_id, pair, scope) —
                      replays and concurrent passes converge to one row
strength              strength = 1 - exp(-weighted_positive/10) adjusted
                      by failure ratio; confidence grows with evidence and
                      is capped; both explained by the endpoint
health/quality        health_state and quality derive from the same
                      counters; monthly markers compare previous vs current
                      month for weakening/strengthening change states
bounded               every read is an indexed lookup; analyze_gaps scans
                      <= MAX_GAP_PROJECTS_PER_PASS projects and
                      <= MAX_GAP_UNIT_PAIRS; burns capped evidence batches
governance            reads need brain:read; resolving a signal needs
                      employees:manage; person visibility resolved before
                      data assembly — hidden persons/foreign tenants 404,
                      scope-anchored callers see only in-scope pairs
advisory-only         signals resolve to nothing in the graph; the engine
                      writes ONLY collaboration/memory tables, never
                      operating entities
change-driven         the 4F.5 bridge in handlers.py feeds task.*,
                      decision.*, meeting.ended, message.* into the graph
                      through the event bus; a task.blocked emission added
                      to task_service.update() (direct PATCH-to-blocked,
                      deduped via via_transition so transition() with
                      blockers still fires exactly one event)
```

## Certified surfaces

```
/brain/collaboration/overview                      one-glance posture:
                                                   health distribution,
                                                   strongest + weakening
                                                   pairs, open signals,
                                                   org rollup
/brain/collaboration/relationships/people/{a}/with/{b}   one canonical pair:
                                                   counters, strength,
                                                   confidence, health,
                                                   quality, monthly markers,
                                                   recent evidence items
                                                   AND the strength
                                                   explanation (formula,
                                                   weighted_positive,
                                                   failure_ratio)
/brain/collaboration/people/{id}                   one person's world:
                                                   strongest partners
                                                   (ranked), rollup and
                                                   share of org strength
/brain/collaboration/units/{team|department}/{id}  cross-unit collaboration
                                                   with other_unit labels,
                                                   health and quality
/brain/collaboration/projects/{id}                 per-person evidence
                                                   share, top pairs,
                                                   dependency concentration
                                                   advisory (never a verdict)
/brain/collaboration/changes                       recent graph evolution
                                                   (emerging/strengthening/
                                                   weakening/dormant)
/brain/collaboration/signals  + /gaps, /bottlenecks  advisory lists by kind
/brain/collaboration/analyze                       one bounded gap-analysis
                                                   pass (advisory writes only)
/brain/collaboration/signals/{id}/resolve          governed acknowledge
brain NL intents                                   collaboration_person /
                                                   collaboration_changes /
                                                   collaboration_project /
                                                   collaboration_signals
                                                   ("who works most closely
                                                   with X", "how has
                                                   collaboration changed
                                                   recently")
```

Governance: reads need `brain:read`; signal resolution needs
`employees:manage`; person visibility is resolved before data is assembled
(hidden persons and foreign tenants 404); scope-anchored callers only see
pairs whose people are in their visible set (consistent with 4F.4/4C).

## Implementation (diffs from vcos-slice-4f4-complete)

Backend (new + extended):

- `backend/app/models/collaboration_intelligence.py` — the seven canonical
  tables (`CollaborationEvidence`, `CollaborationRelationship`,
  `CollaborationUnitPair`, `CollaborationPersonRollup`,
  `CollaborationOrgRollup`, `CollaborationSignal`,
  `CollaborationUnitPair`), provenance columns and unique pair indexes
  (portable to SQLite and Postgres).
- `backend/app/intelligence/work_collaboration_engine.py` — the engine:
  per-org write locking + evidence application with the idempotency law,
  canonical pair ordering, counter + strength + confidence + health + quality
  maintenance, monthly markers, O(1) rollups, advisory signal lifecycle
  (gap / slowdown / negative_shift / concentration with auto-resolve of
  stale findings), bounded reads (overview / relationship_detail with
  strength explanation / person_relationships / unit_relationships /
  project_view / changes / signals), bounded `analyze_gaps` (required
  department pairs on shared active projects with almost no evidence →
  gap), and the governed `resolve_signal_by_id`.
- `backend/app/models/__init__.py` — the collaboration tables registered so
  `create_all` builds them live.
- `backend/app/events/event_bus.py` — a process-wide `asyncio.Lock`
  serializes `process_pending` passes, eliminating the concurrent
  check-then-INSERT deadlock between the in-process 60s worker and manual
  drains (cross-process safety stays on the atomic job claim).
- `backend/app/events/handlers.py` — the 4F.5 bridge feeding
  `task.created/completed/blocked/transitioned/updated`,
  `decision.made`, `meeting.ended`, `message.*` into the graph.
- `backend/app/work/task_service.py` — `update()` now emits `task.blocked`
  when a direct PATCH moves a task to blocked with no blockers
  (`via_transition=False` only, so `transition()` with blockers still fires
  exactly one event) — closes the gap where PATCH-to-blocked produced no
  failure evidence in the graph.
- `backend/app/api/v1/brain.py` — the `/brain/collaboration/*` governed
  surface (12 endpoints).
- `backend/app/knowledge/intelligence_engine.py` — collaboration intents
  answering from the canonical graph.
- `backend/tests/test_4f5_collaboration.py`, `test_4f5_events.py`,
  `test_4f5_governance.py`, `test_4f5_lineage.py`, `test_4f5_scale.py` —
  38 slice tests.
- `scripts/accept_slice4f5.py` — 48 live acceptance checks.

Frontend (new):

- `frontend/lib/api.ts` — Slice 4F.5 block: types
  (`CollaborationRelationshipRow`, `CollaborationSignalRow`,
  `CollaborationOverview`, `CollaborationPairDetail`, `CollaborationPersonView`,
  `CollaborationUnitView`, `CollaborationProjectView`,
  `CollaborationChangesResponse`, `CollaborationSignalsResponse`,
  `CollaborationAnalyzeSummary`) and one function per surface.
- `frontend/app/(app)/collaboration/page.tsx` — the collaboration workspace:
  stat cards (relationships, cross-functional, open signals, org strength),
  health distribution, strongest + weakening pairs with counters, recent
  changes tray, open signals with Acknowledge (governed, `employees:manage`),
  "Run gap analysis" (advisory write only), and a project collaboration
  picker (per-person evidence share, top pairs, dependency-concentration
  advisory).
- `frontend/components/sidebar/Sidebar.tsx` — "Work Collaboration" entry in
  the Knowledge group (`brain:read`).
- `frontend/e2e/slice4f5-collaboration.spec.ts` — Playwright E2E.

## Design decisions locked by tests

- **Evidence first.** A pair only exists once its events were applied; the
  suite verifies an org built ONLY from task/decision/meeting/message work
  has exactly the derived pairs — no pre-populated "collaboration" data.
- **Canonical pairing.** Relationship rows store the pair in deterministic
  order with a unique (person_a, person_b, scope) index; the changes surface
  is order-tolerant because the graph is undirected by nature.
- **One event, one evidence item, forever.** The (event_id, pair) uniqueness
  makes replays and concurrent workers converge; the deadlock fix (process
  pass lock) makes concurrent dispatch safe in the single-process
  deployment.
- **task.blocked is a real graph signal.** A task moved to blocked through
  the direct PATCH (no dependency chain) now emits the event through
  `task_service.update()`; `transition()` delegates with `via_transition=True`
  so blocker-driven transitions still fire exactly one `task.blocked` (the
  4D.3/4D.4 memory + pattern tests re-lock exact-once across the whole
  event cascade).
- **Explainable, not a black box.** Every strength value comes with the
  formula inputs (weighted positive, failure ratio, evidence count); the
  E2E and acceptance assert the explanation along with the number.
- **Analysis is advisory, period.** Gap/slowdown/concentration signals say
  "review (advisory only)"; resolving a signal changes nothing in the
  graph; the acceptance asserts the graph is untouched after analyze.
- **Concentration is potential risk, never a label.** Bottleneck findings
  are backed by share-of-org-strength accumulators with explicit thresholds
  and readable reasons.
- **Scalability.** Reads are indexed lookups; analyze is bounded per pass;
  rollups are O(1) updates; no rescan, no full-table scans — the same
  architecture holds for a 5-person startup and a 50,000-person enterprise.

## Verification

Backend unit tests (the slice):

```
38 passed  (test_4f5_collaboration / events / governance / lineage / scale)
54 passed  (the 4F.5 batch + phase-3 step4/step5 event tests, re-run green
            after the fixes below)
```

Fixes this slice locked by tests:

- `test_slice3_step4_events.py` drains the memory-formation queue too (the
  new `task.blocked` emission enqueues a `memory.formation` job); the
  test's intent — "work events process without failures" — now covers the
  full cascade.
- `test_4f5_lineage.py` drains its own publishes and treats the undirected
  pair order as an implementation detail (reconstructed after a debug pass
  proved evidence → relationship exists exactly once).

Full cross-slice regression (the complete backend suite, hermetic SQLite,
pytest-xdist 6 workers):

```
856 passed in 757.00s (0:12:37)
```

(The 818-test 4F.4 baseline is included; 4F.5 adds 38 collected tests.)
Note: a single-threaded full run exceeds 30 minutes in this environment,
which is why the regression uses xdist with `--dist loadscope`.

Live acceptance (`scripts/accept_slice4f5.py` against the restarted backend
on :8999, exit 0):

```
48/48 checks passed — register/login, org seeded via teams/employees/
projects/tasks/meetings through the live event bus, project lifecycle
start, canonical pair with counters (shared_tasks=9, fail=1), strength
explain formula (0.5747), evidence provenance on pair (meeting.ended,
task.created/completed/blocked), overview totals (4 relationships),
strongest pairs list, team unit surface, project collaboration view with
evidence share + concentration advisory, changes list, signals list +
gaps + bottlenecks, brain /ask collaboration_person / collaboration_changes,
scoped-reader 404s on hidden pairs and hidden persons, gated overview
counts, gap analysis + signals after analyze
```

Playwright E2E (`frontend/e2e/slice4f5-collaboration.spec.ts`):

```
1 passed (7.0s warm) — full governed trail through the live UI + API:
shared-work seeding through the event bus (pairs form only from evidence),
overview contract with health distribution, Ada↔Bob pair detail with
counters, formula explanation, failure ratio and task.completed evidence,
cross-team unit surface (Engineering ↔ Operations via meeting attendance),
project evidence share, changes surface, advisory gap analysis, signal
resolve, brain /ask collaboration_person, and the collaboration workspace
UI (stat cards, strongest/weakening pairs, recent changes, open signals,
project picker with dependency-concentration advisory, run gap analysis)
```

Frontend static check: `npm run build` clean (repo gate: tsc/next build;
ESLint is not configured).

## Universal Company OS moat test

- **5-person startup:** "who actually works with whom" — one screen, no
  configuration: pairs form automatically from meetings, tasks and
  decisions; every number is explained. ✓
- **50,000-person enterprise:** the same canonical tables, indexed bounded
  reads, per-org writes, tenant isolation and visibility gating answer "how
  do these two business units collaborate" with the SAME architecture. ✓
- **Connected, not isolated:** the graph consumes the 4F.1–4F.3 event
  stream (one bridge), rolls up into 4D company memory/patterns (blocked
  task evidence feeds exactly-once memory formation), answers Company Brain
  intents, and is advisory by design — a competitor cannot copy this as a
  standalone "who's on what project" dropdown. ✓

## Post-acceptance state

- The running backend on :8999 is the verified 4F.5 code (single uvicorn
  instance; restart = kill the cmd parent AND the listener, otherwise an
  orphaned in-process worker keeps stale transactions).
- Commit + tag `vcos-slice-4f5-complete` created.
- **STOP**: next slice is 4F.6 per the locked roadmap.