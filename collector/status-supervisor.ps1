# One-screen status: is the supervisor alive, is the keeper alive, how fresh is the cookie.
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$data = Join-Path $here 'data'

function Age($path) {
  if (-not (Test-Path $path)) { return 'missing' }
  $m = (Get-Item $path).LastWriteTime
  $min = [int]((Get-Date) - $m).TotalMinutes
  return ($m.ToString('yyyy-MM-dd HH:mm:ss') + ' (' + $min + ' min ago)')
}

Write-Host "== supervisor =="
$pidFile = Join-Path $data 'supervisor.pid'
if (Test-Path $pidFile) {
  $p = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($p -and (Get-Process -Id $p -ErrorAction SilentlyContinue)) { Write-Host ("  running, pid=" + $p) }
  else { Write-Host "  NOT running (stale pid file)" }
} else { Write-Host "  NOT running (no pid file)" }

Write-Host "== keeper =="
$n = -1
try {
  $procs = Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction Stop
  $n = @($procs | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('keeper.mjs') }).Count
} catch { }
Write-Host ("  node keeper.mjs processes: " + $n)

Write-Host "== files =="
Write-Host ("  keeper.log : " + (Age (Join-Path $data 'keeper.log')))
Write-Host ("  cookie.txt : " + (Age (Join-Path $data 'cookie.txt')))
Write-Host ("  supervisor : " + (Age (Join-Path $data 'supervisor.log')))

Write-Host "== autostart =="
$lnk = Join-Path ([Environment]::GetFolderPath('StartUp')) 'SSD-Weread-Supervisor.lnk'
if (Test-Path $lnk) { Write-Host "  shortcut present" } else { Write-Host "  no shortcut (will not start at logon)" }

Write-Host ""
Write-Host "== last 6 log lines =="
$k = Join-Path $data 'keeper.log'
if (Test-Path $k) { Get-Content $k -Encoding UTF8 -Tail 6 | ForEach-Object { Write-Host ("  " + $_) } }
