# Post-DR Regression Sweep Evidence

**Date:** 2026-10-17
**Workstream:** Post-DR regression sweep + deployment automation assessment + ops runbook finalization
**Supersedes:** nothing (new artifact; DR.3 baseline evidence remains `backend/DR3_RECOVERY_BASELINE_EVIDENCE.json`)

---

## 1. Environment identity

| Item | Value |
|---|---|
| Host OS | Windows (win32), repository `D:\vcos1\workspace\vcos` |
| PostgreSQL | 18.2 (`postgresql-x64-18`, port 5432) |
| Python | 3.13.7 |
| pytest | 8.3.4 (pytest-asyncio 0.24.0, mode=auto) |
| Sweep database | `vcos_test` (real PostgreSQL; `postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test`) |
| Protected database | `vcos4` (production app DB; verified 688 tables before and after; 0 sweep rows) |
| Test-mode bypass | `VCOS_TEST_MODE` never set to `1` in any command below |

## 2. Command sequence

```powershell
# From backend/ ; all runs against real PostgreSQL vcos_test
set DATABASE_URL=postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test
set TEST_DATABASE_URL=postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test

# 1) New focused regression module (defects fixed this workstream)
python -m pytest tests\test_post_dr_regression_sweep.py -v

# 2) Ratified gate sweep (12 files)
python -m pytest tests\test_gate6b_canonical_mutation.py tests\test_gate6c_temporal_truth.py ^
  tests\test_gate6d_provenance_integrity.py tests\test_gate6e_contradiction_preservation.py ^
  tests\test_gate6f_epistemic_integrity.py tests\test_gate13_strategic_alignment.py ^
  tests\test_gate30_canonical_company_continuity.py tests\test_gate31_canonical_reality_integrity.py ^
  tests\test_gate32_canonical_reliability.py tests\test_gate35g2_canonical_concurrency_stress.py ^
  tests\test_gate35h_failure_under_load.py tests\test_phase_i_longitudinal_company.py -q

# 3) DR suites
python -m pytest tests\test_deployment_backup_restore_dr.py tests\test_recovery_manifest.py ^
  tests\test_backup_executor.py tests\acceptance\test_backup_restore_roundtrip.py ^
  tests\acceptance\test_deployment_dr_production_verification.py ^
  tests\acceptance\test_production_deployment_dr_e2e.py -q

# 4) Environment / residue checks (psql)
psql -U postgres -h localhost -d vcos_test -c "select cast('[]'::json as text);"
psql -U postgres -h localhost -d vcos_test -c "select count(*) from organizations where id like 'sweep-org-%';"
psql -U postgres -h localhost -d vcos4     -c "select count(*) from information_schema.tables where table_schema='public';"
```

## 3. Raw results

| Run | Result |
|---|---|
| New regression module `test_post_dr_regression_sweep.py` | **15 passed** (12.32s) |
| Gate sweep, 12 files / 389 collected | **384 passed, 5 failed** (42.68s) — all 5 failures pre-existing gate32 drift, see §5 |
| Gate31 file alone (after portability fix) | **36 passed** |
| DR suites, 6 files | **98 passed** (15.00s) |
| `CAST('[]'::json AS TEXT)` on real PG | `[]` (confirms cast fix semantics on PostgreSQL) |
| `sweep-org-%` residue rows in `vcos_test` after full sweep | 0 organizations, 0 contradictions, 0 provenance, 0 snapshots |
| `vcos4` surface | 688 tables, 0 sweep rows (untouched) |
| Ports / processes | 5432 open; 53093 closed; 0 orphan python processes |

Interim finding: the first gate sweep showed 7 failures (2 gate31 portability + 5 gate32 pre-existing). The gate31 failures were fixed (see §4, item 4) and re-verified green; the 5 gate32 failures are classified pre-existing in §5.

## 4. Defects fixed in this workstream (each with regression proof)

1. **Systemic severity-filter defect (canonical integrity).** `IntegritySeverity` is a str-enum with
   lowercase values (`"critical"`), so every `finding.severity == "CRITICAL"` filter was always False
   (`IntegritySeverity.CRITICAL == "CRITICAL"` -> False, confirmed empirically). All critical/high
   finding-based blocking was silently inert across restore/DR/deployment/release paths.
   Fix: module-level `severity_matches(finding, severity)` (case-insensitive, enum- and str-safe) in
   `canonical_reality_integrity_service.py`, applied in `post_restore_validator.py`,
   `isolated_restore.py`, `restore_service.py`, `pitr_test_orchestrator.py`, `pitr_service.py`,
   `deployment_contract_service.py`, `release_deployment_orchestrator.py`,
   `release_failure_recovery.py`. (`release_safety_preflight.py` already compared enums correctly.)
   Regression proof: `test_severity_matches_normalizes_enum_and_string` + all phase-failure tests.
2. **Post-restore validator phases calling nonexistent/broken APIs.** `_validate_contradiction`
   called `validate_contradiction_preservation` with a wrong signature; `_validate_longitudinal`
   called a nonexistent `check_longitudinal_integrity`; `_validate_company_brain` called a
   nonexistent `check_company_brain_dependencies`. Fix: real implementations added to
   `canonical_reality_integrity_service.py` (`check_contradiction_integrity`,
   `check_longitudinal_integrity`, `check_company_brain_dependencies` plus 13 helpers, 12 new
   finding types). Not registered in `run_integrity_scan`, so default scan behavior and ratified
   test counts are unchanged.
   Regression proof: contradiction/longitudinal/brain phase tests (critical -> FAILED,
   high -> WARNING, clean -> VERIFIED) + full `validate_restored_database(checks=[...])` reproducer.
3. **Latent NameErrors on deployment/release paths.** `deployment_contract_service.py` used `text`
   without importing it (~line 230); `release_deployment_orchestrator.py` used `ValidationStatus`
   without importing it (lines ~383/416). Both fixed; import sweep clean.
4. **PostgreSQL-only SQL breaking SQLite paths.** Two integrity checks used `::text` casts
   (`verification_contexts.evidence_fingerprints::text = '[]'`), which SQLite cannot parse
   ("unrecognized token: \":\""). Replaced with SQLAlchemy `cast(col, Text)`, verified on both
   engines (gate31 36/36 green on SQLite fixture; `CAST(... AS TEXT)` semantics confirmed on real
   PostgreSQL).
5. **Test-infrastructure defect discovered while adding regression tests.** Async fixture teardown
   ran in the session-scoped loop while asyncpg connections were bound to the function-scoped loop,
   silently failing and leaving zombie transactions that blocked later tests. Fixed in the new test
   module via `loop_scope="function"` + rollback-then-cleanup teardown.

## 5. Limitations and classified residuals

- **5 pre-existing gate32 failures (unrelated to this workstream's changed files):**
  - `TestReliabilityModels::test_canonical_operation_creation` — asserts `op.fingerprint == "fp-123"`
    although no fingerprint is supplied; `CanonicalOperation.fingerprint` is NOT NULL with no default.
  - `TestReliabilityModels::test_external_unknown_state_creation` — passes `request_state`, which is
    not a field of `ExternalUnknownState` (TypeError).
  - `TestRegressionCompatibility::test_gate30_continuity_integration` — SQLite NOT NULL violation on
    `company_operating_continuity.fingerprint` (verified: no column default exists on real PG either).
  - `TestRegressionCompatibility::test_gate28_governed_autonomy_integration` — SQLite NOT NULL
    violation on `autonomy_proposals.fingerprint` (same class).
  - `TestScaleInvariance::test_incremental_scan` — same continuity fingerprint insert path.
  Classification: drift between committed gate32 tests and untracked reliability/continuity model
  code created by earlier workstreams. No shared code paths with the defects fixed here; recorded
  for the next workstream, not papered over.
- **DR.3 E2E harness was not re-executed** in this sweep (by design: no automatic destructive E2E
  rerun). DR.3 evidence from run 14 (2026-10-17 02:13–02:15 UTC, `overall_success: true`, 10/10
  checks) was re-validated instead: `DR3_TEST_RESULTS.json` overall_success=true; evidence pair
  `C:\VCOS-Backups\DR3_RECOVERY_BASELINE_EVIDENCE.json` + `backend\DR3_RECOVERY_BASELINE_EVIDENCE.json`
  hash-identical (`E3128F3191040707EBC31F43C9FC370DF8D60760992A8C9A208AD3640B7A8972`).
- **Repository hygiene observations (not changed during a certified sweep):**
  `canonical_reality_integrity_service.py.bak` / `.bak2` remain in `backend/app/services/`;
  `calibration_state` is declared twice in `app/models/longitudinal.py` (~lines 706/710);
  `CallerAccess` in `restore_service.py:1439` is a harmless string annotation flagged by pyflakes.
- Gate31 runs on the SQLite in-memory fixture; PostgreSQL-validity of the `cast` fix was confirmed
  separately via the `CAST('[]'::json AS TEXT)` probe rather than a full PG re-run of that fixture.

## 6. Mechanism (why this proves regression closure)

The severity-filter defect meant critical canonical findings could never block any restore, DR,
deployment, or release decision — a silent invariant bypass. The regression module asserts, against
real PostgreSQL-seeded data, that (a) critical findings map to FAILED phase verdicts via the
normalized severity comparison, (b) the three previously-broken post-restore phases execute real
checks and produce FAILED/WARNING/VERIFIED correctly, (c) a clean organization yields VERIFIED
overall from `validate_restored_database` for exactly those phases, (d) recovery gates cannot
advance on FAILED/BLOCKED gate results and cannot activate from a non-approved state, and
(e) corrupted backup artifacts are rejected by checksum verification. Together with the ratified
gate sweep (384/389) and DR suites (98/98), this demonstrates the DR/restore/deployment blocking
paths are live, not inert.

## 7. Verdict

**PASS for the post-DR regression sweep** (15/15 new regression tests; 384/389 gate tests green;
98/98 DR suite tests green; gate31 fixed and green; environment verified clean).
**5 pre-existing gate32 failures remain classified (not caused by this workstream) and are carried
forward as residuals for the next workstream.**
