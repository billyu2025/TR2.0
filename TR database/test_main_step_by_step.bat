@echo off
REM 分步测试主脚本的各个部分
setlocal enabledelayedexpansion

echo ============================================
echo 分步测试主脚本
echo ============================================
echo.

echo [步骤1] 测试基本设置
set "SERVICE_NAME=TR-Backend"
set "SCRIPT_DIR=%~dp0"
set "PYTHON_SCRIPT=%SCRIPT_DIR%auto_update_all_tables.py"
echo     SERVICE_NAME = %SERVICE_NAME%
echo     SCRIPT_DIR = %SCRIPT_DIR%
echo     PYTHON_SCRIPT = %PYTHON_SCRIPT%
echo     [完成]
echo.

echo [步骤2] 测试管理员权限检查
net session >nul 2>&1
if errorlevel 1 (
    echo     管理员权限: 否
    set "SERVICE_CONTROL_ENABLED=0"
) else (
    echo     管理员权限: 是
    set "SERVICE_CONTROL_ENABLED=1"
)
echo     SERVICE_CONTROL_ENABLED = !SERVICE_CONTROL_ENABLED!
echo     [完成]
echo.

echo [步骤3] 测试服务控制逻辑
if "!SERVICE_CONTROL_ENABLED!"=="1" (
    echo     服务控制已启用，检查服务...
    sc query %SERVICE_NAME% >nul 2>&1
    if errorlevel 1 (
        echo     无法查询服务
        set "SERVICE_WAS_RUNNING=0"
    ) else (
        sc query %SERVICE_NAME% | findstr "RUNNING" >nul
        if errorlevel 1 (
            echo     服务未运行
            set "SERVICE_WAS_RUNNING=0"
        ) else (
            echo     服务正在运行
            set "SERVICE_WAS_RUNNING=1"
        )
    )
) else (
    echo     服务控制未启用
    set "SERVICE_WAS_RUNNING=0"
)
echo     SERVICE_WAS_RUNNING = !SERVICE_WAS_RUNNING!
echo     [完成]
echo.

echo [步骤4] 测试Python脚本检查
if exist "%PYTHON_SCRIPT%" (
    echo     Python脚本存在
) else (
    echo     Python脚本不存在: %PYTHON_SCRIPT%
)
echo     [完成]
echo.

echo [步骤5] 测试Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo     Python不可用
) else (
    echo     Python可用
    python --version
)
echo     [完成]
echo.

echo ============================================
echo 所有测试完成
echo ============================================
echo.
echo 如果以上测试都通过，主脚本应该可以正常运行
echo 如果主脚本仍然中断，可能是：
echo 1. 用户按了 Ctrl+C
echo 2. 脚本执行时间过长，用户误操作
echo 3. 脚本中某个命令执行失败
echo.
pause
