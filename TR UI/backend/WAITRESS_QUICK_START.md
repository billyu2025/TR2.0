# Waitress 快速啟動指南

## 問題解決

如果遇到以下錯誤：
```
TypeError: Flask.__call__() missing 2 required positional arguments
```

**原因：** `--call` 參數使用不正確

**解決方法：** 不要使用 `--call` 參數，直接指定應用

## 正確的啟動方式

### 方法一：使用 Python 腳本（推薦）

```bash
cd "C:\TR-master\TR UI\backend"
python start_waitress.py
```

### 方法二：使用批處理腳本

```cmd
cd "C:\TR-master\TR UI\backend"
start_production_waitress.bat
```

### 方法三：命令行（正確語法）

```bash
cd "C:\TR-master\TR UI\backend"
waitress-serve --host=0.0.0.0 --port=5000 --threads=4 tr_fill_in_api:app
```

**注意：** 不要使用 `--call` 參數！

## 參數說明

### 正確的語法

```bash
waitress-serve [選項] 模組:應用
```

例如：
```bash
waitress-serve --host=0.0.0.0 --port=5000 --threads=4 tr_fill_in_api:app
```

### 錯誤的語法

```bash
# ❌ 錯誤：不要使用 --call
waitress-serve --call "tr_fill_in_api:app"

# ✅ 正確：直接指定應用
waitress-serve tr_fill_in_api:app
```

## 完整啟動命令

### 基本啟動

```bash
waitress-serve --host=0.0.0.0 --port=5000 --threads=4 tr_fill_in_api:app
```

### 帶更多選項

```bash
waitress-serve \
  --host=0.0.0.0 \
  --port=5000 \
  --threads=4 \
  --channel-timeout=120 \
  --connection-limit=1000 \
  tr_fill_in_api:app
```

## 驗證運行

啟動後，應該看到類似輸出：

```
============================================================
TR Report System - Waitress 服務器
============================================================
監聽地址: http://0.0.0.0:5000
線程數: 4
工作模式: 生產環境
============================================================
按 Ctrl+C 停止服務器
============================================================
```

然後測試：

```bash
curl http://localhost:5000/health
```

## 停止服務器

按 `Ctrl+C` 停止服務器
