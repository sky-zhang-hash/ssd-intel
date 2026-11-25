@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0node"

echo ============================================
echo   SSD 日报 · 微信读书 Cookie 守护（首次配置）
echo ============================================
echo.

where node >nul 2>nul
if errorlevel 1 (
  echo [x] 没找到 node。请先装 Node.js 20+（https://nodejs.org），再重跑本脚本。
  pause & exit /b 1
)

echo [1/4] 安装依赖（第一次要一分钟左右）...
call npm install --no-audit --no-fund
if errorlevel 1 ( echo [x] npm install 失败 & pause & exit /b 1 )

if not exist .env (
  echo [2/4] 生成 .env，请把 GitHub token 填进去
  copy /y .env.example .env >nul
  notepad .env
) else (
  echo [2/4] 已有 .env，跳过
)

echo.
echo [3/4] 打开浏览器扫码登录（扫完窗口会自己关）
node keeper.mjs login
if errorlevel 1 (
  echo [x] 登录没成功。再跑一次本脚本，或手动执行：cd node ^&^& node keeper.mjs login
  pause & exit /b 1
)

echo.
echo [4/4] 注册每 12 小时自动续期的计划任务
schtasks /create /tn "SSD-Weread-Keeper" /tr "cmd /c cd /d \"%~dp0node\" && node keeper.mjs once" /sc hourly /mo 12 /f
if errorlevel 1 (
  echo [!] 计划任务注册失败（可能需要用管理员身份再跑一次这个脚本）
) else (
  echo      已创建计划任务 SSD-Weread-Keeper（每 12 小时跑一次 once）
)

echo.
echo 完成。以后：
echo   - 想立刻续期：双击 node\..\update-cookie.cmd 或跑 node keeper.mjs once
echo   - 看日志：type data\keeper.log
echo   - 手动取消计划任务：schtasks /delete /tn "SSD-Weread-Keeper" /f
pause
