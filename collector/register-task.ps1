# Register the SSD-Weread-Keeper scheduled task (runs every 12 hours).
# ASCII only on purpose: cmd.exe reads .cmd in the ANSI codepage, and mixing
# UTF-8 with chcp 65001 makes it parse the rest of the file wrongly.
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$nodeDir = Join-Path $here 'node'
$taskName = 'SSD-Weread-Keeper'

if (-not (Test-Path $nodeDir)) {
    Write-Host "[x] not found: $nodeDir" -ForegroundColor Red
    exit 1
}

$node = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $node) {
    Write-Host '[x] node.exe not found in PATH. Install Node.js 20+ first.' -ForegroundColor Red
    exit 1
}

Write-Host "node : $node"
Write-Host "work : $nodeDir"

$action = New-ScheduledTaskAction -Execute $node -Argument 'keeper.mjs once' -WorkingDirectory $nodeDir
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Hours 12)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Settings $settings -Description 'Refresh the WeRead cookie used by SSD Intel daily report' -Force | Out-Null
} catch {
    Write-Host "[x] Register-ScheduledTask failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host '    Run this file as Administrator.' -ForegroundColor Yellow
    exit 1
}

$t = Get-ScheduledTask -TaskName $taskName
$info = Get-ScheduledTaskInfo -TaskName $taskName
Write-Host ''
Write-Host "[ok] task created: $($t.TaskName) / state: $($t.State)" -ForegroundColor Green
Write-Host "     next run: $($info.NextRunTime)"
Write-Host ''
Write-Host 'Remove it later with:'
Write-Host "  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
