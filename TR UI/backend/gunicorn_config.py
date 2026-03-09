# Gunicorn 配置文件
# 使用方式: gunicorn -c gunicorn_config.py tr_fill_in_api:app

import multiprocessing
import os

# 服務器配置
bind = f"0.0.0.0:{os.getenv('API_PORT', '5000')}"
workers = multiprocessing.cpu_count() * 2 + 1  # 根據CPU核心數自動計算
worker_class = "sync"  # 同步工作器（適合I/O密集型）
worker_connections = 1000
timeout = 120  # 請求超時時間（秒）
keepalive = 5  # Keep-alive 連接時間（秒）

# 進程管理
max_requests = 1000  # 每個工作進程處理1000個請求後重啟（防止內存洩漏）
max_requests_jitter = 50  # 隨機抖動，避免同時重啟
preload_app = True  # 預加載應用（節省內存）

# 日誌配置
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 性能優化
worker_tmp_dir = "/dev/shm"  # 使用內存文件系統（Linux）
graceful_timeout = 30  # 優雅關閉超時時間

# 安全配置
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

def on_starting(server):
    """服務器啟動時執行"""
    print(f"[INFO] Gunicorn 服務器啟動中...")
    print(f"[INFO] 工作進程數: {workers}")
    print(f"[INFO] 綁定地址: {bind}")

def on_reload(server):
    """重載時執行"""
    print(f"[INFO] Gunicorn 服務器重載中...")

def worker_int(worker):
    """工作進程中斷時執行"""
    print(f"[WARNING] 工作進程 {worker.pid} 被中斷")

def pre_fork(server, worker):
    """工作進程創建前執行"""
    pass

def post_fork(server, worker):
    """工作進程創建後執行"""
    print(f"[INFO] 工作進程 {worker.pid} 已創建")

def when_ready(server):
    """服務器準備就緒時執行"""
    print(f"[INFO] Gunicorn 服務器已準備就緒，監聽 {bind}")

def worker_abort(worker):
    """工作進程異常退出時執行"""
    print(f"[ERROR] 工作進程 {worker.pid} 異常退出")
