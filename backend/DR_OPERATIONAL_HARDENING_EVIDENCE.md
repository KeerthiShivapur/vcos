# DR Operational Hardening — Evidence

**Date:** 2026-10-17 (evening)
**Scope:** Operational guardrails for the failure class observed on 2026-10-17: the system drive
reached 0 bytes free, which made DR.3 runs fail with `[Errno 28] No space left on device` during
isolated restore and `pg_ctl start exit 1`. The ratified DR architecture was **not** changed;
recovery logic remains exactly as verified by DR.3 run-6 (`ev-36db013230fe`, VERIFIED).

## 1. Files created / modified

| File | Change |
|---|---|
| `backend/app/services/dr_ops_guardrails.py` | NEW — disk-space preflight (`require_free_space`, `DiskSpaceBlocked`, `VCOS_MIN_FREE_SPACE_GB`) + scratch retention (`scan_scratch`, `execute_retention`, structured reports, canary protection, active-instance skip, dry-run default) |
| `backend/scripts/run_scratch_retention.py` | NEW — retention CLI (dry-run default, `--apply`, `--max-age-hours`, `--protect`, JSON-lines log) |
| `backend/tests/test_dr_ops_guardrails.py` | NEW — 16 unit tests, no DB required |
| `backend/tests/test_dr3_recovery_baseline.py` | Pre-flight free-space check (vault + scratch temp, explicit BLOCKED result JSON + early exit) and a re-check immediately before Phase 6 restore; `disk_space_preflight` added to the mandatory checks |
| `backend/DR_RUNBOOK.md` | Version 1.2 — section 18: disk exhaustion, orphaned instances, interrupted restores, retention task |
| `docs/VCOS_IMPLEMENTATION_STATUS.md` | Sections 2.2 addendum + 2.4 |

## 2. What the guardrails do

- **Blocking preflight:** expensive DR work refuses to start when free space is below the
  threshold (default 5.0 GB, `VCOS_MIN_FREE_SPACE_GB`). The harness writes an explicit
  `"blocked": true` result to `C:\VCOS-Backups\DR3_TEST_RESULTS.json` and exits without
  touching backups, WAL or scratch.
- **Retention:** only strict VCOS-owned names are candidates
  (`vcos_dr3_restore_YYYYMMDD_HHMMSS`, `pg_ctl_vcos_dr3_restore_YYYYMMDD_HHMMSS.log`).
  Symlinks never followed; unknown entries ignored; live instances skipped via
  `postmaster.pid` + `OpenProcess` liveness; `canary`/protected names skipped; dry-run is the
  default; every run appends a structured JSON record to `vcos_scratch_retention.log`.

## 3. Test results (real execution)

```
cd D:\vcos1\workspace\vcos\backend
.venv\Scripts\python.exe -m pytest tests\test_dr_ops_guardrails.py -v --tb=short
```

Result: **16 passed in 0.51s** (patterns/traversal rejection, preflight block + pass,
missing-path resolution, PID liveness, fresh/active/protected skips, dry-run no-op,
apply deletes only candidates, report serialization/rendering).

## 4. Real-environment retention demonstration (%TEMP%, Windows)

Setup: created `vcos_dr3_restore_20250101_000000` with directory mtime 100 h in the past.

Dry-run (`scripts\run_scratch_retention.py --base-dir <temp> --max-age-hours 72`):
- entries scanned: 74, candidates: 1 (the fake old dir), skipped (too fresh): 1
  (`vcos_dr3_restore_20260101_000000` — the numeric canary, protected by freshness), deleted: 0.

Apply (`--apply`):
- candidates: 1, **deleted: 1**, failed: 0.

Verification after apply:
- fake dir gone: True
- canary `vcos_dr3_restore_CANARY_20261017`: present
- canary `vcos_dr3_restore_20260101_000000`: present
- structured log: two JSON records appended to `%TEMP%\vcos_scratch_retention.log`
  (dry-run record: `deleted: []`; apply record: `deleted: ["vcos_dr3_restore_20250101_000000"]`,
  `failed: []`).

Live guardrail reading (harness call path, real paths):

```
threshold GB: 5.0
C:\VCOS-Backups: 7.72 GB free
C:\Users\SKEERT~1\AppData\Local\Temp: 7.72 GB free
```

## 5. Honest limitations

- The **BLOCKED path** of the harness preflight is proven by unit test (impossible threshold)
  plus code inspection; it was not triggered against real hardware (disk healthy, 7.7 GB free).
- The first CLI demonstration attempt failed due to a **shell quoting issue** (a trailing
  backslash in `$env:TEMP` consumed the closing quote in PowerShell). Rerun with a trimmed
  path succeeded. Operators: not a product defect; noted for runbook use.
- Retention age uses **directory mtime** (last contents change), documented in the module.
- The harness change is additive; the last full DR.3 run (`ev-36db013230fe`) predates the
  preflight check. The next mandated DR.3 run will include `disk_space_preflight` as an
  additional mandatory check.

## 6. Verdict

**IMPLEMENTED + LOCALLY VERIFIED** (16/16 tests, retention exercised for real with canaries
preserved, guardrail readings on real paths). No requirement to rerun the full DR.3 E2E was
created; it remains green from run-6.
