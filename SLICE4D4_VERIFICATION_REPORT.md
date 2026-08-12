# Slice 4D.4 Verification Report — Universal Organizational Pattern Intelligence

**Date:** 2026-08-12
**Slice:** 4D.4 — Change-driven universal pattern intelligence (23-rule registry → evidence-backed `pattern_detections` with lifecycle + confidence → governed read surface (`/brain/patterns/*`) → reasoning claims → Pattern Intelligence frontend tab), full lifecycle governance (candidate → emerging → confirmed → persistent → fading → resolved) with exactly-once event lineage

## Acceptance results

| Script / check | Result |
|---|---|
| `backend/scripts/accept_slice4d4.py` (live, 12 checks) | 12 passed, 0 failed (exit 0) |
| Backend slice-4D.4 pytest (7 files, 64 tests incl. `test_pattern_intelligence.py` 6 tests) | 64 passed |
| Full backend `pytest -q` | 595 passed (589 pre-existing + 6 new), 0 failed |
| Full Playwright `e2e/*.spec.ts` (16 tests incl. new `slice4d4-patterns.spec.ts`) | 16 passed (7.6m), 0 failed |
| Frontend `npx tsc --noEmit` | passed (exit 0) |
| Frontend `npm run build` | passed (exit 0) |

All runs executed against the live stack (uvicorn `http://localhost:8999`, `next dev` `http://localhost:3000`). ESLint is not configured in this repo (`next lint` opens an interactive setup prompt) — the established frontend regression is tsc + build + Playwright.

## Slice 4D.4 coverage exercised by `accept_slice4d4.py`

1. **Change-driven formation:** three blocked tasks in a governance-scoped project emit `task.transitioned` events; draining the durable event bus enqueues `pattern.evaluate` jobs (CAS-claimed, exactly-once via `PatternEvent` lineage) and one `repeated_delay` pattern forms with `count=3`, `family=execution`, `scope_type=project`, lifecycle `emerging`, confidence ≥ 0.4.
2. **Evidence lineage:** `/brain/patterns/{id}/evidence` resolves every contributing event (all `task.transitioned`, each with `occurred_at`); the occurrence history endpoint matches `count` exactly.
3. **One occurrence is never a pattern:** a single blocked task in its own scoped project never becomes observable — no row is returned anywhere.
4. **Exactly-once replay:** re-draining the bus and re-running the pattern worker never changes occurrence counts or history.
5. **Legacy surface:** phase 9 `GET /intelligence/patterns?status=open` still lists lifecycle patterns (the old `"open"` filter maps to all active lifecycle states via `ACTIVE_PATTERN_STATUSES`).
6. **Governance:** a project-scoped `brain:read`-only reader sees their project's pattern; a hidden project's pattern is 404 on get/evidence/related (never 403/leak); `PATCH` status → 403 for them.
7. **Tenant isolation:** rival organization sees nothing of the seeded org's patterns.
8. **Brain integration:** `/brain/answer` answers pattern-flavored questions from deterministic `reasoning_engine` claims (`kind=pattern`) with `/brain/patterns/{id}` evidence urls.
9. **Worker + scheduler:** `pattern` worker registered at `interval_seconds=120`, runs on demand, idempotent.
10. **Lifecycle:** `PATCH /brain/patterns/{id}` acknowledge persists and lists under `status=acknowledged`; invalid status → 422 via the legacy route.
11. **Endpoint contract:** anonymous list/get → 401/403; missing pattern → 404; invalid status → 422.
12. **Related links:** bounded (≤10) and governance-filtered.

## No-OpenAI guarantee

- Pattern confidence uses explicit, deterministic signals only (occurrence count vs. rule minimum, span, interval regularity, corroboration from memory/graph/semantic surfaces) — no LLM calls anywhere in the pipeline.
- The pipeline is fully observational: it reads operating tables and records `PatternDetection`/`PatternEvent`/`BackgroundJob` rows only. The sole write-back surfaces are the governed PATCH status endpoints (`brain:manage` / `intelligence:manage`) — human lifecycle actions never mutate any operating entity.

## Notable fixes during verification

- **`_anchor_scope` missing `await`** — the governance scope lookup never ran; every anchored pattern would fall back to the organization scope.
- **`evidence_visible`/`history_visible` scalar precedence** — `await db.execute(...).scalars()` without parens kept an un-awaited coroutine around; the visible row was inside a coroutine object and always truthy, leaking `404` semantics.
- **`task.transitioned` event semantics** — the payload carries the *old* status, so rules read the current DB status from `ctx["task"]["status"]`; `repeated_delay` fires only when the task is currently `blocked`, and `handoff_failure` counts only active-status transitions. `ownership_change_delay` was made dormant (empty event set) because assignee changes are not observable from transition payloads, and `task.updated` is *not* registered (fires after every status change and would double-count).
- **Lifecycle simplification** — occurrence thresholds drive lifecycle directly (2/3/4/6 for candidate/emerging/confirmed/persistent; span ≥ 2×window only gates persistent; 14d fade, 30d resolve); corroboration now feeds confidence only (it no longer mutates lifecycle).
- **E2E/acceptance contract details** — `scope_id` is the **governance scope id** while `auth_project_id` is the anchor project id (predicates must filter on `auth_project_id`); `source_events` in the evidence payload are **event ids**, event names are `evidence[].title`; the Pattern Intelligence tab's accessible name includes its count badge, so the Playwright click must use `getByRole("button", { name: /Pattern Intelligence/ })`; the UI acknowledge step must run before status-filtered API checks because acknowledged patterns leave the active list (by design).
- **`BrainMemoryOutcomeRequest` frontend type was broken** (unclosed interface from an earlier repair) — closed, `outcome: string | null`, duplicate declaration removed.
- **`test_slice3_step4_events.py`** — post-4D.4, `pattern.evaluate` jobs accumulate during work-event processing; the test now drains the pattern worker so the job queue is empty at the end, restoring the pre-4D.4 invariant.

## Architecture notes

- `pattern.evaluate` jobs are unique by `(name, event_id)` and CAS-claimed (status `queued → running`) with stale-reclaim (600s) and orphan adoption of significant events that never got a job — no organization-wide rescan exists anywhere in the pipeline.
- The 23-rule registry (`pattern_types.py`) covers execution, decision, governance, communication, knowledge and organization families with explainable `description`/`detail` templates; rules gate creation with `min_occurrences` (a single event can never be a pattern).
- Schema additions for existing tables shipped as idempotent `_POSTGRES_ALTERS` entries in `app/db/database.py` (verified against the live Postgres `vcos2`); the new `pattern_events` table is created by `create_all`.

## Repository state

- Tag: `vcos-slice-4d4-complete`
- Slice 4D.4 is complete; the next slice is not started.