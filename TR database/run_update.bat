@echo off
REM ============================================
REM 数据库更新脚本启动器
REM 确保窗口保持打开并显示所有输出
REM ============================================

REM 设置控制台代码页为UTF-8
chcp 65001 >nul 2>&1

REM 切换到脚本目录
cd /d "%~dp0"

REM 显示启动信息
echo.
echo ============================================
echo TR 数据库更新脚本启动器
echo ============================================
echo.
echo [INFO] 当前目录: %CD%
echo [INFO] 准备启动更新脚本...
echo.

REM 检查主脚本是否存在
if not exist "auto_update_all_tables.bat" (
    echo [ERROR] 找不到 auto_update_all_tables.bat
    echo [ERROR] 请确保文件在正确的目录中
    echo.
    pause
    exit /b 1
)

REM 运行主脚本
echo [INFO] 正在启动更新脚本...
echo.
call auto_update_all_tables.bat

REM 获取退出代码
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo ============================================
echo 脚本执行完成
echo ============================================
echo.
echo 退出代码: %EXIT_CODE%
echo.

REM 如果退出代码不为0，显示错误信息
if not %EXIT_CODE% equ 0 (
    echo [警告] 脚本执行时遇到错误
    echo [提示] 请查看日志文件获取详细信息
    echo [提示] 日志文件位置: %CD%\logs\
    echo.
)

REM 等待用户按键
echo 按任意键关闭窗口...
pause >nul

exit /b %EXIT_CODE%
