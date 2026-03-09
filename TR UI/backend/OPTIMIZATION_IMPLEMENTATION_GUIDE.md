# TR Report System 優化實施指南

## 快速開始

### 第一步：安裝依賴

```bash
cd backend
pip install gunicorn flask-limiter psutil
```

### 第二步：配置環境變量

創建 `.env` 文件（如果還沒有）：

```env
API_HOST=0.0.0.0
API_PORT=5000
DEBUG=False
DB_PATH=../TR database/data_3years.db
```

### 第三步：啟動生產服務器

**Windows:**
```cmd
cd backend
start_production.bat
```

**Linux/Mac:**
```bash
cd backend
chmod +x start_production.sh
./start_production.sh
```

## 優化實施步驟

### 階段一：基礎優化（立即實施）

#### 1.1 使用 Gunicorn 替代開發服務器

**當前問題：**
- Flask 開發服務器不適合生產環境
- 單線程處理，無法充分利用多核CPU
- 沒有進程管理

**解決方案：**
使用 `start_production.bat` 或 `start_production.sh` 啟動服務

**驗證：**
```bash
# 檢查進程
ps aux | grep gunicorn  # Linux/Mac
tasklist | findstr gunicorn  # Windows

# 檢查健康狀態
curl http://localhost:5000/health
```

#### 1.2 添加健康檢查端點

健康檢查端點已自動添加：
- `GET /health` - 完整健康檢查
- `GET /ready` - 就緒檢查（用於負載均衡器）
- `GET /live` - 存活檢查（用於容器編排）

**測試：**
```bash
curl http://localhost:5000/health
```

#### 1.3 配置 Nginx 負載均衡

編輯 `nginx-1.28.0/conf/nginx.conf`：

```nginx
upstream flask_backend {
    least_conn;
    server 127.0.0.1:5000;
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
    
    location /health {
        proxy_pass http://flask_backend;
        access_log off;
    }
}
```

### 階段二：數據庫優化（1週內）

#### 2.1 實施連接池（可選，如果遇到連接問題）

如果遇到 "database is locked" 錯誤，可以啟用連接池：

1. 修改 `tr_fill_in_api.py`：
```python
from db_pool import init_pool, get_pool

# 在應用啟動時初始化
init_pool(DB_PATH, max_connections=10)

# 修改 get_db_connection 函數
def get_db_connection():
    pool = get_pool()
    return pool.get_connection()
```

**注意：** 當前實現已經使用了 WAL 模式和 busy_timeout，通常不需要連接池。只有在遇到大量並發問題時才需要。

### 階段三：緩存優化（2週內）

#### 3.1 安裝 Redis（可選）

如果需要緩存功能：

```bash
# Windows: 下載 Redis for Windows
# Linux: 
sudo apt-get install redis-server
# Mac:
brew install redis

# 啟動 Redis
redis-server
```

#### 3.2 實施緩存（需要時）

參考 `SYSTEM_OPTIMIZATION_PLAN.md` 中的緩存實現。

### 階段四：監控和日誌（1個月內）

#### 4.1 設置日誌輪轉

日誌文件會自動輪轉（Gunicorn 配置中已設置）：
- `logs/gunicorn_access.log` - 訪問日誌
- `logs/gunicorn_error.log` - 錯誤日誌

#### 4.2 監控系統資源

可以使用以下工具：
- **Windows**: Task Manager, Performance Monitor
- **Linux**: htop, iotop, netstat
- **通用**: Prometheus + Grafana（進階）

## 性能測試

### 使用 Apache Bench 測試

```bash
# 安裝 Apache Bench
# Windows: 下載 Apache HTTP Server
# Linux: sudo apt-get install apache2-utils
# Mac: brew install httpd

# 測試登入端點（100個請求，10個並發）
ab -n 100 -c 10 -p login.json -T application/json http://localhost:5000/api/auth/login

# 測試訂單列表（1000個請求，50個並發）
ab -n 1000 -c 50 http://localhost:5000/api/orders/list?page=1&per_page=100
```

### 使用 curl 測試健康檢查

```bash
# 健康檢查
curl http://localhost:5000/health

# 就緒檢查
curl http://localhost:5000/ready

# 存活檢查
curl http://localhost:5000/live
```

## 故障排查

### 問題1：數據庫鎖定錯誤

**症狀：** `database is locked`

**解決方案：**
1. 檢查是否有長時間運行的查詢
2. 增加 `busy_timeout`（已在代碼中設置為30秒）
3. 考慮使用連接池（見階段二）

### 問題2：內存使用過高

**症狀：** 服務器內存持續增長

**解決方案：**
1. 檢查 `max_requests` 設置（Gunicorn 配置中已設置為1000）
2. 檢查是否有內存洩漏
3. 減少工作進程數

### 問題3：響應時間慢

**症狀：** API 響應時間 > 1秒

**解決方案：**
1. 檢查數據庫查詢是否使用了索引
2. 檢查是否有慢查詢
3. 考慮實施緩存
4. 檢查網絡延遲

### 問題4：並發用戶數不足

**症狀：** 多個用戶同時使用時系統變慢

**解決方案：**
1. 增加 Gunicorn 工作進程數（修改 `gunicorn_config.py`）
2. 實施負載均衡（多個實例）
3. 考慮遷移到 PostgreSQL

## 監控建議

### 關鍵指標

1. **響應時間**
   - 目標：< 500ms（95%請求）
   - 監控：Gunicorn 訪問日誌

2. **錯誤率**
   - 目標：< 0.1%
   - 監控：Gunicorn 錯誤日誌

3. **並發連接數**
   - 目標：支持至少 50 個並發用戶
   - 監控：Nginx 狀態或系統工具

4. **系統資源**
   - CPU 使用率：< 80%
   - 內存使用率：< 80%
   - 磁盤空間：> 10% 可用

### 告警設置

建議設置以下告警：
- 健康檢查失敗
- 錯誤率 > 1%
- 響應時間 > 2秒
- CPU 使用率 > 90%
- 內存使用率 > 90%
- 磁盤空間 < 5%

## 最佳實踐

1. **定期備份數據庫**
   - 建議每天備份一次
   - 保留至少7天的備份

2. **監控日誌文件大小**
   - 定期清理舊日誌
   - 使用日誌輪轉

3. **定期更新依賴**
   - 檢查安全更新
   - 測試後更新

4. **性能測試**
   - 每次重大更新後進行負載測試
   - 記錄性能基準

5. **文檔維護**
   - 記錄配置變更
   - 記錄故障和解決方案

## 下一步

根據實際使用情況，逐步實施：
1. 基礎優化（立即）
2. 緩存機制（如需要）
3. 異步任務（如需要）
4. 監控系統（如需要）

## 聯繫支持

如有問題，請查看：
- `SYSTEM_OPTIMIZATION_PLAN.md` - 詳細優化方案
- 系統日誌文件
- 健康檢查端點
