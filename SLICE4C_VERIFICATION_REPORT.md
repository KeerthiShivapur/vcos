# Slice 4C Verification Report — Governance Kernel

**Date:** 2026-08-11
**Slice:** 4C — Governance: scoped roles, delegations, approval policies, tenant isolation, audit/events
**Scope change (mid-slice):** approval policies replaced raw approvals as the authority for approval decisions.

## Acceptance results

| Script | Result |
|---|---|
| `backend/scripts/accept_slice4c.py` | 25 passed, 0 failed |
| `backend/scripts/accept_slice4b.py` | 28 passed, 0 failed |
| `backend/scripts/accept_slice4a.py` | 32 passed, 0 failed |
| `backend/scripts/accept_slice3.py` | 35 passed, 0 failed |
| `backend/scripts/accept_slice2.py` | 32 passed, 0 failed |
| `backend/scripts/accept_slice1.py` | 34 passed, 0 failed |
| Backend `pytest tests/test_governance.py` | 11 passed in 82.13s |
| Full backend `pytest tests/ -q` | 530 passed in 2256.26s (37:36) |
| Full Playwright `e2e/*.spec.ts` | 12 passed (8.8m), 0 failed |
| Frontend `tsc --noEmit` | passed |
| Frontend `npm run build` | passed (exit 0) |

All runs executed against the live backend (uvicorn, `http://localhost:8999`) and frontend (`next dev`, `http://localhost:3000`).

## Slice 4C coverage exercised by `accept_slice4c.py`

1. Auth/session for two orgs + two employees (org A, org B outsider).
2. Role creation with permission set (scoped + org-wide).
3. Scope tree + depth cap: `MAX_SCOPE_DEPTH = 32` (`governance_service.py:24`) — depth 33 rejected 400; bounded ancestry enforced.
4. Scoped role assignment: effective permissions at the scope, no sibling leakage (Finance scope unaffected), org-wide authority unchanged.
5. No privilege escalation: assignment requires `governance:manage`; employee cannot assign roles (403).
6. Delegation create → use → revoke (403) → expiry (lazy deny 403).
7. Approval policies gate decisions: employee without the policy permission refused (403); policy holder approves (200).
8. Tenant isolation: outsider org sees only its own scopes (no leak of org A scope names); cross-org member evaluation returns 404.
9. Event trail + audit records for every governance mutation (scope/assignment/delegation/policy lifecycle).

## Notable fixes during verification

- **Stale-response race (e2e):** Next.js StrictMode double-mount caused a slow second `load()` to wipe fresh post-create state. Fixed with a `loadSeq` ref guard in `frontend/app/(app)/governance/page.tsx`; `refresh()` now reloads all six collections (scopes, assignments, delegations, policies, roles, employees).
- **`EmployeeSummary.user_id` missing** (`backend/app/schemas/people.py`): Pydantic stripped `user_id` from `GET /employees`, breaking member→user resolution in the UI; added `user_id: Optional[str] = None`.
- **Depth-cap check in acceptance script:** chain rebuilt to land exactly at depth 32 (`range(31)`), proving the cap at the boundary.
- **Tenant-isolation check semantics:** outsider org's own scope list is legitimately empty (200), not 404; script now asserts no leakage of org A scope names.

## Repository state

- Commit: `fe1579a` (Slice 4c: governance kernel)
- Tag: `vcos-slice-4c-complete`
