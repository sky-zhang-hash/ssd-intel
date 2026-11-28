# Register the supervisor to start automatically at logon (no admin needed:
# we put a shortcut in the current user's Startup folder).
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$vbs  = Join-Path $here 'watch-supervisor.vbs'
$startup = [Environment]::GetFolderPath('StartUp')
$lnk  = Join-Path $startup 'SSD-Weread-Supervisor.lnk'

if (-not (Test-Path $vbs)) {
  Write-Host "[x] missing file: $vbs"
  exit 1
}

try {
  $ws = New-Object -ComObject WScript.Shell
  $s  = $ws.CreateShortcut($lnk)
  $s.TargetPath = 'wscript.exe'
  $s.Arguments  = '"' + $vbs + '"'
  $s.WorkingDirectory = $here
  $s.WindowStyle = 7
  $s.Description = 'Keep the WeChat-Reading login fresh for the SSD daily report'
  $s.Save()
  Write-Host "[ok] autostart shortcut created:"
  Write-Host "     $lnk"
} catch {
  Write-Host ("[x] could not create shortcut: " + $_.Exception.Message)
  exit 1
}

# disable older scheduled tasks so they cannot start a second keeper
# (two keepers fight over the same browser profile)
foreach ($t in @('SSD-Weread-Watch', 'SSD-Weread-Keeper')) {
  try {
    $task = Get-ScheduledTask -TaskName $t -ErrorAction Stop
    Disable-ScheduledTask -TaskName $t -ErrorAction Stop | Out-Null
    Write-Host ("[ok] disabled legacy scheduled task: " + $t)
  } catch { }
}

# start it right now, so the user does not have to log off / on
try {
  Start-Process -FilePath 'wscript.exe' -ArgumentList ('"' + $vbs + '"') -WorkingDirectory $here
  Write-Host "[ok] supervisor started in background"
} catch {
  Write-Host ("[warn] started? " + $_.Exception.Message)
}

Start-Sleep -Seconds 3
$pidFile = Join-Path $here 'data\supervisor.pid'
if (Test-Path $pidFile) {
  $p = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($p -and (Get-Process -Id $p -ErrorAction SilentlyContinue)) {
    Write-Host ("RESULT: OK   supervisor pid = " + $p)
  } else {
    Write-Host "RESULT: UNKNOWN   supervisor.pid exists but process not found yet"
  }
} else {
  Write-Host "RESULT: UNKNOWN   no supervisor.pid yet (check data\supervisor.log)"
}
Write-Host ""
Write-Host "Log: $(Join-Path $here 'data\supervisor.log')"
Write-Host "Stop: double-click stop-autostart.cmd"
