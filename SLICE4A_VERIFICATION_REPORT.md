# VCOS Slice 4A — Verification Report

Status: **COMPLETE** — tag `vcos-slice-4a-complete`

## Acceptance gate results

| Gate | Result |
|---|---|
| Backend pytest suite | **504 passed, 0 failed** (497 original + 6 decision-execution tests + 1 my-work regression test, 22:47) |
| Playwright E2E suite (slice1–7 + slice4a, 10 tests) | **10/10 passed** (final run 3.8m; slice4a spec also passed standalone) |
| `scripts/accept_slice1.py` (live API) | **34 passed, 0 failed** |
| `scripts/accept_slice2.py` (live API) | **32 passed, 0 failed** |
| `scripts/accept_slice3.py` (live API) | **35 passed, 0 failed** |
| `scripts/accept_slice4a.py` (live API) | **32 passed, 0 failed** |

All acceptance scripts run against the live backend (`:8999`) with fresh
tenants, invite/accept flows, tenant-isolation checks, live event-worker
notification delivery, and the synchronous auto-implement worker path.

## Delivered scope

- Decision → Execution loop: every decision carries structured follow-up
  actions (text, owner, project, goal, due date, status). Executing an action
  creates a real task carrying the full lineage (`decision_id`, `goal_id`,
  `project_id`, assignee = action owner, description cites the decision
  context, `decision` tag, `decision` citation payload).
- Closed loop: completion of every produced task auto-implements the decision
  (executed actions → `completed`, unexecuted actions stay `pending`).
- API: `POST /decisions/{id}/actions/{index}/execute` (duplicate guarded,
  400), `GET /decisions/{id}/tasks` (hydrated), validation on create/update
  (ValueError → 400), cross-tenant decision/task links rejected (400/404).
- Canonical side effects re-used: `decision.implemented` event + audit,
  `decision.executed`/`decision.created` trail, notification to the action
  owner (`task.assigned … from decision '…'`) and to decision
  participants/decision-maker (`decision.implemented`), knowledge-graph
  `produces` edge (decision → task), search indexing of follow-up text.
- Frontend: decision form (follow-up action block: owner/project/goal/due
  date), convert-to-task on the decision detail page with success toast and
  live status chip (`text · todo`), task Why-card ("Why this task exists" →
  decision link, reason, context, goal), my-work task subtitle
  (`· from decision "…"`).
- Tests: `backend/tests/test_decision_execution.py` (6 tests),
  `frontend/e2e/slice4a-decision-execution.spec.ts` (full UI journey).

## Bug fixes surfaced by verification

- `TaskUpdate` silently dropped `goal_id`/`decision_id` (extra-field discard)
  → added to the schema; removed the stale "not editable" guard.
- `execute_action` passed `due_date` as a string into `Task(...)` →
  `asyncpg` DataError; now coerced via `date.fromisoformat` with safe
  fallback.
- `GET /decisions/{id}/tasks` returned un-hydrated tasks (`decision: null`)
  → hydrates each task.
- Task Why-card `reason` was empty for UI-created decisions (form sends
  `description`) → hydration falls back to `summary or impact or
  description`.
- **Pre-existing latent bug (not introduced by 4A):** `my_work` compared
  `date < datetime` (`t.due_date < now`), crashing `/my-work` with
  `TypeError` for any due-dated task — the exact shape 4A conversion produces.
  Fixed both the overdue filter and the `today_tasks` sort key
  (`now.date()`); regression test `test_my_work_with_due_dated_tasks`
  added. This was blocking the E2E my-work lineage check.
- `create`/`update` decision endpoints leaked 500s on validation errors →
  wrapped as 400.

## Regression notes

- E2E flakiness observed under sustained suite load is infrastructure, not
  4A: the event-worker fleet intermittently starves on the PG connection
  pool (`QueuePool limit … connection timed out`, "too many clients"), which
  temporarily delays worker-delivered notifications (slice2 "Manager changed",
  slice3 dependency-unblock) and caused one client-side 2.5s fetch abort on
  decision create (preflight 200, POST aborted before send). The same specs
  pass immediately after a clean backend restart; no worker timeout exceeded
  its poll window on the final runs.
- `decision.implemented` notifications target decision participants + the
  decision-maker (not the creator by default) — exercised via
  `participants`/`decision_maker_id` in the accept script, mirroring the
  backend tests.
- Out of scope (untouched, per plan): messaging (4B), RBAC refinement (4C),
  intelligence/autonomy (4D), twin/autonomy decision duplicates.
