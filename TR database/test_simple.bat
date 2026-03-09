@echo off
REM 简单测试脚本 - 检查基本功能
echo ============================================
echo 简单测试脚本
echo ============================================
echo.

echo [1] 测试基本输出
echo    测试成功

echo.
echo [2] 测试延迟变量扩展
setlocal enabledelayedexpansion
set "TEST_VAR=test_value"
echo    变量值: !TEST_VAR!

echo.
echo [3] 测试错误处理
net session >nul 2>&1
if errorlevel 1 (
    echo    管理员权限: 否
) else (
    echo    管理员权限: 是
)

echo.
echo [4] 测试服务查询
sc query TR-Backend >nul 2>&1
if errorlevel 1 (
    echo    服务查询: 失败（服务可能未安装）
) else (
    echo    服务查询: 成功
    sc query TR-Backend | findstr "RUNNING" >nul
    if errorlevel 1 (
        echo    服务状态: 已停止
    ) else (
        echo    服务状态: 运行中
    )
)

echo.
echo ============================================
echo 测试完成
echo ============================================
pause
