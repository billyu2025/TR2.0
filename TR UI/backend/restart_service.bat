@echo off
REM 简单的服务重启脚本
cd /d "%~dp0"
echo 正在重启 TR-Backend 服务...
nssm-2.24\win64\nssm.exe restart TR-Backend
timeout /t 3 /nobreak >nul
nssm-2.24\win64\nssm.exe status TR-Backend
echo.
echo 完成！
pause
