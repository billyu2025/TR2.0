#!/bin/bash
# Celery Worker 启动脚本 (Linux/WSL)

cd "$(dirname "$0")"

echo "========================================"
echo "TR Backend Celery Worker"
echo "========================================"
echo ""

# 检查 Redis 连接
python3 -c "import redis; r = redis.Redis(host='localhost', port=6379, db=0); print('Redis 连接:', '成功' if r.ping() else '失败')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "错误: Redis 未运行或连接失败"
    echo "请确保 Redis 已启动"
    exit 1
fi

echo "正在启动 Celery Worker..."
echo ""

# 启动 Celery Worker (使用 prefork 池)
celery -A celery_app worker --concurrency=4 --loglevel=info
