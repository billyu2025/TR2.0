@echo off
REM 修复并重启服务脚本 - 需要以管理员身份运行
chcp 65001 >nul
echo ========================================
echo TR-Backend 修复并重启脚本
echo ========================================
echo.

echo [1/5] 停止服务...
cd /d "%~dp0"
nssm-2.24\win64\nssm.exe stop TR-Backend
timeout /t 3 /nobreak >nul

echo [2/5] 关闭占用端口 5000 的进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000.*LISTENING" 2^>nul') do (
    echo 找到进程 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
    if not errorlevel 1 (
        echo 已终止进程 %%a
    ) else (
        echo 警告: 无法终止进程 %%a (可能需要管理员权限)
    )
)
timeout /t 2 /nobreak >nul

echo [3/5] 清理 Python 缓存...
for /d /r . %%d in (__pycache__) do @if exist "%%d" (
    echo 删除: %%d
    rd /s /q "%%d" 2>nul
)
for /r . %%f in (*.pyc) do @if exist "%%f" (
    echo 删除: %%f
    del /f /q "%%f" 2>nul
)
echo 缓存清理完成

echo [4/5] 验证端口已释放...
netstat -ano | findstr ":5000.*LISTENING" >nul
if errorlevel 1 (
    echo [OK] 端口 5000 已释放
) else (
    echo [ERROR] 端口 5000 仍被占用，请手动关闭进程后重试
    pause
    exit /b 1
)

echo [5/5] 启动服务...
nssm-2.24\win64\nssm.exe start TR-Backend
timeout /t 5 /nobreak >nul

echo.
echo 检查服务状态...
nssm-2.24\win64\nssm.exe status TR-Backend

echo.
echo 检查端口...
netstat -ano | findstr ":5000.*LISTENING"

echo.
echo ========================================
echo 完成！
echo ========================================
echo.
echo 如果服务启动失败，请查看日志:
echo   logs\nssm_error.log
echo   logs\app.log
echo.
pause
