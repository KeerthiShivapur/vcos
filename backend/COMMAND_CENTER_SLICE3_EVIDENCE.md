# Command Center MVP (Slice 3) — Evidence

**Date:** 2026-10-17 (evening)
**Scope:** Real Command Center page with Decision Inbox, Company State, Risk & Integrity, and
Company Timeline — built entirely on existing canonical APIs. No parallel backend, no mock product
data, no new company-truth model.

## 1. Files created / modified

| File | Change |
|---|---|
| `frontend/app/(app)/command-center/page.tsx` | NEW — Command Center page (4 sections, per-section loading/error/empty/partial/stale states, permission-aware rendering) |
| `frontend/components/sidebar/Sidebar.tsx` | Added `Command Center` nav item to the Executive group (icon `LayoutDashboard`, gate `dashboard:read`); additive only |
| `frontend/e2e/slice8-command-center.spec.ts` | NEW — real-backend end-to-end test (seeding via REST, UI assertions, tenant-isolation check) |

No backend files were modified in this slice.

## 2. APIs reused (all existing; permission shown is the server-side gate)

| Section | Endpoints | Gate |
|---|---|---|
| Decision Inbox | `GET /decisions?limit=200`, `GET /approvals` | `knowledge:read`, `approvals:read` |
| Company State | `GET /dashboard/summary`, `GET /brain/execution/company/state` | `dashboard:read`, `brain:read` |
| Risk & Integrity | `GET /risks`, `GET /canonical/integrity/findings?limit=100` | `risks:read`, authenticated user (existing endpoint contract) |
| Timeline | `GET /executive/timeline?limit=60` | `executive:view` |

Frontend wrappers reused: `listDecisions`, `listApprovals`, `listRisks`, `integrityFindings`,
`getOrganizationTimeline`, `api`. Types reused: `Decision`, `Approval`, `Risk`, `DashboardSummary`
(`@/types`), `IntegrityFinding`, `ExecutiveTimelineEntry` (`@/lib/api`).

## 3. Governance / epistemic behavior implemented

- **Decision != Authorization:** each decision row shows its own state (Proposed/Made/...) and a
  separate `Authorization:` line sourced only from linked approvals
  (`entity_type == "decision" && entity_id == decision.id`). No approval is inferred from the
  existence of a decision; a freshly created decision shows `Authorization: none on record`.
- **Authorization != commitment/execution/outcome:** the inbox deliberately shows no executed or
  verified-outcome claims; only recorded states from canonical tables.
- **Estimates vs verified:** Company State separates verified administrative facts (dashboard
  summary StatCards, hinted "verified") from the operating-engine picture, which is rendered with
  an `Advisory` badge and the note "advisory assessments, not verified outcomes"
  (`advisory_only` flag and `generated_at` rendered when present).
- **Integrity findings** render `status`, `epistemic_classification` and `source_subsystem`
  verbatim; nothing is resolved, reclassified, or scored client-side.
- **Timeline** shows occurred-time and source per event with the note that recording does not prove
  the claimed business outcome; ordering is the API's occurred-time order.
- **Freshness:** every section shows `Data as of <client load time>`; the brain picture shows its
  own server `generated_at`.

## 4. Permission behavior

- Sections degrade independently: missing permissions produce an explicit permission note (with the
  required permission code), never an empty-company state.
- Partial dependency failure: `Promise.allSettled` per section; a failed sub-source renders a
  "Partial data" banner with retry while the other sources still render.
- Backend authorization is enforced server-side (JWT + `require_permission` + organization
  scoping); the frontend only hides/sections UI. A frontend-supplied organization ID is never used.

## 5. Tenant isolation

- All queried endpoints filter by the authenticated organization server-side.
- E2E check: organization B (separate context, real registration) sees zero of organization A's
  decision, approval, and risk records on `/command-center` (`toHaveCount(0)` assertions passed).

## 6. Test / verification commands and exact results

| Command | Result |
|---|---|
| `npx tsc --noEmit` (frontend) | Clean (no output) |
| `npm run build` (frontend) | Success — `/command-center` compiled, 5.52 kB page / 127 kB first load; 80/80 static pages generated |
| `npx playwright test e2e/slice8-command-center.spec.ts` | **1 passed (13.1s)** — real backend on :8999, real UI on :3000 |
| `npx playwright test e2e/slice6-approvals-risks.spec.ts` (regression for sidebar change) | **1 passed (15.9s)** |
| `npm run lint` | Not available — repository has no ESLint config; `next lint` opens an interactive setup prompt. Not weakened, not configured (out of scope). |
| Backend tests | Not run — zero backend files modified in this slice; reused endpoints have existing coverage. |

E2E scenario verified (fresh organization, founder role): seed decision (proposed) + linked
approval (pending) + risk via REST → Command Center shows the decision with badge `Proposed`, the
authorization line `Authorization: pending — <approval title>`, no `Approved` label anywhere
(decision ≠ authorization), the pending-authorization row, verified Company State cards, the risk
entry, and the Company Timeline section; second organization sees none of it.

## 7. Known limitations / remaining gaps (honest)

- Timeline requires `executive:view`; roles without it (e.g. manager) see a permission note. An
  `events:read` fallback (paginated `/events`) is not implemented — would need an events wrapper in
  `lib/api.ts` (documented gap, not a blocker).
- `/canonical/integrity/findings` is gated only by authentication in the backend (existing
  behavior, unchanged here); it returns organization-scoped findings only.
- Lists render the first 6–8 items with a link to the full page; no in-page pagination.
- `getByText`-based e2e locators (no `data-testid` convention exists in this repo).
- Operational note: running `next build` while the dev server is up replaces `.next` and can 500
  the dev server until it recompiles; the dev server was restarted during verification.

## 8. Stop-condition status

- **IMPLEMENTED:** Command Center page, nav entry, e2e test, this evidence document.
- **LOCALLY VERIFIED:** typecheck, production build, slice-8 e2e (real backend + real DB), slice-6
  regression e2e.
- **HOSTED VERIFICATION BLOCKED:** no hosted environment exists; verification is local-only.
