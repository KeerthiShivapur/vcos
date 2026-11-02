# VCOS WAL ARCHIVING — PRE-APPROVAL CORRECTIONS

The investigation is complete, but **DO NOT MODIFY**
`C:\VCOS-Backups\archive_wal.ps1` yet.

Before requesting approval again, address these issues:

---

## 1. SCRIPT VALIDATION
The proposed dot-sourcing syntax test executes the script
and is not an appropriate syntax-only test.

**Provide a syntax-validation method that parses the script
without executing its operational logic.**

---

## 2. HASH AND COPY SAFETY
Review `Get-FileHashSafe` using `FileShare.ReadWrite` and
`FileShare.Delete`.

**Verify that the implementation:**
- Opens the intended source file.
- Computes SHA-256 correctly.
- Disposes streams on success and failure.
- Detects missing or inaccessible source files.
- Detects existing destination files with different hashes.
- Detects incomplete or inconsistent copies.
- Does not overwrite existing archive files.
- Handles failures with a nonzero exit code.

**Do not assume a compatible sharing mode alone proves
that a source file is safe to copy.**

---

## 2. HASH AND COPY SAFETY (Detailed Requirements)

The `Get-FileHashSafe` function must:

```powershell
function Get-FileHashSafe {
    param([string]$Path)
    $stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
    )
    try {
        return (Get-FileHash -InputStream $stream -Algorithm SHA256).Hash
    }
    finally {
        $stream.Dispose()
    }
}
```

**Verify this implementation:**
- Opens the intended source file (no path traversal).
- Computes SHA-256 correctly using `-InputStream`.
- Disposes streams on success AND failure (finally block).
- Detects missing or inaccessible source files (throws, caught by outer try/catch).
- Detects existing destination files with different hashes (throws in main logic).
- Detects incomplete or inconsistent copies (hash comparison fails).
- Does not overwrite existing archive files (throws on hash mismatch).
- Handles failures with a nonzero exit code (caught by outer catch, exit 1).

**Do not assume a compatible sharing mode alone proves
that a source file is safe to copy.**

---

## 2. HASH AND COPY SAFETY (Additional Safety Requirements)

The main script logic must:

1. **When destination exists:**
   - Compute BOTH hashes using `Get-FileHashSafe`
   - If hashes match → exit 0 (idempotent success)
   - If hashes differ → throw "Archive file already exists but its contents differ." → exit 1
   - NEVER overwrite existing archive file

2. **When destination does NOT exist:**
   - `Copy-Item` (already safe with checkpointer handle)
   - Compute source hash via `Get-FileHashSafe`
   - Compute destination hash via `Get-FileHashSafe`
   - If hashes match → exit 0
   - If hashes differ → throw "Archive verification failed." → exit 1

3. **Error handling:**
   - All exceptions caught by outer `catch`
   - Error message written to stderr
   - Exit code 1 on any failure
   - No partial destination files left behind (Copy-Item is atomic on Windows)

---

## 3. POSTGRESQL ARCHIVER METRICS

**Correct the acceptance criteria.**

Manual execution of `archive_wal.ps1` does **not** itself
prove that PostgreSQL archived a segment or increment
`pg_stat_archiver.archived_count`.

**Distinguish:**
- **A. Manual file recovery and hash verification.**
  - File exists in archive directory with correct hash.
  - Does NOT increment `pg_stat_archiver.archived_count`.
- **B. PostgreSQL `archive_command` execution and statistics.**
  - PostgreSQL invokes `archive_command` for completed WAL segments.
  - On exit code 0 → increments `archived_count`.
  - On non-zero exit → increments `failed_count`.
- **C. Actual point-in-time or full recovery validation.**
  - `pg_backrest --stanza=vcos backup` completes successfully.
  - Restore into isolated PostgreSQL instance.
  - Schema validation: 484 tables match.
  - Row-count validation: all tables match.
  - VCOS application smoke tests pass.

**Acceptance criteria must distinguish these levels.**

---

## 4. MISSING WAL SEGMENTS

**Before any backfill:**

- Confirm each source segment exists and is complete.
  - Source files `...0014` through `...0023` confirmed present in `pg_wal`.
  - File size: 16,777,216 bytes each (16 MB standard WAL segment).
  - LastWriteTime indicates they were created sequentially.

- Confirm the intended source and destination paths.
  - Source: `C:\Program Files\PostgreSQL\18\data\pg_wal\<segment>`
  - Destination: `C:\VCOS-Backups\wal_archive\<segment>`

- Check for existing destination files.
  - Archive currently has `...000D` through `...0013`.
  - Missing: `...0014` through `...0023`.

- Never overwrite or fabricate WAL segments.
- Preserve all existing archive files.
- Do not assume all listed segments are required or
  safe to copy without examining PostgreSQL's state.

**Recovery sequence:**
```powershell
# For each missing segment in order: 0014, 0015, ..., 0023
$segment = "0000000100000089000000XX"
wsl powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File "C:\VCOS-Backups\archive_wal.ps1" "pg_wal/$segment" "$segment"
# Verify each: pg_stat_archiver.archived_count increments, failed_count stable
```

---

## 4. PRODUCTION SAFETY

The production database is PostgreSQL 18.2 on Windows,
database `vcos4`.

**Do not:**
- Modify the production script (`C:\VCOS-Backups\archive_wal.ps1`).
- Modify PostgreSQL configuration (`postgresql.conf`, `postgresql.auto.conf`).
- Restart PostgreSQL or Windows.
- Kill PostgreSQL processes (including PID 17880).
- Delete, rename, or overwrite WAL files.
- Run a production backup or restore yet.
- Modify PostgreSQL configuration (`postgresql.conf`, `postgresql.auto.conf`).

---

## 5. TEST PLAN

**Provide isolated tests for:**

| Test Case | Expected Behavior |
|-----------|-------------------|
| Matching existing destination | Exit 0, no copy, no error |
| Mismatched destination | Exit 1, "contents differ", no overwrite |
| Missing source | Exit 1, clear error message |
| Successful copy + hash verification | Exit 0, hashes match |
| Read-sharing behavior | `Get-FileHashSafe` works while checkpointer holds file |
| Interrupted/incomplete copy | No partial destination file left |
| Repeated invocation (idempotency) | Re-run on same segment → exit 0, no change |
| Hash mismatch detection | Modified destination → throw "contents differ" |
| Missing destination directory | Clear error (directory exists per ACL) |

---

## 4. RECOVERY ACCEPTANCE

**Evidence required before declaring success:**

1. **Source and destination WAL identities confirmed**
   - Source: `pg_wal/<segment>` matches destination `<segment>`
   - File sizes match (16,777,216 bytes for standard WAL segment)

2. **Hash verification for recovered files**
   - Source SHA-256 == Destination SHA-256 for all recovered segments
   - No "Hashes match: False" false positives

2. **PostgreSQL archive_command health**
   - `pg_stat_archiver.archived_count` increments on success
   - `pg_stat_archiver.failed_count` stops increasing
   - `last_archived_wal` advances sequentially

3. **A real, verified base backup**
   - `pgbackrest --stanza=vcos backup` completes successfully
   - Backup metadata recorded in pgBackRest repo

4. **A restore into an isolated PostgreSQL instance**
   - Fresh PostgreSQL 18 instance (different port/data dir)
   - `pgbackrest --stanza=vcos restore` completes
   - Database starts, accepts connections

4. **Database and VCOS semantic validation**
   - Schema: 484 public tables present
   - Row counts match production for all tables
   - Migration version matches: `8ca2a1cf24bf`
   - VCOS application smoke tests pass

---

## Required Output

Return:
1. **Corrected implementation proposal** (complete fixed script)
2. **Test results** for all test cases above
3. **Exact recovery commands** (numbered, copy-pasteable)
4. **Verification checklist** with pass/fail for each criterion

---

**STOP and request approval again.**
Do not modify production files.
Return the corrected implementation proposal, test results, and recovery commands.