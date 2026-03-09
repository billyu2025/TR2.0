# TR Report System 系統優化方案

## 當前系統架構分析

### 現有架構
- **前端**：HTML + Vue.js + Nginx (8000端口)
- **後端**：Flask (Python) (5000端口)
- **數據庫**：SQLite (單文件數據庫)
- **文件系統**：大量文件索引和操作

### 潛在問題

1. **數據庫連接管理**
   - 每次請求都創建新連接，沒有連接池
   - SQLite 在多用戶並發時性能有限
   - 連接沒有正確關閉可能導致資源洩漏

2. **Flask 服務器**
   - 使用開發服務器（`app.run()`），不適合生產環境
   - 單線程處理，無法充分利用多核CPU
   - 沒有進程管理，進程崩潰會導致服務中斷

3. **性能瓶頸**
   - PDF 生成是同步操作，會阻塞請求
   - 文件下載是同步操作
   - 沒有緩存機制，重複查詢數據庫

4. **穩定性問題**
   - 沒有請求限流，可能被惡意請求攻擊
   - 沒有錯誤監控和告警
   - 沒有自動重啟機制

5. **資源管理**
   - 沒有連接數限制
   - 沒有內存監控
   - 沒有日誌輪轉

## 優化方案

### 階段一：數據庫優化（優先級：高）

#### 1.1 實現連接池
```python
# 使用 SQLite 連接池
from sqlite3 import Connection
import threading
from queue import Queue

class ConnectionPool:
    def __init__(self, db_path, max_connections=10):
        self.db_path = db_path
        self.max_connections = max_connections
        self.pool = Queue(maxsize=max_connections)
        self.lock = threading.Lock()
        
        # 預先創建連接
        for _ in range(max_connections):
            conn = self._create_connection()
            self.pool.put(conn)
    
    def _create_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    
    def get_connection(self):
        return self.pool.get()
    
    def return_connection(self, conn):
        # 檢查連接是否有效
        try:
            conn.execute("SELECT 1")
            self.pool.put(conn)
        except:
            # 連接已損壞，創建新連接
            conn.close()
            new_conn = self._create_connection()
            self.pool.put(new_conn)
```

#### 1.2 考慮遷移到 PostgreSQL（長期方案）
- SQLite 不適合高並發場景
- PostgreSQL 支持真正的並發讀寫
- 更好的性能監控和優化工具

### 階段二：服務器優化（優先級：高）

#### 2.1 使用 Gunicorn 作為 WSGI 服務器
```bash
# 安裝 Gunicorn
pip install gunicorn

# 啟動命令
gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 --max-requests 1000 --max-requests-jitter 50 tr_fill_in_api:app
```

**配置說明**：
- `-w 4`：4個工作進程（根據CPU核心數調整）
- `--timeout 120`：請求超時時間120秒
- `--max-requests 1000`：每個工作進程處理1000個請求後重啟（防止內存洩漏）
- `--max-requests-jitter 50`：隨機抖動，避免同時重啟

#### 2.2 使用 Nginx 作為反向代理和負載均衡
```nginx
upstream flask_backend {
    least_conn;  # 使用最少連接負載均衡
    server 127.0.0.1:5000;
    server 127.0.0.1:5001;  # 可以啟動多個實例
    keepalive 32;
}

server {
    listen 8000;
    
    location /api/ {
        proxy_pass http://flask_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # 超時設置
        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
        
        # 緩衝設置
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }
}
```

### 階段三：緩存機制（優先級：中）

#### 3.1 實現 Redis 緩存
```python
import redis
from functools import wraps
import json
import hashlib

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

def cache_result(expire=300):
    """緩存函數結果"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成緩存鍵
            cache_key = f"{func.__name__}:{hashlib.md5(str(args + tuple(kwargs.items())).encode()).hexdigest()}"
            
            # 嘗試從緩存獲取
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
            
            # 執行函數並緩存結果
            result = func(*args, **kwargs)
            redis_client.setex(cache_key, expire, json.dumps(result))
            return result
        return wrapper
    return decorator

# 使用示例
@cache_result(expire=600)  # 緩存10分鐘
def get_orders_list(page, per_page, ...):
    # 原有邏輯
    pass
```

#### 3.2 緩存策略
- **用戶列表**：緩存5分鐘
- **訂單列表**：緩存1分鐘（數據變化頻繁）
- **文件索引**：緩存30分鐘
- **統計數據**：緩存10分鐘

### 階段四：異步處理（優先級：中）

#### 4.1 使用 Celery 處理異步任務
```python
from celery import Celery

celery_app = Celery('tr_system', broker='redis://localhost:6379/0')

@celery_app.task
def generate_pdf_async(order_no):
    """異步生成PDF"""
    # PDF生成邏輯
    pass

# API端點
@app.route('/api/pdf/generate/<int:order_no>', methods=['POST'])
def generate_pdf_endpoint(order_no):
    task = generate_pdf_async.delay(order_no)
    return jsonify({
        'success': True,
        'task_id': task.id,
        'status': 'processing'
    })
```

#### 4.2 任務狀態查詢
```python
@app.route('/api/tasks/<task_id>/status', methods=['GET'])
def get_task_status(task_id):
    task = celery_app.AsyncResult(task_id)
    return jsonify({
        'status': task.status,
        'result': task.result if task.ready() else None
    })
```

### 階段五：監控和日誌（優先級：中）

#### 5.1 實現健康檢查端點
```python
@app.route('/health', methods=['GET'])
def health_check():
    """健康檢查"""
    checks = {
        'database': False,
        'redis': False,
        'disk_space': False
    }
    
    # 檢查數據庫
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        checks['database'] = True
    except:
        pass
    
    # 檢查Redis
    try:
        redis_client.ping()
        checks['redis'] = True
    except:
        pass
    
    # 檢查磁盤空間
    import shutil
    total, used, free = shutil.disk_usage('/')
    checks['disk_space'] = free > 1024 * 1024 * 1024  # 至少1GB
    
    status = 200 if all(checks.values()) else 503
    return jsonify({
        'status': 'healthy' if all(checks.values()) else 'unhealthy',
        'checks': checks
    }), status
```

#### 5.2 實現請求日誌
```python
import logging
from logging.handlers import RotatingFileHandler

# 配置日誌
log_handler = RotatingFileHandler(
    'logs/app.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
log_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
app.logger.addHandler(log_handler)
app.logger.setLevel(logging.INFO)

@app.before_request
def log_request():
    app.logger.info(f"{request.method} {request.path} - {request.remote_addr}")
```

### 階段六：安全優化（優先級：高）

#### 6.1 實現請求限流
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@app.route('/api/orders/list')
@limiter.limit("10 per minute")  # 每分鐘最多10次請求
def get_orders_list():
    pass
```

#### 6.2 實現認證限流
```python
@app.route('/api/auth/login', methods=['POST'])
@limiter.limit("5 per minute")  # 登入嘗試限制
def login():
    pass
```

### 階段七：資源優化（優先級：低）

#### 7.1 數據庫查詢優化
- 已經實現了索引優化（`_ensure_bbs_dd_indexes`）
- 繼續優化慢查詢
- 使用 EXPLAIN QUERY PLAN 分析查詢計劃

#### 7.2 文件操作優化
- 使用異步文件操作
- 實現文件操作隊列
- 限制並發文件操作數量

## 實施優先級

### 立即實施（1-2週）
1. ✅ 數據庫連接池
2. ✅ Gunicorn WSGI 服務器
3. ✅ Nginx 負載均衡配置
4. ✅ 健康檢查端點
5. ✅ 請求限流

### 短期實施（1個月）
1. Redis 緩存機制
2. 異步任務處理（Celery）
3. 日誌系統優化
4. 監控和告警

### 長期規劃（3-6個月）
1. 遷移到 PostgreSQL
2. 微服務架構（如果需要）
3. 容器化部署（Docker）
4. 自動擴展機制

## 性能目標

- **響應時間**：API 響應時間 < 500ms（95%請求）
- **並發能力**：支持至少 50 個並發用戶
- **可用性**：99.9% 在線時間
- **錯誤率**：< 0.1%

## 監控指標

1. **系統指標**
   - CPU 使用率
   - 內存使用率
   - 磁盤 I/O
   - 網絡帶寬

2. **應用指標**
   - 請求響應時間
   - 錯誤率
   - 並發連接數
   - 數據庫查詢時間

3. **業務指標**
   - 用戶登入次數
   - PDF 生成成功率
   - 文件下載次數

## 測試計劃

1. **負載測試**
   - 使用 Apache Bench 或 JMeter
   - 模擬 50-100 個並發用戶
   - 測試各種 API 端點

2. **壓力測試**
   - 逐步增加負載
   - 找出系統瓶頸
   - 測試系統恢復能力

3. **穩定性測試**
   - 長時間運行測試（24小時）
   - 監控內存洩漏
   - 監控錯誤率
