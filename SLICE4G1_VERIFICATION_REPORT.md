# Slice 4G.1 Verification Report — Project & Execution Intelligence

**Status: COMPLETE** — 28 slice backend tests, the FULL cross-slice regression
(903 tests + 28 slice = 931 collected), the live API acceptance script (10
checks), and the Playwright E2E pass with zero failures. Commit + tag
`vcos-slice-4g1-complete` created.

## What this slice delivers

4G.1 answers **WHAT the company is trying to accomplish, HOW it is going,
WHAT is blocking it, WHAT could change the outcome and WHAT should happen
next** as one canonical per-project execution record — the Execution Command
Center. Goal → project → milestone → task; deterministic health
(healthy|watch|at_risk|critical) with one human explain and a primary cause;
blocker root-cause chains with systemic grouping; the REAL CPM critical path
with slack; capacity constraints (4F.6) and pending decisions (4A) read from
their own records; a mandatory outcome record; and a deterministic,
prioritized, bounded "what should happen next" — all advisory-only, fed
change-driven from the SAME durable events the platform already emits,
replay-safe and exact-once.

```
ProjectExecutionState     one canonical row per project: health score +
                          status + factors + explain + primary cause,
                          counts, critical path, blockers, systemic
                          blockers, capacity constraints, pending
                          decisions, goal chain, outcome — refreshed only
                          by the event stream, never by user writes
ProjectExecutionSnapshot  the change history: every refresh keys a
                          snapshot on source_event_id (exact-once),
                          capped at 40, "what changed" stays answerable
```

Deterministic laws under test:

```
advisory-only          the engine only writes its own tables — it never
                       rewrites projects, tasks, people or capacity;
                       even the outcome record leaves the project untouched
exact-once             every event-driven refresh is keyed on
                       source_event_id; replays converge (engine test
                       asserts exactly 1 snapshot per source event across
                       replays; live drain re-processes nothing new)
change-driven          the record is fed from the platform's real durable
                       events: project.created/started/..., task.created/
                       transitioned/blocked/..., dependency.added/removed,
                       decision.made/..., goal.created/... — handlers never
                       commit
deterministic health   80 base, bounded penalty budget per surface
                       (timeline, dependencies, capacity, decisions,
                       ownership); one primary cause; one human explain
real CPM               forward/backward passes with slack over
                       estimate_hours; slack <= 0.5h critical; the
                       backward pass relaxes to the TIGHTEST late start
                       when a task has multiple successors (diamond
                       graphs) — found by the E2E, fixed, pinned by tests
blocker analysis       root-cause chains over the TaskDependency graph
                       (bounded depth 5), deeply-blocked counts, systemic
                       grouping (3+ blocked by the SAME root, bounded 6)
next-first             deterministic prioritization: decisions with open
                       actions -> critical-path pressure -> blocked path
                       work -> overdue milestones -> ready high-priority
                       work; bounded at 20, ready work at 2/project
governance             command/next are ORG-WIDE surfaces (scoped callers
                       404, same idiom as 4F.6/4F.7); project detail is
                       scope-checked; the outcome requires projects:manage
                       — a human writes the outcome, never the system
outcome record         planned vs actual + assessment in
                       successful|partial|unsuccessful; snapshotted and
                       fed forward as evidence; never rewrites the project
bounded                every read is capped: 200 active projects, 300
                       tasks/project, 40 snapshots, 40 blocked rows, 6
                       systemic groups, 20 next items, 20 decisions,
                       12 capacity rows, 50 milestones, depth 3 goal chain
timezone-safe          all new timestamp columns are
                       DateTime(timezone=True) (the asyncpg/Postgres rule)
```

## Certified surfaces

```
GET  /brain/execution/command             the Execution Command Center:
                                          every active project's health,
                                          explain, primary cause, last
                                          change + bounded counts
                                          (org-wide only)
GET  /brain/execution/next                what should happen next —
                                          deterministic, prioritized,
                                          bounded 20 (org-wide only)
GET  /brain/execution/projects/{id}       one project's full execution
                                          record: health + factors +
                                          explain + primary cause,
                                          critical path with slack,
                                          blocker chains, systemic
                                          blockers, capacity constraints,
                                          pending decisions, goal chain,
                                          outcome, history
                                          (scope-checked, lazy
                                          materialization)
POST /brain/execution/projects/{id}/outcome   the mandatory outcome
                                          record (projects:manage;
                                          successful|partial|
                                          unsuccessful)
POST /brain/knowledge/query               execution intents: "is X on
                                          track", "why is the project at
                                          risk", "command center" ->
                                          intent execution; "what should
                                          we do next?" -> execution_next;
                                          "what is blocked?" /
                                          "what is overdue?" -> org-wide
                                          execution surfaces with honest
                                          fallback to the 4E knowledge
                                          answers when the record is empty
```

## Implementation (diffs from vcos-slice-4f7-complete)

Backend (new + extended):

- `backend/app/models/execution_intelligence.py` —
  `ProjectExecutionState` + `ProjectExecutionSnapshot`, all timestamps
  `DateTime(timezone=True)`, JSON columns for factors/counts/critical path/
  blockers/systemic/capacity/decisions/goal chain/outcome.
- `backend/app/intelligence/execution_engine.py` — the engine: health
  penalty budget + explain + primary cause, CPM with slack, blocker
  root-cause chains + systemic grouping, overdue milestones, 4F.6 capacity
  read, 4A pending-decision read, root-first goal chain, next
  prioritization, outcome record, snapshot history with exact-once replay
  guard (snapshot-by-source_event_id) and pruning. Fixes locked by tests:
  `_dependencies` is async and awaited; `_systemic_blockers` reads
  `blocked_rows`; `_goal_chain` uses `Goal.name` and fetches unknown
  parents in bounded root-first batches; the CPM backward pass relaxes to
  the tightest late start (diamond graphs — found live by the E2E).
- `backend/app/events/handlers.py` — `handle_execution_state` bridge on
  the REAL catalog event names (project.*, task.*, milestone.*,
  dependency.added/removed, decision.*, goal.*); never commits.
- `backend/app/knowledge/intelligence_engine.py` — the `execution` intent
  block + `_resolve_execution_project` (name-overlap, then substring,
  then sole-project; matches draft|active|paused) + `_execution_query`
  (org-wide or scope-checked); `next`/`blocked`/`overdue` intents upgrade
  to the execution surfaces for org-wide callers with honest fallback.
- `backend/app/api/v1/brain.py` — the four `/execution/*` endpoints with
  `_people_access` governance and lazy materialization.
- `backend/app/events/event_models.py` + `backend/app/models/__init__.py`
  — model registration for `create_all`.
- `backend/tests/test_4g1_engine.py` (14), `test_4g1_surfaces.py` (8),
  `test_4g1_api_governance.py` (6) — the 28 slice tests.
- `backend/scripts/accept_slice4g1.py` — 10 live acceptance checks.

Frontend (new):

- `frontend/lib/api.ts` — Slice 4G.1 block: types (`ExecutionCommandResponse`,
  `ExecutionNextResponse`, `ExecutionProjectDetail`, `ExecutionQueryResponse`,
  critical path, blockers, systemic blockers, capacity constraints, pending
  decisions, goal chain, outcome, history) and one function per surface
  (`getExecutionCommand`, `getExecutionNext`,
  `getExecutionProjectDetail`, `recordExecutionOutcome`, `askExecution`).
- `frontend/app/(app)/execution/page.tsx` — the Execution Command Center:
  five stat cards, the command-center rows (health, explain, primary
  cause, last change, counts), the "What should happen next" prioritized
  list, "Ask the brain" (execution answers rendered as project records),
  "Why projects change", and the full project record panel: health bar +
  explain, goal chain, critical path with slack, blocker chains, systemic
  blockers, capacity constraints, pending decisions, "What changed over
  time" history, the outcome record and the projects:manage-gated outcome
  form.
- `frontend/components/sidebar/Sidebar.tsx` — "Execution Center" entry in
  the Knowledge group (`brain:read`).
- `frontend/e2e/slice4g1-execution.spec.ts` — Playwright E2E.

## Design decisions locked by tests

- **The record is change-driven, never user-written.** Projects, tasks and
  dependencies created through the real API produce the record via the
  durable bus. The engine's only write path for the record itself is
  refresh-on-event; the only other write is the human-gated outcome.
- **Advisory means advisory.** The outcome record is written by a human
  (projects:manage); after recording, the project stays exactly as it was
  (live check 6; E2E asserts status stays "active").
- **Exact-once by snapshot identity.** Replay protection keys on
  `ProjectExecutionSnapshot.source_event_id` — the state row's id is
  overwritten every refresh and can't prove identity. The engine test
  asserts exactly one snapshot per source event across replays, and the
  live check drains the bus after a full session and sees the record
  unchanged.
- **Command surfaces are org-wide.** `/execution/command` and
  `/execution/next` 404 for scoped callers (same idiom as 4F.6/4F.7);
  project detail is scope-checked per project; hidden projects are
  indistinguishable from missing ones (live check 8).
- **The intent layer upgrades, then falls back honestly.** "what should we
  do next?" returns `execution_next` when the org has execution data, and
  the knowledge-action `next` answer otherwise; "what is blocked?" upgrades
  to the execution surfaces and falls back to the knowledge `blocked`
  answer — never a fabricated execution record (slice test asserts the
  fallback intents exactly).
- **The critical path must be the real CPM.** The backward pass relaxes to
  the tightest late start: a task with two successor paths takes the
  minimum, not the first-visited (diamond graphs). The bug surfaced live
  (slack flip-flopped with dependency insert order), was fixed, and is now
  pinned by the engine CPM test and the E2E.
- **Timestamps are timezone-safe.** Every new `DateTime` column is
  `DateTime(timezone=True)`.

## Verification

Backend unit tests (the slice):

```
28 passed (test_4g1_engine 14 / test_4g1_surfaces 8 /
           test_4g1_api_governance 6) in 99.08s
```

Hermetic SQLite, event-bus drains, register_org per test, tenant isolation
covered; every scenario runs through the real API to enqueue the durable
events.

Full cross-slice regression (the complete backend suite, hermetic SQLite,
pytest-xdist 6 workers):

```
903 passed in 1006.86s (0:16:46)   (plus the 28 slice tests = 931 collected)
```

Live acceptance (`backend/scripts/accept_slice4g1.py` against the live
backend on :8999 — final result exactly):

```
10/10 checks passed:
 1. project.created fed the command center from the real event stream
 2. the real critical path is computed with slack and projected finish
 3. the overdue critical task drives the primary cause and explain
 4. blocker analysis names the root cause chain
 5. execution next prioritizes the overdue critical-path work
 6. the outcome record is written by a human and never rewrites the project
 7. the universal query routes execution questions to the execution record
 8. scoped callers: command/next 404, own project visible, others invisible
 9. snapshot history answers 'what changed' over time
10. replay is exact-once: the execution record is stable under replay
```

Two live bugs were found and fixed during acceptance: the outcome
snapshot's synthetic `source_event_id` overflowed the `varchar(32)` column
on Postgres (SQLite never enforces length — the fix is a 32-char id), and
the CPM backward-pass first-visit lock (above).

Playwright E2E (`frontend/e2e/slice4g1-execution.spec.ts`):

```
1 passed (33.6s) — full journey through the live UI + API: real project +
tasks + dependencies + blocked transition through the real API and the
event bus; API contracts (command center with Timeline pressure + explain,
real CPM 9h/9h/slack 0 with all three tasks critical, blocker chain rooted
at A, next-first prioritization with the critical item first, the outcome
record leaving the project untouched) and the Execution Center UI: stat
cards, command-center row with explain + "critical past due", the
prioritized next list, the project record panel (critical path, blocker
chains, history, outcome), and "Ask the brain" answering "is the E2E Atlas
Launch project on track?" with the deterministic execution record.
```

Frontend static check: `npx tsc --noEmit` clean (repo gate: tsc/next build;
ESLint is not configured — `npm run lint` is interactive and not a gate).

## Universal Company OS moat test

- **5-person startup:** "is the launch on track?" — one screen, zero
  configuration: the platform builds the execution record from the tasks
  and dependencies the team already works with, explains the health in one
  human sentence, shows the real critical path and what should happen next;
  a human records the outcome. ✓
- **50,000-person enterprise:** the same canonical tables with indexed,
  bounded reads (200 projects, 300 tasks/project, 40 snapshots, 20 next
  items), per-org locks, tenant isolation and scoped visibility answer the
  same questions with the SAME architecture; replays converge exact-once. ✓
- **Connected, not isolated:** the record is fed by the platform's own
  durable event stream (projects, tasks, dependencies, milestones,
  decisions, goals), reads the 4F.6 capability record and the 4A decision
  registry, routes through the Company Brain intents, and its outcome
  becomes evidence — a competitor cannot copy this as a standalone
  "project health" page. ✓

## Post-acceptance state

- The running backend on :8999 is the verified 4G.1 code (the live
  acceptance and E2E ran against it end-to-end); the live Postgres 4G.1
  tables were built by `create_all` on startup and the varchar(32) fix is
  live.
- Commit + tag `vcos-slice-4g1-complete` created; workspace junk cleaned.
- **STOP**: next slice is 4G.2 per the locked roadmap.
