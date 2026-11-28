# Stop the supervisor and the keeper process, and remove the Startup shortcut.
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$data = Join-Path $here 'data'

# 1) tell the supervisor to exit
New-Item -ItemType Directory -Force -Path $data | Out-Null
Set-Content -Path (Join-Path $data 'STOP') -Value 'stop' -Encoding Ascii

Start-Sleep -Seconds 2

# 2) kill the supervisor if still alive
$pidFile = Join-Path $data 'supervisor.pid'
if (Test-Path $pidFile) {
  $p = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($p -and (Get-Process -Id $p -ErrorAction SilentlyContinue)) {
    Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    Write-Host ("[ok] supervisor stopped (pid=" + $p + ")")
  }
  Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

# 3) kill the keeper (node keeper.mjs watch)
$killed = 0
try {
  $procs = Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction Stop
  foreach ($pr in $procs) {
    if ($pr.CommandLine -and $pr.CommandLine.Contains('keeper.mjs')) {
      Stop-Process -Id $pr.ProcessId -Force -ErrorAction SilentlyContinue
      $killed = $killed + 1
    }
  }
} catch {
  Write-Host ("[warn] could not enumerate node processes: " + $_.Exception.Message)
}
if ($killed -gt 0) { Write-Host ("[ok] keeper stopped (" + $killed + " process)") } else { Write-Host "[ok] no keeper process was running" }

# 4) remove the Startup shortcut
$startup = [Environment]::GetFolderPath('StartUp')
$lnk = Join-Path $startup 'SSD-Weread-Supervisor.lnk'
if (Test-Path $lnk) { Remove-Item $lnk -Force -ErrorAction SilentlyContinue; Write-Host "[ok] autostart shortcut removed" }

Write-Host ""
Write-Host "RESULT: STOPPED - nothing will start at logon any more."
