@echo off
setlocal
cd /d "%~dp0node"
echo ============================================
echo  Step 1/2  stop old keeper (only keeper.mjs)
echo ============================================
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | Where-Object { $_.CommandLine -like '*keeper.mjs*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" 2>nul
echo.
echo ============================================
echo  Step 2/2  scan the QR code with WeChat
echo  (a browser window will open; scan, confirm, then wait for OK)
echo ============================================
node keeper.mjs login
if errorlevel 1 goto fail
echo.
echo [ok] login saved. starting background watcher ...
start "SSD-Weread-Watch" /min cmd /c "%~dp0run-watch.cmd"
echo.
echo Done. You can close this window.
pause
exit /b 0
:fail
echo.
echo [x] login failed. Check the messages above,
echo     then double-click this file again.
pause
exit /b 1
