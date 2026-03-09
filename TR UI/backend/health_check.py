#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
健康檢查模組
提供系統健康狀態監控
"""

import os
import shutil
import time
from flask import jsonify
from functools import wraps


def check_database():
    """檢查數據庫連接"""
    try:
        from tr_fill_in_api import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return True, "正常"
    except Exception as e:
        return False, str(e)


def check_disk_space(path="/", min_free_gb=1):
    """檢查磁盤空間"""
    try:
        total, used, free = shutil.disk_usage(path)
        free_gb = free / (1024 ** 3)
        if free_gb >= min_free_gb:
            return True, f"可用 {free_gb:.2f} GB"
        else:
            return False, f"空間不足，僅剩 {free_gb:.2f} GB"
    except Exception as e:
        return False, str(e)


def check_memory():
    """檢查內存使用（簡化版）"""
    try:
        import psutil
        memory = psutil.virtual_memory()
        usage_percent = memory.percent
        if usage_percent < 90:
            return True, f"使用率 {usage_percent:.1f}%"
        else:
            return False, f"內存使用率過高: {usage_percent:.1f}%"
    except ImportError:
        # psutil 未安裝，跳過檢查
        return True, "未安裝 psutil，跳過檢查"
    except Exception as e:
        return False, str(e)


def health_check_endpoint():
    """健康檢查端點"""
    checks = {
        'database': {'status': False, 'message': ''},
        'disk_space': {'status': False, 'message': ''},
        'memory': {'status': False, 'message': ''},
        'timestamp': time.time()
    }
    
    # 檢查數據庫
    db_ok, db_msg = check_database()
    checks['database'] = {'status': db_ok, 'message': db_msg}
    
    # 檢查磁盤空間
    disk_ok, disk_msg = check_disk_space()
    checks['disk_space'] = {'status': disk_ok, 'message': disk_msg}
    
    # 檢查內存
    mem_ok, mem_msg = check_memory()
    checks['memory'] = {'status': mem_ok, 'message': mem_msg}
    
    # 判斷整體健康狀態
    all_healthy = all([
        checks['database']['status'],
        checks['disk_space']['status'],
        checks['memory']['status']
    ])
    
    status_code = 200 if all_healthy else 503
    
    return jsonify({
        'status': 'healthy' if all_healthy else 'unhealthy',
        'checks': checks,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(checks['timestamp']))
    }), status_code


def readiness_check_endpoint():
    """就緒檢查端點（用於 Kubernetes/Docker）"""
    try:
        from tr_fill_in_api import get_db_connection
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        return jsonify({'status': 'ready'}), 200
    except:
        return jsonify({'status': 'not ready'}), 503


def liveness_check_endpoint():
    """存活檢查端點（用於 Kubernetes/Docker）"""
    return jsonify({'status': 'alive'}), 200
