# VCOS Test & Verification Inventory

**As of:** 2026-10-16
**Purpose:** What verification exists, where it lives, how to run it, and what counts as
ratification evidence. Read with `VCOS_ULTIMATE_MOAT_DOCTRINE.md` §3 (Evidence discipline).

---

## 1. Test suite layout (`backend/tests/`)

| Area | Location | Scale (verified) |
|---|---|---|
| Backend tests | `backend/tests/*.py` | 281 files, ~4,069 test functions |
| Acceptance suite | `backend/tests/acceptance/` | 432 tests: universal matrix (26 dimensions), release-candidate slices 2A–2E, adversarial scenarios, backup/restore roundtrip |
| Recovery/DR unit+integration | `backend/tests/` (test_backup_*, test_restore_*, test_pitr*, test_recovery*, test_dr3_recovery_baseline.py) | DR stack coverage |
| Scale tests | `backend/tests/scale/` | Seed scale profiles used by RPO/RTO runners |

**Frameworks:** pytest 8.3.4, pytest-asyncio. SQLAlchemy 2.0 async; test DBs are SQLite
in-memory OR real PostgreSQL depending on `DATABASE_URL` (conftest switches). Critical
PostgreSQL-bound suites (canonical validation, recovery, migration) must run against real
PostgreSQL for ratification — SQLite green is necessary, not sufficient.

## 2. Gate suites (ratified, treat as regression protection)

| Suite | Tests | Notes |
|---|---|---|
| Gate 6B | 48 | Canonical substrate gates |
| Gate 6C | 23 | |
| Gate 6D | 25 | |
| Gate 6E | 12 | |
| Gate 6F | 18 | |
| Gate 35G.2 | 15 | |
| Gates 13/30/32 | 152 | |
| 35-H (failure under load) | 63 | |
| 35-I (longitudinal reality) | 36 | CERTIFIED PASSING (per REGRESSION_LINUX_EVIDENCE.md) |
| **Total (6B–6F + 35G.2 + 13/30/32 + 35-H)** | **415** | Ratified green on PostgreSQL 18.2 |

## 3. How to run

```powershell
# From backend/ with real PostgreSQL 18 running on 127.0.0.1:5432
$env:DATABASE_URL='postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/vcos4'
$env:VCOS_TEST_MODE='0'          # never '1' for evidence runs

# Full backend suite
python -m pytest tests -q

# Gate suites (names indicate slices)
python -m pytest tests -q -k "gate_6b or gate_6c or gate_6d or gate_6e or gate_6f"
python -m pytest tests -q -k "35G2 or gate_35g"
python -m pytest tests -q -k "35_h or failure_under_load"
python -m pytest tests -q -k "35_i or longitudinal"

# Acceptance matrix
python -m pytest tests/acceptance -q

# DR.3 E2E (script harness, not pytest)
python tests\test_dr3_recovery_baseline.py
```

CI runs these on GitHub Actions (`.github/workflows/ci.yml`): `pr-backend-tests`,
`pr-frontend-tests`, `full-regression`, `migration-verification` (fresh DB must produce
688 tables; mismatch is a hard failure).

## 4. What counts as ratification evidence

Per workstream, an evidence file must contain:

1. **Environment identity:** OS, PostgreSQL version, Python version, exact database names,
   git revision (or workspace path + date).
2. **Command sequence:** copy-pasteable commands, in order.
3. **Raw results:** test counts (passed/failed/skipped), or raw service outputs; plus paths
   to machine-readable artifacts when applicable (e.g. `C:\VCOS-Backups\DR3_TEST_RESULTS.json`).
4. **Mechanism:** one paragraph explaining WHY this proves the capability (e.g., "restored
   checksum computed from the artifact file equals live-source hash of the same tables").
5. **Limitations & historical gaps:** known permanent limitations (e.g., WAL segment 0014)
   restated so the evidence doesn't overclaim.
6. **Verdict:** PASS / FAIL / BLOCKED with the exact failure if not PASS.

The repository convention: `*_EVIDENCE.md` at repo root or `backend/`; ratification
artifacts use `*_RATIFICATION_EVIDENCE.md`. Never edit an old evidence file — supersede it.

## 5. Test-mode bypasses (danger list)

- `VCOS_TEST_MODE=1` makes `backup_service.verify_backup` return all-VERIFIED without
  running checks. Allowed ONLY in unit tests that explicitly assert on other behavior.
  FORBIDDEN in any evidence/ratification run.
- SQLite auto-fallback paths in some services (e.g. `PRAGMA` probes) are for unit tests;
  a PostgreSQL ratification must be produced on PostgreSQL.

## 6. Current DR.3 verification status

- Harness: `backend/tests/test_dr3_recovery_baseline.py` (rewritten this session to drive
  the real services end-to-end; see `VCOS_IMPLEMENTATION_STATUS.md` §2.2 for the defect list
  it previously tripped on).
- Last artifact: `C:\VCOS-Backups\DR3_TEST_RESULTS.json` — `overall_success: false`
  (2026-10-16 09:17 local). Superseded runs must overwrite this file and produce
  `DR3_RECOVERY_BASELINE_EVIDENCE.json`.
