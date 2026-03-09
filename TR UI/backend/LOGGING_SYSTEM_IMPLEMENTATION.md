# 統一日誌系統實施總結

## 已完成的實施

### 1. 創建日誌配置模組

**文件：** `backend/logger_config.py`

**功能：**
- ✅ 統一日誌格式
- ✅ 日誌文件自動輪轉（10MB，保留5個文件）
- ✅ 分離錯誤日誌（單獨文件，保留10個）
- ✅ 訪問日誌（單獨文件）
- ✅ 控制台輸出（根據調試模式調整級別）

**日誌文件：**
- `logs/app.log` - 所有應用日誌
- `logs/error.log` - 僅錯誤日誌
- `logs/access.log` - API 訪問日誌

### 2. 集成到主應用

**文件：** `backend/tr_fill_in_api.py`

**修改：**
- ✅ 導入日誌模組
- ✅ 初始化日誌系統
- ✅ 替換關鍵的 print 語句為 logger

**已替換的日誌：**
- ✅ 所有 `[INFO]` 標記的 print → `logger.info()`
- ✅ 所有 `[WARNING]` 標記的 print → `logger.warning()`
- ✅ 所有 `[ERROR]` 標記的 print → `logger.error()`
- ✅ 啟動信息使用 logger

## 日誌級別

### 日誌級別說明

1. **DEBUG** - 詳細調試信息（僅調試模式）
2. **INFO** - 一般信息（正常操作）
3. **WARNING** - 警告信息（潛在問題）
4. **ERROR** - 錯誤信息（需要關注）
5. **CRITICAL** - 嚴重錯誤（系統可能無法繼續）

### 使用建議

```python
# 一般信息
logger.info("用戶登入成功")

# 警告
logger.warning("數據庫連接數過高")

# 錯誤（帶異常信息）
logger.error("處理請求失敗", exc_info=True)

# 調試信息
logger.debug("查詢參數: %s", params)
```

## 日誌格式

### 標準格式

```
2025-01-27 15:30:45 - tr_system - INFO - 用戶登入成功
2025-01-27 15:30:46 - tr_system - ERROR - 處理請求失敗
Traceback (most recent call last):
  ...
```

### 格式組成

- **時間戳**：`2025-01-27 15:30:45`
- **日誌器名稱**：`tr_system`
- **級別**：`INFO`、`ERROR` 等
- **消息**：實際日誌內容

## 日誌文件管理

### 自動輪轉

- **最大文件大小**：10MB
- **備份文件數**：5個（app.log）、10個（error.log）
- **編碼**：UTF-8

### 文件位置

```
backend/
  logs/
    app.log          # 所有日誌
    app.log.1        # 備份1
    app.log.2        # 備份2
    ...
    error.log        # 錯誤日誌
    error.log.1     # 錯誤備份1
    ...
    access.log       # 訪問日誌
```

## 使用方式

### 在代碼中使用

```python
from logger_config import get_logger

# 獲取日誌器
logger = get_logger()

# 記錄日誌
logger.info("操作成功")
logger.warning("警告信息")
logger.error("錯誤信息", exc_info=True)
```

### 訪問日誌

```python
from logger_config import get_access_logger

access_logger = get_access_logger()
access_logger.info(f"API 訪問: {request.path} - {request.method}")
```

## 後續優化建議

### 1. 逐步替換所有 print 語句

**當前狀態：**
- ✅ 已替換關鍵的 INFO/WARNING/ERROR 日誌
- ⚠️ 仍有部分 print 語句需要替換

**建議：**
- 逐步替換剩餘的 print 語句
- 優先替換錯誤處理和關鍵操作

### 2. 添加請求日誌中間件

**建議實施：**
```python
@app.before_request
def log_request():
    access_logger.info(f"{request.method} {request.path} - {request.remote_addr}")

@app.after_request
def log_response(response):
    access_logger.info(f"Response: {response.status_code}")
    return response
```

### 3. 添加性能日誌

**建議實施：**
```python
import time

@app.before_request
def before_request():
    g.start_time = time.time()

@app.after_request
def after_request(response):
    duration = time.time() - g.start_time
    if duration > 1.0:  # 記錄超過1秒的請求
        logger.warning(f"慢請求: {request.path} - {duration:.2f}秒")
    return response
```

## 驗證日誌系統

### 1. 檢查日誌文件

```bash
# 查看應用日誌
type backend\logs\app.log

# 查看錯誤日誌
type backend\logs\error.log

# 查看訪問日誌
type backend\logs\access.log
```

### 2. 測試日誌級別

啟動服務器後，應該看到：
- 控制台輸出日誌（根據 DEBUG_MODE）
- 日誌文件自動創建
- 日誌格式統一

### 3. 驗證日誌輪轉

當日誌文件超過 10MB 時：
- 自動創建備份文件
- 保留指定數量的備份

## 注意事項

### 1. 日誌目錄權限

確保 `backend/logs/` 目錄有寫入權限。

### 2. 日誌文件大小

定期檢查日誌文件大小，必要時手動清理舊日誌。

### 3. 敏感信息

避免在日誌中記錄：
- 密碼
- 敏感令牌
- 個人隱私信息

## 總結

✅ **已完成：**
- 統一日誌系統配置
- 關鍵日誌語句替換
- 日誌文件自動管理

🔄 **進行中：**
- 逐步替換剩餘 print 語句

📋 **後續計劃：**
- 添加請求日誌中間件
- 添加性能監控日誌
- 完善日誌分析工具

統一日誌系統已成功實施，系統的可維護性和可追蹤性得到顯著提升！
