# Windows 部署指南 - 使用 Waitress

## 問題說明

Gunicorn 在 Windows 上不兼容，因為它依賴 `fcntl` 模組（僅在 Unix/Linux 上可用）。

**錯誤信息：**
```
ModuleNotFoundError: No module named 'fcntl'
```

## 解決方案：使用 Waitress

Waitress 是一個純 Python 實現的 WSGI 服務器，完全兼容 Windows，功能類似 Gunicorn。

## 第一步：安裝 Waitress

```bash
cd "C:\TR-master\TR UI\backend"
pip install waitress
```

或者從 requirements.txt 安裝：

```bash
pip install -r requirements.txt
```

## 第二步：啟動服務器

### 方法一：使用啟動腳本（推薦）

```cmd
cd "C:\TR-master\TR UI\backend"
start_production_waitress.bat
```

### 方法二：命令行啟動

```bash
cd "C:\TR-master\TR UI\backend"
waitress-serve --host=0.0.0.0 --port=5000 --threads=4 --call "tr_fill_in_api:app"
```

### 方法三：使用 Python 代碼啟動

創建 `start_waitress.py`：

```python
from waitress import serve
from tr_fill_in_api import app
import os

if __name__ == '__main__':
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', '5000'))
    threads = 4
    
    print(f"正在啟動 Waitress 服務器...")
    print(f"地址: http://{host}:{port}")
    print(f"線程數: {threads}")
    print("按 Ctrl+C 停止服務器")
    
    serve(app, host=host, port=port, threads=threads)
```

然後運行：

```bash
python start_waitress.py
```

## Waitress 配置選項

### 基本參數

```bash
waitress-serve \
  --host=0.0.0.0 \          # 監聽地址
  --port=5000 \              # 端口
  --threads=4 \             # 線程數（建議為 CPU 核心數）
  --call "tr_fill_in_api:app"  # 應用入口
```

### 高級參數

```bash
waitress-serve \
  --host=0.0.0.0 \
  --port=5000 \
  --threads=4 \
  --channel-timeout=120 \   # 通道超時（秒）
  --connection-limit=1000 \ # 最大連接數
  --cleanup-interval=30 \   # 清理間隔（秒）
  --ident=TR-System \       # 服務器標識
  --call "tr_fill_in_api:app"
```

## 性能對比

### Waitress vs Gunicorn

| 特性 | Waitress | Gunicorn |
|------|----------|----------|
| Windows 支持 | ✅ 完全支持 | ❌ 不支持 |
| Linux 支持 | ✅ 支持 | ✅ 支持 |
| 多進程 | ❌ 不支持 | ✅ 支持 |
| 多線程 | ✅ 支持 | ✅ 支持 |
| 性能 | 良好 | 優秀 |
| 穩定性 | 優秀 | 優秀 |

### 線程數建議

- **2核 CPU**：2-4 個線程
- **4核 CPU**：4-8 個線程
- **8核 CPU**：8-16 個線程

**公式：** `線程數 = CPU核心數 × 2`

## 驗證服務運行

### 1. 檢查進程

```cmd
tasklist | findstr python
```

### 2. 測試 API

```bash
# 使用 curl
curl http://localhost:5000/health

# 或使用瀏覽器
# http://localhost:5000/health
```

### 3. 查看日誌

Waitress 的日誌會輸出到控制台。如果需要保存日誌，可以使用重定向：

```cmd
waitress-serve --host=0.0.0.0 --port=5000 --threads=4 --call "tr_fill_in_api:app" > logs\waitress.log 2>&1
```

## 停止服務器

- 在運行窗口按 `Ctrl+C`
- 或在任務管理器中結束 Python 進程

## 生產環境建議

### 1. 使用進程管理器

**使用 NSSM（Non-Sucking Service Manager）將 Waitress 註冊為 Windows 服務：**

1. 下載 NSSM：https://nssm.cc/download
2. 安裝服務：
   ```cmd
   nssm install TR-System "C:\Python310\python.exe" "C:\TR-master\TR UI\backend\start_waitress.py"
   ```
3. 啟動服務：
   ```cmd
   nssm start TR-System
   ```

### 2. 使用 Nginx 反向代理

配置 Nginx 將請求轉發到 Waitress：

```nginx
upstream waitress_backend {
    server 127.0.0.1:5000;
    keepalive 32;
}

server {
    listen 8000;
    
    location /api/ {
        proxy_pass http://waitress_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }
}
```

### 3. 日誌管理

創建日誌輪轉腳本或使用 Windows 任務計劃程序定期清理舊日誌。

## 故障排查

### 問題1：端口已被占用

**解決方法：**
```cmd
# 查找占用端口的進程
netstat -ano | findstr :5000

# 結束進程（替換 PID）
taskkill /PID <PID> /F
```

### 問題2：模組導入錯誤

**解決方法：**
```bash
# 確保在正確的目錄
cd "C:\TR-master\TR UI\backend"

# 檢查依賴
pip install -r requirements.txt
```

### 問題3：線程數設置過高

**症狀：** 系統變慢，響應時間增加

**解決方法：** 減少線程數
```bash
waitress-serve --host=0.0.0.0 --port=5000 --threads=2 --call "tr_fill_in_api:app"
```

## 性能優化建議

### 1. 調整線程數

根據實際負載調整：
- 輕負載：2-4 個線程
- 中等負載：4-8 個線程
- 高負載：8-16 個線程

### 2. 使用連接池

如果遇到數據庫連接問題，可以啟用連接池（見 `db_pool.py`）。

### 3. 啟用緩存

考慮使用 Redis 緩存查詢結果（可選）。

## 快速參考

```bash
# 安裝
pip install waitress

# 啟動（基本）
waitress-serve --host=0.0.0.0 --port=5000 --threads=4 --call "tr_fill_in_api:app"

# 啟動（使用腳本）
start_production_waitress.bat

# 停止
Ctrl+C
```

## 總結

對於 Windows 系統：
- ✅ **推薦使用 Waitress**（完全兼容，穩定可靠）
- ❌ **不推薦使用 Gunicorn**（不兼容 Windows）
- 🔄 **可選：使用 WSL**（如果需要在 Windows 上使用 Gunicorn）

Waitress 在 Windows 上提供與 Gunicorn 類似的功能和性能，是 Windows 環境下的最佳選擇。
