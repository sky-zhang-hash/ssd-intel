@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0node"
if not exist "%~dp0data" mkdir "%~dp0data"
set "LOG=%~dp0data\setup.log"
echo ==== %DATE% %TIME% setup 开始 ==== >>"%LOG%"

echo ============================================
echo   SSD 日报 · 微信读书 Cookie 守护（首次配置）
echo ============================================
echo   日志同时写入 data\setup.log
echo.

where node >nul 2>nul
if errorlevel 1 (
  echo [x] 没找到 node。请先装 Node.js 20+（https://nodejs.org），再重跑本脚本。
  echo [x] 没找到 node >>"%LOG%"
  pause & exit /b 1
)

echo [1/4] 安装依赖（第一次要一分钟左右）...
call npm install --no-audit --no-fund >>"%LOG%" 2>&1
if errorlevel 1 (
  echo [x] npm install 失败，详情见 data\setup.log
  pause & exit /b 1
)

if not exist .env (
  echo [2/4] 生成 .env，请把 GitHub token 填进去
  copy /y .env.example .env >nul
  notepad .env
) else (
  echo [2/4] 已有 .env，跳过
)

echo.
echo [3/4] 打开浏览器扫码登录（扫完窗口会自己关）
echo ---- login 输出开始 ---- >>"%LOG%"
node keeper.mjs login 2>&1
set "RC=%ERRORLEVEL%"
echo ---- login 输出结束（退出码 %RC%）---- >>"%LOG%"
if not "%RC%"=="0" (
  echo.
  echo [x] 登录没成功（退出码 %RC%）。上面就是错误信息，也可以看 data\setup.log
  echo.
  echo     实在不行就手动跑这两行，把输出复制给我：
  echo       cd /d "%~dp0node"
  echo       node keeper.mjs login
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
echo   - 登录态过期：双击 update-cookie.cmd
echo   - 看状态：双击 status.cmd
echo   - 取消计划任务：schtasks /delete /tn "SSD-Weread-Keeper" /f
echo ==== setup 结束 ==== >>"%LOG%"
pause
