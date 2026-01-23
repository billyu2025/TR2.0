@echo off
REM ============================================
REM TR数据库自动更新批处理文件
REM 功能：自动更新 TR_Report 和 TR_Report_Deduplication 表
REM 日期：2025-11-20
REM 版本：3.0
REM ============================================

REM 立即显示信息，确保窗口打开
echo.
echo ============================================
echo TR Database Auto Update Task
echo ============================================
echo.
echo Script is starting...
echo.

REM 启用延迟变量扩展
setlocal enabledelayedexpansion

REM 初始化变量
set "EXIT_CODE=0"
set "MANUAL_RUN=1"
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%~f0"
set "PYTHON_SCRIPT=%SCRIPT_DIR%auto_update_all_tables.py"

REM 检查命令行参数
if /i "%1"=="/NO_PAUSE" (
    set "MANUAL_RUN=0"
) else (
    set "MANUAL_RUN=1"
)

REM 设置Python编码环境变量
set "PYTHONIOENCODING=utf-8"

REM 切换到脚本目录
cd /d "%SCRIPT_DIR%" 2>nul
if errorlevel 1 (
    echo ERROR: Cannot change to script directory: %SCRIPT_DIR%
    echo Current directory: %CD%
    echo.
    if "%MANUAL_RUN%"=="1" (
        pause
    )
    exit /b 1
)

REM 生成时间戳
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "DATETIME=%%I"
set "TIMESTAMP=%DATETIME:~0,8%_%DATETIME:~8,6%"
set "TIMESTAMP=%TIMESTAMP: =0%"

REM 如果wmic不可用，使用备用方法
if not defined TIMESTAMP (
    set "TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
    set "TIMESTAMP=%TIMESTAMP: =0%"
    set "TIMESTAMP=%TIMESTAMP:/=%"
    set "TIMESTAMP=%TIMESTAMP::=%"
)

REM 创建日志目录
if not exist "%SCRIPT_DIR%logs" (
    mkdir "%SCRIPT_DIR%logs" 2>nul
)

REM 设置日志文件路径
if exist "%SCRIPT_DIR%logs" (
    set "LOG_FILE=%SCRIPT_DIR%logs\batch_run_%TIMESTAMP%.log"
) else (
    set "LOG_FILE=%TEMP%\batch_run_%TIMESTAMP%.log"
)

REM 设置临时输出文件路径
if exist "%SCRIPT_DIR%logs" (
    set "TEMP_OUTPUT=%SCRIPT_DIR%logs\temp_output_%TIMESTAMP%.txt"
) else (
    set "TEMP_OUTPUT=%TEMP%\temp_output_%TIMESTAMP%.txt"
)

REM 写入日志文件
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

REM 显示启动信息
echo [INFO] Script Directory: %SCRIPT_DIR%
echo [INFO] Current Directory: %CD%
echo [INFO] Log File: %LOG_FILE%
echo.

REM 检查Python
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

REM 记录Python路径
for /f "delims=" %%i in ('where python 2^>nul') do (
    echo [INFO] Python found at: %%i >> "%LOG_FILE%" 2>&1
    echo [INFO] Python found at: %%i
)

REM 检查Python版本
python --version >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [ERROR] Cannot execute python --version >> "%LOG_FILE%" 2>&1
    echo [ERROR] Cannot execute python --version
    set "EXIT_CODE=1"
    goto :error_exit
)

echo [INFO] Python version checked successfully
echo.

REM 检查Python脚本
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

REM 执行Python脚本
echo [INFO] Starting Python script execution...
echo [INFO] Starting Python script execution... >> "%LOG_FILE%" 2>&1
echo [INFO] Command: python "%PYTHON_SCRIPT%" >> "%LOG_FILE%" 2>&1
echo [INFO] Output file: %TEMP_OUTPUT% >> "%LOG_FILE%" 2>&1
echo [INFO] Execution start time: %date% %time% >> "%LOG_FILE%" 2>&1
echo.
echo ============================================
echo Executing Python script...
echo This may take 2-3 minutes...
echo ============================================
echo.

REM 执行Python脚本
python "%PYTHON_SCRIPT%" > "%TEMP_OUTPUT%" 2>&1
set "EXIT_CODE=!errorlevel!"

REM 记录执行结果
echo [INFO] Python script execution completed >> "%LOG_FILE%" 2>&1
echo [INFO] Execution end time: %date% %time% >> "%LOG_FILE%" 2>&1
echo [INFO] Exit code: !EXIT_CODE! >> "%LOG_FILE%" 2>&1
echo.
echo Python script execution completed.
echo Exit code: !EXIT_CODE!
echo.

REM 检查输出文件
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

REM 删除临时输出文件
del "%TEMP_OUTPUT%" >nul 2>&1

REM 检查错误日志
echo [INFO] Checking error logs... >> "%LOG_FILE%" 2>&1
if exist "%SCRIPT_DIR%logs\error_log_*.log" (
    for /f "delims=" %%F in ('dir /b /o-d "%SCRIPT_DIR%logs\error_log_*.log" 2^>nul') do (
        echo [INFO] Found error log: %%F >> "%LOG_FILE%" 2>&1
        echo [INFO] Error log content: >> "%LOG_FILE%" 2>&1
        type "%SCRIPT_DIR%logs\%%F" >> "%LOG_FILE%" 2>&1
        echo. >> "%LOG_FILE%" 2>&1
        goto :error_log_done
    )
)
if exist "%SCRIPT_DIR%logs\import_error_*.log" (
    for /f "delims=" %%F in ('dir /b /o-d "%SCRIPT_DIR%logs\import_error_*.log" 2^>nul') do (
        echo [INFO] Found import error log: %%F >> "%LOG_FILE%" 2>&1
        echo [INFO] Import error log content: >> "%LOG_FILE%" 2>&1
        type "%SCRIPT_DIR%logs\%%F" >> "%LOG_FILE%" 2>&1
        echo. >> "%LOG_FILE%" 2>&1
        goto :error_log_done
    )
)
:error_log_done

REM 记录最终结果
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
REM 如果是手动运行，等待用户按键
if "%MANUAL_RUN%"=="1" (
    echo.
    echo ============================================
    echo Press any key to exit...
    echo ============================================
    pause >nul 2>&1
    if errorlevel 1 (
        timeout /t 10 /nobreak >nul 2>&1
    )
)

REM 记录脚本结束时间
echo. >> "%LOG_FILE%" 2>&1
echo [INFO] Batch script completed >> "%LOG_FILE%" 2>&1
echo [INFO] Final exit code: !EXIT_CODE! >> "%LOG_FILE%" 2>&1
echo ============================================ >> "%LOG_FILE%" 2>&1
echo End Time: %date% %time% >> "%LOG_FILE%" 2>&1
echo ============================================ >> "%LOG_FILE%" 2>&1

REM 退出
if not defined EXIT_CODE set "EXIT_CODE=0"
exit /b %EXIT_CODE%

