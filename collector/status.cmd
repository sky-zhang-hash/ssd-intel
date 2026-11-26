@echo off
setlocal
cd /d "%~dp0"
echo ==== cookie ====
if exist "data\cookie.txt" (
  powershell -NoProfile -Command "$p='data\cookie.txt'; $s=Get-Content $p -Raw; Write-Host ('length: ' + $s.Length); Write-Host ('modified: ' + (Get-Item $p).LastWriteTime)"
) else (
  echo no data\cookie.txt yet
)
echo.
echo ==== last log lines ====
if exist "data\keeper.log" (
  powershell -NoProfile -Command "Get-Content 'data\keeper.log' -Encoding UTF8 -Tail 15"
) else (
  echo no data\keeper.log yet
)
echo.
echo ==== scheduled task ====
powershell -NoProfile -Command "$t=Get-ScheduledTask -TaskName 'SSD-Weread-Keeper' -ErrorAction SilentlyContinue; if ($t) { $i=Get-ScheduledTaskInfo -TaskName 'SSD-Weread-Keeper'; Write-Host ('state: ' + $t.State); Write-Host ('last run: ' + $i.LastRunTime); Write-Host ('next run: ' + $i.NextRunTime) } else { Write-Host 'task not registered' }"
echo.
pause
