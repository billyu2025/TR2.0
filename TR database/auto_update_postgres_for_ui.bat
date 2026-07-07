@echo off
REM UI 全量更新阶段 B（PostgreSQL）：同步 TR_Report 等到 PostgreSQL，并写 auto_update_all 风格日志供 API 轮询。
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs" 2>nul

for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value 2^>nul') do set "DATETIME=%%I"
set "TIMESTAMP=%DATETIME:~0,8%_%DATETIME:~8,6%"
set "TIMESTAMP=%TIMESTAMP: =0%"
if not defined TIMESTAMP set "TIMESTAMP=manual"

set "MARKER_LOG=%SCRIPT_DIR%logs\auto_update_all_%TIMESTAMP%.log"
set DB_BACKEND=postgres
set POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/tr_db
set PYTHONIOENCODING=utf-8

echo ============================================ > "%MARKER_LOG%"
echo TR PostgreSQL Auto Update (UI phase B) >> "%MARKER_LOG%"
echo Start Time: %date% %time% >> "%MARKER_LOG%"
echo ============================================ >> "%MARKER_LOG%"

call "%SCRIPT_DIR%update_tr_tables_postgres.bat"
set "EXIT_CODE=!errorlevel!"

echo. >> "%MARKER_LOG%"
if !EXIT_CODE! equ 0 (
    echo [INFO] Update completed successfully! >> "%MARKER_LOG%"
    echo TR Database Tables Update Completed >> "%MARKER_LOG%"
    echo 自动更新流程结束 >> "%MARKER_LOG%"
) else (
    echo [ERROR] Update failed, exit code: !EXIT_CODE! >> "%MARKER_LOG%"
    echo 更新流程结束 >> "%MARKER_LOG%"
)
echo End Time: %date% %time% >> "%MARKER_LOG%"

endlocal & exit /b %EXIT_CODE%
