# OpenCode Task: Diagnose and Fix PostgreSQL 18 WAL Archiving Failures on Windows

## 1. Objective
Investigate and resolve a persistent PostgreSQL 18 WAL archiving failure in the VCOS production environment running on Windows 11.
PostgreSQL repeatedly fails to archive the WAL segment:
`000000010000008900000013`
The configured archive command invokes a PowerShell script that attempts to read, copy, and SHA-256-verify WAL files.
Windows reports that the failing WAL file cannot be read because another process is using it.
The PostgreSQL archive failure counter continues increasing, while the successful archive counter has not advanced.
Your objective is to identify the actual root cause, implement the smallest safe production-quality fix, and verify that WAL archiving recovers correctly.
Do not assume the diagnosis is already known. Investigate the actual code, operating-system behavior, PostgreSQL documentation, and runtime evidence.

## 2. Production environment
**PostgreSQL configuration**
- Operating system: Windows 11
- PostgreSQL version: 18.2
- Windows service: postgresql-x64-18
- Service status: Running
- Service startup type: Automatic
- PostgreSQL data directory: `C:\Program Files\PostgreSQL\18\data`
- WAL directory: `C:\Program Files\PostgreSQL\18\data\pg_wal`
- Production database: vcos4
- Archive directory: `C:\VCOS-Backups\wal_archive`
- Archive script: `C:\VCOS-Backups\archive_wal.ps1`
- PostgreSQL log: `C:\Program Files\PostgreSQL\18\data\log\postgresql-2026-10-14_120317.log`
- Sysinternals Handle utility: `C:\VCOS-Backups\Sysinternals\Handle\handle64.exe`

**Current PostgreSQL archive configuration**
The configured archive command is:
```
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "C:\VCOS-Backups\archive_wal.ps1" "%p" "%f"
```

Observed configuration:
```
archive_mode = on
archive_timeout = 0
pending_restart = false
```

The configured command is active, and PostgreSQL is attempting to execute it.
Do not assume that the configuration is otherwise correct. Inspect the effective configuration, including any relevant service environment, Windows permissions, and PostgreSQL settings.

## 3. Current archive script
The current contents of `C:\VCOS-Backups\archive_wal.ps1` are:
```powershell
param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$FileName
)


$ErrorActionPreference = 'Stop'


if (-not [System.IO.Path]::IsPathRooted($Source)) {
    $Source = Join-Path 'C:\Program Files\PostgreSQL\18\data' $Source
}


$Destination = Join-Path 'C:\VCOS-Backups\wal_archive' $FileName


try {
    if (Test-Path -LiteralPath $Destination) {
        $SourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
        $DestinationHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash


        if ($SourceHash -eq $DestinationHash) {
            exit 0
        }


        throw "Archive file already exists but its contents differ."
    }


    Copy-Item -LiteralPath $Source -Destination $Destination


    $SourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
    $DestinationHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash


    if ($SourceHash -eq $DestinationHash) {
        exit 0
    }


    throw "Archive verification failed."
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
```

A previous attempt to correct relative-path resolution did not resolve the problem.
The script has an important failure mode to investigate: when a destination already exists, a source-read failure can leave the source hash unavailable and then lead to a misleading error saying that the existing archive contents differ.
Determine whether this behavior is actually occurring and correct the error handling if necessary.

## 4. Exact failure evidence
The PostgreSQL log contains repeated errors such as:
```
The file 'C:\Program Files\PostgreSQL\18\data\pg_wal\000000010000008900000013'
cannot be read: The process cannot access the file
'C:\Program Files\PostgreSQL\18\data\pg_wal\000000010000008900000013'
because it is being used by another process.
```
PostgreSQL records:
```
LOG: archive command failed with exit code 1
```
It also records:
```
WARNING: archiving write-ahead log file
"000000010000008900000013" failed too many times, will try again later
```
The errors have recurred repeatedly.

**PostgreSQL archiver statistics**
At approximately 20:05 on October 14, 2026, the following query returned:
```sql
SELECT
    archived_count,
    failed_count,
    last_archived_wal,
    last_archived_time,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;
```
Results:
```
archived_count       = 6
failed_count         = 278
last_archived_wal    = 000000010000008900000012
last_archived_time   = 2026-10-14 18:42:22.612861+05:30
last_failed_wal      = 000000010000008900000013
last_failed_time     = 2026-10-14 20:05:11.003883+05:30
```
Earlier observations:
- Failure count was 243.
- It increased to 255.
- It subsequently increased to 278.
- Successful archive count remained 6.
- The latest failed WAL remained ...0013.

These statistics show persistent archive failures. They do not independently establish the root cause.

### 5. Windows file-handle investigation
Sysinternals Handle was executed against the failing WAL file:
```
& "C:\VCOS-Backups\Sysinternals\Handle\handle64.exe" -accepteula "C:\Program Files\PostgreSQL\18\data\pg_wal\000000010000008900000013"
```
Output:
```
postgres.exe pid: 17880 type: File
1D8: C:\Program Files\PostgreSQL\18\data\pg_wal\000000010000008900000013
```
The process details were:
- ProcessId: 17880
- ParentProcessId: 8056
- ExecutablePath: `C:\Program Files\PostgreSQL\18\bin\postgres.exe`
- CommandLine: `"C:/Program Files/PostgreSQL/18/bin/postgres.exe" --forkchild="checkpointer" 5304`

Task Manager also confirmed:
```
postgres.exe
PID: 17880
Status: Running
```
This is a PostgreSQL checkpointer child process.
**Important:** A checkpointer holding a WAL file open does not, by itself, prove that PostgreSQL is malfunctioning or that the handle is the root cause. Investigate Windows file-sharing semantics and PostgreSQL 18's actual WAL lifecycle before making that conclusion.
**Do not terminate PID 17880.**

### 6. File-read test
The following PowerShell test was executed against the source WAL file:
```powershell
$path = "C:\Program Files\PostgreSQL\18\data\pg_wal\000000010000008900000013"


try {
    $stream = [System.IO.File]::Open(
        $path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
    )


    $stream.Dispose()
    "READ TEST: SUCCESS"
}
catch {
    "READ TEST: FAILED"
    $_.Exception.Message
}
```
Output:
```
READ TEST: SUCCESS
```
This proves that the file could be opened under the explicitly requested sharing mode at that moment. It does not prove that the archive script's normal `Get-FileHash` or `Copy-Item` operations can read it.
Investigate whether the sharing mode used by the script is incompatible with the existing handle, and whether an alternative read implementation is appropriate and safe.
**Do not blindly replace `Copy-Item` with a custom file-copy implementation. Establish the actual cause first.**

### 7. WAL file inventory
**Source directory**
Command:
```powershell
Get-ChildItem "C:\Program Files\PostgreSQL\18\data\pg_wal" -Filter "0000000100000089000000*" |
    Select-Object Name, Length, LastWriteTime
```
Observed files:
```
000000010000008900000013 16777216 14-10-2026 19:41:48
000000010000008900000014 16777216 14-10-2026 19:42:48
000000010000008900000015 16777216 10-10-2026 06:23:43
000000010000008900000016 16777216 10-10-2026 06:24:01
000000010000008900000017 16777216 10-10-2026 06:24:03
000000010000008900000018 16777216 10-10-2026 06:24:05
000000010000008900000019 16777216 10-10-2026 06:24:25
00000001000000890000001A 16777216 10-10-2026 06:24:26
00000001000000890000001B 16777216 10-10-2026 06:24:27
00000001000000890000001C 16777216 10-10-2026 06:24:28
00000001000000890000001D 16777216 10-10-2026 06:24:30
00000001000000890000001E 16777216 10-10-2026 06:24:31
00000001000000890000001F 16777216 10-10-2026 06:33:33
000000010000008900000020 16777216 10-10-2026 06:33:37
000000010000008900000021 16777216 10-10-2026 06:33:39
000000010000008900000022 16777216 10-10-2026 06:34:19
000000010000008900000023 16777216 10-10-2026 06:39:00
```
The older timestamps do not independently prove corruption or stale files. Investigate PostgreSQL's WAL retention and recycling behavior before proposing cleanup.

**Archive directory**
Command:
```powershell
Get-ChildItem "C:\VCOS-Backups\wal_archive" -Filter "0000000100000089000000*" |
    Select-Object Name, Length, LastWriteTime
```
Observed files:
```
00000001000000890000000D 16777216 14-10-2026 17:20:11
00000001000000890000000E 16777216 14-10-2026 17:33:04
00000001000000890000000F 16777216 14-10-2026 17:33:12
000000010000008900000010 16777216 14-10-2026 17:35:13
000000010000008900000011 16777216 14-10-2026 17:35:36
000000010000008900000012 16777216 14-10-2026 18:02:54
000000010000008900000013 16777216 14-10-2026 19:41:48
```
The archive currently lacks ...0014 through ...0023.
WAL file ...0013 exists in both locations, but equality of contents has not been established.
The older source file ...0012 is no longer present in pg_wal, although its archive copy remains. Therefore, a test that assumes every archived WAL segment remains in pg_wal is invalid.

### 8. Hash evidence
The archived copy of ...0013 produced this SHA-256:
```
051C5A778D99689364269913F1A5536260411574F4C4FB253852B3E4846BC205
```
An attempt to hash the source WAL file failed with a Windows sharing violation.
Consequently, an earlier comparison printed:
```
Hashes match: False
```
That result is not evidence that the hashes differ, because the source hash could not be obtained.
A previously successful comparison for WAL file ...0012 produced matching SHA-256 values:
```
56A8778018847D4D452EA83CE35AF45D7CE457B4380ABFA15449D0F08C2581BD
```
The archived copy of ...0013 must not be assumed correct or corrupt without a valid comparison.
**Do not overwrite existing archive files merely to make the script succeed.**

### 9. Archive directory permissions
The archive directory's ACL was inspected using:
```powershell
Get-Acl "C:\VCOS-Backups\wal_archive" |
    Select-Object -ExpandProperty Access |
    Format-Table IdentityReference, FileSystemRights, AccessControlType, IsInherited -AutoSize
```
Visible permissions included:
- BUILTIN\Administrators: FullControl.
- NT AUTHORITY\SYSTEM: FullControl.
- BUILTIN\Users: ReadAndExecute.
- NT AUTHORITY\Authenticated Users: Modify, Synchronize.

The output does not establish a definite archive-directory permission problem.

The PostgreSQL Windows service runs as:
`NT AUTHORITY\NetworkService`

The ACL on the source WAL file has not yet been conclusively ruled out. Inspect it only if doing so contributes to a supported diagnosis.
**Do not grant broad permissions or modify the ACLs speculatively.**

### 10. Existing backup and recovery protection
A fresh logical production backup exists:
`C:\VCOS-Backups\vcos4-production-20261014.dump`

Size: 1,723,991 bytes
SHA-256: `2E1172530CD85854424776441140DFDE9661AC562C6FA6ED6ED4D8487F882B33`

The backup was created from PostgreSQL 18.2 using custom dump format.
It was restored into the isolated database: `vcos4_recovery_verify_20261014`

Observed validation:
- Production schema: 484 public tables.
- Restored schema: 484 public tables.
- Production migration version: 8ca2a1cf24bf.
- Restored migration version: 8ca2a1cf24bf.
- Exact row-count reports were generated for all tables in production and the restored database.
- The report comparisons produced no differences.

These checks support the logical backup's recoverability, but they do not prove record-by-record equality or physical point-in-time recovery.
**Preserve this backup and all existing WAL archive files.**
**Do not claim that physical WAL/PITR recovery is working.**

---

## 11. Mandatory investigation
Follow this sequence:

**A. EXPLORE**
Inspect the actual PostgreSQL configuration, archive script, archive directory, relevant logs, and any existing VCOS backup or disaster-recovery implementation.
Determine whether any existing backup code, scheduled jobs, antivirus configuration, or Windows process is interacting with the WAL files.
Do not assume a generic PostgreSQL Linux fix applies to Windows.

**B. UNDERSTAND**
Determine:
- Why the script's `Get-FileHash` or `Copy-Item` call fails on ...0013.
- Whether the checkpointer's existing file handle actually prevents the script's requested access.
- Whether PostgreSQL's archive command contract and Windows file-sharing rules are being respected.
- Whether PowerShell's default file-opening behavior differs from the successful explicit-share-mode test.
- Whether another process, filesystem filter, security product, or file operation could explain the failure.
- Whether the existing destination file should be compared, skipped, quarantined, or treated as a hard error under each possible outcome.
- Why ...0013 is repeatedly retried while later segments are not successfully archived.
- How to recover safely from a failed segment without creating a WAL gap or falsely reporting success.
Consult PostgreSQL 18 documentation and verify any relevant Windows-specific assumptions against actual runtime evidence.

**C. REUSE**
Reuse the existing archive directory, backup strategy, configuration, and validation mechanisms where appropriate.
Do not replace the production backup architecture unnecessarily.

**D. EXTEND**
If a script change is justified, improve it to provide:
- Correct Windows file handling.
- Safe, reliable WAL copying.
- Correct handling of an existing destination.
- Hash verification that never compares an unavailable hash.
- Clear diagnostics that distinguish access errors, sharing violations, destination conflicts, copy failures, and verification failures.
- Appropriate nonzero exit codes for genuine failures.
- No false success.
- No silent overwriting of an existing WAL segment.
- No incomplete final destination file being mistaken for a successfully archived segment.
Use a temporary destination file and atomic promotion only if the design is appropriate for the Windows filesystem and can be implemented safely.
Any proposed retry behavior must be bounded and must not conceal a persistent failure.

**E. IMPLEMENT**
If a supported root cause is established, implement the smallest production-quality correction in the actual relevant project/script files.
Do not stop after writing an explanation or proposed script.
Before changing a live archive script, preserve a timestamped copy of the existing file.
Do not make speculative modifications to PostgreSQL's data directory, pg_wal, service configuration, permissions, or recovery settings.

**F. VERIFY**
Verification must include:
- Syntax validation of the modified PowerShell script.
- A safe test using a WAL segment whose source is available and whose archive destination does not already contain a conflicting copy, where such a test can be arranged without manually fabricating production WAL.
- Verification of source/destination equality after a successful copy.
- Correct behavior when an identical destination already exists.
- Correct behavior when a destination exists but differs.
- Correct behavior when the source is missing or inaccessible.
- Correct exit codes for success and failure.
- Confirmation that the archive script does not delete, truncate, or overwrite existing valid WAL files.
- Confirmation that PostgreSQL's `pg_stat_archiver` advances after the production archive path recovers.
- Confirmation that the missing WAL sequence is addressed without creating an unrecoverable gap.
A unit test alone is not sufficient to claim production recovery.

### 12. Strict safety requirements
The production database is actively running. Treat this as a production incident.
**YOU MUST NOT:**
- Terminate postgres.exe PID 17880.
- Kill PostgreSQL processes.
- Restart or stop PostgreSQL without a specific, evidence-supported reason and an explicit maintenance plan.
- Disable WAL archiving as a workaround.
- Delete, rename, truncate, or manually overwrite WAL files.
- Manually fabricate WAL files.
- Report success merely because a PowerShell command returns exit code zero.
- Ignore the failure of an existing-destination comparison.
- Change PostgreSQL configuration before the root cause is understood.
- Assume the archived ...0013 is valid.
- Claim point-in-time recovery is available solely because a logical dump exists.
- Claim the problem is fixed without evidence from PostgreSQL's archiver statistics and a validated archive.
If the evidence is insufficient, stop before changing production behavior and explain precisely which additional read-only evidence is needed.

### 13. Required final report
After the investigation, provide:
- Root cause: Confirmed, probable, or unresolved, with evidence.
- Why the current implementation fails.
- Files inspected and modified.
- Exact code changes, including the rationale for each.
- Tests performed and results.
- Production verification results.
- Current archive completeness, including any unresolved WAL gaps.
- Remaining recovery risks.
- The next action, if production recovery requires an approved maintenance window.
Do not claim that the incident is resolved until the production archive process succeeds and the relevant WAL recovery chain has been verified.

---

## ADDITIONAL EVIDENCE — SOURCE WAL FILE ACL INSPECTED

The ACL on:
```
C:\Program Files\PostgreSQL\18\data\pg_wal\000000010000008900000013
```
shows:
- BUILTIN\Administrators: FullControl
- NT AUTHORITY\SYSTEM: FullControl
- NT AUTHORITY\NETWORK SERVICE: FullControl
- Current user: FullControl

The archive directory ACL shows:
- Administrators: FullControl
- SYSTEM: FullControl
- Authenticated Users: Modify, Synchronize

Therefore, no obvious NTFS permission deficiency has been identified.

The source WAL file remains held open by PostgreSQL checkpointer PID 17880.
A PowerShell File.Open test using FileShare.ReadWrite | FileShare.Delete returned READ TEST: SUCCESS, but the archive script's Get-FileHash operation previously failed with a sharing violation.

Investigate the exact Windows file-sharing behavior of Get-FileHash and Copy-Item versus an explicit FileStream opened with compatible sharing flags. Establish the root cause before changing the script.

**Do not terminate PID 17880, restart PostgreSQL, change ACLs speculatively, or overwrite/delete WAL files. Preserve the existing archive and production backup.**

**My recommendation:** Let OpenCode inspect the actual script and propose an evidence-based correction before you change anything. We should not treat this as resolved until PostgreSQL successfully archives new WAL segments and the recovery chain is verified.

---

## 12. Strict safety requirements
The production database is actively running. Treat this as a production incident.
**YOU MUST NOT:**
- Terminate postgres.exe PID 17880.
- Kill PostgreSQL processes.
- Restart or stop PostgreSQL without a specific, evidence-supported reason and an explicit maintenance plan.
- Disable WAL archiving as a workaround.
- Delete, rename, truncate, or manually overwrite WAL files.
- Manually fabricate WAL files.
- Report success merely because a PowerShell command returns exit code zero.
- Ignore the failure of an existing-destination comparison.
- Change PostgreSQL configuration before the root cause is understood.
- Assume the archived ...0013 is valid.
- Claim point-in-time recovery is available solely because a logical dump exists.
- Claim the problem is fixed without evidence from PostgreSQL's archiver statistics and a validated archive.
If the evidence is insufficient, stop before changing production behavior and explain precisely which additional read-only evidence is needed.

### 13. Required final report
After the investigation, provide:
- Root cause: Confirmed, probable, or unresolved, with evidence.
- Why the current implementation fails.
- Files inspected and modified.
- Exact code changes, including the rationale for each.
- Tests performed and results.
- Production verification results.
- Current archive completeness, including any unresolved WAL gaps.
- Remaining recovery risks.
- The next action, if production recovery requires an approved maintenance window.
Do not claim that the incident is resolved until the production archive process succeeds and the relevant WAL recovery chain has been verified.

**Important instruction to OpenCode**
Before changing anything, inspect the current runtime and code, establish the root cause, and explain the proposed corrective action. Then implement and test the fix when it is safe to do so.
The priority is not merely to eliminate the error message. The priority is to restore trustworthy PostgreSQL WAL archiving without compromising VCOS production data or recovery capability.

After OpenCode investigates
Send me its root-cause findings and proposed fix before applying any destructive or service-affecting action. I can help review whether its reasoning is sound and whether the proposed change is safe for the production database.