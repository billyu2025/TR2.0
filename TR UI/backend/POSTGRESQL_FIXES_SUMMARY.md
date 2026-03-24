# PostgreSQL 兼容性修复总结

## 修复的问题

### 1. 会话过期时间解析错误
**错误**: `'datetime.datetime' object has no attribute 'endswith'`

**原因**: PostgreSQL 返回的是 datetime 对象，而代码假设是字符串。

**修复**: 在 `_get_session()` 函数中添加类型检查，支持 datetime 对象和字符串两种格式。

### 2. 表名大小写问题
**错误**: `relation "tr_report_deduplication" does not exist`

**原因**: PostgreSQL 表名是大小写敏感的，需要使用引号包裹。

**修复**: 
- 所有表名使用条件判断：`'"TR_Report_Deduplication"' if is_postgres() else 'TR_Report_Deduplication'`
- 所有列名使用引号包裹：`"Order_No"`, `"Del_Date"` 等

### 3. SQL 占位符问题
**错误**: `the query has 0 placeholders but 1 parameters were passed`

**原因**: 硬编码的 `?` 占位符在 PostgreSQL 中应该使用 `%s`。

**修复**: 所有查询使用 `db_placeholders(count)` 函数，自动根据数据库类型返回正确的占位符。

### 4. GROUP_CONCAT 函数兼容性
**问题**: SQLite 使用 `GROUP_CONCAT`，PostgreSQL 使用 `string_agg`。

**修复**: 在查询中根据数据库类型选择正确的函数。

## 修复的文件和函数

### tr_fill_in_api.py

1. **`_get_session(token)`** (第 984-1030 行)
   - 修复会话过期时间解析
   - 修复 SQL 占位符

2. **`get_orders_list()`** (第 2758-2970 行)
   - 修复表名大小写
   - 修复所有 WHERE 条件中的占位符
   - 修复列名引用（使用引号）
   - 修复 LIMIT/OFFSET 占位符

3. **`get_job_statistics()`** (第 3070-3140 行)
   - 修复表名大小写
   - 修复 WHERE 条件占位符
   - 修复 GROUP_CONCAT 函数兼容性

4. **PDF 生成相关函数** (第 3390 行)
   - 修复表名和列名引用

## 使用的辅助函数

- `is_postgres()`: 判断当前数据库类型
- `db_placeholders(count)`: 获取正确的占位符（`%s` 或 `?`）

## 表名处理模式

```python
# PostgreSQL 表名需要引号包裹
table_dedup = '"TR_Report_Deduplication"' if is_postgres() else 'TR_Report_Deduplication'
table_pdf = '"PDF_Status"' if is_postgres() else 'PDF_Status'
```

## 列名处理模式

```python
# PostgreSQL 列名需要引号包裹
f'o."Order_No" = p."Order_No"'
f'"Del_Date" >= {db_placeholders(1)}'
```

## 下一步

重启服务以应用所有修复：

```powershell
.\fix_and_restart.bat
```

或

```powershell
.\force_restart_complete.ps1
```
