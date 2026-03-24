@echo off
REM PostgreSQL 模式启动脚本

echo ========================================
echo 启动后端服务 (PostgreSQL 模式)
echo ========================================
echo.

REM 设置环境变量
set DB_BACKEND=postgres
set POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/tr_db

echo 数据库后端: PostgreSQL
echo 连接字符串: %POSTGRES_DSN%
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 启动后端服务
echo 正在启动后端服务...
python tr_fill_in_api.py

pause
