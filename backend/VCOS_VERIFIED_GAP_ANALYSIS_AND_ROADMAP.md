# VCOS - Verified Gap Analysis, Scorecard & Roadmap

Date: 2026-10-19
Method: canonical-reality verification - every figure below was produced by executing
code, querying the live test databases, or reading the actual repository files. Claims
from external/pasted documents were treated as unverified until confirmed. "No fabrication"
rule applied throughout: anything not executed is explicitly marked as such.

Repository: D:\vcos1\workspace\vcos (git repo; HEAD = cd653b8 "Ratify Slice 4H.1";
large intentional uncommitted working tree - active development in progress).

---

## 1. What was executed today (evidence)

| Run | Result | Where |
|---|---|---|
| Legacy suite: tests/test_slice1_foundation.py + test_workflows.py + test_auth.py + test_rbac.py | **36 passed** (was 3 failed / 29 passed) | SQLite conftest suite |
| Regression on PG18: 232-set + complete_company_e2e + payment + google + slack + backup_roundtrip | **381 passed, 1 skipped** (55.15s) | vcos_test_matrix (local PG18) |

Problems found and fixed during this session (see section 4 for detail):
- `auth_service.login` crashed (500) with `MultipleResultsFound` whenever an email existed
  more than once (schema intentionally has no global unique constraint on users.email).
- Global search silently returned 0 results on non-PostgreSQL dialects because the FTS
  service swallowed its own errors instead of triggering the existing LIKE fallback; the
  fallback itself contained a stale import (`FeatureFlag` moved to app/models/feature_flags.py).
- 3 pre-existing legacy test failures + 1 latent failure (test_rbac workspace check).

---

## 2. Verified inventory

| Item | Verified value |
|---|---|
| Router modules (app/api + app/industry/api) | **135** modules containing APIRouter; **139** router instances; 139 include_router calls |
| Canonical model tables | **687** (models imported in app/models/__init__.py); + alembic_version = **688** in vcos_test_matrix |
| Frontend pages | **95** app/**/page.tsx; **90** inside (app) shell; command-center 590 lines, truth-center 612 lines |
| Company demo service | app/demo_company.py, 360 lines |
| Infrastructure assets | infrastructure/{docker,kubernetes,helm,ansible,terraform,disaster_recovery,backups,monitoring,secrets} |
| CI | .github/workflows/ci.yml - push/PR job (backend critical tests on PG18 + frontend lint/build + Playwright step) and schedule/dispatch-only "full-regression" job |
| Frontend stack | Next 14.2.5, Playwright 1.62.1 (testDir ./e2e, baseURL localhost:3000); package.json scripts: dev/build/start/lint - **no "test" script** (CI Playwright step cannot actually run) |
| DR3 baseline | DR3_RECOVERY_BASELINE_EVIDENCE.json: ev-68f7497c48eb, final_verdict VERIFIED, **16/16 gates passed**, RPO 0.120135s, RTO 5.5E-05s, backup bkp-d66819a284d9, 688 tables before/after, WAL healthy |
| RLS inventory | RLS_TENANT_INVENTORY.json: 688 tables classified; TENANT_SCOPED_DIRECT 640; **662 rls_missing_on_scoped**; **rls_enabled_count 0**; 25 special-case review |
| Track B evidence | backend/REAL_INTEGRATIONS_COMPANY_PROVISIONING_E2E_EVIDENCE.md (this workstream; Track B VERIFIED on local PG18) |
| Other evidence docs | 35-G (289/289) and 35-H (415 tests) evidence at repo root; SLICE3_VERIFICATION_REPORT.md (repo root); PRIVATE_ALPHA_READINESS_EVIDENCE.md (474 lines); UNIVERSAL_ACCEPTANCE_RATIFICATION_EVIDENCE.md (pre-existing, claims 20/20 - not re-run by this workstream) |

---

## 3. Corrections to the pasted/claimed figures

| Claim in pasted content | Verified reality |
|---|---|
| "133 routers" | 135 modules / 139 router instances (133 was v1-only counting) |
| "93 frontend pages" | 95 page.tsx total, 90 in-app |
| "35-I evidence exists" | **No 35-I evidence file. Additionally: no 35-I test file, and the CI full-regression job references tests/acceptance/test_longitudinal_reality.py which does not exist** |
| "5 pre-existing gate32 failures" | Stale - gate32 suite is green (part of today's 232-set pass) |
| "validate_recovery() always returns True (legacy gap)" | Incorrect - it is **fail-closed** (raises RuntimeError outside test/dev) and returns hardcoded values explicitly labeled "SIMULATED validation (legacy harness)"; callers audited (execute_recovery L373, test_dr_simulation_fail_closed covers it) |
| "Track B / Real Integrations + Company Provisioning E2E not started - STOP" | Stale - Track B is **COMPLETE and VERIFIED** (evidence doc above; all matrix suites green) |
| "78% complete" | Unsupported number; replaced by the evidence-based scorecard in section 6 (**~75%**, equal weights, stated assumptions) |

Additionally discovered during verification (not in any pasted claim):
- The schedule-only CI "full-regression" job references **8 nonexistent test files**
  (tests/acceptance/test_canonical_mutation.py, test_concurrency.py,
  test_failure_under_load.py, test_longitudinal_reality.py, test_canonical_integrity.py,
  test_reconciliation.py, test_reliability.py, test_recovery.py). Current canonical
  equivalents live at tests/ root (e.g. test_gate6b_canonical_mutation.py,
  test_gate35g2_canonical_concurrency_stress.py, test_gate35h_failure_under_load.py,
  test_gate31_canonical_reality_integrity.py, test_gate32_canonical_reliability.py,
  test_recovery_manifest.py, test_dr3_recovery_baseline.py). NOT rewired in this session -
  mapping is not 1:1 verified and the job is schedule-gated (decision needed, section 8).

---

## 4. Remaining limitations - status

### Solved in this session
1. **Login crash on duplicate emails (real bug, was a 500).**
   `auth_service.login` used `scalar_one_or_none()` on email; users.email has no global
   unique constraint (only an index), so any DB containing the same email twice (legal in
   multi-tenant data, and produced by shared test fixtures) returned HTTP 500 for every
   account with that email. Fix: fetch all candidates ordered by created_at; single
   candidate = unchanged behavior; multiple candidates = credential-verified
   disambiguation (exactly one password match required, otherwise generic 401). File:
   backend/app/services/auth_service.py.
2. **Global search returned 0 results on non-PostgreSQL dialects.**
   `PostgresFullTextSearchService.search_fulltext` caught and logged per-entity errors and
   returned an empty result, so `search_service`'s existing LIKE fallback never ran. Fix:
   explicit dialect guard raises on non-PostgreSQL, activating the LIKE fallback. The
   fallback itself had a stale import (`FeatureFlag` now lives in
   app/models/feature_flags.py) and referenced a nonexistent `flag.enabled` attribute
   (model lifecycle field is `status`); both fixed. Files:
   backend/app/services/postgres_fulltext_search.py, backend/app/services/search_service.py.
3. **3 failing legacy tests + 1 latent legacy failure fixed (now 36/36).**
   - tests/test_slice1_foundation.py::test_suspended_user_cannot_login - used a fixed email
     also created by another test in the same shared SQLite session (duplicate users);
     rewritten to use a unique email via the existing invite/accept helpers; asserts 403.
   - tests/test_workflows.py::test_workspace_lifecycle - asserted the personal-workspace
     API (GET/PATCH /workspace, /workspace/items, /workspace/dashboard) that was
     intentionally superseded by the Universal Workspace router (frontend lib/api.ts only
     calls /workspace/my-day, /company-home, /search, /command, /settings); rewritten to
     exercise the current /workspace/settings read-update-read lifecycle.
   - tests/test_rbac.py - same stale endpoint (GET /api/v1/workspace) changed to
     /workspace/settings (preserves the RBAC intent: employee can use own workspace).
4. **.bak hygiene completed.** Two stray untracked test backups deleted
   (test_gate32_canonical_reliability.py.bak, test_deployment_dr_production_verification.py.bak;
   live originals exist and are green). The archive/service_snapshots_2026-09-19/ directory
   is retained intentionally - it has a README documenting the preserved service snapshots.

### Verified as already-safe (no change needed)
5. `disaster_recovery_service.validate_recovery()` - fail-closed + explicitly labeled
   simulation (see section 3).
6. Historical WAL archive failures (165) - all pre-baseline; recorded in every manifest as
   a permanent honest record; WAL archive is currently healthy per DR3 evidence.
7. Table-count reconciliation - 687 model tables + alembic_version = 688; no missing
   tables (the earlier company_timeline_events gap was fixed in this workstream by adding
   the longitudinal model import).

### Open - blocked on infrastructure or credentials (not code defects)
8. **RLS rollout (user workstream, do not touch)**: 0/662 tenant-scoped tables have RLS
   enabled; 25 tables flagged for special-case review. Until this lands, database-level
   tenant isolation does not exist (application-layer isolation tests are green).
9. **Hosted/cloud verification BLOCKED**: no cloud environment or secrets; real external
   provider E2E (Slack/Google/payment) BLOCKED without authorized credentials/consent.
   All verified runs to date are local PG18 (vcos_test_matrix) or mocked-provider E2E.
10. **pgBackRest not installed on this machine** (Windows dev box uses pg_basebackup path);
    RPO/RTO baseline (0.12s / 5.5e-05s) is local-infrastructure only.
11. **Universal Acceptance Matrix not re-run** by this workstream (pre-existing
    ratification document only).
12. **CI wiring gaps**: full-regression job stale paths (section 3); frontend has no
    `npm test` script so Playwright never executes in CI.
13. **35-I (Longitudinal Reality) suite/evidence absent** - planned but never created.
14. Residual code cleanups (non-blocking): duplicate `version` column on RestoreOperation,
    duplicate calibration_state in longitudinal.py, dead reconcile_unknown references;
    Slice 4 residuals (Groq default model retired, AI_MAX_TOKENS truncation, hosted
    acceptance pending).

**Limitation resolution score: 7 of 13 tracked items resolved/verified in this session;
the 6 remaining are infrastructure/credential-bound or CI-wiring decisions, not application
defects.**

---

## 5. The moat (why this is not "just a feature list")

1. **Canonical reality kernel as the single source of truth.** One governed model graph
   (687 tables, slices 1-4H ratified), explicit prohibition of parallel truth/decision/
   governance engines, provenance and evidence chains enforced by governance gates.
2. **Verification as product DNA, not afterthought.** Every gate produces a reproducible
   evidence artifact (e.g. DR3 16/16 with machine-readable RPO/RTO, 35-G 289/289,
   35-H 415, Track B matrix). Fail-closed guards (e.g. recovery validation) are tested.
   This is the layer competitors cannot retrofit quickly.
3. **One architecture from 1-2 employees to 500K+.** Same schemas/engines for every
   tenant size; universality comes from roles, scopes and surfaces
   (my-day -> manager -> executive -> company-home) rather than separate products.
4. **Full B2B SaaS substrate**: multi-tenant auth/RBAC, audit, events, notifications,
   universal search, workspace, company brain, digital twin, industry packs, marketplace/
   extensions, billing (payment integration), DR, observability, deployment assets.
5. The composite - canonical kernel + universal scale + evidence discipline - is the
   defensible layer. Individual features are copyable; the invariant system is not.

---

## 6. Percentage scorecard (equal weights, assumptions stated)

Assumption: percentage = verified-working scope / scope required for a production B2B SaaS
launch, measured on local PG18 evidence where live infrastructure is unavailable (noted).
Weights: 8 dimensions, 12.5% each.

| # | Dimension | % | Basis | Main blocker to raise it |
|---|---|---|---|---|
| A | Core product / domain breadth | 92 | 687 tables, 135 router modules, all gate suites green, 36P company E2E, 90 in-app pages | residual stubs/dead refs |
| B | Verification & evidence discipline | 85 | Track A+B matrix green; evidence docs per gate; legacy suite now 36/36 | UAM not re-run; 35-I absent; CI stale paths |
| C | Security / multi-tenancy enforcement | 55 | app-layer isolation adversarial tests green; RBAC/audit strong | **RLS 0/662 enabled** (dominant structural gap) |
| D | Reliability / DR / backup | 80 | DR3 16/16, backup roundtrip green, fail-closed guards verified | pgBackRest absent; RPO/RTO local-only; hosted DR unproven |
| E | Integrations | 70 | Slack 30 / Google 30 / payment 24 / provisioning E2E 36 all green | real external credentials (BLOCKED); hosted callbacks |
| F | Deployment / infrastructure readiness | 65 | docker/k8s/helm/ansible/terraform/DR/monitoring manifests exist; CI builds | never deployed to a real cloud env; pgBackRest; npm test gap |
| G | Frontend | 75 | 95 pages, lint+build in CI, command-center/truth-center built | Playwright never runs in CI; hosted acceptance pending |
| H | Observability / operability | 80 | gate34 green in CI; observability routers/surfaces; monitoring configs | hosted telemetry unverified |

**Equal-weight overall: 602/8 = 75.25% (~75%).**

Interpretation: the application core is effectively private-alpha-ready on local
infrastructure. General availability is gated by three things, in order: (1) RLS rollout
(dimension C), (2) a real hosted environment with credentials (dimensions D/E/F/G/H),
(3) re-run of the Universal Acceptance Matrix on that environment (dimension B).

---

## 7. Step-by-step roadmap

### Phase 0 - Stabilize the working tree (DONE this session)
- Fixed login duplicate-email 500; fixed FTS fallback + stale import; fixed 3+1 legacy
  tests (36/36); regression 381 passed / 1 skipped on PG matrix; .bak hygiene.
- Exit criteria met: no known failing tests in the executed sets; zero regressions.

### Phase 1 - RLS completion (user workstream; the single biggest gap)
1. Take each of the 662 rls_missing_on_scoped tables from RLS_TENANT_INVENTORY.json and add
   `ENABLE ROW LEVEL SECURITY` + tenant policy (organization_id = current_setting) per the
   established tenant policy pattern.
2. Resolve the 25 SPECIAL_CASE_REVIEW_REQUIRED tables (documented decision per table:
   shared/global table vs policy).
3. Re-run the inventory generator; require rls_missing_on_scoped = 0 and
   rls_enabled_count = 662+.
4. Re-run tests/acceptance/test_rls_adversarial.py plus the app-layer isolation suites.
5. Produce RLS completion evidence document (inventory diff before/after + test results).
6. Only then flip the application to assume DB-level enforcement (connection role split:
   app role with RLS, migration role without).
- Exit criteria: inventory clean, adversarial suite green, evidence doc ratified.

### Phase 2 - Hosted environment bring-up (requires user decisions: cloud account, region, domain, SMTP, secrets)
1. Choose provider/region (Azure was the earlier recommendation; unconfirmed).
2. Apply infrastructure/terraform (or helm) to create DB, app runtime, object storage,
   monitoring; register domain; configure SMTP + provider secrets in the secret store.
3. Deploy backend + frontend; run migrations (alembic upgrade head) and verify
   `alembic current` = head.
4. Run the acceptance suite against the hosted environment (not mocks); record results.
5. Produce hosted deployment evidence document.
- Exit criteria: hosted API healthy, migrations at head, hosted acceptance green.

### Phase 3 - Real integrations + backup substrate
1. Obtain sandbox credentials for Slack/Google/payment; run real-provider E2E (replaces
   the current mocked-provider PASS with REAL EXTERNAL E2E PASS or documented BLOCKED).
2. Install pgBackRest on the target OS; switch backup manifests off the pg_basebackup
   fallback path.
3. Re-baseline DR3 (rerun DR3_RECOVERY_BASELINE) on hosted infrastructure; update
   DR3_RECOVERY_BASELINE_EVIDENCE.json with the new run id and numbers.
- Exit criteria: real-provider E2E evidence; new DR3 baseline with pgBackRest.

### Phase 4 - Universal Acceptance Matrix rerun + 35-I
1. Rerun the UAM on the hosted environment; replace the pre-existing ratification document
   with a fresh run (this workstream deliberately did not run it).
2. Create the missing 35-I (Longitudinal Reality) suite - the CI step already expects
   tests/acceptance/test_longitudinal_reality.py; write it, run it, produce 35-I evidence.
3. Rewire or retire the CI full-regression stale paths (8 files) once mapping is verified;
   add a real `npm test` script so Playwright executes in CI.
- Exit criteria: UAM evidence current; 35-I evidence exists; CI full-regression green.

### Phase 5 - Private alpha launch + YC
1. Walk PRIVATE_ALPHA_READINESS_EVIDENCE.md as a checklist against the hosted environment.
2. YC Winter 2027 application (deadline Nov 2, 2026, 8pm PT) using the now-current
   evidence set.
3. Onboard first design-partner tenants (small) on the same architecture they will use at
   scale.

### Phase 6 - Scale certification (matches the 1-2 -> 500K+ claim)
1. Synthetic tenant load profiles: 1-2 seats, 100s, 10Ks, 500K+; verify identical
   architecture behavior (no product forks).
2. Multi-region DR drill with measured RPO/RTO on real infrastructure.
3. Publish scale evidence; ratify.

---

## 8. Decisions needed from the user
1. Cloud provider/region + domain + SMTP details (Phase 2 prerequisites).
2. Sandbox credentials for Slack/Google/payment (Phase 3).
3. Approval to install pgBackRest on the target machine and re-baseline DR3.
4. Whether to rewire the CI full-regression job now (I did not do it blind - mapping is
   not 1:1 verified).
5. Retention decision for archive/service_snapshots_2026-09-19/ (currently kept per its README).

## 9. Do-not-do list (standing constraints)
- Do not create parallel truth/decision/governance engines.
- Do not touch the user's RLS workstream files.
- Do not claim mocked-provider tests as real external E2E; do not fabricate evidence.
- Do not commit or push unless explicitly requested.
- Do not silently rewire CI paths without a verified mapping.
