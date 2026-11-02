# VCOS Repository Architecture

**Status:** Verified 2026-10-16 against repository at `D:\vcos1\workspace\vcos`
**Audience:** Engineers and future model sessions continuing VCOS implementation
**Rule:** This document describes what EXISTS. Anything unverified is marked as such.

---

## 1. Repository layout

```
D:\vcos1\                          # outer workspace folder (evidence drop zone)
├── DEPLOYMENT_DR_SLICE_2F_EVIDENCE.md      # Stage 1: real backup/restore proof
├── LINUX_CI_EVIDENCE.md                    # Stage 2: CI evidence
├── REGRESSION_LINUX_EVIDENCE.md            # Stage 2: regression evidence
└── workspace\vcos\                         # THE PROJECT (git root here)
    ├── README.md
    ├── opencode.json                       # opencode model config
    ├── .github\workflows\ci.yml            # CI pipeline
    ├── backend\                            # Python 3.13 / FastAPI backend
    ├── frontend\                           # Next.js 14.2 frontend
    ├── scripts\                            # operational scripts
    └── docs\                               # THIS handoff documentation set
```

Repository root also contains ~55 durable evidence/report files (`SLICE*_VERIFICATION_REPORT.md`,
`*_RATIFICATION_EVIDENCE.md`, `*_EVIDENCE.md`) — the project's audit trail convention is:
**every verified slice lands as a markdown evidence file.** Do not delete or rewrite them;
add new evidence files for new work.

## 2. Backend (`backend/`)

**Stack:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2.0 async (asyncpg / aiosqlite),
Alembic (partial), pytest + pytest-asyncio 8.3.

```
backend/
├── app/
│   ├── main.py                 # FastAPI app; lifespan calls init_db()
│   ├── core/                   # config.py (Settings), timeutils.utcnow
│   ├── db/                     # database.py: engine, AsyncSession, init_db()
│   ├── models/                 # 112 model files; models/__init__ imports 109 modules
│   ├── api/v1/                 # ~140 route modules (all HTTP endpoints)
│   ├── services/               # 79 service modules (business logic)
│   ├── intelligence/           # ~85 modules (Company Brain, canonical mutation boundary)
│   ├── validation/             # capability_contract.py — capability-aware validation
│   └── ...
├── alembic/versions/           # 8 migration scripts (partial; see §5)
├── tests/                      # 281 test files, ~4,069 test functions
│   └── acceptance/             # 432 acceptance tests (universal matrix, adversarial)
├── .env                        # DATABASE_URL -> localhost:5432/vcos4 (dev/prod host)
└── *.md                        # evidence files for backend-level workstreams
```

### Database bootstrap (IMPORTANT)
`app/db/database.py:init_db()` is the canonical schema bootstrap used at app startup:
1. `Base.metadata.create_all` (idempotent; creates missing tables only)
2. `_create_universal_indexes()` (idempotent `CREATE INDEX IF NOT EXISTS`)
3. `_run_postgres_alter_migrations()` (idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`)

The full current model layer produces **688 tables** in `public` schema (verified against
`vcos_test` and CI fresh-DB runs). A database with fewer tables is schema-stale and must be
converged by running `init_db()` before being used as a backup/recovery source.

## 3. Frontend (`frontend/`)

Next.js 14.2 App Router, React 18, TypeScript, Tailwind.
~55 authenticated route directories under `app/`. Not the focus of the current workstream.

## 4. Core domain boundary — canonical mutation

All writes to canonical company reality pass through:
- `app/intelligence/canonical_mutation.py` — the canonical mutation boundary
- `app/services/canonical_reality_integrity_service.py` — integrity scanning

No parallel engines, no bypass writes. Recovery/backup validation re-uses these services
(`restore_service._validate_*`, `post_restore_validator`, `canonical_reality_integrity_service`)
against restored databases — this is how a restored copy earns the same validation as live data.

## 5. Data layer facts (verified 2026-10-16 on the Windows host)

| Fact | Value |
|---|---|
| PostgreSQL | 18.2, Windows service `postgresql-x64-18`, port 5432 |
| Production/app DB (per `backend/.env`) | `vcos4` (30 organizations, 487 tables — schema-stale) |
| Test DB | `vcos_test` (688 tables = current model schema) |
| Alembic state | `alembic/versions/` has only 8 migrations; `vcos4.alembic_version = 8ca2a1cf24bf`. Schema is maintained primarily via `init_db()` create_all, NOT alembic. Alembic is a bolt-on for a few targeted migrations (`001_add_supersedes_id`, `002_add_autonomy...`, `003_add_backup_manifests`). |
| Known ORM/DB drift | `Session.device_fingerprint` exists in `app/models/user.py:67` but not in the live `sessions` table — resolved by running `init_db()`/alter migrations, not by scratch scripts. Scratch ALTER scripts (`add_restore_columns.py`, `create_backup_tables.py`) exist in `backend/` from earlier sessions; they duplicate what `init_db()` now does idempotently. Do not build new workflow on scratch scripts. |
| Duplicate definitions | `app/models/backup_manifest.py` defines `RecoveryManifestState` and `RecoveryVerificationStatus` twice (lines ~52/77 and ~338/363); the later definitions win at import. Harmless today; candidate cleanup. |

## 6. Deployment + Backup/Restore + DR service stack

All in `app/services/`:

| Module | Lines | Role |
|---|---|---|
| `backup_service.py` | ~1934 | Ratified backup orchestration + deep verification. NOTE: `verify_backup` defined twice (329, 1801); the 1801 definition wins. `VCOS_TEST_MODE=1` short-circuits verification — never set it in production runs. |
| `restore_service.py` | ~1891 | Ratified logical restore + `_validate_schema/_validate_tenant_isolation/_validate_temporal_integrity/_validate_provenance/_validate_epistemic/_validate_governance/_validate_readiness` (shared by recovery gates). |
| `deployment_contract_service.py` | ~1703 | Deployment contracts. |
| `recovery_gates.py` | ~1038 | 19-state recovery state machine (CREATED → … → READY_FOR_APPROVAL → ACTIVATED; FAILED/BLOCKED/INCONCLUSIVE/INTERRUPTED). Gates look up isolated restores by `context.metadata["restore_id"]` (falls back to `recovery_id`). |
| `migration_safety.py` | ~991 | Migration safety harness. |
| `pitr_test_orchestrator.py` | ~923 | 16-phase PITR test (preflight → baseline backup → isolated restore → validations → RPO/RTO → evidence). |
| `backup_executor.py` | ~883 | Capability-aware backup executor (pgbackrest > pg_basebackup > pg_dump), manifest lifecycle, artifact verification, recovery manifest, WAL baseline recording. |
| `release_failure_recovery.py` | ~1736 | Release failure handling. |
| `post_restore_validator.py` | ~855 | Canonical validation of a restored DB (12 phases, org-scoped). |
| `isolated_restore.py` | ~789 | Physical restore into an isolated instance on a scratch port (initdb → extract → configure → recovery.signal/WAL replay → start → validate). |
| `disaster_recovery_service.py` | ~716 | DR orchestration. |
| `wal_archive_monitor.py` | ~642 | WAL archiving health: archive_mode/command, `pg_stat_archiver`, archive_status, segment-file integrity, continuity from declared baseline. |
| `deployment_rollback.py` | ~625 | Rollback execution. |
| `rpo_rto_measurement.py` | ~533 | Phase-timestamped RPO/RTO measurement (global singleton `rpo_rto_service`). |
| `recovery_evidence.py` | ~318 | Machine-readable recovery evidence artifacts (`generate_from_restore`, `generate_from_pitr_test`). |

**Environment anchors wired into these services:**
- WAL archive dir: `C:\VCOS-Backups\wal_archive` (env `WAL_ARCHIVE_DIR` honored)
- Archive script: `C:\VCOS-Backups\archive_wal.ps1` (validated 2026-10-15; rollback copy `archive_wal.ps1.backup.20261015_171854`)
- Local backup vault: `C:\VCOS-Backups\` (env `VAULT_BUCKET`)
- Base backup artifact (verification baseline): `C:\VCOS-Backups\basebackup_new\basebackup_20261016_070611\base.tar.gz` (107,851,042 bytes)
- DR runbook: `backend/DR_RUNBOOK.md`

## 7. WAL archiving state (verified 2026-10-16)

- `archive_mode=on`, `archive_command` → `archive_wal.ps1`, `archive_timeout=0`
- Segment `000000010000008900000014` is PERMANENTLY MISSING (recycled before fix; 18-byte remnant). Documented limitation: no PITR across that gap. Segments 0015–0023 form a continuous verified chain.
- Archive lag metrics look "stale" on an idle DB because `archive_timeout=0` and no WAL is generated; this is NOT a failure. Health logic must distinguish "no pending WAL" from "archive stalled".

## 8. CI (`/.github/workflows/ci.yml`)

Jobs: `pr-backend-tests`, `pr-frontend-tests`, `full-regression`, `migration-verification`.
Real PostgreSQL 18 service container; no SQLite fallback for critical suites. See
`VCOS_TEST_VERIFICATION_INVENTORY.md` for commands and suite counts.

## 9. Semantic invariants enforced by the architecture

- DECISION ≠ AUTHORIZATION ≠ COMMITMENT ≠ RESPONSIBILITY ≠ ACTION ≠ EXECUTION ≠ OUTCOME
- OBSERVATION ≠ INFERENCE ≠ PREDICTION; AI OUTPUT ≠ CANONICAL TRUTH
- UNKNOWN ≠ FAILED ≠ SUCCESS
- SIMULATION ≠ OUTCOME

These map to real tables/services (e.g. `company_decisions`, `company_authorizations`,
`company_commitments`, `company_actions`; epistemic classification in intelligence services).
Any new code must preserve these distinctions — see `VCOS_ULTIMATE_MOAT_DOCTRINE.md`.
