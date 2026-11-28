@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo  restart watcher (no QR scan needed)
echo ============================================
echo stopping old keeper processes ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | Where-Object { $_.CommandLine -like '*keeper.mjs*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" 2>nul
timeout /t 2 /nobreak >nul
echo starting watcher in background ...
start "SSD-Weread-Watch" /min cmd /c "%~dp0run-watch.cmd"
timeout /t 4 /nobreak >nul
echo.
echo ---- last lines of keeper.log ----
powershell -NoProfile -Command "Get-Content -Encoding UTF8 '%~dp0data\keeper.log' -Tail 6"
echo ----------------------------------
echo If the last line timestamp is within 15 min, watcher is running.
pause
