@echo off
REM 实时监控 TR 系统日志

echo ========================================
echo TR System Log Monitor
echo ========================================
echo Press Ctrl+C to stop
echo.

cd /d "C:\TR-master\TR UI\backend\logs"

:loop
cls
echo ========================================
echo TR System Logs - %date% %time%
echo ========================================
echo.

echo [ERROR LOG - Last 20 lines]
echo ----------------------------------------
powershell -Command "Get-Content 'nssm_error.log' -Tail 20 -ErrorAction SilentlyContinue" 2>nul
echo.

echo [OUTPUT LOG - Last 20 lines]
echo ----------------------------------------
powershell -Command "Get-Content 'nssm_output.log' -Tail 20 -ErrorAction SilentlyContinue" 2>nul
echo.

echo [APP LOG - Last 10 lines]
echo ----------------------------------------
powershell -Command "Get-Content 'app.log' -Tail 10 -ErrorAction SilentlyContinue" 2>nul
echo.

echo ========================================
echo Refreshing in 5 seconds... (Ctrl+C to stop)
timeout /t 5 /nobreak >nul
goto loop
