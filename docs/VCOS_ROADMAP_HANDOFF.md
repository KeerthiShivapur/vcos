# VCOS Roadmap & Handoff Guide

**As of:** 2026-10-16
**Audience:** The next engineer or model session continuing VCOS.
**Read first:** `VCOS_ULTIMATE_MOAT_DOCTRINE.md`, then `VCOS_IMPLEMENTATION_STATUS.md`,
then `VCOS_REPOSITORY_ARCHITECTURE.md`.

---

## 1. Where the project is

All major product stages are ratified (evidence files in repo root and `backend/`):
foundations → canonical reality (35-G/H/I) → real integrations + provisioning →
universal acceptance → release-candidate hardening → private-alpha readiness →
billing. The **current frontier is not new features** — it is completing the
Deployment + Backup/Restore + Disaster Recovery hardening to production evidence grade.

**Active stage: DR.3 — Production Recovery Baseline Establishment + E2E DR Ratification.**
The first attempt failed honestly (`C:\VCOS-Backups\DR3_TEST_RESULTS.json`,
`overall_success: false`); the defect list is in `VCOS_IMPLEMENTATION_STATUS.md` §2.2.

## 2. What "done" looks like for DR.3 (acceptance criteria)

1. A **fresh** base backup of the application database is executed through the ratified
   `BackupExecutor` service (not a manual script), producing a VERIFIED manifest whose
   artifact checksum is computed from the real artifact file.
2. A WAL baseline is recorded for that backup and the archive monitor can prove
   **continuous WAL chain from that baseline** to the latest archived segment.
3. An **isolated physical restore** of that backup runs on a scratch port with a
   PITR target inside the verified recovery window; the isolated instance starts, replays
   WAL, and the restored application database is reachable.
4. **Post-restore canonical validation** (structural, tenant, temporal, provenance,
   epistemic, governance, operating chain, contradiction, longitudinal, company brain)
   runs against the RESTORED database with real results recorded.
5. The **recovery gates state machine** advances from CREATED to READY_FOR_APPROVAL and
   ACTIVATED, executing every gate's validator for real (any legitimate FAIL/BLOCK is
   recorded and stops the chain — it is not bypassed).
6. **RPO/RTO measurement** is recorded from real timestamps of this run.
7. A machine-readable evidence artifact is written
   (`C:\VCOS-Backups\DR3_RECOVERY_BASELINE_EVIDENCE.json`) plus a repository evidence file.
8. `overall_success: true` appears in a regenerated `DR3_TEST_RESULTS.json` — or the
   run **stops with an honest BLOCKED report** naming the failing gate and root cause.

## 3. Environment bootstrap (Windows host)

```powershell
# PostgreSQL
Get-Service postgresql-x64-18              # must be Running
$env:PGPASSWORD='postgres'
$psql = 'C:\Program Files\PostgreSQL\18\bin\psql.exe'
& $psql -h 127.0.0.1 -U postgres -d vcos4 -c "SELECT 1"

# Key env for DR work
$env:DATABASE_URL  = 'postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/vcos4'
$env:VAULT_BUCKET  = 'C:\VCOS-Backups'
$env:WAL_ARCHIVE_DIR = 'C:\VCOS-Backups\wal_archive'
$env:PGDATA        = 'C:\Program Files\PostgreSQL\18\data'

# Run the DR.3 E2E (from backend/, system Python 3.13)
python tests\test_dr3_recovery_baseline.py
```

Notes:
- The historical WSL path (`192.168.208.1`) only applies when running from inside WSL.
  From the Windows host use `127.0.0.1`.
- WAL archiving is driven by `C:\VCOS-Backups\archive_wal.ps1` (see `backend/DR_RUNBOOK.md`).
- `archive_timeout=0` means an idle DB archives nothing; the DR.3 test explicitly forces
  `SELECT pg_switch_wal()` and waits for the archiver to seal the window it needs.

## 4. Stage sequence after DR.3

| Order | Stage | Status |
|---|---|---|
| 1 | Deployment + Backup/Restore + DR hardening (DR.3 E2E baseline) | **ACTIVE** |
| 2 | Post-DR ratification sweep: rerun gate suites 6B–6F, 35G.2, 35-H, 35-I against the fixed services (regression protection) | Pending DR.3 |
| 3 | Deployment automation evidence (blue/green + rollback proof) if not already covered by ratified deployment evidence | Assess after DR.3 |
| 4 | Operations runbook consolidation (DR_RUNBOOK + release runbooks into `docs/`) | Assess later |

Do NOT invent new major stages; the endgame roadmap (private alpha → GA) is already ratified
at the process level — the remaining risk is operational evidence quality.

## 5. Non-negotiables for the next session

1. Read the doctrine file. Evidence discipline is not bureaucracy — it is the product.
2. Ratified work is closed. If you believe something ratified is broken, bring reproducible
   evidence + a regression test; do not "fix" it by refactor.
3. One canonical reality: no parallel engines, no bypasses of
   `canonical_mutation.py`, no second recovery subsystem.
4. Never run destructive commands without printing and verifying the target DB name.
5. Never set `VCOS_TEST_MODE=1` for evidence runs.
6. Keep the evidence-file convention: every verified slice leaves a markdown artifact with
   commands, raw outputs, environment identity, limitations, verdict.
7. When blocked: write it down, stop, and report. A clean BLOCKED beats a dirty green.

## 6. Where things live (quick index)

- Architecture / stack map: `docs/VCOS_REPOSITORY_ARCHITECTURE.md`
- Doctrine / laws: `docs/VCOS_ULTIMATE_MOAT_DOCTRINE.md`
- Current status + active defect list: `docs/VCOS_IMPLEMENTATION_STATUS.md`
- Test/verification inventory: `docs/VCOS_TEST_VERIFICATION_INVENTORY.md`
- DR operational runbook: `backend/DR_RUNBOOK.md`
- WAL fix report: `backend/WAL_ARCHIVING_FINAL_REPORT.md`
- Stage evidence: repo root `*.md` + `backend/*EVIDENCE*.md`
- DR.3 harness: `backend/tests/test_dr3_recovery_baseline.py`
- Runtime artifacts: `C:\VCOS-Backups\` (archive, base backups, results JSON, archive script + rollback copy)
