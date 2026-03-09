@echo off
REM Celery Worker 启动脚本 (Windows)
REM 使用 eventlet 池以支持 Windows

cd /d "%~dp0"

echo ========================================
echo TR Backend Celery Worker
echo ========================================
echo.

REM 检查 Redis 连接
python -c "import redis; r = redis.Redis(host='localhost', port=6379, db=0); print('Redis 连接:', '成功' if r.ping() else '失败')" 2>nul
if errorlevel 1 (
    echo 错误: Redis 未运行或连接失败
    echo 请确保 Redis 已启动
    pause
    exit /b 1
)

echo 正在启动 Celery Worker...
echo.

REM 启动 Celery Worker (使用 eventlet 池)
celery -A celery_app worker --pool=eventlet --concurrency=4 --loglevel=info

pause
