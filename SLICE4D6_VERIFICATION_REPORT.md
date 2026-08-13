# Slice 4D.6 Verification Report — Unified Company Intelligence Experience

**Date:** 2026-08-13
**Slice:** 4D.6 — Unified company intelligence experience: the Company Brain composes every 4D.1–4D.5 producer (patterns, insights, memory, knowledge) into one canonical `/brain/answer` with cross-source evidence, a unified `Company Brain` tab, graph relationship sync feeding an evidence drawer with graph neighbors, bounded attention/related/overview reads, determinism (reads never mutate), and governance applied **before** retrieval for scoped `brain:read` readers.

## Acceptance results

| Script / check | Result |
|---|---|
| `backend/scripts/accept_slice4d6.py` (live, 20 checks) | 20 passed, 0 failed (exit 0) |
| Slice 4D.6 backend pytest (24 focused tests) | 24 passed |
| Producer regressions 4D.1–4D.5 (65 tests) | 65 passed |
| Full backend `pytest -q` | 627 passed, 0 failed (39:46) |
| Playwright `slice4d6-unified-brain.spec.ts` | passed (multiple consecutive runs, full scenario incl. UI) |
| Full Playwright `e2e/*.spec.ts` (18 tests incl. new `slice4d6-unified-brain.spec.ts`) | 18 passed (8.3m), 0 failed |
| Frontend `npx tsc --noEmit` | passed (exit 0) |
| Frontend `npm run build` | passed (exit 0, 66 routes) |

All runs executed against the live stack (uvicorn `http://localhost:8999`, `next dev` `http://localhost:3000`, Postgres `vcos2`). ESLint is not configured in this repo (`next lint` opens an interactive setup prompt) — the established frontend regression is tsc + build + Playwright.

## Slice 4D.6 coverage exercised by `accept_slice4d6.py`

1. **Canonical seeding:** a dependency-blocked project (3 `finish_to_start` blocker edges → `task.blocked` transitions), a pending decision, a seeded institutional memory, and a published policy document; the full background pipeline (`pattern` → `memory_formation` → `insight` → `indexing`) forms one `execution_bottleneck` insight with inherited project governance scope and anchored `auth_project_id`.
2. **Change-driven composition:** the `task.blocked` signal is the sole seed — the insight's evidence set is built from pattern-typed refs over blocked-task events.
3. **Unified answer:** ONE `/brain/answer` composes all four producers for one anchor — `patterns`, `insights`, `memories`, `knowledge` all ≥ 1.
4. **Answer semantics:** summary names the anchor; confidence bounded `[0, 1]`; `answered_at` present; `scope.org_wide=true` for the founder; `sources_consulted ⊇ {context, patterns, insights, memory, knowledge}`.
5. **Bounded answer surface:** each section ≤ 3 (`ANSWER_SECTION_LIMIT`), related entities ≤ 8 (`ANSWER_RELATED_LIMIT`), claim evidence ≤ 5 (`EVIDENCE_LINK_LIMIT`).
6. **Evidence lineage:** every claim evidence URL resolves — never a dead link in an answer.
7. **Evidence drawer:** `/brain/evidence/{source}` returns cross-source evidence plus graph-neighbor related entities after `/brain/graph/relationships/sync` (the same call the tab's sync button makes).
8. **Graph sync idempotent:** a second sync returns `synced ≥ 0` without error.
9. **Related bounded:** `limit` honored and `truncated` flagged.
10. **Overview bounds:** attention ≤ 3 **per source** (insights/patterns/memories), recent-intelligence counts all ≥ 1 observing the same seeded intelligence.
11. **No-mutation reads:** overview re-reads return identical attention ids.
12. **Determinism:** the same question composes the same summary + confidence.
13. **Observation-only:** answer reads never change task statuses or memory row counts — the brain is read-only over the operating layer.
14. **Governance before retrieval:** a scoped `brain:read`-only reader receives `org_wide=false` and every claim evidence URL in their answer resolves under their scope.
15. **Governance 404:** a hidden project's evidence drawer and related reads are 404 for the scoped reader; nothing from the hidden project leaks into the scoped answer.
16. **Tenant isolation:** a rival org's brain never composes or lists this org's intelligence.
17. **Worker registry:** `pattern`, `memory_formation`, `insight`, `indexing` all registered; insight @ 120s on demand.
18. **Org-scoped on-demand runs:** founder- and rival-triggered worker runs report bounded `processed` counts without cross-org interference.
19. **Endpoint contract:** anonymous answer/overview/sync → 401/403; missing resource → 404.
20. **Knowledge + memory producers cited:** the published policy document appears in `knowledge` and a project-anchored blocked-task memory appears in `memories`.

## No-OpenAI guarantee

- The unified brain is a deterministic composition layer over 4D.1–4D.5 producers — no LLM calls anywhere in the answer/overview/evidence/related path. Answers are observations + explanations with evidence-cited claims, never recommendations, never autonomous actions.
- `company_brain.py` reads patterns/insights/memories/knowledge through the producers' own governed read surfaces (`_visible_to`/`resolve_accessible_ids`), so scope filtering happens before retrieval and cached results can never bypass governance.
- Reads never mutate: answer/overview/evidence/related write nothing to operating tables (verified by check 13: task statuses and memory row counts unchanged across answer reads).
- Memory-feed fallback in the answer pipeline degrades gracefully to seeded/verified memories; hidden (deleted/private) memory rows are excluded from composition.

## Notable fixes during verification

- **On-demand worker runs were global-FIFO, starving the calling org** — with a Postgres-wide event backlog from prior runs, the calling org's jobs were never claimed, so insights never formed live. Fixed by threading `organization_id` through `_claim_batch` and `_adopt_orphan_events` in `pattern_worker.py`, `memory_formation_worker.py` and `insight_worker.py`; `run_once` signatures accept `organization_id` and `POST /intelligence/workers/{name}/run` passes it. The scheduler still drains globally (no `organization_id` → global). After the fix the insight forms on the first live drive attempt.
- **`source_event_ids.contains([id])` rendered as JSON `~~` on Postgres → 500** on `/brain/evidence`. Replaced with `cast(CompanyMemory.source_event_ids, String).like(f'%"{source_id}"%')` in `company_brain.py`.
- **Graph neighbors were empty live** because relationship rows had never synced — the E2E/acceptance now exercise `POST /brain/graph/relationships/sync` (the exact call the tab's sync button makes) before the evidence-drawer assertions.
- **Scoped-answer governance in the E2E used the founder's auth header** (wrongly `org_wide=true`); the spec now passes the scoped reader's `scopedAuth` headers. A manual repro (`dbg_governance.py`) confirmed the scoped flow yields `org_wide=false`.
- **Claim evidence URLs are relative**; the E2E evidence probe must prefix the API base, otherwise it 404s against the frontend origin. The spec now resolves `evidence.url` against the API origin.
- **Known pre-existing console noise (non-fatal):** `Pattern attribute value [a-z0-9-]+ is not a valid regular expression` from the frontend HTML (present in every spec, including untouched slice-1 specs) and transient `REQ-FAIL GET /home?_rsc=... ERR_ABORTED` RSC prefetches that retry successfully.

## Architecture notes

- `/brain/answer`, `/brain/overview`, `/brain/evidence/{type}/{id}`, `/brain/related/{type}/{id}`, `/brain/insights/{id}`, `/brain/graph/relationships/sync` all live in `app/api/v1/brain.py` backed by `app/intelligence/company_brain.py` (`CompanyBrainEngine`), sharing one bounds table (`ANSWER_SECTION_LIMIT=3`, `ANSWER_RELATED_LIMIT=8`, `EVIDENCE_LINK_LIMIT=5` edge 10, `EVIDENCE_CANDIDATES=30`, `OVERVIEW_ATTENTION_LIMIT=3` per source, `RELATED_LIMIT=8` edge 20).
- Answer confidence is a deterministic weighted composition of the evidence-cited claim confidences (patterns/insights/memory/knowledge); claims carry `kind` + `confidence` + `evidence[{type,id,url,title}]` so the UI renders "why this answer reached you" entirely from the payload.
- Access is resolved once per request via `resolve_caller_access` in `company_context.py`; scoped readers get project-filtered composition (governance **before** retrieval), hidden resources return 404 (never 403/leak).
- The frontend `Company Brain` tab (`app/(app)/intelligence/company-brain-tab.tsx`) renders attention (What needs attention), the ask-box with `lib/api.ts` `brainAnswer`, confidence badge, Composed-from sections (Patterns/Insights/Memory/Knowledge), evidence drawer with graph neighbors, related entities, "Why this answer reached you", and recent intelligence.

## Repository state

- Tag: `vcos-slice-4d6-complete`
- Slice 4D.6 is complete; the unified company intelligence experience is verified end-to-end. The next slice is not started.
