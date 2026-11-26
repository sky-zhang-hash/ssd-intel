@echo off
setlocal
cd /d "%~dp0node"
if not exist "%~dp0data" mkdir "%~dp0data"
echo ==== %DATE% %TIME% watch start ==== >>"%~dp0data\keeper.log"
node keeper.mjs watch >>"%~dp0data\keeper.log" 2>&1
echo ==== watch exit %ERRORLEVEL% ==== >>"%~dp0data\keeper.log"
exit /b %ERRORLEVEL%
