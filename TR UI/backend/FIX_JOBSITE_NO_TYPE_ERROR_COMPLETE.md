# 修复 jobsite_no 类型不匹配错误（完整版）

## 问题描述

当搜索订单时，出现以下错误：
```
operator does not exist: text = smallint
LINE 4: WHERE b.jobsite_no = $1 AND CAST(b.dd_delive...
HINT: No operator matches the given name and argument types. You might need to add explicit type casts.
```

## 根本原因

在 PostgreSQL 中，`bbs_dd.jobsite_no` 字段是 `SMALLINT` 类型，但查询参数可能被识别为 `TEXT` 类型，导致类型不匹配错误。

即使 Python 代码中将 `job_no` 转换为整数，PostgreSQL 的参数绑定机制可能仍然将其视为 TEXT 类型。

## 解决方案

在 `get_bbs_dd_list()` 函数中修复了两处类型转换问题：

### 1. `job_no` 参数的类型转换

**修改前：**
```python
if job_no:
    try:
        job_no_int = int(job_no)
        where_conditions.append(f"b.jobsite_no = {db_placeholders(1)}")
        params.append(job_no_int)
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
```

### 2. `scoped_jobs` (用户权限范围内的 Job No) 的 `IN` 子句

**修改前：**
```python
if scoped_jobs_int:
    placeholders = ','.join([db_placeholders(1)] * len(scoped_jobs_int))
    where_conditions.append(f"b.jobsite_no IN ({placeholders})")
    params.extend(scoped_jobs_int)
```

**修改后：**
```python
if scoped_jobs_int:
    if is_postgres():
        # PostgreSQL: 为每个参数添加类型转换
        placeholders = ','.join([f"{db_placeholders(1)}::SMALLINT" for _ in scoped_jobs_int])
    else:
        placeholders = ','.join([db_placeholders(1)] * len(scoped_jobs_int))
    where_conditions.append(f"b.jobsite_no IN ({placeholders})")
    params.extend(scoped_jobs_int)
```

## 修复要点

1. **使用 PostgreSQL 类型转换语法**：`$1::SMALLINT` 将参数显式转换为 SMALLINT 类型
2. **`IN` 子句的类型转换**：为 `IN` 子句中的每个参数都添加类型转换
3. **数据库兼容性**：SQLite 不需要类型转换，保持原有逻辑
4. **参数类型**：确保 Python 代码中传递的是整数类型

## 相关修复

同时修复了：
- `scoped_jobs`（用户权限范围内的 Job No）的类型转换问题，确保字符串 job_no 转换为整数后再进行比较
- 日期比较的类型转换问题（`del_date`）

## 测试

修复后，应该能够：
1. 使用 `job_no` 参数搜索订单
2. 普通用户只能看到授权范围内的 Job No
3. 支持纯数字和包含通配符的 job_no 搜索
4. 使用日期范围搜索（start_date 和 end_date）

## 重要提示

**必须重启服务才能使修复生效！**

```powershell
cd "C:\TR-master\TR UI\backend"
.\nssm-2.24\win64\nssm.exe restart TR-Backend
```

## 相关文件

- `backend/tr_fill_in_api.py` - 主要修复文件
  - `get_bbs_dd_list()` 函数
    - `job_no` 参数处理（第 2566-2580 行）
    - `scoped_jobs` 处理（第 2611-2638 行）
    - 日期比较处理（第 2592-2610 行）
