@echo off
REM ============================================
REM Fix Windows Scheduled Task to Run with Highest Privileges
REM ============================================
REM This script modifies an existing scheduled task to run with administrator privileges
REM Run this script as Administrator

echo ============================================
echo Fix Scheduled Task Privileges
echo ============================================
echo.

REM Check administrator privileges
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] This script requires administrator privileges!
    echo Please run this script as Administrator
    echo.
    pause
    exit /b 1
)

REM Set task name (modify this if your task has a different name)
set "TASK_NAME=TR_Database_Auto_Update"

echo [INFO] Task Name: %TASK_NAME%
echo.

REM Check if task exists
echo [INFO] Checking if task exists...
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Task "%TASK_NAME%" not found!
    echo.
    echo [TIP] Please check the task name in Task Scheduler
    echo [TIP] Or create a new task with highest privileges
    echo.
    pause
    exit /b 1
)

echo [INFO] Task found!
echo.

REM Show current configuration
echo [INFO] Current task configuration:
echo ============================================
schtasks /query /tn "%TASK_NAME%" /fo LIST /v | findstr /C:"Run Level" /C:"Task Name" /C:"Status"
echo ============================================
echo.

REM Change task to run with highest privileges
echo [INFO] Changing task to run with highest privileges...
schtasks /change /tn "%TASK_NAME%" /rl HIGHEST

if errorlevel 1 (
    echo [ERROR] Failed to change task privileges
    echo.
    echo [TIP] Make sure:
    echo   1. You are running as Administrator
    echo   2. The task name is correct
    echo   3. The task is not currently running
    echo.
    pause
    exit /b 1
)

echo [SUCCESS] Task privileges updated successfully!
echo.

REM Verify the change
echo [INFO] Verifying new configuration:
echo ============================================
schtasks /query /tn "%TASK_NAME%" /fo LIST /v | findstr /C:"Run Level" /C:"Task Name" /C:"Status"
echo ============================================
echo.

REM Check Run Level
schtasks /query /tn "%TASK_NAME%" /fo LIST /v | findstr /C:"Run Level" | findstr /C:"Highest" >nul
if errorlevel 1 (
    echo [WARNING] Run Level may not be set to Highest
    echo [WARNING] Please verify in Task Scheduler GUI
) else (
    echo [SUCCESS] Task is now configured to run with highest privileges!
)

echo.
echo [INFO] Next steps:
echo   1. Test the task: Right-click in Task Scheduler and select "Run"
echo   2. Check logs: C:\TR-master\TR database\logs\
echo   3. Verify service control works (should not see "Administrator privileges not detected")
echo.
pause
