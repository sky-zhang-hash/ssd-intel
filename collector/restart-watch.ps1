# Restart the WeRead keeper watcher (ASCII only - AGENTS.md 9.1)
# v4: start the watcher via WMI Win32_Process (no cmd quoting, returns a PID),
#     then verify by counting keeper processes.
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

function Count-Keepers {
    try {
        return @(Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction Stop |
                 Where-Object { $_.CommandLine -like '*keeper.mjs*' }).Count
    } catch { return -1 }
}
function LogTail([int]$n) {
    $log = Join-Path $here 'data\keeper.log'
    if (Test-Path $log) { Get-Content -Path $log -Encoding UTF8 -Tail $n } else { Write-Host "(no keeper.log)" }
}

Write-Host "============================================"
Write-Host " restart watcher (no QR scan needed)"
Write-Host "============================================"

Write-Host "[1/4] stopping old keeper processes ..."
Write-Host "      before: $(Count-Keepers)"
try {
    Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -like '*keeper.mjs*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {
    Write-Host "      (WMI blocked, fallback: taskkill /F /IM node.exe)"
    taskkill /F /IM node.exe 2>$null | Out-Null
}
Start-Sleep -Seconds 2
Write-Host "      after kill: $(Count-Keepers)"

Write-Host "[2/4] starting watcher via WMI ..."
$runner = Join-Path $here 'run-watch.cmd'
if (-not (Test-Path $runner)) { Write-Host "      [x] missing: $runner"; Read-Host "Enter to close"; exit 1 }
$pid2 = 0
try {
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine      = "cmd.exe /c `"$runner`""
        CurrentDirectory = $here
    } -ErrorAction Stop
    $pid2 = [int]$r.ProcessId
    Write-Host "      launched cmd.exe /c run-watch.cmd  (pid $pid2, returnValue $($r.ReturnValue))"
} catch {
    Write-Host "      [x] WMI create failed: $($_.Exception.Message)"
}
Start-Sleep -Seconds 10

Write-Host "[3/4] verification ..."
$after = Count-Keepers
Write-Host "      keeper processes now: $after"
if ($pid2 -gt 0) {
    $alive = @(Get-Process -Id $pid2 -ErrorAction SilentlyContinue).Count
    Write-Host "      launched cmd pid $pid2 alive: $alive"
}

Write-Host "[4/4] last lines of data\keeper.log:"
Write-Host "------------------------------------------"
LogTail 10
Write-Host "------------------------------------------"
if ($after -ge 1) {
    Write-Host "RESULT: OK - keeper is running. The watcher will log every 15 minutes."
} else {
    Write-Host "RESULT: FAILED - no keeper process."
    Write-Host "Please just double-click run-watch.cmd in this folder and keep the window open."
}
Read-Host "Press Enter to close"
