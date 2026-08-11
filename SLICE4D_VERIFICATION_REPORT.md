# Slice 4D.1 Verification Report — Canonical Company Intelligence & Evidence Layer

**Date:** 2026-08-11
**Slice:** 4D.1 — Governance-scoped, evidence-backed `/brain/answer`, connected relationship graph, permission-filtered search, change-driven company-intel consumers

## Acceptance results

| Script / check | Result |
|---|---|
| `backend/scripts/accept_slice4d.py` (live) | 14 passed, 0 failed (exit 0) |
| Backend slice-4D.1 pytest (5 files) | 21 passed in 40.90s |
| Full backend `pytest tests/ -q` | 551 passed in 1023s (17:03) — run before the final one-line `_WORKER_MODULES` addition; that addition re-verified by the 21-test slice suite + full Playwright + live acceptance |
| Full Playwright `e2e/*.spec.ts` | 14 passed (5.5m), 0 failed |
| Frontend `tsc --noEmit` | passed (exit 0) |
| Frontend `npm run build` | passed (exit 0) |

All runs executed against the live backend (uvicorn, `http://localhost:8999`) and frontend (`next dev`, `http://localhost:3000`).

## Slice 4D.1 coverage exercised by `accept_slice4d.py`

1. `/brain/answer` canonical contract: 200 with non-empty `claims[]`; evidence refs carry real entity ids/types.
2. Grounded answers: cited project evidence matches the actual created project (no fabrication).
3. Tenant isolation: outsider org receives zero cross-tenant evidence.
4. Messaging evidence is membership-gated: conversation member sees `message`-type evidence for "decided/discussed" questions.
5. Scoped-only caller denied: after removing the org-wide role assignment, `/brain/answer` returns 403.
6. Permission-filtered search: member finds the message, non-member does not.
7. Search tenant isolation: outsider org gets no hits on the tenant's project.
8. Relationship sync: `POST /brain/graph/relationships/sync` returns `{"synced": n>=1, "mode": entity|recent}`.
9. Bounded traversal: `task -> project` reachable; `limits.max_nodes == 64` enforced.
10. Graph RBAC: sync requires `brain:manage` (403), traverse requires `brain:read` (403).
11. Change-driven consumer: `messaging.message_sent` is processed by the event worker (`processed_at` set) and the conversation→message edge becomes reachable via traversal.
12. Idempotency: single message node before and after a re-sync (no duplicate edges).
13. Worker on demand: `POST /intelligence/workers/company_intel/run` → 200 `{worker, processed>=0}`, repeat run also 200.
14. Scheduler registry: `/intelligence/workers` exposes `company_intel` with `interval_seconds == 900`.

## Notable fixes during verification

- **Stale backend process:** an old uvicorn from a previous session still owned port 8999 and served code without the brain router (404 on `/brain/answer`); killed both uvicorn PIDs and restarted cleanly.
- **Stale Next.js build cache:** after `npm run build`, the dev server threw `TypeError: __webpack_modules__[moduleId] is not a function` on `/login`; fixed by clearing `.next` and restarting `next dev`.
- **`_WORKER_MODULES` gap:** the scheduler registry contained `company_intel` but the workers API (`_WORKER_MODULES` in `backend/app/api/v1/intelligence.py`) did not, so the worker was neither listable nor on-demand-runnable; added it.
- **`/intelligence/graph/edges` hides message edges:** the endpoint returns the org-graph subset (project/task/employee edges) and filters message/conversation edges; the acceptance now verifies change-driven edges through `/brain/graph/relationships/traverse` from the conversation node, and the events API's `processed_at`.
- **Slow manual event dispatch:** `POST /intelligence/events/process` exceeds 60s on the ~1M-event dev DB; acceptance polls the background event worker (≤60s cadence) instead of dispatching synchronously.
- **Scoped-only 403 semantics:** the pytest denies `/brain/answer` only after the caller's org-wide role assignment is removed; the acceptance mirrors this by deleting the employee's org-wide assignment.
- **Cold-start page load:** the first `/intelligence` load during the E2E run exceeded the 15s expectation (DB warmup of aggregate endpoints); subsequent runs pass (42.3s total for the spec).

## Repository state

- Commit: (post-`63b4d81`) Slice 4D.1 commit
- Tag: `vcos-slice-4d-complete`
- Per slice rules: slices 4D.2–4D.7 are NOT started.
