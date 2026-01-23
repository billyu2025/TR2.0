@echo off
chcp 65001 >nul
echo ========================================
echo TR系统文件提取脚本批量执行工具
echo ========================================
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 记录开始时间
set START_TIME=%time%
echo [开始时间] %date% %time%
echo.

REM 执行四个提取脚本
echo ========================================
echo [1/4] 开始执行 Ext_Stockist.py
echo ========================================
python "Ext_Stockist.py"
if %errorlevel% neq 0 (
    echo [错误] Ext_Stockist.py 执行失败
) else (
    echo [完成] Ext_Stockist.py 执行成功
)
echo.

echo ========================================
echo [2/4] 开始执行 Ext_Testreport_IATFormal.py
echo ========================================
python "Ext_Testreport_IATFormal.py"
if %errorlevel% neq 0 (
    echo [错误] Ext_Testreport_IATFormal.py 执行失败
) else (
    echo [完成] Ext_Testreport_IATFormal.py 执行成功
)
echo.

echo ========================================
echo [3/4] 开始执行 Ext_Testreport_PrivateFormal.py
echo ========================================
python "Ext_Testreport_PrivateFormal.py"
if %errorlevel% neq 0 (
    echo [错误] Ext_Testreport_PrivateFormal.py 执行失败
) else (
    echo [完成] Ext_Testreport_PrivateFormal.py 执行成功
)
echo.

echo ========================================
echo [4/4] 开始执行 Ext_Testreport_PrivatePrelim.py
echo ========================================
python "Ext_Testreport_PrivatePrelim.py"
if %errorlevel% neq 0 (
    echo [错误] Ext_Testreport_PrivatePrelim.py 执行失败
) else (
    echo [完成] Ext_Testreport_PrivatePrelim.py 执行成功
)
echo.

REM 记录结束时间
set END_TIME=%time%
echo ========================================
echo [执行完成] 所有脚本执行完毕
echo [开始时间] %START_TIME%
echo [结束时间] %END_TIME%
echo ========================================
echo.

REM 等待用户按键后关闭（可选，如果不需要可以删除下面两行）
pause
