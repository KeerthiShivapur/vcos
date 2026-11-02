[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$MetadataPath,
  [Parameter(Mandatory = $true)][string]$Target,
  [string]$PgBin = 'C:\Program Files\PostgreSQL\18\bin',
  [string]$PgHost = '127.0.0.1',
  [int]$PgPort = 5432,
  [string]$PgUser = 'postgres',
  [string]$OutDir = ''
)

$ErrorActionPreference = 'Stop'

function Fail([string]$message) {
  Write-Output ("PHASE1-RESTORE-FAILED: " + $message)
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

if ($Target -notmatch '^vcos4_recovery_verify_[0-9]{8}_[0-9]{6}$') {
  Fail ("restore-isolation guard: target database must match vcos4_recovery_verify_<yyyymmdd>_<hhmmss> (got '" + $Target + "')")
}
if (@('vcos4', 'postgres', 'template0', 'template1', 'vcos_test', 'vcos_test_matrix') -contains $Target) {
  Fail ("restore-isolation guard: protected database name rejected: " + $Target)
}
if (-not $env:PGPASSWORD) { Fail 'PGPASSWORD environment variable is required (its value is never echoed)' }
if (-not (Test-Path -LiteralPath $MetadataPath)) { Fail ("metadata manifest not found: " + $MetadataPath) }
if (-not (Test-Path -LiteralPath $PgBin)) { Fail ("PgBin not found: " + $PgBin) }

$psql      = Join-Path $PgBin 'psql.exe'
$pgRestore = Join-Path $PgBin 'pg_restore.exe'
$createdb  = Join-Path $PgBin 'createdb.exe'
foreach ($tool in @($psql, $pgRestore, $createdb)) {
  if (-not (Test-Path -LiteralPath $tool)) { Fail ("required tool missing: " + $tool) }
}

$metadata = Get-Content -LiteralPath $MetadataPath -Raw | ConvertFrom-Json
if ($metadata.database -ne 'vcos4') { Fail ("metadata manifest is not for vcos4 (got '" + $metadata.database + "')") }

$dumpPath = [string]$metadata.logical.path
if (-not (Test-Path -LiteralPath $dumpPath)) { Fail ("logical dump missing: " + $dumpPath) }
$dumpShaNow = Get-Sha256 $dumpPath
if ($dumpShaNow -ne $metadata.logical.sha256) {
  Fail ("logical dump sha256 mismatch: manifest=" + $metadata.logical.sha256 + " actual=" + $dumpShaNow + " (corrupt, modified or incomplete backup - refusing)")
}

$listOut = & $pgRestore --list $dumpPath 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { Fail ("pg_restore --list failed on dump: invalid backup artifact - " + $listOut.Trim()) }
$entryCount = @(($listOut -split "`n") | Where-Object { $_ -match '^\d+;' }).Count
if ($entryCount -ne [int]$metadata.logical.pg_restore_list_entries) {
  Fail ("dump manifest mismatch: manifest entries=" + $metadata.logical.pg_restore_list_entries + " actual=" + $entryCount + " (incomplete backup - refusing)")
}
Write-Output ("phase1-restore: dump integrity verified (sha256 + pg_restore --list " + $entryCount + " entries)")

$targetExists = [int](Invoke-Scalar 'postgres' ("SELECT count(*) FROM pg_database WHERE datname = '" + $Target + "'"))
if ($targetExists -gt 0) { Fail ("target database already exists: " + $Target + " (refusing to overwrite; drop it explicitly if intended)") }

$preBaseline = Get-Content -LiteralPath ([string]$metadata.rowcounts.baseline_pre_path) -Raw | ConvertFrom-Json
$postBaseline = Get-Content -LiteralPath ([string]$metadata.rowcounts.baseline_post_path) -Raw | ConvertFrom-Json
if ($preBaseline.database -ne 'vcos4' -or $postBaseline.database -ne 'vcos4') { Fail 'rowcount baselines are not for vcos4' }

$sourceTables = [int](Invoke-Scalar 'vcos4' "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
$sourceFks = [int](Invoke-Scalar 'vcos4' "SELECT count(*) FROM pg_constraint WHERE contype = 'f' AND connamespace = 'public'::regnamespace")
$sourceAlembic = Invoke-Scalar 'vcos4' "SELECT COALESCE((SELECT version_num FROM alembic_version), 'NONE')"

Write-Output ("phase1-restore: creating isolated target database " + $Target)
& $createdb -h $PgHost -p $PgPort -U $PgUser $Target 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { Fail ("createdb failed for " + $Target) }

Write-Output 'phase1-restore: running pg_restore (strict, --exit-on-error)'
$restoreStarted = Get-Date
$restoreLogPath = Join-Path $env:TEMP ("vcos_phase1_restore_" + $Target + ".log")
& $pgRestore -d $Target -h $PgHost -p $PgPort -U $PgUser --no-owner --no-privileges --exit-on-error $dumpPath > $restoreLogPath 2>&1
$restoreExit = $LASTEXITCODE
$restoreFinished = Get-Date
if ($restoreExit -ne 0) {
  $tail = (Get-Content -LiteralPath $restoreLogPath -Tail 20) -join ' | '
  Fail ("pg_restore failed (exit " + $restoreExit + "); partial target left in place for inspection: " + $Target + " :: " + $tail)
}
Write-Output ("phase1-restore: pg_restore completed in " + [math]::Round(($restoreFinished - $restoreStarted).TotalSeconds, 1) + "s")

$countsSqlPath = Join-Path $env:TEMP ("vcos_phase1_counts_" + [guid]::NewGuid().ToString('N') + ".sql")
Set-Content -LiteralPath $countsSqlPath -Encoding ASCII -Value @'
SELECT tablename AS tbl, COALESCE((xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM public.%I', tablename), false, true, '')))[1]::text::bigint, -1) AS exact_rows
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
'@

function Get-RowCounts([string]$db) {
  $out = & $psql -U $PgUser -h $PgHost -p $PgPort -d $db -t -A -F "|" -v ON_ERROR_STOP=1 -f $countsSqlPath 2>&1
  if ($LASTEXITCODE -ne 0) { Fail ("rowcount snapshot failed on " + $db + ": " + (($out | Out-String).Trim())) }
  $map = @{}
  foreach ($line in @($out)) {
    $s = ([string]$line).Trim()
    if (-not $s) { continue }
    $i = $s.LastIndexOf('|')
    if ($i -lt 1) { continue }
    $map[$s.Substring(0, $i)] = [long]$s.Substring($i + 1)
  }
  return $map
}

Write-Output 'phase1-restore: comparing exact rowcounts (restored copy vs backup-time baselines)'
$restoredCounts = Get-RowCounts $Target
$postMap = @{}
foreach ($p in $postBaseline.counts.PSObject.Properties) { $postMap[$p.Name] = [long]$p.Value }
$preMap = @{}
foreach ($p in $preBaseline.counts.PSObject.Properties) { $preMap[$p.Name] = [long]$p.Value }

$targetTables = [int](Invoke-Scalar $Target "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
$targetFks = [int](Invoke-Scalar $Target "SELECT count(*) FROM pg_constraint WHERE contype = 'f' AND connamespace = 'public'::regnamespace")
$targetAlembic = Invoke-Scalar $Target "SELECT COALESCE((SELECT version_num FROM alembic_version), 'NONE')"

$equal = 0; $driftExplained = 0; $mismatches = @()
foreach ($key in $postMap.Keys) {
  $base = $postMap[$key]
  if (-not $restoredCounts.ContainsKey($key)) {
    $mismatches += [ordered]@{ table = $key; baseline_post = $base; baseline_pre = if ($preMap.ContainsKey($key)) { $preMap[$key] } else { $null }; restored = $null; live_now = $null; classification = 'missing-table-in-restored' }
    continue
  }
  $restoredVal = [long]$restoredCounts[$key]
  if ($restoredVal -eq $base) { $equal++; continue }
  if ($preMap.ContainsKey($key) -and $restoredVal -eq $preMap[$key] -and $preMap[$key] -ne $base) {
    $driftExplained++
    Write-Output ("phase1-restore: drift-explained (writes landed between pre/post snapshots) " + $key + " pre=" + $preMap[$key] + " post=" + $base + " restored=" + $restoredVal)
    continue
  }
  $liveNow = [long](Invoke-Scalar 'vcos4' ("SELECT count(*) FROM public." + $key))
  $mismatches += [ordered]@{ table = $key; baseline_post = $base; baseline_pre = if ($preMap.ContainsKey($key)) { $preMap[$key] } else { $null }; restored = $restoredVal; live_now = $liveNow; classification = 'unexplained' }
}
$extraTables = @($restoredCounts.Keys | Where-Object { -not $postMap.ContainsKey($_) })
foreach ($key in $extraTables) {
  $mismatches += [ordered]@{ table = $key; baseline_post = $null; baseline_pre = $null; restored = [long]$restoredCounts[$key]; live_now = $null; classification = 'extra-table-in-restored' }
}

$schemaParity = ($sourceTables -eq $targetTables) -and ($sourceFks -eq $targetFks) -and ($sourceAlembic -eq $targetAlembic)
$verdict = 'PASS'
if (-not $schemaParity -or $mismatches.Count -gt 0) { $verdict = 'FAIL' }

if (-not $OutDir) { $OutDir = Split-Path -Parent (Resolve-Path -LiteralPath $MetadataPath) }
$resultsPath = Join-Path $OutDir ("phase1_restore_verify_" + $Target + ".json")
$results = [ordered]@{
  phase = 1
  kind = 'vcos4-dr-phase1-restore-verify'
  generated_at = (Get-Date).ToString('o')
  target_database = $Target
  metadata_path = (Resolve-Path -LiteralPath $MetadataPath).Path
  metadata_sha256 = (Get-Sha256 $MetadataPath)
  dump_path = $dumpPath
  dump_sha256_verified = $true
  restore_exit = $restoreExit
  restore_seconds = [math]::Round(($restoreFinished - $restoreStarted).TotalSeconds, 1)
  schema_parity = [ordered]@{
    source_tables = $sourceTables; target_tables = $targetTables
    source_fks = $sourceFks; target_fks = $targetFks
    source_alembic = $sourceAlembic; target_alembic = $targetAlembic
    parity = $schemaParity
  }
  rowcounts = [ordered]@{
    compared_tables = $postMap.Count
    equal = $equal
    drift_explained = $driftExplained
    mismatches = $mismatches
  }
  verdict = $verdict
}
$results | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $resultsPath -Encoding UTF8

Write-Output ("phase1-restore: tables source=" + $sourceTables + " target=" + $targetTables + " | fks source=" + $sourceFks + " target=" + $targetFks + " | alembic source=" + $sourceAlembic + " target=" + $targetAlembic)
Write-Output ("phase1-restore: rowcounts compared=" + $postMap.Count + " equal=" + $equal + " drift_explained=" + $driftExplained + " mismatches=" + $mismatches.Count)
Write-Output ("phase1-restore: results=" + $resultsPath)
Write-Output ("phase1-restore: VERDICT=" + $verdict + " target=" + $Target)
if ($verdict -ne 'PASS') {
  foreach ($m in $mismatches) { Write-Output ("phase1-restore: MISMATCH " + ($m | ConvertTo-Json -Compress)) }
  exit 1
}
exit 0
