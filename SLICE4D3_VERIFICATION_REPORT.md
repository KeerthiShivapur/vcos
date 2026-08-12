# Slice 4D.3 Verification Report — Organizational Memory Automation

**Date:** 2026-08-12
**Slice:** 4D.3 — Change-driven memory formation (event → experience → context → outcome → lesson → historical memory), governed read surface (`/brain/memory/*`), Company Memory frontend tab

## Acceptance results

| Script / check | Result |
|---|---|
| `backend/scripts/accept_slice4d3.py` (live, 12 checks) | 12 passed, 0 failed (exit 0) |
| Backend slice-4D.3 pytest (6 files, 26 tests) | 26 passed |
| Full backend `pytest -q` | 589 passed (563 pre-existing + 26 new), 0 failed |
| Full Playwright `e2e/*.spec.ts` (15 tests incl. new `slice4d3-memory.spec.ts`) | 15 passed (7.8m), 0 failed |
| Frontend `npx tsc --noEmit` | passed (exit 0) |
| Frontend `npm run build` | passed (exit 0) |

All runs executed against the live stack (uvicorn `http://localhost:8999`, `next dev` `http://localhost:3000`). ESLint is not configured in this repo (`next lint` opens an interactive setup prompt) — the established frontend regression is tsc + build + Playwright.

## Slice 4D.3 coverage exercised by `accept_slice4d3.py`

1. **Change-driven formation:** blocking a dependency-gated task emits `task.blocked`; draining the durable event bus and running the `memory_formation` worker forms an experience memory with `memory_category=experience`, evidence refs (event/task/project/dependency), project-scoped `auth_scope`, no outcome until resolution.
2. **Evidence lineage:** `/brain/memory/{id}/evidence` resolves task/project/dependency/event refs into titles, urls and human-readable event descriptions.
3. **Outcome journey:** blocker completion (`task.unblocked`) + dependent completion (`task.completed`) resolve the open experience positive and derive a lesson memory; a manual `negative` outcome POST is recorded in history but **rejected on the memory** (monotonic, upgrade-only).
4. **Historical search:** semantic retrieval (deterministic provider) hits the blocked experience, returns explicit confidence + `fact_kind=observation`; unrelated query matches 0; blank question → 422.
5. **Timeline:** episodes link memories to their forming events (`episode_events ⊆ source_event_ids`); experience/lesson/outcome categories all present.
6. **Related links:** bounded (≤5) and governance-filtered.
7. **Feed governance:** a project-scoped `brain:read`-only reader sees only their project's memory; an out-of-scope memory is 404 on get/evidence/related (never 403/leak); outcome POST → 403.
8. **Tenant isolation:** rival organization's feed contains nothing from the seeded org.
9. **Exactly-once replay:** re-draining + re-running the worker never duplicates memories.
10. **Brain integration:** `/brain/answer` cites historical memory claims with `type=memory` evidence and `/brain/memory/...` urls (history questions only; labeled with memory category + fact kind).
11. **Worker + scheduler:** `memory_formation` registered at `interval_seconds=300`, runs on demand, idempotent.
12. **Endpoint contract:** anonymous feed/timeline → 401/403; invalid `outcome_type` → 422.

## No-OpenAI guarantee

- Memory embeddings reuse the Slice 4D.2 deterministic provider (`app/knowledge/embeddings.py`) — zero OpenAI references; scores are explicit retrieval signals.
- The pipeline is fully observational: it reads operating tables and records `CompanyMemory`/`MemoryEvent`/`MemoryOutcome` rows only. The sole write-back surface is `POST /brain/memory/{id}/outcome` (`brain:manage`), which records an observation — never mutating any operating entity.

## Notable fixes during verification

- **Missing awaits in the formation pipeline** (`app/memory/formation.py`): `_find_open_by_entity`, `_resolve_project_scope` (3 call sites), and the `_upsert_memory` dedupe lookup were not awaited — every formation job crashed after the first event.
- **`task.blocked` lesson crash:** lesson lambdas did not accept `(ctx, payload)`; `task.unblocked`/`task.completed`/`task.commented`/`decision.executed`/`decision.implemented` were missing `title` lambdas (dereferenced `None`).
- **Summary fallback ordering:** `(outcome or title)` evaluated the outcome lambda before it existed; reordered so the outcome is computed first.
- **Same-second project-code collisions:** `project_service.create` now generates `PRJ-{yy%m%d%H%M%S}{microsecond//1000:03d}`; three consolidation tests created multiple projects in the same second and hit the unique `(org, code)` constraint.
- **Nondeterministic related links:** the CAS re-select in `memory_formation_worker._claim_batch` had no ORDER BY, so SQLite's B-tree order (random UUIDs) varied per run and the newest-written memory sometimes linked fewer peers; now FIFO (`created_at ASC, id ASC`), making episode processing order deterministic.
- **Outcome monotonicity in `record_outcome`:** manual outcomes are gated by `_OUTCOME_RANK` (upgrades only, confidence bump capped at 0.95); history is always appended to `memory_outcomes`, so downgrades are traceable even when rejected.
- **Acceptance/E2E contract details:** the dependency endpoint takes `depends_on_task_id`; a blocked experience has `outcome_type=null` until resolved; memory inherits project scope only when the project is governance-scoped **before** the episode forms (downward-only visibility); timeline is ordered by `occurred_at DESC` so the first dependent episode is the outcome, not the lesson.
- **Global event-queue backlog:** `process_pending` is global FIFO; acceptance pre-drains (dispatch until `processed == 0`, `limit=500` polls) exactly as Slice 4D.2 documented.

## Repository state

- Tag: `vcos-slice-4d3-complete`
- Per slice rules: slice 4D.4 is NOT started.
