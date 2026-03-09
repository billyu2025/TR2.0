@echo off
REM ============================================
REM TR Database Auto Update Batch File
REM Function: Auto update TR_Report and TR_Report_Deduplication tables
REM Date: 2025-11-20
REM Version: 5.0 (Full English version with service control)
REM ============================================

REM Set console code page to UTF-8 FIRST
chcp 65001 >nul 2>&1

REM Enable delayed variable expansion
setlocal enabledelayedexpansion

REM Keep window open
if not "%1"=="/NO_PAUSE" (
    set "KEEP_WINDOW_OPEN=1"
) else (
    set "KEEP_WINDOW_OPEN=0"
)

REM Set error handling
set "ERROR_OCCURRED=0"

REM Display information
echo.
echo ============================================
echo TR Database Auto Update Task
echo ============================================
echo.
echo Script is starting...
echo [INFO] Script path: %~f0
echo [INFO] Script directory: %~dp0
echo [INFO] Current directory: %CD%
echo.

REM ============================================
REM Service control section
REM ============================================
set "SERVICE_NAME=TR-Backend"

REM Check administrator privileges
net session >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Administrator privileges not detected
    echo [WARNING] Service control requires administrator privileges
    echo [WARNING] Update may fail if backend service is running
    echo [TIP] It is recommended to run this script as administrator
    echo.
    set "SERVICE_CONTROL_ENABLED=0"
) else (
    echo [INFO] Administrator privileges check passed, service control enabled
    echo.
    set "SERVICE_CONTROL_ENABLED=1"
)

REM If service control is enabled, check and stop the service
if "!SERVICE_CONTROL_ENABLED!"=="1" (
    echo [INFO] Checking backend service status...
    sc query %SERVICE_NAME% >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] Cannot query backend service, service may not be installed
        echo [INFO] Skipping service control, continuing with update
        echo.
        set "SERVICE_WAS_RUNNING=0"
    ) else (
        sc query %SERVICE_NAME% | findstr "RUNNING" >nul
        if errorlevel 1 (
            echo [INFO] Backend service is not running
            echo.
            set "SERVICE_WAS_RUNNING=0"
        ) else (
            echo [INFO] Backend service is running, preparing to stop...
            echo [INFO] Stopping backend service: %SERVICE_NAME%
            net stop %SERVICE_NAME%
            set STOP_EXIT_CODE=!errorlevel!
            if !STOP_EXIT_CODE! neq 0 (
                echo [ERROR] Cannot stop backend service, exit code: !STOP_EXIT_CODE!
                echo [WARNING] Will continue with update, but may fail
                set "SERVICE_WAS_RUNNING=0"
            ) else (
                echo [INFO] Backend service stopped successfully
                set "SERVICE_WAS_RUNNING=1"
            )
            echo.
            REM Wait for service to fully stop
            timeout /t 3 /nobreak >nul
        )
    )
) else (
    echo [INFO] Service control not enabled, skipping service check
    echo.
    set "SERVICE_WAS_RUNNING=0"
)

REM Initialize variables
set "EXIT_CODE=0"
set "MANUAL_RUN=1"
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%~f0"
set "PYTHON_SCRIPT=%SCRIPT_DIR%auto_update_all_tables.py"

REM Check command line arguments
if /i "%1"=="/NO_PAUSE" (
    set "MANUAL_RUN=0"
) else (
    set "MANUAL_RUN=1"
)

REM Set Python encoding environment variable
set "PYTHONIOENCODING=utf-8"

REM Switch to script directory
cd /d "%SCRIPT_DIR%" 2>nul
if errorlevel 1 (
    echo [ERROR] Cannot change to script directory: %SCRIPT_DIR%
    echo [ERROR] Current directory: %CD%
    echo.
    echo [TIP] Please check if the path is correct
    echo.
    if "%MANUAL_RUN%"=="1" (
        pause
    )
    exit /b 1
)

REM Generate timestamp
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "DATETIME=%%I"
set "TIMESTAMP=%DATETIME:~0,8%_%DATETIME:~8,6%"
set "TIMESTAMP=%TIMESTAMP: =0%"

REM If wmic is not available, use fallback method
if not defined TIMESTAMP (
    set "TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
    set "TIMESTAMP=%TIMESTAMP: =0%"
    set "TIMESTAMP=%TIMESTAMP:/=%"
    set "TIMESTAMP=%TIMESTAMP::=%"
)

REM Create log directory
if not exist "%SCRIPT_DIR%logs" (
    mkdir "%SCRIPT_DIR%logs" 2>nul
)

REM Set log file path
if exist "%SCRIPT_DIR%logs" (
    set "LOG_FILE=%SCRIPT_DIR%logs\batch_run_%TIMESTAMP%.log"
) else (
    set "LOG_FILE=%TEMP%\batch_run_%TIMESTAMP%.log"
)

REM Set temporary output file path
if exist "%SCRIPT_DIR%logs" (
    set "TEMP_OUTPUT=%SCRIPT_DIR%logs\temp_output_%TIMESTAMP%.txt"
) else (
    set "TEMP_OUTPUT=%TEMP%\temp_output_%TIMESTAMP%.txt"
)

REM Write to log file
echo ============================================ > "%LOG_FILE%" 2>&1
echo TR Database Auto Update Task >> "%LOG_FILE%" 2>&1
echo Start Time: %date% %time% >> "%LOG_FILE%" 2>&1
echo ============================================ >> "%LOG_FILE%" 2>&1
echo. >> "%LOG_FILE%" 2>&1
echo [INFO] Script Directory: %SCRIPT_DIR% >> "%LOG_FILE%" 2>&1
echo [INFO] Script Path: %SCRIPT_PATH% >> "%LOG_FILE%" 2>&1
echo [INFO] Current Directory: %CD% >> "%LOG_FILE%" 2>&1
echo [INFO] Log File: %LOG_FILE% >> "%LOG_FILE%" 2>&1
echo [INFO] Python Script: %PYTHON_SCRIPT% >> "%LOG_FILE%" 2>&1
echo. >> "%LOG_FILE%" 2>&1

REM Display startup information
echo [INFO] Script Directory: %SCRIPT_DIR%
echo [INFO] Current Directory: %CD%
echo [INFO] Log File: %LOG_FILE%
echo.

REM Check Python
echo [INFO] Checking Python...
echo [INFO] Checking Python... >> "%LOG_FILE%" 2>&1

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH >> "%LOG_FILE%" 2>&1
    echo.
    echo [ERROR] Python not found in PATH
    echo Please ensure Python is installed and added to PATH
    echo.
    set "EXIT_CODE=1"
    goto :error_exit
)

REM Record Python path
for /f "delims=" %%i in ('where python 2^>nul') do (
    echo [INFO] Python found at: %%i >> "%LOG_FILE%" 2>&1
    echo [INFO] Python found at: %%i
)

REM Check Python version
python --version >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [ERROR] Cannot execute python --version >> "%LOG_FILE%" 2>&1
    echo [ERROR] Cannot execute python --version
    set "EXIT_CODE=1"
    goto :error_exit
)

echo [INFO] Python version checked successfully
echo.

REM Check Python script
echo [INFO] Checking Python script...
echo [INFO] Checking Python script... >> "%LOG_FILE%" 2>&1

if not exist "%PYTHON_SCRIPT%" (
    echo [ERROR] Python script not found: %PYTHON_SCRIPT% >> "%LOG_FILE%" 2>&1
    echo [ERROR] Current directory: %CD% >> "%LOG_FILE%" 2>&1
    echo.
    echo [ERROR] Python script not found: %PYTHON_SCRIPT%
    echo [ERROR] Current directory: %CD%
    echo.
    set "EXIT_CODE=1"
    goto :error_exit
)

echo [INFO] Python script found: %PYTHON_SCRIPT%
echo.

REM Execute Python script
echo [INFO] Starting Python script execution...
echo [INFO] Starting Python script execution... >> "%LOG_FILE%" 2>&1
echo [INFO] Command: python "%PYTHON_SCRIPT%" >> "%LOG_FILE%" 2>&1
echo [INFO] Output file: %TEMP_OUTPUT% >> "%LOG_FILE%" 2>&1
echo [INFO] Execution start time: %date% %time% >> "%LOG_FILE%" 2>&1
echo.
echo ============================================
echo Executing Python script...
echo This may take 5-15 minutes...
echo ============================================
echo.
echo [IMPORTANT] 
echo    - Database update may take a long time (usually 5-15 minutes)
echo    - Especially when fetching large amounts of data from SQL Server (338,000+ records)
echo    - Please wait patiently, do not close the window
echo    - Do not press Ctrl+C to interrupt the script
echo    - You can check detailed progress in the log file
echo    - Log file: %SCRIPT_DIR%logs\auto_update_all_*.log
echo.
echo [INFO] Starting execution, please wait...
echo ============================================
echo.

REM Execute Python script
call python "%PYTHON_SCRIPT%" > "%TEMP_OUTPUT%" 2>&1
set "EXIT_CODE=!errorlevel!"

REM Record execution result
echo [INFO] Python script execution completed >> "%LOG_FILE%" 2>&1
echo [INFO] Execution end time: %date% %time% >> "%LOG_FILE%" 2>&1
echo [INFO] Exit code: !EXIT_CODE! >> "%LOG_FILE%" 2>&1
echo.
echo Python script execution completed.
echo Exit code: !EXIT_CODE!
echo.

REM Check output file
if exist "%TEMP_OUTPUT%" (
    for %%A in ("%TEMP_OUTPUT%") do set "FILE_SIZE=%%~zA"
    if !FILE_SIZE! GTR 0 (
        echo [INFO] Output file size: !FILE_SIZE! bytes >> "%LOG_FILE%" 2>&1
        echo.
        echo ============================================
        echo Python Script Output:
        echo ============================================
        type "%TEMP_OUTPUT%"
        echo ============================================
        echo.
        echo [INFO] Saving output to log file... >> "%LOG_FILE%" 2>&1
        type "%TEMP_OUTPUT%" >> "%LOG_FILE%" 2>&1
    ) else (
        echo [WARNING] Output file is empty! >> "%LOG_FILE%" 2>&1
        echo [WARNING] Exit code: !EXIT_CODE! >> "%LOG_FILE%" 2>&1
        echo.
        echo [WARNING] Output file is empty!
        echo [WARNING] Exit code: !EXIT_CODE!
        echo.
        echo This may indicate:
        echo - Python script exited immediately
        echo - Python script encountered an error
        echo - Check error logs in: %SCRIPT_DIR%logs\
        echo.
    )
) else (
    echo [ERROR] Cannot create output file: %TEMP_OUTPUT% >> "%LOG_FILE%" 2>&1
    echo.
    echo [ERROR] Cannot create output file: %TEMP_OUTPUT%
    echo.
    echo This may indicate:
    echo - Python script may not have executed
    echo - Output was not captured
    echo - Check error logs in: %SCRIPT_DIR%logs\
    echo.
)

REM Delete temporary output file
del "%TEMP_OUTPUT%" >nul 2>&1

REM ============================================
REM Service restart section
REM ============================================
echo.
echo [DEBUG] Service restart check: SERVICE_CONTROL_ENABLED=!SERVICE_CONTROL_ENABLED!, SERVICE_WAS_RUNNING=!SERVICE_WAS_RUNNING! >> "%LOG_FILE%" 2>&1
echo [DEBUG] Service restart check: SERVICE_CONTROL_ENABLED=!SERVICE_CONTROL_ENABLED!, SERVICE_WAS_RUNNING=!SERVICE_WAS_RUNNING!

if "!SERVICE_CONTROL_ENABLED!"=="1" (
    echo [DEBUG] Service control is enabled, checking service status... >> "%LOG_FILE%" 2>&1
    echo [DEBUG] Service control is enabled, checking service status...
    
    REM Check if service should be restarted
    REM If SERVICE_WAS_RUNNING is 1, or if service is currently stopped, restart it
    set "SHOULD_RESTART=0"
    
    if "!SERVICE_WAS_RUNNING!"=="1" (
        echo [DEBUG] SERVICE_WAS_RUNNING is 1, will restart service >> "%LOG_FILE%" 2>&1
        echo [DEBUG] SERVICE_WAS_RUNNING is 1, will restart service
        set "SHOULD_RESTART=1"
    ) else (
        REM Check current service status as backup
        sc query %SERVICE_NAME% >nul 2>&1
        if !errorlevel! equ 0 (
            sc query %SERVICE_NAME% | findstr "STOPPED" >nul
            if !errorlevel! equ 0 (
                echo [DEBUG] Service is currently stopped, will attempt to start >> "%LOG_FILE%" 2>&1
                echo [DEBUG] Service is currently stopped, will attempt to start
                set "SHOULD_RESTART=1"
            ) else (
                sc query %SERVICE_NAME% | findstr "RUNNING" >nul
                if !errorlevel! equ 0 (
                    echo [INFO] Service is already running, no restart needed >> "%LOG_FILE%" 2>&1
                    echo [INFO] Service is already running, no restart needed
                    set "SHOULD_RESTART=0"
                ) else (
                    echo [DEBUG] Cannot determine service status, will attempt restart based on SERVICE_WAS_RUNNING >> "%LOG_FILE%" 2>&1
                    echo [DEBUG] Cannot determine service status, will attempt restart based on SERVICE_WAS_RUNNING
                    REM If we had admin privileges and stopped the service, try to restart
                    if "!SERVICE_WAS_RUNNING!"=="0" (
                        set "SHOULD_RESTART=0"
                    ) else (
                        set "SHOULD_RESTART=1"
                    )
                )
            )
        ) else (
            echo [WARNING] Cannot query service status, skipping restart >> "%LOG_FILE%" 2>&1
            echo [WARNING] Cannot query service status, skipping restart
            set "SHOULD_RESTART=0"
        )
    )
    
    if "!SHOULD_RESTART!"=="1" (
        echo.
        echo ============================================
        echo [INFO] Preparing to restart backend service
        echo ============================================
        echo [INFO] Restarting backend service: %SERVICE_NAME% >> "%LOG_FILE%" 2>&1
        echo [INFO] Restarting backend service: %SERVICE_NAME%
        
        REM Wait longer to ensure service is fully stopped and resources are released
        echo [INFO] Waiting for service to fully stop... >> "%LOG_FILE%" 2>&1
        echo [INFO] Waiting for service to fully stop...
        timeout /t 5 /nobreak >nul
        
        REM Check service status before attempting to start
        sc query %SERVICE_NAME% >nul 2>&1
        if !errorlevel! equ 0 (
            sc query %SERVICE_NAME% | findstr "STOPPED" >nul
            if !errorlevel! neq 0 (
                echo [WARNING] Service may not be fully stopped, waiting additional time... >> "%LOG_FILE%" 2>&1
                echo [WARNING] Service may not be fully stopped, waiting additional time...
                timeout /t 3 /nobreak >nul
            )
        )
        
        REM Start service using PowerShell Start-Service
        echo [INFO] Attempting to start service: %SERVICE_NAME% >> "%LOG_FILE%" 2>&1
        echo [INFO] Attempting to start service: %SERVICE_NAME%
        powershell -Command "Start-Service -Name '%SERVICE_NAME%' -ErrorAction Stop" 2>&1
        set "START_EXIT_CODE=!errorlevel!"
        
        echo [DEBUG] PowerShell Start-Service exit code: !START_EXIT_CODE! >> "%LOG_FILE%" 2>&1
        echo [DEBUG] PowerShell Start-Service exit code: !START_EXIT_CODE!
        
        REM Verify service is actually started
        timeout /t 2 /nobreak >nul
        sc query %SERVICE_NAME% | findstr "RUNNING" >nul
        set VERIFY_EXIT_CODE=!errorlevel!
        
        if !START_EXIT_CODE! equ 0 (
            if !VERIFY_EXIT_CODE! equ 0 (
                echo [INFO] Backend service restarted successfully >> "%LOG_FILE%" 2>&1
                echo [INFO] Backend service restarted successfully
                echo [INFO] Service status verified: Running >> "%LOG_FILE%" 2>&1
                echo [INFO] Service status verified: Running
            ) else (
                echo [WARNING] Service start command succeeded but service may not be running >> "%LOG_FILE%" 2>&1
                echo [WARNING] Service start command succeeded but service may not be running
                echo [TIP] Please check service status manually: sc query %SERVICE_NAME% >> "%LOG_FILE%" 2>&1
                echo [TIP] Please check service status manually: sc query %SERVICE_NAME%
            )
        ) else (
            echo [ERROR] Cannot restart backend service, exit code: !START_EXIT_CODE! >> "%LOG_FILE%" 2>&1
            echo [ERROR] Cannot restart backend service, exit code: !START_EXIT_CODE!
            echo [INFO] Checking service status for more details... >> "%LOG_FILE%" 2>&1
            echo [INFO] Checking service status for more details...
            sc query %SERVICE_NAME% >> "%LOG_FILE%" 2>&1
            sc query %SERVICE_NAME%
            echo.
            echo [TIP] Possible solutions: >> "%LOG_FILE%" 2>&1
            echo [TIP] Possible solutions:
            echo   1. Check service logs: C:\TR-master\TR UI\backend\logs\nssm_output.log >> "%LOG_FILE%" 2>&1
            echo   1. Check service logs: C:\TR-master\TR UI\backend\logs\nssm_output.log
            echo   2. Try starting manually with PowerShell: Start-Service %SERVICE_NAME% >> "%LOG_FILE%" 2>&1
            echo   2. Try starting manually with PowerShell: Start-Service %SERVICE_NAME%
            echo   4. Check Windows Event Viewer for service errors >> "%LOG_FILE%" 2>&1
            echo   4. Check Windows Event Viewer for service errors
        )
        echo.
    ) else (
        echo [INFO] Service restart not needed >> "%LOG_FILE%" 2>&1
        echo [INFO] Service restart not needed
        echo [DEBUG] SERVICE_WAS_RUNNING value: !SERVICE_WAS_RUNNING! >> "%LOG_FILE%" 2>&1
        echo [DEBUG] SERVICE_WAS_RUNNING value: !SERVICE_WAS_RUNNING!
        echo.
    )
) else (
    echo [INFO] Service control not enabled, skipping service restart >> "%LOG_FILE%" 2>&1
    echo [INFO] Service control not enabled, skipping service restart
    echo [DEBUG] SERVICE_CONTROL_ENABLED value: !SERVICE_CONTROL_ENABLED! >> "%LOG_FILE%" 2>&1
    echo [DEBUG] SERVICE_CONTROL_ENABLED value: !SERVICE_CONTROL_ENABLED!
    echo.
)

REM Record final result
echo. >> "%LOG_FILE%" 2>&1
if !EXIT_CODE! equ 0 (
    echo [INFO] Task completed successfully! >> "%LOG_FILE%" 2>&1
    echo [INFO] Log file: %LOG_FILE% >> "%LOG_FILE%" 2>&1
    echo.
    echo ============================================
    echo Task completed successfully!
    echo ============================================
    echo.
    echo Log file: %LOG_FILE%
) else (
    echo [ERROR] Task completed with errors, exit code: !EXIT_CODE! >> "%LOG_FILE%" 2>&1
    echo [ERROR] Log file: %LOG_FILE% >> "%LOG_FILE%" 2>&1
    echo.
    echo ============================================
    echo Task completed with errors!
    echo Exit code: !EXIT_CODE!
    echo ============================================
    echo.
    echo Log file: %LOG_FILE%
)

echo. >> "%LOG_FILE%" 2>&1
echo ============================================ >> "%LOG_FILE%" 2>&1
echo End Time: %date% %time% >> "%LOG_FILE%" 2>&1
echo ============================================ >> "%LOG_FILE%" 2>&1

:error_exit
REM If manual run, wait for user key press
if "%MANUAL_RUN%"=="1" (
    echo.
    echo ============================================
    echo Press any key to exit...
    echo ============================================
    pause >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Waiting 10 seconds before auto-closing...
        timeout /t 10 /nobreak >nul 2>&1
    )
) else if "!KEEP_WINDOW_OPEN!"=="1" (
    echo.
    echo [INFO] An error occurred, waiting 10 seconds before auto-closing...
    echo [INFO] To view error information, please run this script as administrator
    timeout /t 10 /nobreak >nul 2>&1
)

REM Record script end time
echo. >> "%LOG_FILE%" 2>&1
echo [INFO] Batch script completed >> "%LOG_FILE%" 2>&1
echo [INFO] Final exit code: !EXIT_CODE! >> "%LOG_FILE%" 2>&1
echo ============================================ >> "%LOG_FILE%" 2>&1
echo End Time: %date% %time% >> "%LOG_FILE%" 2>&1
echo ============================================ >> "%LOG_FILE%" 2>&1

REM Exit
if not defined EXIT_CODE set "EXIT_CODE=0"
exit /b %EXIT_CODE%
