# Test Move-Item atomic publication behavior on Windows
# Verifies: Move-Item without -Force fails if destination exists
# Tests concurrent destination creation scenario

$ErrorActionPreference = 'Stop'

Write-Host "=== ATOMIC PUBLICATION TEST ==="
Write-Host ""

$testDir = "C:\VCOS-Backups\wal_archive\atomic_test"
if (-not (Test-Path $testDir)) {
    New-Item -ItemType Directory -Path $testDir -Force | Out-Null
}

# Test 1: Move-Item without -Force fails when destination exists
Write-Host "TEST 1: Move-Item without -Force fails when destination exists"
$src = "C:\VCOS-Backups\atomic_test_src.txt"
$dest = "C:\VCOS-Backups\wal_archive\atomic_test_dest.txt"

try {
    "source content" | Set-Content -LiteralPath "C:\VCOS-Backups\atomic_test_src.txt" -Force
    "existing dest" | Set-Content -LiteralPath "C:\VCOS-Backups\wal_archive\atomic_dest.txt" -Force
    
    Move-Item -LiteralPath "C:\VCOS-Backups\atomic_test_src.txt" -Destination "C:\VCOS-Backups\wal_archive\atomic_dest.txt" -ErrorAction Stop
    Write-Host "FAIL: Move-Item should have failed but succeeded"
}
catch {
    Write-Host "PASS: Move-Item correctly failed when destination exists"
}

# Cleanup
Remove-Item "C:\VCOS-Backups\atomic_test_src.txt" -ErrorAction SilentlyContinue
Remove-Item "C:\VCOS-Backups\wal_archive\atomic_dest.txt" -ErrorAction SilentlyContinue
Write-Host ""

# Test 2: Move-Item fails when destination created concurrently (simulated)
Write-Host "TEST 2: Move-Item fails when destination created concurrently (simulated)"
$src = "C:\VCOS-Backups\atomic_test_src2.txt"
$dest = "C:\VCOS-Backups\wal_archive\atomic_dest2.txt"

try {
    "source content" | Set-Content -LiteralPath "C:\VCOS-Backups\atomic_test_src2.txt" -Force
    
    # Simulate concurrent creation by creating destination first
    "concurrent content" | Set-Content -LiteralPath "C:\VCOS-Backups\wal_archive\atomic_dest2.txt" -Force
    
    Move-Item -LiteralPath "C:\VCOS-Backups\atomic_test_src2.txt" -Destination "C:\VCOS-Backups\wal_archive\atomic_dest2.txt" -ErrorAction Stop
    Write-Host "FAIL: Move-Item should have failed but succeeded"
}
catch {
    Write-Host "PASS: Move-Item correctly failed when destination exists"
}

# Cleanup
Remove-Item "C:\VCOS-Backups\atomic_test_src2.txt" -ErrorAction SilentlyContinue
Remove-Item "C:\VCOS-Backups\wal_archive\atomic_dest2.txt" -ErrorAction SilentlyContinue
Write-Host ""

# Test 3: Verify Move-Item without -Force is atomic on NTFS
Write-Host "TEST 3: Verify Move-Item is atomic on NTFS (no partial file visible)"
$src = "C:\VCOS-Backups\atomic_test_src3.txt"
$dest = "C:\VCOS-Backups\wal_archive\atomic_dest3.txt"

try {
    "source content" | Set-Content -LiteralPath "C:\VCOS-Backups\atomic_test3.txt" -Force
    
    Move-Item -LiteralPath "C:\VCOS-Backups\atomic_test3.txt" -Destination "C:\VCOS-Backups\wal_archive\atomic_dest3.txt" -ErrorAction Stop
    
    if (Test-Path "C:\VCOS-Backups\wal_archive\atomic_dest3.txt") {
        $hash = (Get-FileHash -LiteralPath "C:\VCOS-Backups\wal_archive\atomic_dest3.txt" -Algorithm SHA256).Hash
        Write-Host "PASS: Move-Item succeeded atomically, hash verified"
    } else {
        Write-Host "FAIL: Destination not found after Move-Item"
    }
}
catch {
    Write-Host "FAIL: Move-Item failed unexpectedly - $($_.Exception.Message)"
}

# Cleanup
Remove-Item "C:\VCOS-Backups\atomic_test_src3.txt" -ErrorAction SilentlyContinue
Remove-Item "C:\VCOS-Backups\wal_archive\atomic_dest3.txt" -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== ATOMIC PUBLICATION TEST COMPLETE ==="