@echo off
REM 诊断脚本 - 检查批处理文件问题
echo ============================================
echo 批处理文件诊断工具
echo ============================================
echo.

echo [1] 检查文件是否存在...
if exist "auto_update_all_tables.bat" (
    echo    文件存在
) else (
    echo    文件不存在
    pause
    exit /b 1
)

echo.
echo [2] 检查管理员权限...
net session >nul 2>&1
if %errorlevel% equ 0 (
    echo    管理员权限: 是
) else (
    echo    管理员权限: 否
)

echo.
echo [3] 检查Python...
python --version 2>&1
if %errorlevel% equ 0 (
    echo    Python: 可用
) else (
    echo    Python: 不可用
)

echo.
echo [4] 检查Python脚本...
if exist "auto_update_all_tables.py" (
    echo    Python脚本: 存在
) else (
    echo    Python脚本: 不存在
)

echo.
echo [5] 检查后端服务...
sc query TR-Backend >nul 2>&1
if %errorlevel% equ 0 (
    echo    后端服务: 已安装
    sc query TR-Backend | findstr "RUNNING" >nul
    if %errorlevel% equ 0 (
        echo    服务状态: 运行中
    ) else (
        echo    服务状态: 已停止
    )
) else (
    echo    后端服务: 未安装
)

echo.
echo [6] 测试延迟变量扩展...
setlocal enabledelayedexpansion
set "TEST_VAR=test"
if "!TEST_VAR!"=="test" (
    echo    延迟变量扩展: 正常
) else (
    echo    延迟变量扩展: 异常
)

echo.
echo ============================================
echo 诊断完成
echo ============================================
pause
