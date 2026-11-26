@echo off
setlocal
cd /d "%~dp0node"
if not exist "%~dp0data" mkdir "%~dp0data"
node keeper.mjs once >>"%~dp0data\keeper.log" 2>&1
exit /b %ERRORLEVEL%
