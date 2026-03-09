@echo off
REM ============================================
REM 诊断批处理文件问题
REM ============================================

echo ============================================
echo 诊断批处理文件问题
echo ============================================
echo.

REM 设置控制台代码页为UTF-8
chcp 65001 >nul 2>&1

REM 检查当前目录
echo [1] 检查当前目录...
echo 当前目录: %CD%
echo 脚本目录: %~dp0
echo.

REM 检查批处理文件是否存在
echo [2] 检查批处理文件...
if exist "%~dp0auto_update_all_tables.bat" (
    echo [OK] auto_update_all_tables.bat 存在
) else (
    echo [ERROR] auto_update_all_tables.bat 不存在！
    echo 请确保文件在正确的目录中
    pause
    exit /b 1
)
echo.

REM 检查Python
echo [3] 检查Python...
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 未找到！
    echo 请确保Python已安装并添加到PATH
    echo.
    echo 尝试查找Python...
    if exist "C:\Python*" (
        echo 找到可能的Python安装目录:
        dir /b /ad "C:\Python*" 2>nul
    )
    if exist "%LOCALAPPDATA%\Programs\Python" (
        echo 找到可能的Python安装目录:
        dir /b /ad "%LOCALAPPDATA%\Programs\Python" 2>nul
    )
) else (
    for /f "delims=" %%i in ('where python 2^>nul') do (
        echo [OK] Python 找到: %%i
    )
    python --version
)
echo.

REM 检查Python脚本
echo [4] 检查Python脚本...
if exist "%~dp0auto_update_all_tables.py" (
    echo [OK] auto_update_all_tables.py 存在
) else (
    echo [ERROR] auto_update_all_tables.py 不存在！
    pause
    exit /b 1
)
echo.

REM 检查管理员权限
echo [5] 检查管理员权限...
net session >nul 2>&1
if errorlevel 1 (
    echo [警告] 未检测到管理员权限
    echo [提示] 服务控制功能需要管理员权限
    echo [提示] 但更新脚本本身不需要管理员权限
) else (
    echo [OK] 检测到管理员权限
)
echo.

REM 检查服务
echo [6] 检查后端服务...
sc query TR-Backend >nul 2>&1
if errorlevel 1 (
    echo [INFO] 无法查询TR-Backend服务（可能未安装）
) else (
    sc query TR-Backend | findstr "RUNNING" >nul
    if errorlevel 1 (
        echo [INFO] TR-Backend服务未运行
    ) else (
        echo [INFO] TR-Backend服务正在运行
    )
)
echo.

REM 测试Python脚本执行
echo [7] 测试Python脚本执行...
echo 尝试执行: python --version
python --version
if errorlevel 1 (
    echo [ERROR] Python执行失败！
) else (
    echo [OK] Python可以执行
)
echo.

REM 检查日志目录
echo [8] 检查日志目录...
if exist "%~dp0logs" (
    echo [OK] logs目录存在
) else (
    echo [INFO] logs目录不存在（将自动创建）
)
echo.

echo ============================================
echo 诊断完成
echo ============================================
echo.
echo 如果所有检查都通过，但双击批处理文件仍然无法运行，
echo 可能的原因：
echo   1. 文件关联问题（.bat文件没有关联到cmd.exe）
echo   2. 防病毒软件阻止
echo   3. 文件权限问题
echo.
echo 建议：
echo   1. 右键点击 auto_update_all_tables.bat
echo   2. 选择"以管理员身份运行"
echo   3. 或者，在命令提示符中运行：
echo      cd "C:\TR-master\TR database"
echo      auto_update_all_tables.bat
echo.
pause
