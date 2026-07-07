@echo off
REM Register Windows Task Scheduler: daily at 19:00
chcp 65001 >nul 2>&1
setlocal

set "TASK_NAME=TR-Daily-Download-Report"
set "BAT_PATH=C:\TR-master\run_daily_download_report.bat"
set "BAT_DIR=C:\TR-master"

echo ============================================
echo Register scheduled task: %TASK_NAME%
echo Run daily at 19:00
echo Script: %BAT_PATH%
echo ============================================
echo.

if not exist "%BAT_PATH%" (
    echo [ERROR] Batch file not found: %BAT_PATH%
    exit /b 1
)

schtasks /create /tn "%TASK_NAME%" /tr "%BAT_PATH%" /sc DAILY /st 19:00 /rl HIGHEST /f
if errorlevel 1 (
    echo [ERROR] schtasks /create failed. Run this bat as Administrator.
    exit /b 1
)

echo.
echo [OK] Task created. Verify:
schtasks /query /tn "%TASK_NAME%" /fo LIST /v | findstr /C:"Task Name" /C:"Status" /C:"Next Run Time" /C:"Run Level"
echo.
echo To test now: schtasks /run /tn "%TASK_NAME%"
echo To remove:    schtasks /delete /tn "%TASK_NAME%" /f
exit /b 0
