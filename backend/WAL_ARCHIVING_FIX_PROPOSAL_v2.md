# VCOS WAL ARCHIVING — FINAL SAFETY REVIEW & FIX PROPOSAL v2

## Current Status
- **Root cause hypothesis**: `Get-FileHash -LiteralPath` uses default `FileShare.Read` incompatible with PostgreSQL checkpointer's exclusive handle
- **Proposed fix**: `Get-FileHashSafe` using explicit `FileStream` with `FileShare.ReadWrite | FileShare.Delete`
- **Status**: Awaiting final safety review before deployment
- **Production database**: PostgreSQL 18.2 on Windows, database `vcos4`
- **Current archive stats**: 7 archived, 285 failed, stuck on segment `...0013`

---

## MANDATORY PRE-DEPLOYMENT REQUIREMENTS

### 1. REPRODUCIBLE FILE-SHARING TEST
**Requirement**: Provide a self-contained, reproducible test that demonstrates:
- `Get-FileHash -LiteralPath` fails with sharing violation when checkpointer holds the file
- `Get-FileHash -InputStream` with explicit `FileStream(FileShare.ReadWrite | FileShare.Delete)` succeeds
- `Copy-Item` succeeds (already confirmed)

**Test must be runnable in isolation** and produce clear PASS/FAIL output.

### 3. SCRIPT SAFETY IMPROVEMENTS
The fixed script must guarantee:

| Safety Requirement | Implementation |
|-------------------|----------------|
| **Never overwrite existing destination** | Throw on hash mismatch before any write |
| **Unavailable source hash → no misleading comparison** | If source hash unavailable, throw; never compare null/empty hash |
| **Partial destination protection** | Use temp file + atomic rename, or verify `Copy-Item` atomicity on Windows |
| **Destination conflict handling** | Existing dest with different hash → throw before any write |
| **Unavailable source hash** | Throw before any comparison; never compare null/empty hash |

### 4. BACKUP PROTECTION
- **Timestamped backup** of current production script before any modification
- Format: `archive_wal.ps1.backup.YYYYMMDD_HHMMSS`

### 5. NO WSL/MANUAL BACKFILL
- Do NOT use WSL commands or manual loops to invoke archive script
- PostgreSQL's `archive_command` must handle retries automatically
- Explain how PostgreSQL retries failed segments and how missing segments recover without manual intervention

### 6. POSTGRESQL RETRY BEHAVIOR
Explain:
- How PostgreSQL retries failed `archive_command` (exponential backoff, `archive_timeout`)
- How missing segments `...0014`–`...0023` will be handled once the fix works
- Why no manual backfill loop is needed — PostgreSQL will retry automatically
- How to avoid WAL gaps during recovery

### 7. FINAL DELIVERABLES
Provide:
1. **Verified root cause** with reproducible test evidence
2. **Complete patched script** (complete fixed `archive_wal.ps1`)
3. **Test results** for all safety requirements
4. **Rollback plan** (exact commands to restore previous script)
5. **Deployment sequence** (numbered steps)
6. **Rollback commands** (exact commands to restore previous script)

---

## SAFETY CHECKLIST — MUST ALL BE ✅ BEFORE DEPLOYMENT

| Check | Required |
|-------|----------|
| ✅ Reproducible file-sharing test proves root cause | |
| ✅ `Get-FileHashSafe` validated with explicit FileStream | |
| ✅ Existing destination never overwritten | |
| ✅ Unavailable source hash never produces false comparison | |
| ✅ Partial destination cannot be accepted as success | |
| ✅ Timestamped backup of current script created | |
| ✅ No WSL/manual backfill commands in recovery plan | |
| ✅ PostgreSQL retry behavior explained | |
| ✅ WAL gap prevention explained | |
| ✅ Rollback commands provided | |
| ✅ Complete patched script provided | |
| ✅ All test results presented | |

---

## DEPLOYMENT SEQUENCE (Only After All ✅)

1. **Backup current script** with timestamp
2. **Deploy corrected script** 
3. **Validate syntax** (parser check)
4. **Observe PostgreSQL archive retries** (watch `pg_stat_archiver`)
5. **Confirm new segments archived** (`archived_count` increments, `failed_count` stable)
6. **Verify archive sequence continuity** (no gaps)
6. **Verify pgBackRest backup works** (if configured)
7. **Full recovery validation** (isolated restore + semantic checks)

---

## REQUIRED OUTPUT FROM OPENCODE

Return a single response containing:

1. **Reproducible file-sharing test** (code + output)
2. **Final patched `archive_wal.ps1`** (complete)
3. **Test results** for all safety requirements
3. **Rollback commands** (exact commands)
4. **Deployment sequence** (numbered steps)
4. **Rollback commands** (exact commands to restore)
5. **Confirmation all safety checklist items ✅**

---

**DO NOT MODIFY PRODUCTION UNTIL ALL ITEMS ARE ✅ AND I EXPLICITLY APPROVE.**

---

**Next Action**: Run this prompt in OpenCode and share its complete response here for review.