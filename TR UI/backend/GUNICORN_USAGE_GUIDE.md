# Gunicorn 使用指南

## 第一步：安裝 Gunicorn

### 方法一：使用 pip 安裝（推薦）

```bash
cd "C:\TR-master\TR UI\backend"
pip install gunicorn
```

### 方法二：從 requirements.txt 安裝

```bash
cd "C:\TR-master\TR UI\backend"
pip install -r requirements.txt
```

### 驗證安裝

```bash
python -c "import gunicorn; print('Gunicorn 版本:', gunicorn.__version__)"
```

或者：

```bash
gunicorn --version
```

## 第二步：準備環境

### 1. 創建日誌目錄

```bash
cd "C:\TR-master\TR UI\backend"
mkdir logs
```

### 2. 檢查配置文件

確保以下文件存在：
- `gunicorn_config.py` - Gunicorn 配置文件
- `tr_fill_in_api.py` - Flask 應用主文件

## 第三步：啟動 Gunicorn

### 方法一：使用配置文件（推薦）

```bash
cd "C:\TR-master\TR UI\backend"
gunicorn -c gunicorn_config.py tr_fill_in_api:app
```

### 方法二：使用命令行參數

```bash
cd "C:\TR-master\TR UI\backend"
gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 tr_fill_in_api:app
```

參數說明：
- `-w 4`：4個工作進程
- `-b 0.0.0.0:5000`：綁定地址和端口
- `--timeout 120`：請求超時時間（秒）

### 方法三：使用啟動腳本（Windows）

```cmd
cd "C:\TR-master\TR UI\backend"
start_production.bat
```

## 第四步：驗證服務運行

### 1. 檢查進程

**Windows:**
```cmd
tasklist | findstr gunicorn
```

**PowerShell:**
```powershell
Get-Process | Where-Object {$_.ProcessName -like "*python*"} | Select-Object ProcessName, Id, CPU
```

### 2. 測試 API

```bash
# 測試健康檢查
curl http://localhost:5000/health

# 或者使用瀏覽器訪問
# http://localhost:5000/health
```

### 3. 檢查日誌

```bash
# 查看訪問日誌
type logs\gunicorn_access.log

# 查看錯誤日誌
type logs\gunicorn_error.log
```

## 第五步：停止 Gunicorn

### 方法一：在運行窗口按 Ctrl+C

如果是在命令行窗口運行的，直接按 `Ctrl+C` 即可停止。

### 方法二：使用任務管理器

1. 打開任務管理器（Ctrl+Shift+Esc）
2. 找到 Python 進程
3. 結束進程

### 方法三：使用命令行（Windows）

```cmd
# 查找進程 ID
tasklist | findstr python

# 結束進程（替換 PID 為實際進程 ID）
taskkill /PID <PID> /F
```

## 配置說明

### 當前配置文件：`gunicorn_config.py`

主要配置項：

```python
workers = 4  # 工作進程數（根據 CPU 核心數自動計算）
timeout = 120  # 請求超時時間（秒）
max_requests = 1000  # 每個進程處理1000個請求後重啟
accesslog = "logs/gunicorn_access.log"  # 訪問日誌
errorlog = "logs/gunicorn_error.log"  # 錯誤日誌
```

### 調整工作進程數

根據您的 CPU 核心數調整：

```python
# 公式：workers = CPU核心數 × 2 + 1
# 例如：4核 CPU → 4 × 2 + 1 = 9 個工作進程
```

**建議：**
- 2核 CPU：4-5 個工作進程
- 4核 CPU：8-9 個工作進程
- 8核 CPU：16-17 個工作進程

## 常見問題

### 問題1：端口已被占用

**錯誤信息：**
```
[ERROR] Connection in use: ('0.0.0.0', 5000)
```

**解決方法：**
1. 停止正在運行的 Flask 開發服務器
2. 或者修改端口：
   ```bash
   set API_PORT=5001
   gunicorn -c gunicorn_config.py tr_fill_in_api:app
   ```

### 問題2：模組導入錯誤

**錯誤信息：**
```
ModuleNotFoundError: No module named 'xxx'
```

**解決方法：**
1. 確保在正確的目錄運行
2. 檢查 Python 環境和依賴：
   ```bash
   pip install -r requirements.txt
   ```

### 問題3：權限錯誤

**錯誤信息：**
```
PermissionError: [Errno 13] Permission denied
```

**解決方法：**
1. 確保有寫入日誌目錄的權限
2. 以管理員身份運行（如果需要）

### 問題4：Windows 上 Gunicorn 不支持

**說明：**
Gunicorn 主要設計用於 Linux/Unix 系統。在 Windows 上：
- 可以使用，但功能有限
- 建議使用 WSL（Windows Subsystem for Linux）
- 或者考慮使用 Waitress（Windows 兼容的 WSGI 服務器）

**Windows 替代方案：Waitress**
```bash
pip install waitress
waitress-serve --host=0.0.0.0 --port=5000 tr_fill_in_api:app
```

## 性能監控

### 查看實時日誌

```bash
# Windows PowerShell
Get-Content logs\gunicorn_access.log -Wait -Tail 20

# 或者使用 Notepad++ 等編輯器打開日誌文件
```

### 監控進程狀態

```powershell
# 查看進程資源使用
Get-Process | Where-Object {$_.ProcessName -like "*python*"} | Format-Table ProcessName, Id, CPU, WorkingSet -AutoSize
```

## 最佳實踐

### 1. 生產環境

- ✅ 使用配置文件啟動
- ✅ 設置適當的工作進程數
- ✅ 啟用日誌記錄
- ✅ 設置請求超時
- ✅ 使用 Nginx 作為反向代理

### 2. 開發環境

- 可以繼續使用 Flask 開發服務器
- 或者使用 Gunicorn 但減少工作進程數（1-2個）

### 3. 部署建議

- 使用進程管理器（如 systemd、supervisor）
- 設置自動重啟
- 監控日誌和資源使用
- 定期備份數據

## 下一步

1. ✅ 安裝 Gunicorn
2. ✅ 測試啟動
3. ✅ 驗證服務運行
4. 🔄 配置 Nginx 反向代理（可選）
5. 🔄 設置自動啟動（可選）

## 快速參考

```bash
# 安裝
pip install gunicorn

# 啟動（使用配置文件）
gunicorn -c gunicorn_config.py tr_fill_in_api:app

# 啟動（命令行參數）
gunicorn -w 4 -b 0.0.0.0:5000 tr_fill_in_api:app

# 停止
Ctrl+C  # 或在任務管理器中結束進程

# 查看日誌
type logs\gunicorn_access.log
type logs\gunicorn_error.log
```
