# SSD Weread keeper supervisor
# Keeps exactly one "node keeper.mjs watch" alive; restarts it within 60s if it dies.
# Started at logon by watch-supervisor.vbs (no console window).
$ErrorActionPreference = 'Continue'
$here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$data  = Join-Path $here 'data'
$log   = Join-Path $data 'supervisor.log'
$pidFile = Join-Path $data 'supervisor.pid'
$stopFile = Join-Path $data 'STOP'

New-Item -ItemType Directory -Force -Path $data | Out-Null

function Log($msg) {
  $line = (Get-Date -Format 'yyyy/MM/dd HH:mm:ss') + '  ' + $msg
  try { Add-Content -Path $log -Value $line -Encoding UTF8 } catch { }
}

# single instance
if (Test-Path $pidFile) {
  $old = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
    Log ("another supervisor is running (pid=" + $old + "), this one exits")
    exit 0
  }
}
$PID | Out-File -FilePath $pidFile -Encoding Ascii
if (Test-Path $stopFile) { Remove-Item $stopFile -Force -ErrorAction SilentlyContinue }

function KeeperCount {
  $n = -1
  try {
    $procs = Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction Stop
    $n = @($procs | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('keeper.mjs') }).Count
  } catch {
    try {
      $n = @(tasklist /FI "IMAGENAME eq node.exe" 2>$null | Select-String 'node.exe').Count
    } catch { $n = -1 }
  }
  return $n
}

Log ("supervisor start (pid=" + $PID + ")")
$started = 0

while ($true) {
  if (Test-Path $stopFile) {
    Log "STOP file found, supervisor exits (keeper is left running on purpose)"
    break
  }
  $n = KeeperCount
  if ($n -lt 1) {
    Log ("keeper not running (count=" + $n + "), starting it")
    try {
      Start-Process -FilePath (Join-Path $here 'run-watch.cmd') -WorkingDirectory $here -WindowStyle Hidden | Out-Null
      $started = $started + 1
      Start-Sleep -Seconds 20
      $after = KeeperCount
      Log ("started, keeper count now = " + $after + " (starts so far: " + $started + ")")
    } catch {
      Log ("start failed: " + $_.Exception.Message)
    }
  } else {
    if (($started -gt 0) -and (Get-Random -Maximum 10) -eq 0) { Log ("keeper ok (count=" + $n + ")") }
  }
  Start-Sleep -Seconds 60
}

Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
