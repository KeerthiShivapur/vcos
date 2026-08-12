# Slice 4D.5 Verification Report — Universal Company Insight Intelligence

**Date:** 2026-08-12
**Slice:** 4D.5 — Universal company insight intelligence: composition layer above 4D.1–4D.4 producing one canonical, evidence-backed, governance-scoped `UniversalInsight` per `(org, insight_type, key)`; change-driven evaluation (9 deterministic rules), compositional confidence with self-explanation, observation-only (`UniversalInsight` + `InsightEvent` only), governed read surface (`/brain/insights/*`), reasoning claims, Company Insights frontend tab

## Acceptance results

| Script / check | Result |
|---|---|
| `backend/scripts/accept_slice4d5.py` (live, 20 checks) | 20 passed, 0 failed (exit 0) |
| Backend slice-4D.5 pytest (44 tests across `test_pattern_intelligence.py`, `test_memory_formation.py`, `test_memory_governance.py`, `test_phase20_brain.py`, `test_slice_4d1_brain_answer.py`, `test_universal_insights.py`) | 44 passed |
| Full backend `pytest -q` | 603 passed (595 pre-existing + 8 new), 0 failed (36:17) |
| Full Playwright `e2e/*.spec.ts` (17 tests incl. new `slice4d5-insights.spec.ts`) | 17 passed (9.9m), 0 failed |
| Frontend `npx tsc --noEmit` | passed (exit 0) |
| Frontend `npm run build` | passed (exit 0) |

All runs executed against the live stack (uvicorn `http://localhost:8999`, `next dev` `http://localhost:3000`, Postgres `vcos2`). ESLint is not configured in this repo (`next lint` opens an interactive setup prompt) — the established frontend regression is tsc + build + Playwright.

## Slice 4D.5 coverage exercised by `accept_slice4d5.py`

1. **Change-driven composition:** three blocked tasks in a governance-scoped project → `pattern.detected` → one `execution_bottleneck` insight (`domain=execution`, `severity=warning`, `status=active`, `scope_type=project`, `scope_id` = the project's governance scope, `auth_project_id` = anchor project, `supporting_pattern_ids ≥ 1`, affected project entity present).
2. **Compositional confidence:** bounded `[0, 1]` with all five components (`occurrence_strength` 0.35, `evidence_completeness` 0.20, `pattern_confidence` 0.20, `memory_corroboration` 0.15, `recency` 0.10) and weights summing to 1.
3. **Evidence lineage:** `/evidence` resolves `supporting_pattern_ids` plus pattern-typed evidence refs.
4. **Recompose history:** every feeding history event is a `pattern.*` event; the insight stays `active` on recompose.
5. **Canonical shape:** `key` exposed on the API surface; claim + summary + affected project entity always present.
6. **Deduplication:** exactly one `execution_bottleneck` per `(org, insight_type, key)` — repeated re-evaluation never creates a second row (`uq_universal_insight_key`).
7. **Decision bottleneck:** a pending decision + blocked work composes a `decision_bottleneck` insight without mutating the decision (status stays `proposed`).
8. **Governance bottleneck:** a pending approval composes a `governance_bottleneck` insight without mutating the approval.
9. **Governance:** a scoped `brain:read`-only reader sees their project's insight; a hidden project's insight is 404 on get/evidence/history/related (never 403/leak).
10. **Tenant isolation:** rival organization sees nothing of the seeded org's insights.
11. **Brain integration:** `/brain/answer` cites insight-shaped deterministic claims (`kind=insight`) with `/brain/insights/{id}` evidence urls.
12. **Worker + scheduler:** `insight` worker registered at `interval_seconds=120` and runs on demand, idempotent.
13. **Exactly-once replay:** re-draining + re-running never duplicates insight rows, supporting patterns, evidence or history.
14. **Observation-only:** insight work never changes task statuses, approvals or decisions — no operating-layer mutation anywhere.
15. **Endpoint contract:** anonymous list/get → 401/403; missing insight → 404; invalid-limit reads honored.
16. **Bounded reads:** `limit` honored with `truncated` flag; related links bounded (≤ limit) and governance-filtered.
17. **Confidence bounds:** every visible insight's confidence is in `[0, 1]`.
18. **Governance inheritance:** the project insight's `scope_id` equals the project's governance scope id.
19. **Status surface:** default list exposes active insights; `status=active` filter works.
20. **Related links:** bounded and governance-filtered.

## No-OpenAI guarantee

- Compositional confidence uses explicit deterministic signals only — no LLM calls anywhere in the 4D.5 pipeline. Insights are observations + explanations (claim/summary), never recommendations, never autonomous actions.
- All 9 rules are deterministic threshold/evidence compositions over the pattern/memory/decision/approval neighborhood. `approvals` in the evidence payload are resolved by id, no rows are read for mutation.
- The pipeline is observation-only: it reads operating tables and records `UniversalInsight`, `InsightEvent`, `insight.evaluate` `BackgroundJob` rows only. The worker never mutates tasks, decisions, approvals, patterns or memory.

## Notable fixes during verification

- **`key` missing from the read surface** — `_present` exposed every canonical field except `key`; the acceptance check 7 surfaced `key=None` on the list payload. Added `key` to `_present` (backend `insight_engine.py`) and `key?: string | null` to the frontend `BrainInsight` type; acceptance re-passed 20/20.
- **Playwright full-suite regressions were environmental, not code:** running `npm run build` while the long-lived `next dev` server was up orphaned the dev server's chunk manifest — served pages referenced `.next` assets that returned 404, so React never hydrated and the register form fell back to a native GET submit (no fetch). Restarting `next dev` cleanly restored all 17 specs to green. Backend pool exhaustion at startup is transient (recovers; register latency 200–400 ms afterwards).

## Architecture notes

- `insight.evaluate` jobs are unique by `(name, event_id)` and CAS-claimed (`queued → running`) with stale-reclaim and orphan adoption; insights upsert on `(org, insight_type, key)` with revive from `faded`/`resolved`; fade/resolve sweep mirrors 4D.4 fading semantics.
- Trigger events (`pattern.detected/updated/confirmed/faded/resolved`, `memory.recorded`, `decision.made`, `approval.requested/approved/rejected`) all funnel into one `insight.evaluate` job via the `@on(...)` registration loop; the event catalog gained `insight.detected/updated/faded/resolved`.
- Governance mirrors `pattern_engine._visible_to`: project-scoped insights are visible only inside the caller's visible scope subtree; org-wide insights only to org-wide callers; hidden → 404.
- The API list payload now includes the canonical `key`; frontend `Company Insights` tab (Radar icon, id `company-insights`) renders filters, severity/status/confidence badges, confidence self-explanation, evidence refs, recompose history and related insights, with the "observation, never prescription" footer.

## Repository state

- Tag: `vcos-slice-4d5-complete`
- Slice 4D.5 is complete; the next slice is not started.