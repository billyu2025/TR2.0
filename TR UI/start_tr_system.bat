@echo off
REM TR 系统启动脚本
REM 使用方法：双击运行此脚本

echo ========================================
echo Starting TR System
echo ========================================
echo.

echo [1/2] Checking backend service...
sc query TR-Backend | findstr "RUNNING" >nul
if errorlevel 1 (
    echo Backend service is not running!
    echo Starting backend service...
    net start TR-Backend
    timeout /t 3 /nobreak >nul
) else (
    echo Backend service is running.
)

echo.
echo [2/2] Starting Nginx...
cd /d "C:\TR-master\TR UI\nginx-1.28.0"
start nginx.exe -p "C:\TR-master\TR UI\nginx-1.28.0" -c conf\nginx.conf
timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo TR System started!
echo ========================================
echo.
echo Access the system at:
echo   - Local: http://localhost:8000
echo   - Network: http://192.168.32.97:8000
echo.
echo Press any key to exit...
pause >nul
