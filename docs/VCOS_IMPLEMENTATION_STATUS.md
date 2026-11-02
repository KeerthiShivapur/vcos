# VCOS Implementation Status

**As of:** 2026-10-18 (Windows host, PostgreSQL 18.2)
**Rule:** Status entries cite evidence files. "Ratified" means a durable evidence artifact exists
in the repository. This document is the map; the evidence files are the territory.

---

## 1. Ratified workstreams (do not reopen without defect evidence + regression test)

| Workstream | Evidence file | Verified result |
|---|---|---|
| Gate 35-G — canonical validation integrity closure | `35-G_RATIFICATION_EVIDENCE.md` | 289 tests pass on real PostgreSQL 18.2 + SQLite |
| Gate 35-H — failure under load | `35-H_RATIFICATION_EVIDENCE.md` | 415 tests pass |
| 35-I — longitudinal reality | `REGRESSION_LINUX_EVIDENCE.md` (36/36 pass); no standalone ratification file found | 36 tests pass |
| Deployment + Backup/Restore + DR (universal moat) | `backend/DEPLOYMENT_DR_UNIVERSAL_MOAT_RATIFICATION_EVIDENCE.md` (2026-10-05) | Ratified; hardening stages continue below |
| **Track A — Deployment + Backup + Restore + DR (A1–A4)** | `backend/DEPLOYMENT_DR_RATIFICATION_EVIDENCE.md` (2026-10-18; supersedes `..._ARCHIVE_2026-10-05.md`) | **Ran all four slices on real PostgreSQL; DR3 E2E 14/14 VERIFIED (`ev-a2046eb2f65b`)** |
| Real Integrations + Provisioning | `backend/REAL_INTEGRATIONS_PROVISIONING_RATIFICATION_EVIDENCE.md` | Ratified |
| Universal Acceptance Matrix | `backend/UNIVERSAL_ACCEPTANCE_RATIFICATION_EVIDENCE.md` | Ratified |
| Release Candidate hardening | `backend/RELEASE_CANDIDATE_RATIFICATION_EVIDENCE.md` + slices 2A–2E | Ratified |
| Private Alpha readiness | `backend/PRIVATE_ALPHA_RATIFICATION_EVIDENCE.md`, `PRIVATE_ALPHA_READINESS_EVIDENCE.md`, `PRIVATE_ALPHA_CLOSURE_SUMMARY.md` | Ratified |
| Billing stages 5.1/5.2 | `backend/BILLING_STAGE_5_1_USAGE_METERING_EVIDENCE.md`, `..._5_2_PAYMENT_RECONCILIATION_EVIDENCE.md` | Ratified |
| Gate 19 feature flags | `backend/GATE_19_FEATURE_FLAGS_RATIFICATION_EVIDENCE.md` | Ratified |
| Integrations (Slack, GitHub, Google Workspace) | `backend/SLACK_INTEGRATION_EVIDENCE.md`, `GITHUB_INTEGRATION_EVIDENCE.md`, `GOOGLE_WORKSPACE_INTEGRATION_EVIDENCE.md` | Ratified |

## 2. Active workstream — Deployment/Backup/Restore/DR hardening

### 2.1 Completed stages (evidence: `workspace\vcos` root + `backend/`)

- **Stage 1 (Slice 2F):** real `pg_dump` backup of `vcos_test` restored into `vcos_restore_test`;
  data fingerprints match. Evidence: `DEPLOYMENT_DR_SLICE_2F_EVIDENCE.md`.
- **Stage 2:** Linux CI integration + full regression run (257/265 critical tests pass; the 8
  failures were SQLite/schema test-infra issues, not product defects). Evidence:
  `LINUX_CI_EVIDENCE.md`, `REGRESSION_LINUX_EVIDENCE.md`.
- **WAL archiving fix (2026-10-15):** root cause was `Get-FileHash -LiteralPath` holding
  `FileShare.Read` and conflicting with PostgreSQL's checkpointer; replaced with a
  FileStream-based hash (`FileShare.ReadWrite|Delete`). Live stats after fix: archiving
  succeeded 15×, 0 failures since fix, last archived `000000010000008900000021`
  (2026-10-16 10:38 local). Evidence: `backend/WAL_ARCHIVING_FINAL_REPORT.md`,
  `backend/DR_RUNBOOK.md`.

### 2.2 Completed stage — **DR.3: Production Recovery Baseline Establishment + E2E DR Ratification (VERIFIED 2026-10-17)**

**E2E verified result (run 2026-10-17 07:43–07:45 local / 02:13–02:15 UTC, duration 150.4s):**
`overall_success: true` — all 10 mandatory checks PASS:

- fresh base backup `bkp-bc51f738eac0` (pg_basebackup, 108,596,128 bytes) + manifest verified;
- WAL sealed + archived, chain continuous from fresh baseline (segment `00000001000000890000004E`,
  `C:\VCOS-Backups\wal_baseline.json`), archive health not unhealthy;
- isolated physical restore succeeded (schema converged 688/688 tables);
- PITR proof on restored DB: `pg_is_in_recovery()=false`, marker1
  `dr3-pitr-marker-1-67158d41` present, marker2 `dr3-pitr-marker-2-776cd845` absent,
  `last_wal_replay_lsn=589735944528`;
- recovery readiness gates: all 16 transitions passed
  (preflight → select_backup → verify_backup → initialize_restore → restore_database →
  replay_wal → validate_schema → validate_canonical → validate_tenant → validate_temporal →
  validate_provenance → validate_governance → validate_longitudinal → validate_dependencies →
  request_approval → activate), final state `activated`;
- RPO/RTO measured from real phase timestamps (RPO 0.059s, RTO activation delta ~48µs;
  full restore window 02:13:45 → 02:15:34 visible in `phase_timings`).

**Evidence artifacts:** `C:\VCOS-Backups\DR3_TEST_RESULTS.json` (overall_success true),
`C:\VCOS-Backups\DR3_RECOVERY_BASELINE_EVIDENCE.json` + repo copy
`backend\DR3_RECOVERY_BASELINE_EVIDENCE.json` (identical hashes, evidence id `ev-21a8fdd08415`,
final verdict **VERIFIED**).

**Defect classes fixed to reach verification (production code first, harness second):**
(1) isolated-restore config/WAL-replay/port/DB-target defects (list below, items 1–5, all fixed);
(2) baseline/WAL continuity defects (items 8–10, all fixed — fresh-baseline setter + sealing via
`pg_switch_wal` + archive-mode isolation in the restored instance's `postgresql.auto.conf`);
(3) backup-executor ordering/verifier defects (items 6–7, fixed);
(4) recovery-gates defects (item 11: `TransitionAction.PREFLIGHT`, restore-id bridging,
`/postgres`→`vcos4` target, missing `ValidationCheck`/`EnvironmentCapability` imports,
fictional `check_governance_integrity`/`check_operating_chain` calls replaced with the real
`check_gate30_integrity`/`check_operating_chain_integrity`, missing
`restore_service._validate_longitudinal`/`_validate_digital_twin_dependencies` implemented,
`transition()` silent no-op on gateless states fixed);
(5) harness defects (item 12, fixed: real backup path, real IDs, orphaned-isolated-instance
cleanup, explicit DSN credentials in all DR paths);
(6) environment root causes: UTF-16 `pgpass.conf` (rewritten ASCII), archive-cascade crash of
isolated instances (archive_mode forced off), baseline `CAST(:lsn AS pg_lsn)` (double-cast fix),
pg_ctl PIPE-inheritance hang (DEVNULL + `-W` + connection polling).

**Schema convergence (2026-10-16/17):** `vcos4` was at 487 tables vs 688 model tables; Phase 0
of the E2E now converges schema via `init_db()` (create_all + universal indexes + alter
migrations) and records before/after counts in evidence (run 14: 688 before → 688 after).

**Evening re-verification (2026-10-17 17:40–17:43 local):** the E2E was re-run to green after
operational hardening (unique per-instance pg_ctl logs, orphan-stop `stop` verb fix, extraction
integrity verify+retry, DR scratch moved off the system drive) — `overall_success: true`, 10/10
checks, evidence `ev-36db013230fe` (VERIFIED). The afternoon failures (runs 4–5) were caused by
the system drive reaching 0 bytes free, not by DR logic. See
`backend/DR_OPERATIONAL_HARDENING_EVIDENCE.md`.

### 2.3 Completed stage — **Post-DR regression sweep + DR residual closure (VERIFIED 2026-10-17)**

**Verified result:** new regression module `backend/tests/test_post_dr_regression_sweep.py` **15/15 passed**
on real PostgreSQL `vcos_test`; ratified gate sweep (12 files, 389 collected) **384/389 passed**; DR suites
**98/98 passed**. Full commands/results/limitations: `backend/POST_DR_REGRESSION_SWEEP_EVIDENCE.md`.

**Defects fixed (each with regression proof):**
- **Systemic severity-filter defect:** `IntegritySeverity` values are lowercase (`"critical"`), so every
  `severity == "CRITICAL"/"HIGH"` finding filter was always False — critical canonical findings could
  never block restore/DR/deployment/release decisions (silently inert blocking). Fixed via
  `severity_matches()` (case-insensitive, enum-safe) in `canonical_reality_integrity_service.py`,
  applied across `post_restore_validator.py`, `isolated_restore.py`, `restore_service.py`,
  `pitr_test_orchestrator.py`, `pitr_service.py`, `deployment_contract_service.py`,
  `release_deployment_orchestrator.py`, `release_failure_recovery.py`.
- **The §2.2-revision residuals are resolved:** `_validate_contradiction`, `_validate_longitudinal`, and
  `_validate_company_brain` in `post_restore_validator.py` previously called a wrong-signature or
  nonexistent API; they now call real implementations (`check_contradiction_integrity`,
  `check_longitudinal_integrity`, `check_company_brain_dependencies`; +12 finding types; deliberately
  not registered in `run_integrity_scan` so ratified default scan counts are unchanged).
- **Latent NameErrors on deployment/release paths fixed:** missing `text` import in
  `deployment_contract_service.py`; missing `ValidationStatus` import in
  `release_deployment_orchestrator.py`.
- **Portability defect fixed:** two PostgreSQL-only `::text` casts in integrity checks replaced with
  portable `cast(col, Text)`; gate31 back to 36/36 (SQLite fixture), cast semantics confirmed on PG.

**Environment re-verified after the sweep:** `vcos4` 688 tables and 0 sweep rows (untouched);
`vcos_test` sweep residue 0 across all sweep tables; port 53093 closed / 5432 open; 0 orphan python
processes; DR.3 evidence pair hash-identical (`E3128F31...B7A8972`); DR.3 E2E harness not rerun
(existing evidence re-validated instead).

**Residuals carried forward (classified, not blocking):** 5 pre-existing gate32 failures — drift between
committed gate32 tests and untracked reliability/continuity models (fingerprint NOT NULL inserts with no
defaults; `request_state` not a model field; impossible `fp-123` assertion; exact list in sweep evidence
§5). Hygiene observations: `canonical_reality_integrity_service.py.bak`/`.bak2` present under
`backend/app/services/`; `calibration_state` declared twice in `app/models/longitudinal.py` (~706/710).

### 2.4 Completed stage — **DR operational hardening (VERIFIED 2026-10-17 evening)**

Guardrails added after the disk-exhaustion incident: `app/services/dr_ops_guardrails.py` (disk-space
preflight with configurable `VCOS_MIN_FREE_SPACE_GB` threshold and explicit BLOCKED result;
scratch-directory retention with dry-run default, strict VCOS-owned name patterns, canary protection,
active-instance skip, structured JSON logs), retention CLI `scripts/run_scratch_retention.py`,
preflight integration in the DR.3 harness (pre-flight + immediately before Phase 6), and 16 unit
tests (`tests/test_dr_ops_guardrails.py`, 16/16 passed). Retention was executed for real against
`%TEMP%` (dry-run: 1 candidate; apply: 1 deleted; canaries untouched; structured log appended).
Evidence: `backend/DR_OPERATIONAL_HARDENING_EVIDENCE.md`. Runbook: `backend/DR_RUNBOOK.md` §18.

### 2.5 Completed stage — **RLS tenant inventory (LOCALLY VERIFIED 2026-10-17 evening)**

Read-only structural inventory of all 688 public tables: `app/services/rls_tenant_inventory.py`
(classification: DIRECT via `organization_id`/`org_id`/`tenant_id`; INDIRECT via bounded FK paths,
depth ≤ 4; SYSTEM via alembic/pg names; GLOBAL/ DERIVED only via explicit allowlists — names never
decide ownership) + CLI `scripts/rls_tenant_inventory.py`. Result against `vcos4`: **640 direct,
22 indirect, 1 system, 25 special-case review, 0 global, 0 derived; RLS enabled on 0 tables; 662
scoped tables missing RLS**. The 25-table review queue includes `organizations` (tenant root —
disposition: anchor table, not tenant-scoped by itself), `users`, `permissions`, `plans`,
`industries`, `cloud_regions`, `marketplace_items`. No enforcement started (by design). Unit tests:
`tests/test_rls_tenant_inventory.py`, 12/12 passed. Artifacts: `backend/RLS_TENANT_INVENTORY.json`,
`backend/RLS_TENANT_INVENTORY_SUMMARY.md`.

### 2.6 Completed stage — **Command Center MVP (LOCALLY VERIFIED 2026-10-17 evening)**

Real Command Center at `/command-center` (nav: Executive group) with four sections on existing
canonical APIs only: Decision Inbox (`/decisions` + `/approvals` with the decision ≠ authorization
distinction explicit), Company State (`/dashboard/summary` verified facts + advisory operating
picture from `/brain/execution/company/state`), Risk & Integrity (`/risks` +
`/canonical/integrity/findings`), Company Timeline (`/executive/timeline`). Per-section
loading/error/empty/partial-failure/permission-denied/freshness states. Verified: `tsc --noEmit`
clean, `next build` success (route compiled), e2e `slice8-command-center` 1 passed (real backend;
includes tenant-isolation check), regression `slice6-approvals-risks` 1 passed. No backend files
modified. Evidence: `backend/COMMAND_CENTER_SLICE3_EVIDENCE.md`.

### 2.7 Completed stage — **Governed AI Worker MVP (LOCALLY VERIFIED 2026-10-18)**

AI work runs as a governed actor on the canonical operation spine (`governed_worker.task` /
`governed_worker.action` operations; idempotency, attempts, lease recovery from
`canonical_reliability_service`; `max_attempts=1`). Read-only research over tenant/scope-validated
canonical context (projects, tasks, decisions, risks); strict JSON model contract with a 60s
timeout; malformed/truncated model output fails (`model_output_invalid`) and is never persisted;
provider `local`/`none`/unreachable → honest facts-only completion with explicit uncertainty.
Recommendation = existing `decision_service` (proposed) + `approval_service`
(`governed_worker_action`) + queued child action op; execution revalidates the approved
authorization at the execution boundary, then creates a real canonical task. API
`/api/v1/governed-worker/*` gated by existing `ai:use`; Command Center section "Governed AI Work"
(no standalone AI dashboard). Fixed a pre-existing lease FK bug (`_create_worker_lease` hardcoded
`organization_id="system"`) that blocked any live `create_operation`. Verified: 16/16 backend
tests; live Postgres local-provider research/recommendation/execution run; real-provider Groq run
(`openai/gpt-oss-120b` via env override — assisted research + assisted recommendation with pending
approval; truncated JSON at default `AI_MAX_TOKENS=1024` correctly rejected; config default model
`llama-3.3-70b-versatile` now 404s at Groq — noted, defaults untouched); e2e
`slice9-governed-worker` 1 passed (approval decided via REST for determinism), regressions
`slice6`/`slice8` passed; `tsc` clean; `next build` success. Pre-existing `auth_service.py` invite
bug (2 failures in `tests/test_decision_execution.py`) documented, not fixed. Independent closeout
re-verification (2026-10-18): pytest 16/16; live Postgres re-run incl. idempotency (sequential +
parallel same-key creates → same operation id) and parallel double-run (HTTP 200+400, no duplicate
execution, final phase completed); rejected approval → execute 400 / `action_rejected`; approved →
`executed` → real canonical task verified in `/tasks`; cancel→run 400; e2e slice6/8/9 **3 passed
(41.0s)**; `tsc` clean; `next build` success; dev server `/command-center` HTTP 200. Evidence JSON:
`%TEMP%\opencode\slice4_final_live_verification.json`. Evidence:
`backend/GOVERNED_AI_WORKER_SLICE4_EVIDENCE.md`.

### 2.8 Completed stage — **Track A: Deployment + Backup + Restore + Disaster Recovery (A1–A4 IMPLEMENTED + LOCALLY VERIFIED 2026-10-18)**

Full evidence: `backend/DEPLOYMENT_DR_RATIFICATION_EVIDENCE.md` (re-issued under the Track A mandate;
the 2026-10-05 original is retained at `backend/DEPLOYMENT_DR_RATIFICATION_EVIDENCE_ARCHIVE_2026-10-05.md`
— it relied on masked gate mappers and a mock-capable backup path, both removed this cycle).

- **A1 (deployment/database env contract):** `EXPECTED_DATABASE_NAME`; `deployment_contract_service`
  real identity/extension/alembic checks (7 checks); `/health/ready` includes `environment_contract`
  (503 on failure). 11 tests; live contract 0 mismatches + `/health/ready` 200
  (`%TEMP%\opencode\slice_a1_ready_endpoint.json`).
- **A2 (real backup with full metadata + checksum):** manifest `source_database_name`
  (`SELECT current_database()`), `schema_revision` from `alembic_version`, environment identity from
  settings+hostname, destination resolution via `_resolve_backup_dest()`; **mock fabrication removed**
  from `backup_service`/`restore_service` (pgBackRest missing/failure/unparsable output ⇒ explicit
  RuntimeError / failure result — "refusing to fabricate a result"). Final artifact
  `bkp-fc0cf7b3dead` (`C:\VCOS-Backups\basebackup_bkp-fc0cf7b3dead\base.tar.gz`, 152,932,093 bytes,
  SHA-256 `18969c6e…ad12a` recomputed independently and matched). 7 new tests
  (`tests/test_backup_metadata_a2.py`).
- **A3 (isolated restore + semantic baseline):** restore into a separate PostgreSQL instance/port
  (source `vcos4` untouched); PITR proof (marker1 present / marker2 absent,
  `last_wal_replay_lsn=592202206112`); semantic validations on the restored DB (schema, canonical,
  tenant, temporal, provenance, governance, longitudinal, dependencies) all verified.
- **A4 (recovery lifecycle gates + RPO/RTO):** fail-closed gate evaluation in `recovery_gates.py`
  (WARNING/INCONCLUSIVE ⇒ gate BLOCKED — an unverified restore cannot activate); approval/activation
  gates record `approval_requested_at/by` + `activated_at/by`; `wal_archive_monitor` readiness from
  persisted real events (`READY`). Measured in final E2E: **RPO 0.124s / RTO 0.000037s**;
  all 16 gates `verified`; evidence `ev-a2046eb2f65b`, **14/14 PASS, verdict VERIFIED**.
- **Defects found & fixed (each with evidence):** (1) gate mappers coerced non-FAILED sub-statuses to
  VERIFIED (masking) — now propagated, fail-closed; (2) shared-env tenant bookkeeping + empty
  canonical/timeline/twin tables reclassified WARNING→NOT_APPLICABLE (nothing to validate ≠
  unverified; missing tables remain FAILED); (3) 11 ORM models redeclared `created_at`/`updated_at`
  without mixin defaults ⇒ 45 NULL rows (`approvals` 18, `projects` 16, `risks` 11, `departments` 2,
  `expertise_scores` 1) — models fixed + migration `9f3c1a7d52e4` (backfill + NOT NULL; verified 0
  NULLs); (4) hardcoded POSIX backup path; (5) `schema_revision` unknown; (6) env identity unknown;
  (7) debug prints in tenant validation.
- **Evidence chain (honest supersession):** `ev-36db013230fe` (10/10, masked era) →
  `ev-0ffd6a550aea` (14/14, still masked) → `ev-1735d4c2512d` (9/14 FAILED — fail-closed exposed the
  masking) → `ev-2c550fe063f4` (14/14, unmasked + timestamp fix) → **`ev-a2046eb2f65b` (final,
  14/14 VERIFIED)**.
- **Verification totals:** DR3 E2E 14/14; `test_post_dr_regression_sweep.py` 17/17 (incl. fail-closed
  gate tests); A1+A2+deployment suites + acceptance roundtrip **90 passed / 1 skipped** (skip =
  explicit pgBackRest-missing BLOCKED case). Real defect discovered via DR3 run, not papered over:
  the skip is an accepted limitation (pgBackRest not installed here), not a hidden pass.

## 3. Verified environment anchors

- PostgreSQL 18.2 (`postgresql-x64-18`, Running), port 5432, superuser `postgres`;
  loopback trust + password auth for DR tooling; ASCII `pgpass.conf` in
  `%APPDATA%\postgresql\` (do not rewrite as UTF-16).
- Databases: `vcos4` (app, 688 tables after DR.3 Phase-0 convergence), `vcos_test`
  (688-table schema reference). Alembic head `9f3c1a7d52e4` (timestamp backfill + NOT NULL,
  2026-10-18; 45 NULL `created_at`/`updated_at` rows backfilled, 0 remaining).
- WAL archive `C:\VCOS-Backups\wal_archive`: current DR.3 baseline segment
  `0000000100000089000000E1` (sealed via `pg_switch_wal`, `C:\VCOS-Backups\wal_baseline.json`);
  historical archive failures (165, last 2026-10-15) remain recorded in manifest `limitations`;
  chain continuous from baseline, `new_archive_failures=0`.
- Latest verified DR.3 backup (Track A final run): `bkp-fc0cf7b3dead` (152,932,093 bytes,
  checksum `18969c6e…ad12a` independently recomputed; `source_database_name=vcos4`,
  `schema_revision=9f3c1a7d52e4`).
- Verified DR.3 evidence: `C:\VCOS-Backups\DR3_TEST_RESULTS.json` (14/14, overall_success true),
  `C:\VCOS-Backups\DR3_RECOVERY_BASELINE_EVIDENCE.json` + repo copy in `backend\`
  (evidence id `ev-a2046eb2f65b`, final verdict VERIFIED), `C:\VCOS-Backups\wal_recovery_verification.json`.
- `archive_wal.ps1` fix deployed 2026-10-15 17:47 with rollback copy preserved.

## 4. Next actions (this workstream)

1. **Track A (A1–A4) is complete and verified — see §2.8 and
   `backend/DEPLOYMENT_DR_RATIFICATION_EVIDENCE.md`.** No further work started in this cycle.
2. Documented residuals (do not reopen without defect evidence): 5 gate32 failures classified
   pre-existing in sweep evidence §5; `.bak`/`.bak2` hygiene files under `backend/app/services/`;
   duplicate `calibration_state` declaration in `app/models/longitudinal.py` (observation only).
   Track A carry-forwards (all in ratification evidence §8): pgBackRest not installed here
   (honest-failure path tested; Windows uses `pg_basebackup`); legacy
   `disaster_recovery_service.validate_recovery()` always-True (not on the Track A gate path);
   `auth_service.invite` pre-existing bug (2 failures in `tests/test_decision_execution.py`,
   1 in `test_slice3_step12_approvals.py`); historical WAL archive failures (165, pre-baseline,
   recorded inside every manifest); RPO/RTO measured on local infra only.
3. **Hosted verification is BLOCKED** (no hosted environment/credentials) — explicitly classified in
   the ratification evidence; do not claim hosted deployment/DR readiness.
4. **Stop rule:** Do not begin the next stage (Real Integrations + Company Provisioning E2E) in this
   slice without a new explicit mandate.
