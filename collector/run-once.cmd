@echo off
setlocal
cd /d "%~dp0node"
if not exist "%~dp0data" mkdir "%~dp0data"
echo ==== %DATE% %TIME% run-once ==== >>"%~dp0data\keeper.log"
node keeper.mjs once >>"%~dp0data\keeper.log" 2>&1
echo ==== exit %ERRORLEVEL% ==== >>"%~dp0data\keeper.log"
exit /b %ERRORLEVEL%
