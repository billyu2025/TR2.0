@echo off
REM Force restart TR-Backend service (handles paused state)
REM Run this as Administrator (Right-click -> Run as administrator)

echo ========================================
echo Force Restarting TR-Backend Service
echo ========================================
echo.
echo NOTE: This script must be run as Administrator!
echo.
pause

cd /d "%~dp0"

echo [1/6] Checking current status...
call nssm-2.24\win64\nssm.exe status TR-Backend
echo.

echo [2/6] Resuming service (if paused)...
call nssm-2.24\win64\nssm.exe continue TR-Backend 2>nul
if errorlevel 1 (
    echo Service is not paused or already stopped
)
timeout /t 2 /nobreak >nul

echo [3/6] Stopping service...
call nssm-2.24\win64\nssm.exe stop TR-Backend 2>nul
if errorlevel 1 (
    echo Trying with sc command...
    sc stop TR-Backend >nul 2>&1
)
timeout /t 5 /nobreak >nul

echo [4/6] Force stopping (if still running)...
sc stop TR-Backend >nul 2>&1
timeout /t 3 /nobreak >nul

echo [5/6] Clearing Python cache...
for /r %%f in (*.pyc) do del /f /q "%%f" 2>nul
for /d /r %%d in (__pycache__) do rmdir /s /q "%%d" 2>nul
echo Cache cleared.

echo [6/6] Starting service...
call nssm-2.24\win64\nssm.exe start TR-Backend
if errorlevel 1 (
    echo.
    echo ERROR: Failed to start service!
    echo The service might still be in PAUSED state.
    echo.
    echo Try this manually:
    echo   1. Open services.msc
    echo   2. Find "TR Report System Backend"
    echo   3. Right-click -^> Restart
    echo.
) else (
    echo Service started successfully!
    timeout /t 3 /nobreak >nul
)

echo.
echo [Final Status Check]
call nssm-2.24\win64\nssm.exe status TR-Backend

echo.
echo ========================================
echo Done! Check the status above.
echo ========================================
pause
