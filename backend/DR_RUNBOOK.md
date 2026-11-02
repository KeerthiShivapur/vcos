# VCOS Disaster Recovery Runbook

**Version:** 1.2  
**Last Updated:** 2026-10-17  
**Status:** VERIFIED  

---

## 1. Current Archive Configuration

### Active Archive Script
- **Path:** `C:\VCOS-Backups\archive_wal.ps1`
- **SHA-256:** `483c45e6a08a0452b4c0601fc57501d26ef4a30df2a26b3a7d96ee3af1573c5b`
- **Key Features:**
  - FileStream-based `Get-FileHashSafe` with `FileShare.ReadWrite | FileShare.Delete`
  - Atomic temporary-file copy with hash verification
  - Collision handling with size validation for recycled WAL segments
  - Temporary-file cleanup on failure

### Rollback Script
- **Path:** `C:\VCOS-Backups\archive_wal.ps1.backup.20261015_171854`
- **SHA-256:** `fa81c9ee641f727f8b3ff625ffe9d1092d836343c38923b98be752d5f9745a0a`
- **Status:** VERIFIED - matches original active script before fix deployment

### WAL Archive Directory
- **Path:** `C:\VCOS-Backups\wal_archive`
- **Verified Segments:** 15 through 1E (continuous chain)
- **Segment Size:** 16,777,216 bytes (16 MB) each

---

## 2. Permanent Segment 14 Gap

### Missing Segment
- **Segment:** `000000010000008900000014`
- **Status:** PERMANENTLY MISSING
- **Reason:** Original source recycled by PostgreSQL; archive contained only 18-byte corrupt file
- **Impact:** PITR cannot recover to any point within segment 14's LSN range

### Consequences
- **DO NOT** attempt to reconstruct or fabricate this segment
- **DO NOT** claim complete PITR coverage across this gap
- Recovery targets MUST be ≥ segment 15 LSN (0/15000000)
- New base backup establishes new recovery baseline from segment 15 onward

---

## 3. Verified WAL Range

| Metric | Value |
|--------|-------|
| **Earliest Verified Segment** | `000000010000008900000015` |
| **Latest Verified Segment** | `00000001000000890000001E` |
| **Continuous Chain** | VERIFIED (segments 15-1E) |
| **Latest Archive Time** | 2026-10-15 17:48:20 UTC |
| **Archive Lag** | < 5 minutes (within threshold) |
| **New Archive Failures** | 0 (post-deployment) |

---

## 4. Recovery Baseline

### New Base Backup (Required)
- **Status:** NOT YET CREATED
- **Method:** pgbackrest (preferred) or pg_basebackup
- **Target:** Establish new baseline from segment 15 onward
- **Must Record:**
  - Backup identifier
  - Start/completion timestamps
  - PostgreSQL version (18.2)
  - Database system identifier
  - Required WAL range
  - Backup integrity checksum
  - VCOS revision and schema revision

### Recovery Manifest
- **Schema Version:** 1.0
- **Location:** Stored in backup_manifests.verification_details
- **State Machine:** CREATED → PREFLIGHTED → BACKUP_SELECTED → ... → READY_FOR_APPROVAL → ACTIVATED

---

## 5. Backup Method

**Primary:** pgbackrest (if available on Windows production)  
**Fallback:** pg_basebackup (tar format)  
**Last Resort:** pg_dump (logical only, no PITR)

**Verification:** Backup is NOT verified until restore test passes

---

## 6. Restore Procedure

### Prerequisites
1. Verified backup manifest exists with status = VERIFIED
2. Target organization matches backup organization_id
3. Isolated environment prepared (separate data directory, port)

### Steps
1. **PREFLIGHT** - Validate PITR capability, WAL archive health, continuous chain
2. **BACKUP_SELECT** - Select appropriate backup for recovery target
3. **BACKUP_VERIFY** - Verify backup integrity (checksum, schema, data)
4. **RESTORE_INIT** - Initialize isolated PostgreSQL instance (initdb)
5. **DATABASE_RESTORED** - Restore base backup (pgbackrest/pg_basebackup)
6. **WAL_REPLAYED** - Configure and replay WAL to target time/LSN
7. **POSTGRES_START** - Start isolated PostgreSQL instance
8. **VALIDATION PHASES** (each in isolated transaction):
   - SCHEMA_VALIDATED
   - CANONICAL_VALIDATED
   - TENANT_VALIDATED
   - TEMPORAL_VALIDATED
   - PROVENANCE_VALIDATED
   - GOVERNANCE_VALIDATED
   - LONGITUDINAL_VALIDATED
   - DEPENDENCIES_VALIDATED
9. **READY_FOR_APPROVAL** - All gates passed, requires human approval
10. **ACTIVATED** - Human approval received, restored DB becomes operational

---

## 7. PITR Procedure

### Recovery Target Selection
- **Target Time:** Must be within verified recovery window
- **Target LSN:** Must be within continuous WAL chain
- **Validation:** Target must be ≥ backup completion AND ≤ last archived WAL

### Execution
1. Use `isolated_restore_service` with `target_time` or `target_lsn`
2. Configure recovery.signal / postgresql.auto.conf with target
3. Start PostgreSQL, allow WAL replay to target
4. Run full canonical validation at recovery target
5. Measure RPO/RTO
6. Generate evidence artifact

---

## 8. Canonical Validation Procedure

Run `post_restore_canonical_validator.validate_restored_database()` with checks:
- structural
- tenant
- temporal
- provenance
- epistemic
- governance
- operating_chain
- contradiction
- longitudinal
- company_brain
- digital_twin

**Verdict:** VERIFIED / FAILED / BLOCKED / INCONCLUSIVE / WARNING

---

## 9. Activation Approval Requirements

- All validation gates PASSED (no FAILED, no BLOCKED)
- Human operator reviews validation report
- Explicit approval recorded in audit log
- Recovery context marked ACTIVATED

---

## 10. RPO/RTO Measurements

| Metric | Target | Measured | Status |
|--------|--------|----------|--------|
| RPO | 5 minutes | TBD | NOT MEASURED |
| RTO | 30 minutes | TBD | NOT MEASURED |
| Backup Time | - | TBD | NOT MEASURED |
| Restore Time | - | TBD | NOT MEASURED |
| Validation Time | - | TBD | NOT MEASURED |

---

## 11. Recovery Limitations

1. **Segment 14 Gap:** No recovery possible within segment 14 LSN range
2. **Logical Backup Only:** Previous logical dump (vcos4-before-recovery.dump) does NOT prove physical PITR capability
3. **Isolated Testing Only:** All restore tests MUST use isolated environment
4. **Windows Production:** pgBackRest availability on Windows must be verified
5. **WSL ≠ Production:** WSL pgBackRest tests do NOT prove Windows production capability

---

## 12. Escalation Conditions

| Condition | Action |
|-----------|--------|
| New archive failures > 0 | Immediate investigation |
| Archive lag > 5 minutes | Alert on-call |
| Accumulating .ready files > 10 | Check archive_command |
| Backup verification FAILED | Block restore, investigate |
| Canonical validation FAILED | Block activation, investigate |
| Recovery test FAILED | Escalate to team lead |

---

## 13. Rollback Conditions

| Condition | Action |
|-----------|--------|
| Archive script causes data corruption | Restore rollback script immediately |
| WAL archive directory corrupted | Restore from rollback script, re-archive |
| pgbackrest repo corrupted | Recreate stanza, new base backup |

### Rollback Steps
1. Copy rollback script to active: `cp archive_wal.ps1.backup.20261015_171854 archive_wal.ps1`
2. Verify hash: `fa81c9ee641f727f8b3ff625ffe9d1092d836343c38923b98be752d5f9745a0a`
3. Test archive with sample WAL segment
4. Monitor pg_stat_archiver for 24 hours

---

## 14. Status Tracking

| Component | Status | Evidence |
|-----------|--------|----------|
| Archive Script Fix | VERIFIED | WAL_ARCHIVING_FINAL_REPORT.md |
| Segment 14 Gap | DOCUMENTED | This runbook |
| Continuous Chain 15-1E | VERIFIED | Hash verification |
| New Base Backup | BLOCKED | Awaiting pgbackrest on Windows |
| Isolated Restore | IMPLEMENTED | isolated_restore_service.py |
| PITR Test | IMPLEMENTED | pitr_test_orchestrator.py |
| Canonical Validation | IMPLEMENTED | post_restore_validator.py |
| Recovery Gates | IMPLEMENTED | recovery_gates.py |
| RPO/RTO Measurement | IMPLEMENTED | rpo_rto_measurement.py |
| DR Runbook | THIS DOCUMENT | DR_RUNBOOK.md |
| Evidence Artifact | IMPLEMENTED | Evidence generator |

---

## 15. Quick Reference Commands

### Check WAL Archive Health
```bash
psql -c "SELECT * FROM pg_stat_archiver;"
```

### Verify Latest Segment
```bash
# Compare hashes
sha256sum "C:\Program Files\PostgreSQL\18\data\pg_wal\<segment>"
sha256sum "C:\VCOS-Backups\wal_archive\<segment>"
```

### Run Isolated Restore
```python
from app.services.isolated_restore import isolated_restore_service
result = await isolated_restore_service.create_isolated_restore(
    db=db,
    backup_id="bkp-xxx",
    organization_id="org-xxx",
    target_time=datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc),
)
```

### Run PITR Test
```python
from app.services.pitr_test_orchestrator import pitr_test_orchestrator
execution = await pitr_test_orchestrator.run_pitr_test(
    db=db,
    organization_id="org-xxx",
    backup_id="bkp-xxx",
    target_time=datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc),
)
```

### Generate Evidence
```python
from app.services.post_restore_validator import post_restore_canonical_validator
report = await post_restore_canonical_validator.validate_restored_database(
    db=isolated_db,
    organization_id="org-xxx",
    restore_id="rst-xxx",
    recovery_target=datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc),
)
```

---

## 16. Verification Checklist

Before marking recovery capability as VERIFIED:

- [ ] New physical base backup created and verified
- [ ] Isolated restore from new backup successful
- [ ] PITR to target within verified window successful
- [ ] All canonical validation gates PASSED at recovery target
- [ ] RPO/RTO measured and within targets
- [ ] Tenant isolation validated at recovery target
- [ ] Temporal integrity validated at recovery target
- [ ] Provenance chains validated at recovery target
- [ ] Epistemic states validated at recovery target
- [ ] Governance rules validated at recovery target
- [ ] Longitudinal integrity validated at recovery target
- [ ] Company Brain dependencies validated at recovery target
- [ ] Evidence artifact generated and stored
- [ ] DR runbook updated with actual measurements

---

## 17. Post-DR Regression Sweep (added 2026-10-17)

Status legend: **TESTED** = command executed and verified on this date; **DOCUMENTED-NOT-RETESTED** =
last verified earlier, do not auto-rerun; **KNOWN-RED** = failing tests unrelated to DR, never treat
as a DR signal. Full results: `backend/POST_DR_REGRESSION_SWEEP_EVIDENCE.md`.

### TESTED (2026-10-17, real PostgreSQL `vcos_test`, never `VCOS_TEST_MODE=1`)

```powershell
# Regression module for the DR-blocking fixes (severity normalization, restored phases, gate machine)
python -m pytest tests\test_post_dr_regression_sweep.py -v          # 15 passed

# Ratified gate sweep (12 files, 389 tests)
python -m pytest tests\test_gate6b*.py tests\test_gate6c*.py tests\test_gate6d*.py ^
  tests\test_gate6e*.py tests\test_gate6f*.py tests\test_gate13*.py tests\test_gate30*.py ^
  tests\test_gate31*.py tests\test_gate32*.py tests\test_gate35g2*.py ^
  tests\test_gate35h*.py tests\test_phase_i_longitudinal_company.py -q   # 384 passed, 5 KNOWN-RED (see below)

# DR suites
python -m pytest tests\test_deployment_backup_restore_dr.py tests\test_recovery_manifest.py ^
  tests\test_backup_executor.py tests\acceptance\test_backup_restore_roundtrip.py ^
  tests\acceptance\test_deployment_dr_production_verification.py ^
  tests\acceptance\test_production_deployment_dr_e2e.py -q          # 98 passed

# Post-run hygiene verification (must return 0 / 688 / closed)
psql -U postgres -h localhost -d vcos_test -c "select count(*) from organizations where id like 'sweep-org-%';"  # 0
psql -U postgres -h localhost -d vcos4 -c "select count(*) from information_schema.tables where table_schema='public';"  # 688
```

### DOCUMENTED-NOT-RETESTED

- **DR.3 E2E harness** — `python tests\test_dr3_recovery_baseline.py` (~150–300s, destructive to
  scratch instances). Last verified run: run 14 (2026-10-17 02:13–02:15 UTC, `overall_success: true`,
  10/10 checks; artifacts `C:\VCOS-Backups\DR3_TEST_RESULTS.json`,
  `DR3_RECOVERY_BASELINE_EVIDENCE.json`). Do not rerun automatically; rerun only on explicit mandate.

### KNOWN-RED (pre-existing, not DR signal — do not "fix" by weakening tests)

5 gate32 tests fail due to drift between committed gate32 tests and untracked reliability models
(fingerprint NOT NULL inserts without defaults; `request_state` not a model field). Exact list and
errors: `backend/POST_DR_REGRESSION_SWEEP_EVIDENCE.md` §5.

---

## 18. Operational Guardrails (added 2026-10-17)

### 18.1 Disk exhaustion procedure

Incident of record (2026-10-17): the system drive reached 0 bytes free; DR.3 runs failed
(`[Errno 28] No space left on device` during restore, `pg_ctl start exit 1`). The DR logic
itself was sound; the environment had no guardrails.

Guardrails now in place (`app/services/dr_ops_guardrails.py`):

- `require_free_space()` blocks expensive DR work when free space is below the threshold.
- Threshold: `VCOS_MIN_FREE_SPACE_GB` env var (default **5.0 GB**).
- The DR.3 harness checks twice: pre-flight (vault dir + scratch temp dir) and again
  immediately before the Phase 6 restore. A pre-flight failure writes an explicit BLOCKED
  result to `DR3_TEST_RESULTS.json` and exits without touching anything.

Operator steps during a real disk-full incident:

1. Measure: `Get-PSDrive C | Select-Object @{n='FreeGB';e={[math]::Round($_.Free/1GB,2)}}`
2. Free space safely: run scratch retention dry-run first, then apply (section 18.4).
3. Consider moving DR scratch off the system drive: set `TEMP` / `TMP` for the DR run
   (e.g., `D:\vcos-temp`) — restores do not need to live on the system drive.
4. Never delete WAL archive segments or base backup artifacts to free space; they are the
   recovery capability itself.

### 18.2 Orphaned isolated instances

Symptoms: a leftover `vcos_dr3_restore_*` directory with a live `postmaster.pid`, and FATAL
entries from that instance in its per-instance `pg_ctl_vcos_dr3_restore_*.log`.

Stop one manually (the DR.3 harness does this automatically at start):

```powershell
$pg_ctl = 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe'
& $pg_ctl stop -D "C:\Users\<you>\AppData\Local\Temp\vcos_dr3_restore_<timestamp>" -m fast -w -t 60
```

Note: the `stop` verb is **required**. `pg_ctl -D ... -m fast` without it exits 1 and stops
nothing (this exact bug was fixed in the DR.3 harness on 2026-10-17).

### 18.3 Interrupted restores

An interrupted restore leaves a scratch directory behind. Safe handling:

1. Confirm no live instance is running in it (section 18.2).
2. Leave the directory for audit, or let the retention task (18.4) age it out.
3. Never delete a scratch directory whose `postmaster.pid` process is alive — the retention
   task refuses to (active-instance skip).

### 18.4 Scratch retention task

```powershell
cd D:\vcos1\workspace\vcos\backend
.venv\Scripts\python.exe scripts\run_scratch_retention.py                          # dry-run (default)
.venv\Scripts\python.exe scripts\run_scratch_retention.py --apply                  # delete candidates
.venv\Scripts\python.exe scripts\run_scratch_retention.py --max-age-hours 24 --apply
```

Safety rules (enforced in code, covered by tests):

- Only recognized VCOS-owned names are candidates: `vcos_dr3_restore_YYYYMMDD_HHMMSS`
  directories and `pg_ctl_vcos_dr3_restore_YYYYMMDD_HHMMSS.log` files.
- Symlinks are never followed or deleted; unknown files/directories are ignored.
- Directories with a live `postmaster.pid` process are skipped.
- Names containing `canary` (case-insensitive) and names in `VCOS_SCRATCH_PROTECTED`
  (or passed via `--protect "name1;name2"`) are always skipped.
- Every run appends one structured JSON record to `<base-dir>\vcos_scratch_retention.log`.
- Age threshold: `VCOS_SCRATCH_RETENTION_HOURS` (default **72 h**), or `--max-age-hours`.

---

**Document Control:** This runbook must be updated after each recovery test with actual measurements. Do not present untested operations as verified capabilities.