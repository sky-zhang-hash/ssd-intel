@echo off
setlocal
cd /d "%~dp0"
echo Registering scheduled task SSD-Weread-Keeper (every 12 hours)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0register-task.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo [x] failed (exit %RC%). Right-click this file and choose "Run as administrator" and try again.
pause
