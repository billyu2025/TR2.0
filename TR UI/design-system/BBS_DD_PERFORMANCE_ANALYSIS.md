# bbs_dd 表查询性能分析

## 问题诊断

### 当前查询存在的问题

#### 1. **CAST 操作阻止索引使用** ⚠️ 严重
```sql
-- 问题代码
CAST(b.bbs_no AS TEXT) LIKE ?
CAST(b.jobsite_no AS TEXT) LIKE ?
CAST(b.dd_no AS TEXT) LIKE ?
CAST(b.bbs_no AS TEXT) = CAST(p.Order_No AS TEXT)
```

**影响：**
- SQLite 无法在 CAST 后的字段上使用索引
- 必须进行全表扫描
- 每个 CAST 操作都需要类型转换，增加 CPU 开销

#### 2. **LIKE 查询使用通配符开头** ⚠️ 严重
```sql
-- 问题代码
LIKE '%value%'  -- 无法使用索引
```

**影响：**
- 即使有索引，`LIKE '%value%'` 也无法使用
- 必须扫描所有行进行模式匹配

#### 3. **JOIN 条件性能问题** ⚠️ 中等
```sql
-- 问题代码
LEFT JOIN PDF_Status p ON CAST(b.bbs_no AS TEXT) = CAST(p.Order_No AS TEXT)
```

**影响：**
- JOIN 条件使用 CAST 无法使用索引
- 需要为每一行进行类型转换和比较

#### 4. **可能缺少索引** ⚠️ 严重
- `bbs_dd` 表可能没有在以下字段建立索引：
  - `bbs_no` (Order No)
  - `jobsite_no` (Job No)
  - `dd_no` (DD No)
  - `dd_delivery_date` (用于排序)

## 优化方案

### 方案 1：创建索引（推荐，立即实施）

```sql
-- 为 bbs_dd 表创建索引
CREATE INDEX IF NOT EXISTS idx_bbs_dd_bbs_no ON bbs_dd(bbs_no);
CREATE INDEX IF NOT EXISTS idx_bbs_dd_jobsite_no ON bbs_dd(jobsite_no);
CREATE INDEX IF NOT EXISTS idx_bbs_dd_dd_no ON bbs_dd(dd_no);
CREATE INDEX IF NOT EXISTS idx_bbs_dd_delivery_date ON bbs_dd(dd_delivery_date DESC);
CREATE INDEX IF NOT EXISTS idx_bbs_dd_composite ON bbs_dd(dd_delivery_date DESC, bbs_no);
```

### 方案 2：优化查询条件（推荐，立即实施）

**避免使用 CAST，直接使用数值比较：**

```python
# 优化前
if order_no:
    where_conditions.append("CAST(b.bbs_no AS TEXT) LIKE ?")
    params.append(f"%{order_no}%")

# 优化后
if order_no:
    try:
        # 如果是纯数字，使用数值比较
        order_no_int = int(order_no)
        where_conditions.append("b.bbs_no = ?")
        params.append(order_no_int)
    except ValueError:
        # 如果不是纯数字，使用 LIKE（但避免通配符开头）
        where_conditions.append("CAST(b.bbs_no AS TEXT) LIKE ?")
        params.append(f"{order_no}%")  # 注意：改为 value% 而不是 %value%
```

### 方案 3：优化 JOIN 条件

**如果 bbs_no 和 Order_No 都是数值类型，直接比较：**

```sql
-- 优化前
LEFT JOIN PDF_Status p ON CAST(b.bbs_no AS TEXT) = CAST(p.Order_No AS TEXT)

-- 优化后（如果类型匹配）
LEFT JOIN PDF_Status p ON b.bbs_no = p.Order_No

-- 或者（如果必须转换）
LEFT JOIN PDF_Status p ON CAST(b.bbs_no AS TEXT) = p.Order_No
-- 至少让一边可以使用索引
```

### 方案 4：优化 COUNT 查询

**使用子查询优化 COUNT：**

```sql
-- 优化前
SELECT COUNT(*) 
FROM bbs_dd b
LEFT JOIN PDF_Status p ON CAST(b.bbs_no AS TEXT) = CAST(p.Order_No AS TEXT)
WHERE ...

-- 优化后（如果不需要 JOIN 信息）
SELECT COUNT(*) 
FROM bbs_dd b
WHERE ...
```

## 实施优先级

1. **高优先级（立即实施）**：
   - 创建索引
   - 优化 LIKE 查询（避免通配符开头）

2. **中优先级（近期实施）**：
   - 优化 JOIN 条件
   - 优化 COUNT 查询

3. **低优先级（长期优化）**：
   - 考虑数据分区
   - 考虑缓存机制

## 预期效果

- **创建索引后**：查询速度预计提升 **10-100 倍**
- **优化 LIKE 查询后**：搜索速度预计提升 **5-10 倍**
- **优化 JOIN 后**：JOIN 操作速度预计提升 **3-5 倍**

## 注意事项

1. 索引会占用额外存储空间（通常很小）
2. 索引会稍微减慢 INSERT/UPDATE 操作（但查询性能提升显著）
3. 对于 SQLite，索引创建很快，可以随时添加
