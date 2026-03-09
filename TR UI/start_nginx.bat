@echo off
REM 启动 Nginx 前端服务器

cd /d "C:\TR-master\TR UI\nginx-1.28.0"
start nginx.exe -p "C:\TR-master\TR UI\nginx-1.28.0" -c conf\nginx.conf

echo Nginx started!
echo Access at: http://localhost:8000
timeout /t 2 /nobreak >nul
