@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0node"
echo == 最近 20 行日志 ==
powershell -NoProfile -Command "Get-Content '%~dp0data\keeper.log' -Tail 20" 2>nul
echo.
echo == 当前保存的 Cookie 长度 ==
for /f %%A in ('powershell -NoProfile -Command "if (Test-Path '%~dp0data\cookie.txt') { (Get-Content '%~dp0data\cookie.txt' -Raw).Length } else { 0 }"') do echo %%A
echo.
echo == 计划任务状态 ==
schtasks /query /tn "SSD-Weread-Keeper" 2>nul | findstr /i "SSD-Weread-Keeper"
pause
