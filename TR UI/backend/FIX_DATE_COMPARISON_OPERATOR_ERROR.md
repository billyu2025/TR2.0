# 修复日期比较操作符错误

## 问题描述

当搜索 Order 1171 在 2025/01/02 这一天的 stockist 和 test report 时，出现 `operator does not exist` 错误。

## 根本原因

在 PostgreSQL 中，当 `Del_Date` 字段是字符串类型（TEXT 或 VARCHAR）时，直接使用字符串比较操作符（`>=`、`<=`）进行日期比较可能会导致类型不匹配错误。

特别是当：
1. 日期格式不一致（如 `2025/01/02` vs `2025-01-02`）
2. 字段类型是字符串而不是 DATE 类型
3. PostgreSQL 无法自动进行类型转换

## 解决方案

在 `tr_fill_in_api.py` 中修复了两处日期比较逻辑：

### 1. `get_orders_list()` 函数中的日期过滤

**修改前：**
```python
if start_date:
    where_conditions.append(f"o.\"Del_Date\" >= {db_placeholders(1)}")
    params.append(start_date)

if end_date:
    where_conditions.append(f"o.\"Del_Date\" <= {db_placeholders(1)}")
    params.append(end_date)
```

**修改后：**
```python
if start_date:
    # PostgreSQL 需要将字符串日期转换为 DATE 类型进行比较
    if is_postgres():
        where_conditions.append(f"CAST(o.\"Del_Date\" AS DATE) >= CAST({db_placeholders(1)} AS DATE)")
    else:
        where_conditions.append(f"o.\"Del_Date\" >= {db_placeholders(1)}")
    # 标准化日期格式为 YYYY-MM-DD
    start_date_normalized = start_date.replace('/', '-')
    params.append(start_date_normalized)

if end_date:
    # PostgreSQL 需要将字符串日期转换为 DATE 类型进行比较
    if is_postgres():
        where_conditions.append(f"CAST(o.\"Del_Date\" AS DATE) <= CAST({db_placeholders(1)} AS DATE)")
    else:
        where_conditions.append(f"o.\"Del_Date\" <= {db_placeholders(1)}")
    # 标准化日期格式为 YYYY-MM-DD
    end_date_normalized = end_date.replace('/', '-')
    params.append(end_date_normalized)
```

### 2. `get_bbs_dd_list()` 函数中的日期过滤

**修改前：**
```python
if start_date:
    where_conditions.append(f"b.dd_delivery_date >= {db_placeholders(1)}")
    params.append(start_date)

if end_date:
    where_conditions.append(f"b.dd_delivery_date <= {db_placeholders(1)}")
    params.append(end_date)
```

**修改后：**
```python
if start_date:
    # PostgreSQL 需要将字符串日期转换为 DATE 类型进行比较
    if is_postgres():
        where_conditions.append(f"CAST(b.dd_delivery_date AS DATE) >= CAST({db_placeholders(1)} AS DATE)")
    else:
        where_conditions.append(f"b.dd_delivery_date >= {db_placeholders(1)}")
    # 标准化日期格式为 YYYY-MM-DD
    start_date_normalized = start_date.replace('/', '-')
    params.append(start_date_normalized)

if end_date:
    # PostgreSQL 需要将字符串日期转换为 DATE 类型进行比较
    if is_postgres():
        where_conditions.append(f"CAST(b.dd_delivery_date AS DATE) <= CAST({db_placeholders(1)} AS DATE)")
    else:
        where_conditions.append(f"b.dd_delivery_date <= {db_placeholders(1)}")
    # 标准化日期格式为 YYYY-MM-DD
    end_date_normalized = end_date.replace('/', '-')
    params.append(end_date_normalized)
```

## 修复要点

1. **类型转换**：在 PostgreSQL 中使用 `CAST(... AS DATE)` 将字符串日期转换为 DATE 类型
2. **日期格式标准化**：将 `2025/01/02` 格式转换为 `2025-01-02` 格式
3. **数据库兼容性**：保持对 SQLite 的兼容性（SQLite 可以使用字符串比较）

## 测试

修复后，应该能够：
1. 搜索 Order 1171 在 2025/01/02 这一天的记录
2. 使用日期范围搜索（start_date 和 end_date）
3. 支持多种日期格式（`YYYY/MM/DD` 和 `YYYY-MM-DD`）

## 相关文件

- `backend/tr_fill_in_api.py` - 主要修复文件
  - `get_orders_list()` 函数（第 2859-2865 行）
  - `get_bbs_dd_list()` 函数（第 2586-2592 行）
