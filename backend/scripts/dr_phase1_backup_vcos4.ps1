[CmdletBinding()]
param(
  [string]$Database = 'vcos4',
  [string]$VaultDir = 'C:\VCOS-Backups',
  [string]$PgBin = 'C:\Program Files\PostgreSQL\18\bin',
  [string]$PgHost = '127.0.0.1',
  [int]$PgPort = 5432,
  [string]$PgUser = 'postgres',
  [int]$MinFreeGb = 5
)

$ErrorActionPreference = 'Stop'

function Fail([string]$message) {
  Write-Output ("PHASE1-BACKUP-FAILED: " + $message)
  exit 1
}

function Invoke-Scalar([string]$db, [string]$sql) {
  $out = & $psql -U $PgUser -h $PgHost -p $PgPort -d $db -t -A -v ON_ERROR_STOP=1 -c $sql 2>&1
  if ($LASTEXITCODE -ne 0) { Fail ("psql failed on " + $db + ": " + (($out | Out-String).Trim())) }
  return (($out | Out-String).Trim())
}

function Get-Sha256([string]$path) {
  return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()
}

if ($Database -ne 'vcos4') { Fail ("refusing to run: this backup script is locked to database 'vcos4' (got '" + $Database + "')") }
if (-not $env:PGPASSWORD) { Fail 'PGPASSWORD environment variable is required (its value is never echoed)' }
if (-not (Test-Path -LiteralPath $PgBin)) { Fail ("PgBin not found: " + $PgBin) }

$psql           = Join-Path $PgBin 'psql.exe'
$pgBasebackup   = Join-Path $PgBin 'pg_basebackup.exe'
$pgDump         = Join-Path $PgBin 'pg_dump.exe'
$pgRestore      = Join-Path $PgBin 'pg_restore.exe'
$pgVerify       = Join-Path $PgBin 'pg_verifybackup.exe'
foreach ($tool in @($psql, $pgBasebackup, $pgDump, $pgRestore)) {
  if (-not (Test-Path -LiteralPath $tool)) { Fail ("required tool missing: " + $tool) }
}

New-Item -ItemType Directory -Path $VaultDir -Force | Out-Null
$driveLetter = (Split-Path -Qualifier $VaultDir).TrimEnd(':')
$freeBeforeGb = [math]::Round((Get-PSDrive $driveLetter).Free / 1GB, 2)
if ($freeBeforeGb -lt $MinFreeGb) { Fail ("free space on " + $driveLetter + ": is " + $freeBeforeGb + " GB (< guardrail " + $MinFreeGb + " GB)") }

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$bidChars = 1..12 | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) }
$bid = 'bkp-' + (-join $bidChars)
$physicalDir = Join-Path $VaultDir ("basebackup_" + $bid)
$logicalDump = Join-Path $VaultDir ("vcos4-logical-" + $ts + ".dump")
$metadataPath = Join-Path $VaultDir ("phase1_backup_metadata_" + $ts + ".json")
$preCountsPath = Join-Path $VaultDir ("phase1_rowcounts_" + $ts + "_pre.json")
$postCountsPath = Join-Path $VaultDir ("phase1_rowcounts_" + $ts + "_post.json")
$countsSqlPath = Join-Path $env:TEMP ("vcos_phase1_counts_" + [guid]::NewGuid().ToString('N') + ".sql")

Write-Output ("phase1-backup: database=vcos4 backup_id=" + $bid + " ts=" + $ts + " vault=" + $VaultDir)
Write-Output ("phase1-backup: free space before = " + $freeBeforeGb + " GB")

$identityDb = Invoke-Scalar 'vcos4' "SELECT 'current_database=' || current_database()"
if ($identityDb -ne 'current_database=vcos4') { Fail ("connected database is not vcos4: " + $identityDb) }

$serverVersion = Invoke-Scalar 'vcos4' "SELECT version()"
$systemIdentifier = Invoke-Scalar 'vcos4' "SELECT system_identifier::text FROM pg_control_system()"
$alembicVersion = Invoke-Scalar 'vcos4' "SELECT COALESCE((SELECT version_num FROM alembic_version), 'NONE')"
$publicTables = [int](Invoke-Scalar 'vcos4' "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
$dbSizeBytes = [long](Invoke-Scalar 'vcos4' "SELECT pg_database_size('vcos4')")

$archivedBefore = [long](Invoke-Scalar 'postgres' "SELECT archived_count FROM pg_stat_archiver")
$failedBefore = [long](Invoke-Scalar 'postgres' "SELECT failed_count FROM pg_stat_archiver")
$lastWalBefore = Invoke-Scalar 'postgres' "SELECT COALESCE(last_archived_wal, 'none') FROM pg_stat_archiver"
$archiveMode = Invoke-Scalar 'postgres' "SHOW archive_mode"
Write-Output ("phase1-backup: archive_mode=" + $archiveMode + " archived=" + $archivedBefore + " failed=" + $failedBefore + " last_wal=" + $lastWalBefore)

Set-Content -LiteralPath $countsSqlPath -Encoding ASCII -Value @'
SELECT tablename AS tbl, COALESCE((xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM public.%I', tablename), false, true, '')))[1]::text::bigint, -1) AS exact_rows
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
'@

function Get-RowCounts([string]$db) {
  $out = & $psql -U $PgUser -h $PgHost -p $PgPort -d $db -t -A -F "|" -v ON_ERROR_STOP=1 -f $countsSqlPath 2>&1
  if ($LASTEXITCODE -ne 0) { Fail ("rowcount snapshot failed on " + $db + ": " + (($out | Out-String).Trim())) }
  $map = [ordered]@{}
  foreach ($line in @($out)) {
    $s = ([string]$line).Trim()
    if (-not $s) { continue }
    $i = $s.LastIndexOf('|')
    if ($i -lt 1) { continue }
    $map[$s.Substring(0, $i)] = [long]$s.Substring($i + 1)
  }
  return $map
}

Write-Output 'phase1-backup: [1/6] pre-dump rowcount snapshot (exact counts, all public tables)'
$walBeforeDump = Invoke-Scalar 'vcos4' 'SELECT pg_current_wal_lsn()'
$preCounts = Get-RowCounts 'vcos4'
$preCountsDoc = [ordered]@{
  database = 'vcos4'; phase = 'pre-dump'; captured_at = (Get-Date).ToString('o'); wal_lsn = $walBeforeDump; table_count = $preCounts.Count; counts = $preCounts
}
$preCountsDoc | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $preCountsPath -Encoding UTF8
Write-Output ("phase1-backup: pre-dump counts captured for " + $preCounts.Count + " tables -> " + $preCountsPath)

Write-Output ('phase1-backup: [2/6] logical dump (pg_dump -Fc) ' + $logicalDump)
$dumpStarted = Get-Date
$dumpOut = & $pgDump -d $Database -h $PgHost -p $PgPort -U $PgUser -Fc -Z 6 -f $logicalDump 2>&1 | Out-String
$dumpExit = $LASTEXITCODE
$dumpFinished = Get-Date
if ($dumpExit -ne 0) { Fail ("pg_dump failed (exit " + $dumpExit + "): " + $dumpOut.Trim()) }
if (-not (Test-Path -LiteralPath $logicalDump)) { Fail 'pg_dump reported success but dump file is missing' }
$dumpSize = (Get-Item -LiteralPath $logicalDump).Length
if ($dumpSize -lt 1048576) { Fail ("dump file suspiciously small: " + $dumpSize + " bytes") }

$walAfterDump = Invoke-Scalar 'vcos4' 'SELECT pg_current_wal_lsn()'
$postCounts = Get-RowCounts 'vcos4'
$postCountsDoc = [ordered]@{
  database = 'vcos4'; phase = 'post-dump'; captured_at = (Get-Date).ToString('o'); wal_lsn = $walAfterDump; table_count = $postCounts.Count; counts = $postCounts
}
$postCountsDoc | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $postCountsPath -Encoding UTF8

$dumpListOut = & $pgRestore --list $logicalDump 2>&1 | Out-String
$listExit = $LASTEXITCODE
if ($listExit -ne 0) { Fail ("pg_restore --list failed on fresh dump (invalid artifact): " + $dumpListOut.Trim()) }
$entryCount = @(($dumpListOut -split "`n") | Where-Object { $_ -match '^\d+;' }).Count
if ($entryCount -lt 1) { Fail 'fresh dump contains no restorable entries' }
$dumpSha = Get-Sha256 $logicalDump
Write-Output ("phase1-backup: dump size=" + [math]::Round($dumpSize / 1MB, 2) + " MB entries=" + $entryCount + " sha256=" + $dumpSha)

Write-Output ('phase1-backup: [3/6] physical base backup (pg_basebackup -F tar) ' + $physicalDir)
$physStarted = Get-Date
$physOut = & $pgBasebackup -D $physicalDir -F tar -z -X fetch -c fast -h $PgHost -p $PgPort -U $PgUser -P 2>&1 | Out-String
$physExit = $LASTEXITCODE
$physFinished = Get-Date
if ($physExit -ne 0) { Fail ("pg_basebackup failed (exit " + $physExit + "): " + $physOut.Trim()) }
$walStart = ([regex]::Match($physOut, 'write-ahead log start point: ([0-9A-F]+/[0-9A-F]+)')).Groups[1].Value
$walEnd = ([regex]::Match($physOut, 'write-ahead log end point: ([0-9A-F]+/[0-9A-F]+)')).Groups[1].Value
if (-not $walStart -or -not $walEnd) { Write-Output 'phase1-backup: NOTE could not parse WAL start/end LSN from pg_basebackup output' }

$manifestPath = Join-Path $physicalDir 'backup_manifest'
if (-not (Test-Path -LiteralPath $manifestPath)) { Fail 'backup_manifest missing from physical backup (unverifiable artifact)' }

$physicalFiles = @()
foreach ($f in (Get-ChildItem -LiteralPath $physicalDir -File | Sort-Object Name)) {
  $physicalFiles += [ordered]@{
    name = $f.Name; size_bytes = $f.Length; sha256 = (Get-Sha256 $f.FullName)
  }
}

$verifyExit = $null
$verifyNote = 'not-run'
if (Test-Path -LiteralPath $pgVerify) {
  Write-Output 'phase1-backup: [4/6] pg_verifybackup on physical backup'
  $verifyOut = & $pgVerify $physicalDir 2>&1 | Out-String
  $verifyExit = $LASTEXITCODE
  if ($verifyExit -ne 0) {
    if ($verifyOut -match 'tar') {
      $verifyNote = 'pg_verifybackup does not support this artifact layout (tar); falling back to tarball integrity scan'
      Write-Output ('phase1-backup: NOTE ' + $verifyNote)
    } else {
      Fail ("pg_verifybackup failed: " + $verifyOut.Trim())
    }
  } else {
    $verifyNote = 'pg_verifybackup passed'
    Write-Output 'phase1-backup: pg_verifybackup passed'
  }
} else {
  $verifyNote = 'pg_verifybackup binary not found'
}

Write-Output 'phase1-backup: [5/6] tarball integrity scan (gzip/tar read-through)'
foreach ($tarball in (Get-ChildItem -LiteralPath $physicalDir -Filter '*.tar.gz' -File)) {
  & tar.exe -tzf $tarball.FullName > $null 2>&1
  if ($LASTEXITCODE -ne 0) { Fail ("tarball integrity scan failed: " + $tarball.Name) }
}
Write-Output 'phase1-backup: all tarballs read through cleanly'

$archivedAfter = [long](Invoke-Scalar 'postgres' "SELECT archived_count FROM pg_stat_archiver")
$failedAfter = [long](Invoke-Scalar 'postgres' "SELECT failed_count FROM pg_stat_archiver")
$lastWalAfter = Invoke-Scalar 'postgres' "SELECT COALESCE(last_archived_wal, 'none') FROM pg_stat_archiver"
$freeAfterGb = [math]::Round((Get-PSDrive $driveLetter).Free / 1GB, 2)
$warnings = @()
if ($failedAfter -gt $failedBefore) { $warnings += ("WAL archiver failed_count increased during backup: " + $failedBefore + " -> " + $failedAfter) }
if ($archiveMode -ne 'on') { $warnings += 'archive_mode is not on' }

$toolVersions = [ordered]@{
  pg_basebackup = ((& $pgBasebackup --version) | Out-String).Trim()
  pg_dump = ((& $pgDump --version) | Out-String).Trim()
  pg_verifybackup = if (Test-Path -LiteralPath $pgVerify) { ((& $pgVerify --version) | Out-String).Trim() } else { 'missing' }
  psql = ((& $psql --version) | Out-String).Trim()
}

$metadata = [ordered]@{
  phase = 1
  kind = 'vcos4-dr-phase1-backup'
  generated_at = (Get-Date).ToString('o')
  host = $env:COMPUTERNAME
  database = 'vcos4'
  identity = [ordered]@{
    server_version = $serverVersion
    system_identifier = $systemIdentifier
    alembic_version = $alembicVersion
    public_tables = $publicTables
    database_size_bytes = $dbSizeBytes
  }
  physical = [ordered]@{
    backup_id = $bid
    dir = $physicalDir
    files = $physicalFiles
    wal_start_lsn = $walStart
    wal_end_lsn = $walEnd
    started_at = $physStarted.ToString('o')
    finished_at = $physFinished.ToString('o')
    verify_exit = $verifyExit
    verify_note = $verifyNote
    tarball_integrity = 'ok'
  }
  logical = [ordered]@{
    path = $logicalDump
    size_bytes = $dumpSize
    sha256 = $dumpSha
    pg_restore_list_entries = $entryCount
    started_at = $dumpStarted.ToString('o')
    finished_at = $dumpFinished.ToString('o')
    wal_lsn_before_dump = $walBeforeDump
    wal_lsn_after_dump = $walAfterDump
  }
  rowcounts = [ordered]@{
    tables = $postCounts.Count
    baseline_pre_path = $preCountsPath
    baseline_post_path = $postCountsPath
    baseline_pre_sha256 = (Get-Sha256 $preCountsPath)
    baseline_post_sha256 = (Get-Sha256 $postCountsPath)
  }
  archiver = [ordered]@{
    archive_mode = $archiveMode
    before = [ordered]@{ archived_count = $archivedBefore; failed_count = $failedBefore; last_archived_wal = $lastWalBefore }
    after = [ordered]@{ archived_count = $archivedAfter; failed_count = $failedAfter; last_archived_wal = $lastWalAfter }
  }
  disk = [ordered]@{ free_gb_before = $freeBeforeGb; free_gb_after = $freeAfterGb; vault = $VaultDir }
  tools = $toolVersions
  warnings = $warnings
}
$metadata | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $metadataPath -Encoding UTF8

Write-Output 'phase1-backup: [6/6] metadata written'
foreach ($w in $warnings) { Write-Output ("phase1-backup: WARNING " + $w) }
Write-Output ("phase1-backup: OK backup_id=" + $bid + " physical=" + $physicalDir + " logical=" + $logicalDump)
Write-Output ("phase1-backup: metadata=" + $metadataPath)
Write-Output ("phase1-backup: free space after = " + $freeAfterGb + " GB")
exit 0
