@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0node"
echo 打开浏览器窗口，用微信扫码登录（登录态会存进 data\profile）
node keeper.mjs login
echo.
echo 日志：
type "%~dp0data\keeper.log" 2>nul
pause
