@echo off
REM 启动 NSSM 服务脚本（CMD 版本）
REM 使用方法：以管理员身份运行 CMD，然后执行：start_nssm_service.bat

cd /d "%~dp0"

echo ========================================
echo 启动 TR Backend 服务
echo ========================================
echo.

REM 检查服务是否存在
sc query TR-Backend >nul 2>&1
if errorlevel 1 (
    echo 错误：服务 TR-Backend 不存在！
    echo 请先运行 install_nssm_service.ps1 安装服务
    pause
    exit /b 1
)

REM 检查服务状态
sc query TR-Backend | findstr "STATE" | findstr "RUNNING" >nul
if not errorlevel 1 (
    echo 服务已在运行中
) else (
    echo 正在启动服务...
    net start TR-Backend
    if errorlevel 1 (
        echo 错误：启动服务失败
        echo 请查看错误日志: logs\nssm_error.log
        pause
        exit /b 1
    ) else (
        echo 服务启动成功！
    )
)

echo.
echo ========================================
echo 服务信息
echo ========================================
sc query TR-Backend

echo.
echo 检查端口 5000...
netstat -ano | findstr ":5000" | findstr "LISTENING"
if errorlevel 1 (
    echo 警告：端口 5000 未监听
) else (
    echo 端口 5000 正在监听
)

echo.
echo 完成！
echo.
echo 常用命令：
echo   启动:   net start TR-Backend
echo   停止:   net stop TR-Backend
echo   状态:   sc query TR-Backend
echo.

pause
