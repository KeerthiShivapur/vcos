$scriptPath = "C:\VCOS-Backups\archive_wal_final.ps1"
$scriptContent = Get-Content $scriptPath -Raw
$errors = $null
$tokens = [System.Management.Automation.PSParser]::Tokenize($scriptContent, [ref]$null)
$errors = $tokens | Where-Object { $_.Type -eq 'Error' }
if ($errors.Count -eq 0) {
    Write-Host "SYNTAX OK"
} else {
    $errors | ForEach-Object { Write-Host "ERROR: $($_.Message) at line $($_.StartLine)" }
}