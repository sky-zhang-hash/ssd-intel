@echo off
setlocal
cd /d "%~dp0"
echo Registering resident task SSD-Weread-Watch (runs at logon, keeps session warm)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0register-watch.ps1"
if not "%ERRORLEVEL%"=="0" echo [x] failed. Right-click this file and choose "Run as administrator".
pause
