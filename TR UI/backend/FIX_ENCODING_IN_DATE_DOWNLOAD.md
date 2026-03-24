# 修复按日期和按 DD_No 下载的编码错误

## 问题描述

当按 dd_no 和按日期下载时，出现以下错误：
```
UnicodeEncodeError: 'charmap' codec can't encode characters in position 6-11: character maps to <undefined>
```

错误发生在 `get_date_count` 函数中的 `print` 语句，包含中文字符。

## 根本原因

在 Windows NSSM 服务环境中，默认编码是 `charmap`（cp1252），无法处理中文字符。`print` 语句中的中文字符会导致编码错误。

## 解决方案

将所有包含中文的 `print` 语句替换为 `logger` 调用，并包装在 `try-except` 块中以避免编码错误。

### 修复的函数

**`get_date_count()` 函数**（第 4597-4785 行）

**修改前：**
```python
print(f"[API] 开始批量查询 {len(order_nos)} 个订单的日期...")
print(f"[API] 批量查询完成，找到 {len(unique_dates)} 个唯一日期")
print(f"[API] 批量查询失败，回退到逐个查询: {e}")
print(f"[API] 处理 Order {order_no} 时出错: {e2}")
print(f"[API] 警告: 没有找到任何日期，使用默认值 1")
print(f"[API] 找到 {date_count} 个唯一的日期: {sorted(unique_dates) if unique_dates else '无'}")
```

**修改后：**
```python
try:
    logger.info("[API] Starting batch query for " + str(len(order_nos)) + " orders dates...")
except (UnicodeEncodeError, UnicodeDecodeError, Exception):
    pass

try:
    logger.info("[API] Batch query completed, found " + str(len(unique_dates)) + " unique dates")
except (UnicodeEncodeError, UnicodeDecodeError, Exception):
    pass

try:
    logger.warning("[API] Batch query failed, falling back to individual queries: " + str(e))
except (UnicodeEncodeError, UnicodeDecodeError, Exception):
    pass

try:
    logger.warning("[API] Error processing Order " + str(order_no) + ": " + str(e2))
except (UnicodeEncodeError, UnicodeDecodeError, Exception):
    pass

try:
    logger.warning("[API] Warning: No dates found, using default value 1")
except (UnicodeEncodeError, UnicodeDecodeError, Exception):
    pass

try:
    dates_str = str(sorted(unique_dates)) if unique_dates else "none"
    logger.info("[API] Found " + str(date_count) + " unique dates: " + dates_str)
except (UnicodeEncodeError, UnicodeDecodeError, Exception):
    pass
```

### 其他修复

同时修复了其他包含中文的 `print` 语句：
- `_ensure_bbs_dd_indexes()` 函数中的索引创建日志（第 441, 445, 449 行）
- `logger.error()` 调用中的中文错误消息（第 4599, 5386 行）

## 修复要点

1. **使用 logger 替代 print**：`logger` 使用 UTF-8 编码，可以正确处理中文字符
2. **字符串拼接替代 f-string**：避免 f-string 在编码错误时立即失败
3. **异常处理**：所有 logger 调用都包装在 `try-except` 块中，确保编码错误不会中断程序执行
4. **英文日志消息**：关键日志消息使用英文，避免编码问题

## 测试

修复后，应该能够：
1. 按日期下载 Stockist 和 Test Report
2. 按 DD_No 下载 Stockist 和 Test Report
3. 获取日期数量（`get_date_count` API）
4. 所有操作都不会因为编码错误而失败

## 相关文件

- `backend/tr_fill_in_api.py` - 主要修复文件
  - `get_date_count()` 函数（第 4597-4785 行）
  - `_ensure_bbs_dd_indexes()` 函数（第 441-449 行）
  - 错误处理中的 logger 调用
