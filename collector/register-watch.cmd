@echo off
setlocal
cd /d "%~dp0"
echo Starting resident watcher (keeps WeRead session warm)...
start "SSD-Weread-Watch" /min "%~dp0run-watch.cmd"
echo [ok] watcher started in background. Log: data\keeper.log
echo.
echo Registering it to start at every logon (needs Administrator)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0register-watch.ps1"
if not "%ERRORLEVEL%"=="0" echo [x] registration failed - the watcher still runs until you log off.
echo.
echo Press any key to close this window (the watcher keeps running).
pause >nul
