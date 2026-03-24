@echo off
REM ============================================
REM TR Database Tables Auto Update Script (PostgreSQL)
REM Function: Update bbs_dd, TR_Report and TR_Report_Deduplication tables
REM This script calls update_tr_tables_postgres.py which handles email sending internally
REM ============================================

REM Enable delayed variable expansion
setlocal enabledelayedexpansion

REM Set working directory to script directory
cd /d "%~dp0"

REM Set paths
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%~f0"
set "PYTHON_SCRIPT=%SCRIPT_DIR%update_tr_tables_postgres.py"

REM Set PostgreSQL environment variables
set DB_BACKEND=postgres
set POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/tr_db

REM Set Python encoding environment variable
set "PYTHONIOENCODING=utf-8"

REM Check if Python script exists
if not exist "%PYTHON_SCRIPT%" (
    echo [ERROR] Python script not found: %PYTHON_SCRIPT%
    echo [ERROR] Current directory: %CD%
    echo.
    exit /b 1
)

echo ============================================
echo TR Database Tables Update Started
echo ============================================
echo.
echo [INFO] Script Directory: %SCRIPT_DIR%
echo [INFO] Python Script: %PYTHON_SCRIPT%
echo [INFO] Database Backend: PostgreSQL
echo.

REM Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH
    echo Please ensure Python is installed and added to PATH
    echo.
    exit /b 1
)

REM Record Python path
for /f "delims=" %%i in ('where python 2^>nul') do (
    echo [INFO] Python found at: %%i
)

echo [INFO] Python version:
python --version
echo.

echo ============================================
echo Executing Python script...
echo This may take 5-15 minutes...
echo ============================================
echo.
echo [IMPORTANT] 
echo    - Database update may take a long time (usually 5-15 minutes)
echo    - Please wait patiently, do not close the window
echo    - Email notification will be sent automatically by Python script
echo.
echo ============================================
echo.

REM Execute Python script (Python script will handle email sending internally)
call python "%PYTHON_SCRIPT%"
set "EXIT_CODE=%errorlevel%"

echo.
echo ============================================
if %EXIT_CODE% equ 0 (
    echo Task completed successfully!
) else (
    echo Task completed with errors!
    echo Exit code: %EXIT_CODE%
)
echo ============================================
echo.

REM Exit immediately without any user interaction
endlocal
exit /b %EXIT_CODE%
