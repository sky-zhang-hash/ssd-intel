# Restart the WeRead keeper watcher (ASCII only - AGENTS.md 9.1)
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "============================================"
Write-Host " restart watcher (no QR scan needed)"
Write-Host "============================================"

function Count-Keepers {
    try {
        return @(Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction Stop |
                 Where-Object { $_.CommandLine -like '*keeper.mjs*' }).Count
    } catch { return -1 }
}

Write-Host "[1/3] stopping old keeper processes ..."
$before = Count-Keepers
Write-Host "      found before: $before"
try {
    Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -like '*keeper.mjs*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {
    Write-Host "      (WMI blocked, fallback: taskkill /F /IM node.exe)"
    taskkill /F /IM node.exe 2>$null | Out-Null
}
Start-Sleep -Seconds 2
Write-Host "      found after kill: $(Count-Keepers)"

Write-Host "[2/3] starting watcher ..."
$runner = Join-Path $here 'run-watch.cmd'
if (-not (Test-Path $runner)) { Write-Host "      [x] missing: $runner"; pause; exit 1 }
Start-Process -FilePath $runner -WorkingDirectory $here -WindowStyle Minimized
Start-Sleep -Seconds 8

$after = Count-Keepers
Write-Host "      keeper processes now: $after"

Write-Host "[3/3] last lines of data\keeper.log:"
Write-Host "------------------------------------------"
$log = Join-Path $here 'data\keeper.log'
if (Test-Path $log) { Get-Content -Path $log -Encoding UTF8 -Tail 10 } else { Write-Host "(no keeper.log)" }
Write-Host "------------------------------------------"
if ($after -ge 1) {
    Write-Host "RESULT: OK - a keeper process is running (see the 'watch start' line above)."
} else {
    Write-Host "RESULT: FAILED - no keeper process. Copy the lines above and send them to me."
    Write-Host "Try: close all Edge windows, then run this again."
}
Read-Host "Press Enter to close"
