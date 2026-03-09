@echo off
REM TR Backend 服务重启脚本
REM 使用方法：双击运行此脚本

echo ========================================
echo Restarting TR Backend Service
echo ========================================
echo.

echo Stopping service...
net stop TR-Backend
timeout /t 3 /nobreak >nul

echo Starting service...
net start TR-Backend
timeout /t 3 /nobreak >nul

echo.
echo Checking service status...
sc query TR-Backend | findstr "STATE"

echo.
echo ========================================
echo Service restarted!
echo ========================================
echo.
pause
