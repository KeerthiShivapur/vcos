# REAL INTEGRATIONS + COMPANY PROVISIONING E2E — TRACK B EVIDENCE

## Scope

Track B mandate: real integrations + company provisioning E2E — implement, test, run, fix, verify, evidence. This document consolidates the post-change verification matrix executed against a dedicated verification database after the prior test database was rebuilt by the RLS workstream.

**Universal Acceptance Matrix was NOT started (by mandate).**

---

## Environment & Verification Database

| Item | Value |
|------|-------|
| PostgreSQL | 18, localhost:5432 |
| Verification DB | `vcos_test_matrix` (owner `vcos`, dedicated) |
| Schema bootstrap | `python -m app.seed` (create_all from canonical model registry) |
| Table count | **687** (673 before the longitudinal registration fix, see Corrections) |
| Alembic state | stamped head `c9a1f4e7b2d8` (`alembic stamp head`) |
| RLS | OFF (see RLS Status) |
| VCOS_TEST_MODE | 1 for acceptance suites; payment suite sets 0 at import (run isolated) |

**Why a separate database (canonical note):** PG logs show `DROP DATABASE IF EXISTS vcos_test` → `CREATE DATABASE vcos_test OWNER vcos` at 2026-10-18 11:40:19 UTC (user's RLS rebuild), which landed mid-run of a prior suite execution; that run's failures were collateral, not a code regression. Per user decision, remaining suites run on `vcos_test_matrix`, leaving `vcos_test` to the RLS workstream.

**Important:** `alembic upgrade head` is **not** a from-scratch schema builder (the chain assumes base schema from seed). Fresh verification DBs are bootstrapped via `python -m app.seed` then stamped to head — the release preflight reads `alembic_version` and a seed-only DB (no `alembic_version` table) correctly reports schema_revision FAILED (fail-closed, pinned by `test_schema_incompatible_blocked`).

---

## Corrections Made During Verification

### 1. Longitudinal model module was unregistered in `app/models/__init__.py`
`app/models/longitudinal.py` (14 canonical tables: `company_timeline_events`, `company_knowledge_snapshots`, `decision_timeline_events`, `learning_timeline_events`, `organizational_timeline_events`, `merger_acquisition_lineage`, `longitudinal_provenance`, `epistemic_calibration_events`, `company_memory_snapshots`, `temporal_query_log`, `future_simulator_calibrations`, `longitudinal_integrity_findings`, `longitudinal_adversarial_tests`, `tenant_historical_isolation`) was never imported by `app/models/__init__.py` — while 14 services import it directly. `init_db()` builds the schema from the `__init__` graph only, so **any freshly bootstrapped database was missing these tables** (integrity scans / longitudinal preflight checks failed → BLOCKED). Fixed by registering the module; matrix DB re-seeded (673 → 687 tables).

### 2. `test_gate7_postgres_verification.py::test_transaction_rollback_recovers` passed vacuously on the stale old DB
The test created a `CompanyGoal` duplicate to force an `IntegrityError` but never committed the pre-failure rows, then asserted they survived the rollback — impossible under canonical SQL semantics. It only "passed" on the old `vcos_test` because that DB's stale schema lacked the canonical `uq_cg_fp_exact_once (organization_id, fingerprint)` constraint. Fixed: commit the good state first, then exercise the real constraint violation → rollback → session recovery; asserts intent + goal both survive and the duplicate is absent. Re-verified green.

### 3. Concurrent-onboarding FK violation (adapter connector identity)
`start_provisioning_only` hardcoded `connector_id="google"` / `"slack"` while resolving the connector by provider (whose id may be a random hex) → FK violation on provisioning insert. Fixed to `connector_id=connector.id` (`google_adapter.py`, `slack_adapter.py`). Test fixtures updated to resolve by provider. 60/60 green.

### 4. Test database isolation (no-argument URLs removed)
`test_google_workspace_integration.py`, `test_slack_integration.py`, `test_payment_integration.py` now honor `TEST_DATABASE_URL` (env override) instead of hardcoded DSNs.

### 5. Cleanup integrity (`tests/conftest.py`)
Integration tables added to the truncate list (`backup_manifests`, `restore_operations`, `connectors`, `connector_instances`, `provisionings`, `health_dimensions`, `approval_policies`, `company_authorizations`, `webhook_deliveries`, `webhook_endpoints`, `sync_cursors`, `sync_runs`, `external_events`); per-table commits so one failing truncate no longer rolls back previously cleaned tables (previously leaked orgs/backups across tests → false preflight statuses).

---

## Verification Matrix (final, on `vcos_test_matrix`)

Commands (pattern):
```powershell
$env:PYTHONPATH="...\backend"
$env:TEST_DATABASE_URL="postgresql+asyncpg://<test-role>@localhost:5432/vcos_test_matrix"
python -u -m pytest <files> -q
```

| Suite | Result | Wall |
|-------|--------|------|
| Slice 2A + 2E (`test_release_candidate_slice_2a.py`, `_2e.py`) | **53 passed** | 19:23 |
| Batch A components + trio (`test_tenant_isolation_adversarial`, `test_real_company_onboarding`, `test_acceptance_real`, `test_integration_adversarial`, `test_release_candidate_hardening_e2e`, `test_real_integrations_provisioning_e2e`) | **69 passed** | 11:12 |
| Slice 2B (`test_release_candidate_slice_2b.py`) | **31 passed** | 6:26 |
| Slice 2C + 2D | **37 passed** | 11:15 |
| Complete Company E2E (`test_complete_company_e2e.py`) | **36 passed** | 0:19 |
| 232-regression set (gate24, gate25, gate32, decision_execution, slice3_step12_approvals, dr_simulation_fail_closed) | **232 passed** | 0:51 |
| Payment integration (isolated run) | **24 passed** | 0:05 |
| Google Workspace + Slack integrations | **60 passed** | 0:20 |
| Backup/restore roundtrip | **29 passed, 1 skipped** | 0:06 |
| Gates: gate33 + postgres infra + gate7 | 59 passed / 1 failed → **after correction: 60 passed, 1 skipped** (gate7 file re-run: 24 passed) | 9:22 + 5:01 |

Matrix total: **all suites green** (2 pre-existing skips; known warnings only, see Limitations).

Earlier smoke context (same DB, pre-final-change): google 30 + slack 30 + preflight-backup 1 = 61 passed 42.72s.

---

## Reals vs Mocks

**REAL (exercised end-to-end against PostgreSQL 18.2 with real services):**
- Company onboarding lifecycle, provisioning state machine, provisionings/steps persistence
- Connector registry + connector instances; adapter contract (`adapter_class(config)` → `authenticate(instance)`)
- Sync runs/cursors, external events, webhook endpoints + deliveries (real HTTP delivery path to local receivers)
- Health dimensions + alert engine; release safety preflight (all checks: backup, DR, canonical/provenance/temporal integrity, governance, tenant isolation, longitudinal, concurrency, observability)
- Canonical mutation boundaries, provenance/temporal/epistemic semantics, fingerprints, integrity scans

**MOCKED at transport boundary (contract tests PASS):**
- Live provider HTTP calls for Google Workspace / Slack / Payment — credentials not available in this environment

**BLOCKED (not claimed):**
- REAL EXTERNAL E2E against live Google/Slack/Payment APIs — BLOCKED: authorized credentials + tenant consent not available
- Hosted-environment verification — BLOCKED: no hosted infrastructure in this environment
- RLS adversarial suites — **user's RLS workstream** (see below)

---

## RLS Status

RLS is owned by the user's separate workstream. `vcos_test_matrix` intentionally has RLS **OFF** (it verifies canonical business logic, matching the profile of the previous test DB). RLS-enabled verification uses the rebuilt `vcos_test` and is not claimed here. `tests/acceptance/test_rls_adversarial.py` was not run/modified in this workstream.

---

## Stack A / Stack B Consolidation

Direction (unchanged, documented): Stack B (`app/intelligence/`) owns lifecycle/API surface and state machines; Stack A (`app/services/`) provides execution engines; integration adapters follow the canonical `adapter_class(config=config)` + `authenticate(instance)` contract registered in `adapter_registry`. No third parallel framework was introduced during Track B — all fixes landed in existing canonical services/models.

---

## Limitations (honest residuals)

- `test_acceptance_real.py`: 9 pre-existing `AsyncSession.get` never-awaited RuntimeWarnings (tests pass).
- 2 pre-existing skips: backup/restore roundtrip (1), gate set (1); conditions unchanged from prior verification.
- Cleanup logs "relation does not exist" for a handful of legacy names (posts/comments/alerts/incident_*) — not part of the canonical schema; cleanup continues past them; harmless.
- Backup-readiness preflight intentionally queries `backup_manifests` globally (no org filter); tests rely on enforced cleanup to isolate.
- Snapshot of schema drift: old test DB carried 691 physical tables incl. stale legacy tables; canonical registry is 687 after registration fix — old DB vs canonical-model drift is what exposed Corrections 1 and 2.

---

## Deliverables

| Item | Status |
|------|--------|
| Track B implementation fixes | ✅ (adapter connector identity; URL isolation; cleanup integrity; model registration; gate7 test correctness) |
| Full suite verification on dedicated DB | ✅ all green (2 skips, known warnings) |
| Evidence document | ✅ this file |
| Universal Acceptance Matrix | ⛔ NOT STARTED (per mandate) |

**Logs:** `%TEMP%\open-coded-*.log` (per-suite run logs retained).

---

## VERDICT: ✅ TRACK B VERIFIED (local), STOPPED BEFORE UNIVERSAL ACCEPTANCE MATRIX (per mandate)
