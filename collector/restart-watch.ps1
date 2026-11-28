# Restart the WeRead keeper watcher (ASCII only on purpose - see AGENTS.md 9.1)
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "============================================"
Write-Host " restart watcher (no QR scan needed)"
Write-Host "============================================"

Write-Host "[1/3] stopping old keeper processes ..."
$killed = 0
try {
    Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -like '*keeper.mjs*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $killed++ }
} catch {
    Write-Host "      (WMI not available, falling back to taskkill /IM node.exe)"
    taskkill /F /IM node.exe 2>$null | Out-Null
}
Write-Host "      stopped: $killed keeper process(es)"

Start-Sleep -Seconds 2

Write-Host "[2/3] starting watcher in background ..."
Start-Process -FilePath "cmd.exe" -ArgumentList '/c','"run-watch.cmd"' -WorkingDirectory $here -WindowStyle Hidden

Start-Sleep -Seconds 6

Write-Host "[3/3] last lines of data\keeper.log:"
Write-Host "------------------------------------------"
$log = Join-Path $here 'data\keeper.log'
if (Test-Path $log) { Get-Content -Path $log -Encoding UTF8 -Tail 8 } else { Write-Host "(no keeper.log yet)" }
Write-Host "------------------------------------------"
Write-Host "OK if the last timestamp is within 15 minutes."
Write-Host "If you see 'profile is already in use', close all Edge windows and run this again."
