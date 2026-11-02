# Production Go-Live + Truth Center — Evidence Artifact

Date: 2026-10-17
Scope: mandate "PHASE 0 PRODUCTION GO-LIVE + TRUTH CENTER IMPLEMENTATION"
Environment: Windows, Python 3.13, FastAPI + SQLAlchemy 2 (async), PostgreSQL 18 (real PG for all verification), Next.js frontend.

## 1. What was implemented

### Phase 0 — production hardening (backend)
- Production config guard: refuses to boot with placeholder secrets (`SECRET_KEY=change-me-in-production`) or debug enabled when `APP_ENV=production`.
- Readiness endpoint `/health/ready`: checks database (real session probe) and returns 503 when dependencies are down.
- Email transport: SMTP with TLS + retry for production; console transport suppresses full message bodies outside development.
- Worker runner (`app/workers/runner.py`): start/stop lifecycle for the scheduler.
- AI verification entrypoint `app/verify_ai.py`: `verify(live=False)` config-level validation (returns 0), `verify(live=True)` for provider calls when credentials exist.
- Canonical integrity endpoints made real: `/api/v1/canonical/integrity/scan|findings|findings/{id}|status` compute findings live from canonical tables (no stubs).

### Demo company (fictional, canonical-path, idempotent)
- `app/demo_company.py`: seeds "Nova Labs Demo" (`nova-labs-demo`) through the product's own HTTP API only; contradiction is written via the ratified engine's exact-once writers (`company_operating_engine.record_decision` + `surface_contradictions`).
- Per-entity idempotency: every entity is checked via list endpoints before creation (`_ensure`), so reruns backfill missing pieces and never duplicate.
- Canonical operating chain: authorization (linked to canonical decision `demo-dec-apollo-001`) → reviewed to `approved` → commitment (`conditional`, linked `authorization_id`) → state `pending_authorization`. Result: zero structural/operating integrity findings for the healthy demo chain.
- Demo credentials: `demo.admin@novalabs-demo.com` / `Demo-Password-2026!` (documented demo-only default).

### Permission reachability fixes (go-live critical)
Endpoints were hard-locked behind permission codes that do not exist in the catalog (dotted syntax; `RequirePermission` has no wildcard). All were corrected to real catalog codes:
- `app/api/v1/governed_commitment.py`: `commitment.read/write` → `commitments:read/manage`; `authorization.read/write` → `authorizations:read/manage` (13 sites).
- `app/api/v1/adaptive_execution.py`: same commitment mapping.
- `app/api/v1/adaptive_planning.py`: `adaptive_planning.read/write` → `intelligence:read/manage` (no dedicated catalog family exists; intelligence family is the closest ratified fit).
- `app/api/v1/decision_intelligence.py`: `decision_intelligence.read/write` → `decisions:read/manage`.
- `governed_commitment.py` response models `CommitmentResponse`/`AuthorizationResponse` never matched the ORM (endpoints were unreachable, so the defect was latent). Fixed: `model_config = ConfigDict(from_attributes=True)` + fields aligned exactly to ORM columns (removed non-existent fields `completed_at`, `condition_status`, `authorization_type`, `authorization_conditions`, `reviewed_*`, `expired_at`, `revoked_*`, `rejection_reason`; `valid_from/valid_until/start_date/target_date` are datetimes; added `approval_required`, `action_ids`, `fulfilled_at`, `fulfilled_by`). No frontend or backend consumer of the removed fields exists.

### Truth Center (frontend, inside the ratified architecture)
- `frontend/app/(app)/truth-center/page.tsx`: 5 tabs — integrity, contradictions, provenance, answers, ledger — all reading the existing real APIs (`canonical/integrity`, brain, operating decisions). No mock-only data.
- `frontend/lib/api.ts`: added Integrity*/Contradiction/Provenance types + functions; reused existing `listCompanyDecisions` / `getCompanyDecisionQuality` (removed duplicate definitions).
- Sidebar: "Truth Center" nav item (executive section, `ShieldCheck`, `PERMISSIONS.BRAIN_READ`).
- Pre-existing frontend breakage fixed so the app builds: `search/page.tsx`, `lib/permissions.ts` duplicates, `workspace/page.tsx` (41 type errors), additive compound API in `components/ui/Tabs.tsx`.

## 2. Commands run and results

### Backend tests (real PostgreSQL `vcos_test`)
```
DATABASE_URL=...vcos_test TEST_DATABASE_URL=...vcos_test python -m pytest tests/test_production_hardening.py tests/test_truth_center_backend.py -q
=> 15 passed in 4.15s
```
Coverage: prod secret/debug guards; readiness 200 (real PG sessionmaker monkeypatch) and 503 (broken session); email console body suppression vs dev retention; worker runner lifecycle; `verify_ai(live=False)==0`; integrity scan status consistency + coverage notes; findings match status + severity filter; 404 for missing finding.

### Schema verification (drift reconciler, additive only)
- `vcos_test`: 27 missing columns added (e.g. `sessions.device_fingerprint`), 0 failed.
- `vcos4` (production schema): 0 missing columns.

### Demo E2E on vcos4 (backend `127.0.0.1:8999`, real HTTP)
```
python -m app.demo_company --with-db   => exit 0, full report: all entities exist,
  created authorization budget → approved authorization budget → created commitment delivery deadline
python verify_demo_e2e.py
  PASS login / org / users / 3 demo decisions
  PASS integrity status real (200)          PASS integrity scan ran total_findings=0
  PASS findings match status (0 == 0)       PASS demo contradiction visible (1 row, both sides)
  PASS brain ask answers (200, 3 citations) PASS evidence for decision (404 as expected)
=> 12/12 checks passed
```
Idempotency: rerunning the seeder creates nothing and reports "contradiction already present (exact-once)".

### Frontend
```
npx tsc --noEmit   => 0 errors (first fully clean run)
npm run build      => exit 0 (includes /truth-center 7.47 kB)
dev routes /workspace /search /decisions /truth-center => all HTTP 200
```
Note: `npm run lint` prompts interactively (ESLint never configured in this repo — pre-existing, not a gate).

### Lint
`python -m pyflakes` clean on all changed backend files.

## 3. Acceptance checklist status

| Item | Status |
|---|---|
| Real deployment | BLOCKED — no hosting target provisioned (external prerequisite) |
| Public HTTPS URL | BLOCKED — `app.vcos.io` / `api.vcos.io` do not resolve (external) |
| Production secrets | BLOCKED — no secrets manager provisioned; prod boot guard verified working (intended refusal) |
| Email delivery verified | BLOCKED — no SMTP credentials; transport implemented + tested at config level; console transport safe in non-dev |
| AI verified E2E | BLOCKED live (no provider key configured: `AI_PROVIDER=none`); config verification passes (`verify_ai`) |
| Registration / onboarding | PASS (register + login exercised in demo seeding) |
| Fictional demo company | PASS (seeded, idempotent, canonical chain, E2E 12/12) |
| Health checks + monitoring | PASS (liveness `/health`, readiness `/health/ready` with real dependency probe) |
| Backup/recovery readiness | PASS per prior DR work (runbook v1.1); no new changes |
| Core journey E2E | PASS (12/12 demo journey on vcos4; 15/15 backend tests) |
| No critical security blocker | PASS within tested scope (permission lockout fixed; prod guard; secret hygiene) |

## 4. Notes / residuals
- Transitional demo rows on vcos4 (first-run commitment without authorization) were deleted via a one-off dev-DB cleanup script and re-seeded through the corrected canonical chain. Seeder code itself never mutates raw tables.
- `adaptive_planning.*` and `decision_intelligence.*` had no exact catalog equivalents; mapped to `intelligence:*` and `decisions:*` respectively (CEO/admin roles hold these).
- DR.3 E2E process (pid 7212) observed earlier was not started by this work and was left untouched.
- CORS in `backend/.env` limited to localhost origins; `GROQ_API_KEY` present in local env only (not committed; rotate before sharing).

## Verdict
Phase 0 go-live work and Truth Center implementation are complete and verified on real PostgreSQL: 15/15 backend tests, 12/12 demo E2E, frontend typecheck/build green, permission lockout and latent response-model defects fixed, demo company canonical and idempotent. External prerequisites (hosting/domain, SMTP credentials, secrets manager) remain BLOCKED as expected and are the only items preventing a public deployment claim.
