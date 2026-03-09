# 日誌輸出條件說明

## 日誌輸出機制

系統的日誌會輸出到**多個目標**，每個目標有不同的輸出條件：

### 輸出目標

1. **app.log** - 應用日誌文件（所有日誌）
2. **error.log** - 錯誤日誌文件（僅錯誤）
3. **access.log** - 訪問日誌文件（API 訪問）
4. **控制台** - 標準輸出（根據模式調整）

## 日誌級別和輸出條件

### 日誌級別層次

```
DEBUG < INFO < WARNING < ERROR < CRITICAL
```

### 輸出條件表

| 日誌級別 | app.log | error.log | 控制台（生產模式） | 控制台（調試模式） |
|---------|---------|-----------|------------------|------------------|
| **DEBUG** | ✅ 僅調試模式 | ❌ | ❌ | ✅ |
| **INFO** | ✅ | ❌ | ❌ | ✅ |
| **WARNING** | ✅ | ❌ | ✅ | ✅ |
| **ERROR** | ✅ | ✅ | ✅ | ✅ |
| **CRITICAL** | ✅ | ✅ | ✅ | ✅ |

## 詳細輸出條件

### 1. app.log（應用日誌文件）

**輸出條件：**
- ✅ **生產模式**：INFO 及以上級別（INFO, WARNING, ERROR, CRITICAL）
- ✅ **調試模式**：DEBUG 及以上級別（所有級別）

**示例：**
```python
logger.info("用戶登入成功")        # ✅ 輸出到 app.log
logger.warning("連接數過高")       # ✅ 輸出到 app.log
logger.error("處理失敗")          # ✅ 輸出到 app.log
logger.debug("查詢參數: ...")      # ⚠️ 僅調試模式輸出
```

### 2. error.log（錯誤日誌文件）

**輸出條件：**
- ✅ **僅 ERROR 和 CRITICAL 級別**

**示例：**
```python
logger.info("操作成功")           # ❌ 不輸出到 error.log
logger.warning("警告信息")        # ❌ 不輸出到 error.log
logger.error("處理失敗")          # ✅ 輸出到 error.log
logger.critical("系統崩潰")       # ✅ 輸出到 error.log
```

### 3. access.log（訪問日誌文件）

**輸出條件：**
- ✅ **使用 `access_logger` 記錄的 INFO 級別日誌**

**示例：**
```python
from logger_config import get_access_logger

access_logger = get_access_logger()
access_logger.info(f"API 訪問: {request.path}")  # ✅ 輸出到 access.log
```

**注意：** 當前系統中 `access.log` 需要手動使用 `access_logger` 才會記錄。

### 4. 控制台輸出

**輸出條件：**
- ✅ **生產模式**：WARNING 及以上級別（WARNING, ERROR, CRITICAL）
- ✅ **調試模式**：DEBUG 及以上級別（所有級別）

**示例：**
```python
# 生產模式（DEBUG=False）
logger.info("操作成功")           # ❌ 不輸出到控制台
logger.warning("警告信息")        # ✅ 輸出到控制台
logger.error("處理失敗")          # ✅ 輸出到控制台

# 調試模式（DEBUG=True）
logger.info("操作成功")           # ✅ 輸出到控制台
logger.debug("調試信息")          # ✅ 輸出到控制台
logger.warning("警告信息")        # ✅ 輸出到控制台
```

## 實際使用場景

### 場景1：正常操作（INFO）

```python
logger.info("用戶登入成功")
logger.info("訂單列表查詢完成")
logger.info("PDF 生成成功")
```

**輸出位置：**
- ✅ app.log（生產和調試模式）
- ❌ error.log
- ❌ 控制台（生產模式）
- ✅ 控制台（調試模式）

### 場景2：警告信息（WARNING）

```python
logger.warning("數據庫連接數過高")
logger.warning("磁盤空間不足")
logger.warning("請求超時")
```

**輸出位置：**
- ✅ app.log
- ❌ error.log
- ✅ 控制台（生產和調試模式）

### 場景3：錯誤信息（ERROR）

```python
logger.error("處理請求失敗", exc_info=True)
logger.error("數據庫連接失敗")
logger.error("文件讀取錯誤")
```

**輸出位置：**
- ✅ app.log
- ✅ error.log（單獨記錄，方便追蹤）
- ✅ 控制台（生產和調試模式）

### 場景4：調試信息（DEBUG）

```python
logger.debug("查詢參數: %s", params)
logger.debug("SQL 語句: %s", sql)
logger.debug("執行時間: %.2f 秒", duration)
```

**輸出位置：**
- ✅ app.log（僅調試模式）
- ❌ error.log
- ✅ 控制台（僅調試模式）

## 調試模式 vs 生產模式

### 調試模式（DEBUG=True）

**設置方式：**
```bash
# 環境變量
set DEBUG=True

# 或 .env 文件
DEBUG=True
```

**輸出特點：**
- ✅ 所有級別的日誌都輸出
- ✅ 控制台顯示詳細信息
- ✅ 方便開發和調試

**適用場景：**
- 開發環境
- 問題排查
- 性能分析

### 生產模式（DEBUG=False）

**設置方式：**
```bash
# 環境變量
set DEBUG=False

# 或 .env 文件
DEBUG=False
```

**輸出特點：**
- ✅ 僅重要日誌輸出（INFO 及以上）
- ✅ 控制台僅顯示警告和錯誤
- ✅ 減少日誌量，提高性能

**適用場景：**
- 生產環境
- 正式部署
- 長期運行

## 日誌輸出示例

### 示例1：用戶登入

```python
logger.info("用戶 admin 登入成功")
```

**生產模式輸出：**
```
app.log: 2025-01-27 15:30:45 - tr_system - INFO - 用戶 admin 登入成功
控制台: （不輸出）
```

**調試模式輸出：**
```
app.log: 2025-01-27 15:30:45 - tr_system - INFO - 用戶 admin 登入成功
控制台: 2025-01-27 15:30:45 - tr_system - INFO - 用戶 admin 登入成功
```

### 示例2：數據庫錯誤

```python
logger.error("數據庫連接失敗", exc_info=True)
```

**生產模式輸出：**
```
app.log: 2025-01-27 15:30:46 - tr_system - ERROR - 數據庫連接失敗
error.log: 2025-01-27 15:30:46 - tr_system - ERROR - 數據庫連接失敗
控制台: 2025-01-27 15:30:46 - tr_system - ERROR - 數據庫連接失敗
```

**調試模式輸出：**
```
app.log: 2025-01-27 15:30:46 - tr_system - ERROR - 數據庫連接失敗
error.log: 2025-01-27 15:30:46 - tr_system - ERROR - 數據庫連接失敗
控制台: 2025-01-27 15:30:46 - tr_system - ERROR - 數據庫連接失敗
（包含完整異常堆棧）
```

### 示例3：警告信息

```python
logger.warning("數據庫連接數過高: 25")
```

**生產模式輸出：**
```
app.log: 2025-01-27 15:30:47 - tr_system - WARNING - 數據庫連接數過高: 25
控制台: 2025-01-27 15:30:47 - tr_system - WARNING - 數據庫連接數過高: 25
```

**調試模式輸出：**
```
app.log: 2025-01-27 15:30:47 - tr_system - WARNING - 數據庫連接數過高: 25
控制台: 2025-01-27 15:30:47 - tr_system - WARNING - 數據庫連接數過高: 25
```

## 日誌文件自動管理

### 文件大小限制

- **最大文件大小**：10MB
- **超過限制時**：自動創建備份文件

### 備份文件

- **app.log**：保留 5 個備份（app.log.1 到 app.log.5）
- **error.log**：保留 10 個備份（error.log.1 到 error.log.10）
- **access.log**：保留 5 個備份（access.log.1 到 access.log.5）

### 自動輪轉示例

```
logs/
  app.log          # 當前日誌（10MB）
  app.log.1        # 備份1（舊的）
  app.log.2        # 備份2（更舊的）
  ...
```

## 總結

### 快速參考

| 情況 | app.log | error.log | 控制台（生產） | 控制台（調試） |
|------|---------|-----------|--------------|--------------|
| **正常操作** | ✅ | ❌ | ❌ | ✅ |
| **警告信息** | ✅ | ❌ | ✅ | ✅ |
| **錯誤信息** | ✅ | ✅ | ✅ | ✅ |
| **調試信息** | ⚠️ 僅調試 | ❌ | ❌ | ✅ |

### 關鍵要點

1. **app.log**：記錄所有重要日誌（INFO 及以上）
2. **error.log**：僅記錄錯誤，方便快速定位問題
3. **控制台**：生產模式僅顯示警告和錯誤，調試模式顯示所有日誌
4. **自動輪轉**：日誌文件超過 10MB 時自動備份

### 建議

- **生產環境**：使用 `DEBUG=False`，減少日誌量
- **開發環境**：使用 `DEBUG=True`，查看詳細信息
- **問題排查**：查看 `error.log` 快速定位錯誤
- **性能分析**：查看 `app.log` 了解系統運行情況
