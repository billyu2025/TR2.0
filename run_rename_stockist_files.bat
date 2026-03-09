@echo off
REM ============================================
REM Run rename_stockist_files.py Script
REM ============================================
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo ============================================
echo Running rename_stockist_files.py
echo ============================================
echo.

REM Try py command first (Python Launcher)
py rename_stockist_files.py

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to run script with 'py' command
    echo [INFO] Trying alternative methods...
    echo.
    
    REM Try python3
    python3 rename_stockist_files.py 2>nul
    if errorlevel 1 (
        REM Try full Python path
        for /f "tokens=*" %%i in ('where py') do (
            "%%i" rename_stockist_files.py
            goto :end
        )
        echo [ERROR] Python not found. Please install Python or add it to PATH.
    )
)

:end
echo.
pause
