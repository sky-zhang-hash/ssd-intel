@echo off
setlocal
cd /d "%~dp0node"
echo Opening browser to log in again (scan the QR code with WeChat, old account)...
node keeper.mjs login
echo.
if errorlevel 1 (
  echo [x] login failed, see ..\data\keeper.log
) else (
  echo [ok] cookie refreshed and written back to the GitHub secret
)
pause
