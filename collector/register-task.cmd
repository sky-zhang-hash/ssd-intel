@echo off
chcp 65001 >nul
setlocal
echo 注册每 12 小时自动续期的计划任务（SSD-Weread-Keeper）
schtasks /create /tn "SSD-Weread-Keeper" /tr "cmd /c cd /d \"%~dp0node\" && node keeper.mjs once" /sc hourly /mo 12 /f
if errorlevel 1 (
  echo.
  echo [x] 注册失败。常见原因：没有权限。请右键本文件 → 「以管理员身份运行」再试。
) else (
  echo.
  echo [ok] 已创建。验证：
  schtasks /query /tn "SSD-Weread-Keeper" /fo LIST
)
echo.
pause
