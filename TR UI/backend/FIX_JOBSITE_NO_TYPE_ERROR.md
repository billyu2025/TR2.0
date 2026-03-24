# 修复 jobsite_no 类型不匹配错误

## 问题描述

当搜索订单时，出现以下错误：
```
operator does not exist: text = smallint
LINE 4: WHERE b.jobsite_no = $1 AND CAST(b.dd_delive...
```

## 根本原因

在 PostgreSQL 中，`bbs_dd.jobsite_no` 字段是 `SMALLINT` 类型，但查询参数可能被识别为 `TEXT` 类型，导致类型不匹配错误。

即使 Python 代码中将 `job_no` 转换为整数，PostgreSQL 的参数绑定机制可能仍然将其视为 TEXT 类型。

## 解决方案

在 `get_bbs_dd_list()` 函数中修复 `job_no` 参数的类型转换：

**修改前：**
```python
if job_no:
    try:
        job_no_int = int(job_no)
        where_conditions.append(f"b.jobsite_no = {db_placeholders(1)}")
        params.append(job_no_int)
    except (ValueError, TypeError):
        where_conditions.append(f"CAST(b.jobsite_no AS TEXT) LIKE {db_placeholders(1)}")
        params.append(f"{job_no}%")
```

**修改后：**
```python
if job_no:
    # PostgreSQL 中 jobsite_no 是 SMALLINT 类型，需要确保参数类型匹配
    try:
        job_no_int = int(job_no)
        if is_postgres():
            # PostgreSQL: 将参数转换为 SMALLINT 类型进行比较
            where_conditions.append(f"b.jobsite_no = {db_placeholders(1)}::SMALLINT")
        else:
            where_conditions.append(f"b.jobsite_no = {db_placeholders(1)}")
        # 确保参数是整数类型
        params.append(job_no_int)
    except (ValueError, TypeError):
        # 如果不是纯数字，使用 LIKE（但避免通配符开头以使用索引）
        where_conditions.append(f"CAST(b.jobsite_no AS TEXT) LIKE {db_placeholders(1)}")
        params.append(f"{job_no}%")
```

## 修复要点

1. **使用 PostgreSQL 类型转换语法**：`$1::SMALLINT` 将参数显式转换为 SMALLINT 类型
2. **数据库兼容性**：SQLite 不需要类型转换，保持原有逻辑
3. **参数类型**：确保 Python 代码中传递的是整数类型

## 相关修复

同时修复了 `scoped_jobs`（用户权限范围内的 Job No）的类型转换问题，确保字符串 job_no 转换为整数后再进行比较。

## 测试

修复后，应该能够：
1. 使用 `job_no` 参数搜索订单
2. 普通用户只能看到授权范围内的 Job No
3. 支持纯数字和包含通配符的 job_no 搜索

## 相关文件

- `backend/tr_fill_in_api.py` - 主要修复文件
  - `get_bbs_dd_list()` 函数（第 2566-2579 行）
  - `scoped_jobs` 处理（第 2611-2630 行）
