@echo off
REM 以管理员身份运行此批处理
cd /d "%~dp0.."
python patches\apply_fix_update_status_detection.py --reset-stuck-job
if errorlevel 1 (
    echo.
    echo 补丁应用失败。请确认以管理员身份运行，且 TR-Backend 服务已停止或当前用户有写权限。
    pause
    exit /b 1
)
echo.
echo 正在重启 TR-Backend...
net stop TR-Backend
net start TR-Backend
echo.
echo 完成。请刷新 TR 记录页面。
pause
