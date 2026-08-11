# Slice 4D.2 Verification Report — Semantic Company Knowledge Intelligence

**Date:** 2026-08-11
**Slice:** 4D.2 — Governed hybrid `/brain/knowledge/search`, change-driven indexing (create/update/delete), offline-first embeddings, Semantic Knowledge frontend tab

## Acceptance results

| Script / check | Result |
|---|---|
| `backend/scripts/accept_slice4d2.py` (live) | 14 passed, 0 failed (exit 0) |
| Backend slice-4D.2 pytest (`tests/test_semantic_knowledge.py`) | 12 passed |
| Full backend `pytest -q` | 563 passed (551 pre-existing + 12 new), 0 failed |
| Full Playwright `e2e/*.spec.ts` | 15 passed (9.5m), 0 failed |
| Frontend `npx tsc --noEmit` | passed (exit 0) |
| Frontend `npm run build` | passed (exit 0) |

All runs executed against the live backend (uvicorn, `http://localhost:8999`) and frontend (`next dev`, `http://localhost:3000`).

## Slice 4D.2 coverage exercised by `accept_slice4d2.py`

1. **Offline provider:** search reports `provider=deterministic` with explicit `semantic_score`, `lexical_score`, `retrieval_score` on every result.
2. **Hybrid ranking:** the matching document ranks first (`_SEMANTIC_WEIGHT=0.6`, `_LEXICAL_WEIGHT=0.4`).
3. **Evidence lineage:** each result carries `source_type`, `source_id`, `title`, `url`, `provider`, `updated_at`, `indexed_at`, `scope`; never `embedding` or `confidence`.
4. **Multi-kind policy:** `Policy` surfaces under `kinds=["policy"]` (approved policy, no `project_id` column — `literal(None)` guard).
5. **Multi-kind wiki:** `Wiki` surfaces under `kinds=["wiki"]` (published).
6. **Change-driven create:** a newly created + published document becomes searchable via `document.created` / `document.published` events.
7. **Change-driven update:** edited content replaces the old content (old-content query no longer hits; stale vectors pruned).
8. **Change-driven delete:** removed document stops surfacing (vector rows deleted via event).
9. **Tenant isolation:** outsider organization sees zero results.
10. **Governance scoping:** delegated scoped manager (brain:read) sees only the project-anchored document, with `scope="project"`.
11. **Governance boundary:** scoped-only caller without delegation gets 403.
12. **Brain integration:** `/brain/answer` cites document evidence from the knowledge store.
13. **Endpoint contract:** blank question → 422; anonymous caller → 401/403.
14. **Worker + scheduler:** `indexing` worker registered at `interval_seconds=1800` and runs idempotently on demand.

## No-OpenAI guarantee

- `app/knowledge/embeddings.py` contains **zero** OpenAI references (grep-verified): the constant is `EmbeddingsApiProvider` for self-hosted / Groq OpenAI-compatible `POST {base}/embeddings` endpoints, plus the deterministic local provider as default.
- `app/core/config.py` defaults to `EMBEDDING_MODEL="bge-m3"` with provider `deterministic | api | groq`; no OpenAI model is configured in the embedding path.
- Tests and E2E prove retrieval fully offline: the deterministic provider hashes tokens into a 256-dim space with explicit scores.

## Notable fixes during verification

- **Policy/SOP/template 500:** those models have no `project_id` column; the candidate query now guards with `getattr(model, "project_id", None)` and `literal(None).label("project_id")`.
- **Zero-overlap noise:** unranked chunks with `retrieval=0` no longer surface; the relevance gate requires a real token overlap (`lexical > 0`) or a cosine above the deterministic hashing noise floor (`_SEMANTIC_FLOOR=0.08`), which eliminated hash-collision artifacts (e.g., 0.0315-noise hits) that made edited content appear to match stale queries.
- **Global event-queue backlog:** `process_pending` is global FIFO across tenants, so stale events from earlier test orgs delayed fresh-org indexing; the acceptance script now pre-drains the queue (dispatch until `processed == 0`) and uses `limit=500` dispatches inside its poll loop.
- **Frontend dev server corruption:** `npm run build` while `next dev` was running corrupted the shared `.next` directory (dev server 404'd on its own chunks → no hydration → native form GET). Cleared `.next` and restarted `next dev`; full suite then 15/15.

## Repository state

- Commit: (post-`e2be8bc`) Slice 4D.2 commit
- Tag: `vcos-slice-4d2-complete`
- Per slice rules: slices 4D.3+ are NOT started.
