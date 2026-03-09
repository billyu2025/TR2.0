#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Celery 应用配置
"""

from celery import Celery
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# Redis 配置
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

# 构建 Redis URL
if REDIS_PASSWORD:
    redis_url = f'redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'
else:
    redis_url = f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'

# 创建 Celery 应用
celery_app = Celery(
    'tr_backend',
    broker=redis_url,
    backend=redis_url
)

# Celery 配置
celery_app.conf.update(
    # 任务序列化
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # 时区
    timezone='UTC',
    enable_utc=True,
    
    # 任务跟踪
    task_track_started=True,
    task_send_sent_event=True,
    
    # 任务超时
    task_time_limit=30 * 60,  # 30 分钟硬超时
    task_soft_time_limit=25 * 60,  # 25 分钟软超时
    
    # Worker 配置
    worker_prefetch_multiplier=1,  # 防止任务堆积
    worker_max_tasks_per_child=50,  # 防止内存泄漏
    
    # 结果过期时间
    result_expires=3600,  # 1 小时后过期
    
    # 任务路由（可选）
    task_routes={
        'tasks.generate_pdf': {'queue': 'pdf'},
        'tasks.batch_download': {'queue': 'download'},
    },
    
    # 任务优先级（可选）
    task_default_priority=5,
    
    # 任务重试配置
    task_acks_late=True,  # 任务完成后才确认
    task_reject_on_worker_lost=True,  # Worker 崩溃时重新排队
)

# 自动发现任务
celery_app.autodiscover_tasks(['tasks'])

print(f"[Celery] 已配置，Redis: {redis_url}")
