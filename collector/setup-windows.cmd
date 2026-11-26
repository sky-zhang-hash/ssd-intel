@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0data" mkdir "%~dp0data"
set "LOG=%~dp0data\setup.log"
echo ==== %DATE% %TIME% setup start ==== >>"%LOG%"

echo ==================================================
echo   SSD Intel - WeRead cookie keeper (first setup)
echo ==================================================
echo   log: data\setup.log
echo.

where node >nul 2>nul
if errorlevel 1 (
  echo [x] node not found. Install Node.js 20+ from https://nodejs.org then rerun.
  pause & exit /b 1
)

echo [1/4] npm install (about one minute the first time)...
pushd "%~dp0node"
call npm install --no-audit --no-fund >>"%LOG%" 2>&1
if errorlevel 1 (
  popd
  echo [x] npm install failed, see data\setup.log
  pause & exit /b 1
)

if not exist ".env" (
  echo [2/4] .env created - put your GitHub token in it, save, close Notepad
  copy /y ".env.example" ".env" >nul
  notepad ".env"
) else (
  echo [2/4] .env already exists, skip
)

echo.
echo [3/4] opening browser, scan the QR code with WeChat
node keeper.mjs login
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" (
  echo.
  echo [x] login failed (exit %RC%). See data\setup.log
  pause & exit /b 1
)

echo.
echo [4/4] registering the every-12-hours task
call "%~dp0register-task.cmd"

echo.
echo Done. Later you can:
echo   - cookie expired: double-click update-cookie.cmd
echo   - check status : double-click status.cmd
echo   - remove task  : schtasks /delete /tn "SSD-Weread-Keeper" /f
echo ==== setup end ==== >>"%LOG%"
pause
