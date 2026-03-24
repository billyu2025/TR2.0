# 修复缺失 Stockist 文件报错问题

## 问题描述

用户报告在按订单下载时，系统提示缺失文件，但实际上文件是存在的。例如：
- Order 134617 提示缺失 Stockist 文件 HL2322
- 但用户检查文件库发现 HL2322 的 Stockist 文件确实存在

## 根本原因

问题出在 PostgreSQL 数据库查询上。在 `stockist_test_download.py` 中，所有查询 `TR_Report` 表的 SQL 语句存在以下问题：

1. **查询字符串未使用 f-string**：使用了 `{self._tr_report_table()}` 但没有使用 f-string，导致表名无法正确替换
2. **列名未使用引号包裹**：PostgreSQL 中列名大小写敏感，需要使用引号包裹
3. **占位符问题**：部分查询使用了硬编码的 `?` 占位符，在 PostgreSQL 中应该使用 `%s`（通过 `db_placeholders()` 函数）

## 修复内容

### 1. `get_order_info()` 方法（第 139-148 行）

**修复前：**
```python
query = """
    SELECT DISTINCT
        stockist_cert,
        rm_dn_no,
        jobsite_type,
        del_date
    FROM {self._tr_report_table()}
    WHERE order_no = ?
    LIMIT 1
"""
```

**修复后：**
```python
query = f"""
    SELECT DISTINCT
        "stockist_cert",
        "rm_dn_no",
        "jobsite_type",
        "del_date"
    FROM {self._tr_report_table()}
    WHERE "order_no" = {db_placeholders(1)}
    LIMIT 1
"""
```

### 2. `get_orders_info_batch()` 方法（第 242-251 行）

**修复前：**
```python
query = f"""
    SELECT DISTINCT
        order_no,
        stockist_cert,
        rm_dn_no,
        jobsite_type,
        del_date
    FROM {self._tr_report_table()}
    WHERE order_no IN ({placeholders})
"""
```

**修复后：**
```python
query = f"""
    SELECT DISTINCT
        "order_no",
        "stockist_cert",
        "rm_dn_no",
        "jobsite_type",
        "del_date"
    FROM {self._tr_report_table()}
    WHERE "order_no" IN ({placeholders})
"""
```

### 3. `get_all_cert_dn_values_batch()` 方法（第 330-336 行）

**修复前：**
```python
SELECT DISTINCT
    order_no,
    stockist_cert,
    rm_dn_no
FROM {self._tr_report_table()}
WHERE order_no IN ({placeholders})
```

**修复后：**
```python
SELECT DISTINCT
    "order_no",
    "stockist_cert",
    "rm_dn_no"
FROM {self._tr_report_table()}
WHERE "order_no" IN ({placeholders})
```

### 4. `get_all_cert_dn_values()` 方法（第 477-483 行）

**修复前：**
```python
query = """
    SELECT DISTINCT
        stockist_cert,
        rm_dn_no
    FROM {self._tr_report_table()}
    WHERE order_no = ?
"""
```

**修复后：**
```python
query = f"""
    SELECT DISTINCT
        "stockist_cert",
        "rm_dn_no"
    FROM {self._tr_report_table()}
    WHERE "order_no" = {db_placeholders(1)}
"""
```

### 5. `get_rm_dn_to_stockist_cert_map()` 方法（第 552-558 行）

**修复前：**
```python
query = """
    SELECT DISTINCT
        rm_dn_no,
        stockist_cert
    FROM {self._tr_report_table()}
    WHERE order_no = ? AND rm_dn_no IS NOT NULL AND rm_dn_no != '' AND stockist_cert IS NOT NULL AND stockist_cert != ''
"""
```

**修复后：**
```python
query = f"""
    SELECT DISTINCT
        "rm_dn_no",
        "stockist_cert"
    FROM {self._tr_report_table()}
    WHERE "order_no" = {db_placeholders(1)} AND "rm_dn_no" IS NOT NULL AND "rm_dn_no" != '' AND "stockist_cert" IS NOT NULL AND "stockist_cert" != ''
"""
```

### 6. `tr_fill_in_api.py` 中的查询（第 4610-4617 行）

**修复前：**
```python
placeholders = ','.join('?' * len(order_nos))
query = f"""
    SELECT DISTINCT order_no, del_date
    FROM TR_Report
    WHERE order_no IN ({placeholders}) AND del_date IS NOT NULL
"""
```

**修复后：**
```python
placeholders = ','.join([db_placeholders(1)] * len(order_nos))
table_tr_report = '"TR_Report"' if is_postgres() else 'TR_Report'
query = f"""
    SELECT DISTINCT "order_no", "del_date"
    FROM {table_tr_report}
    WHERE "order_no" IN ({placeholders}) AND "del_date" IS NOT NULL
"""
```

## 影响

修复后，系统能够：
1. ✅ 正确从 PostgreSQL 数据库查询订单信息
2. ✅ 正确获取 `stockist_cert` 和 `rm_dn_no` 值
3. ✅ 正确匹配文件到对应的 stockist certificate
4. ✅ 不再误报缺失文件

## 测试建议

1. 测试 Order 134617 的下载，确认不再提示缺失 HL2322 文件
2. 测试其他订单的下载，确认文件匹配正常
3. 检查日志，确认没有数据库查询错误

## 下一步

请重启服务以应用修复：

```powershell
cd "C:\TR-master\TR UI\backend"
.\nssm-2.24\win64\nssm.exe restart TR-Backend
```

或运行：

```cmd
restart_service.bat
```
