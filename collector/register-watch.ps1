# Register a resident "watch" task: keeps the WeRead session warm.
# Runs at logon, restarts if it dies, survives reboot.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $here 'run-watch.cmd'
$taskName = 'SSD-Weread-Watch'

if (-not (Test-Path $runner)) { Write-Host "[x] missing $runner" -ForegroundColor Red; exit 1 }

$cmdExe = Join-Path $env:SystemRoot 'System32\cmd.exe'
$action = New-ScheduledTaskAction -Execute $cmdExe -Argument ('/c "' + $runner + '"') -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew

try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
        -Description 'Keep the WeRead web session warm for SSD Intel report' -Force | Out-Null
} catch {
    Write-Host "[x] failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host '    Run as Administrator.' -ForegroundColor Yellow
    exit 1
}

$t = Get-ScheduledTask -TaskName $taskName
Write-Host "[ok] task created: $($t.TaskName) / state: $($t.State)" -ForegroundColor Green
Write-Host '     it starts at next logon; to start now, run:'
Write-Host "  Start-ScheduledTask -TaskName '$taskName'"
Write-Host ''
Write-Host 'Watch its log with:  Get-Content ..\data\keeper.log -Encoding UTF8 -Tail 20 -Wait'
