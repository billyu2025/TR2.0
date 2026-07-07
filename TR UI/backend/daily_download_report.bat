@echo off
REM TR Daily Download Report — run at 19:00 via Task Scheduler
chcp 65001 >nul 2>&1
setlocal

set "BACKEND_DIR=%~dp0"
cd /d "%BACKEND_DIR%"

set "LOG_FILE=%BACKEND_DIR%logs\scheduled_report_run.log"
echo.>>"%LOG_FILE%"
echo ============================================>>"%LOG_FILE%"
echo [%date% %time%] daily_download_report.bat started>>"%LOG_FILE%"
echo BACKEND_DIR=%BACKEND_DIR%>>"%LOG_FILE%"

REM Prefer Python 3.14 (same as interactive shell), fallback to PATH
set "PYTHON_EXE=C:\Python314\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=C:\Users\tradmin\AppData\Local\Programs\Python\Python310\python.exe"
)
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo PYTHON_EXE=%PYTHON_EXE%>>"%LOG_FILE%"

"%PYTHON_EXE%" "%BACKEND_DIR%daily_download_report.py" >>"%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

echo [%date% %time%] finished exit_code=%EXIT_CODE%>>"%LOG_FILE%"

exit /b %EXIT_CODE%
