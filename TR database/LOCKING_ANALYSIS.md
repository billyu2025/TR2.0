# SQLite 锁定机制分析

## 问题：后端服务会一直锁住表吗？

### 实际情况

**是的，后端服务会持有锁，但这不影响我们的策略。** 关键在于理解 SQLite 的锁机制和 WAL 模式。

## SQLite 锁机制

### 1. 锁的层次结构

```
UNLOCKED → SHARED → RESERVED → PENDING → EXCLUSIVE
```

- **SHARED 锁**：读取操作（SELECT），多个连接可以同时持有
- **RESERVED 锁**：写入操作（INSERT/UPDATE），可以与 SHARED 锁并发
- **EXCLUSIVE 锁**：DDL 操作（DROP TABLE, ALTER TABLE），需要独占

### 2. WAL 模式的优势

在 WAL（Write-Ahead Logging）模式下：
- ✅ **读取和写入可以并发**：SELECT 和 INSERT/UPDATE 不会互相阻塞
- ✅ **读取不会阻止写入**：多个 SELECT 可以同时进行
- ✅ **写入不会阻止读取**：INSERT/UPDATE 不会阻止 SELECT

但是：
- ⚠️ **DROP TABLE 仍然需要 EXCLUSIVE 锁**：需要等待所有其他锁释放

## 后端服务的锁使用情况

### 后端服务通常做什么？

1. **SELECT 查询**：持有 **SHARED 锁**
   - 查询 TR_Report 表
   - 查询 bbs_dd 表
   - 查询 TR_Report_Deduplication 表
   - 这些查询通常很快（几毫秒到几百毫秒）

2. **INSERT/UPDATE**：持有 **RESERVED 锁**
   - 更新 PDF_Status 表
   - 插入用户会话
   - 这些操作也很快

3. **连接池**：最大 20 个连接
   - 每个连接在执行查询时持有锁
   - 查询完成后立即释放锁
   - **关键**：锁只在查询执行期间持有，不是一直持有

## 为什么锁定时间可以很短？

### 关键理解：等待时间 vs 锁定时间

```
总时间 = 等待时间（等待后端释放锁） + 锁定时间（执行 DROP TABLE + RENAME）
```

1. **等待时间**（可能几秒到几十秒）：
   - `BEGIN IMMEDIATE` 会尝试获取 RESERVED 锁
   - 如果后端正在执行查询，需要等待查询完成
   - 在 WAL 模式下，查询通常很快（几毫秒到几百毫秒）
   - `busy_timeout=30000` 会等待最多 30 秒

2. **锁定时间**（< 1 秒）：
   - 一旦获取到 EXCLUSIVE 锁，执行 DROP TABLE 和 RENAME 非常快
   - DROP TABLE：删除表结构（元数据操作，< 100ms）
   - RENAME：重命名表（元数据操作，< 10ms）
   - **总共 < 1 秒**

### 为什么等待时间不会太长？

1. **查询很快**：后端服务的查询通常很快（几毫秒到几百毫秒）
2. **WAL 模式**：读取和写入可以并发，不会长时间阻塞
3. **连接池**：连接会快速释放，不会长时间持有锁
4. **busy_timeout**：如果 30 秒内无法获取锁，会抛出错误（可以重试）

## 实际场景分析

### 场景 1：后端服务正在执行查询

```
时间线：
T0: 后端开始 SELECT 查询（持有 SHARED 锁）
T1: 更新脚本执行 BEGIN IMMEDIATE（尝试获取 RESERVED 锁）
T2: 等待后端查询完成（假设 100ms）
T3: 后端查询完成，释放 SHARED 锁
T4: 更新脚本获取 RESERVED 锁，升级到 EXCLUSIVE 锁
T5: 执行 DROP TABLE（50ms）
T6: 执行 RENAME（10ms）
T7: COMMIT，释放锁

总等待时间：100ms（等待后端查询完成）
总锁定时间：60ms（DROP TABLE + RENAME）
总时间：160ms
```

### 场景 2：后端服务有多个并发查询

```
时间线：
T0: 后端有 5 个并发 SELECT 查询（都持有 SHARED 锁）
T1: 更新脚本执行 BEGIN IMMEDIATE（尝试获取 RESERVED 锁）
T2: 等待所有查询完成（假设最长查询 200ms）
T3: 所有查询完成，释放 SHARED 锁
T4: 更新脚本获取 EXCLUSIVE 锁
T5: 执行 DROP TABLE + RENAME（60ms）
T6: COMMIT，释放锁

总等待时间：200ms（等待最长查询完成）
总锁定时间：60ms
总时间：260ms
```

### 场景 3：后端服务有长时间运行的查询（不常见）

```
时间线：
T0: 后端开始长时间查询（假设 5 秒）
T1: 更新脚本执行 BEGIN IMMEDIATE
T2: 等待查询完成（5 秒）
T3: 查询完成，获取锁
T4: 执行 DROP TABLE + RENAME（60ms）
T5: COMMIT

总等待时间：5 秒
总锁定时间：60ms
总时间：5.06 秒
```

## 优化策略

### 1. 使用 busy_timeout

```python
conn.execute("PRAGMA busy_timeout=30000")  # 等待最多 30 秒
```

如果无法在 30 秒内获取锁，会抛出错误，可以重试。

### 2. 使用 BEGIN IMMEDIATE

```python
cursor.execute("BEGIN IMMEDIATE")  # 立即尝试获取 RESERVED 锁
```

这会立即尝试获取锁，而不是等待。

### 3. 重试机制

```python
def execute_with_retry(func, max_retries=15, retry_delay=5):
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
            raise
```

如果获取锁失败，会重试最多 15 次，每次等待 5 秒。

## 结论

### 回答您的问题

**Q: 后端不会一直锁住表吗？**

A: 不会。后端服务只在执行查询时持有锁，查询完成后立即释放。在 WAL 模式下，查询通常很快（几毫秒到几百毫秒）。

**Q: 那这样怎么通过分离操作，将锁定时间缩短到1秒呢？**

A: 
1. **分离操作**：先创建新表并写入数据（不需要锁），然后在最短事务中完成表交换（需要锁）
2. **等待时间**：可能需要等待后端查询完成（通常几毫秒到几百毫秒）
3. **锁定时间**：一旦获取到锁，执行 DROP TABLE + RENAME 非常快（< 1 秒）

### 实际效果

- **大部分时间**（创建新表、写入数据）：不需要锁，后端服务可以正常使用
- **等待时间**：等待后端查询完成（通常 < 1 秒，偶尔几秒）
- **锁定时间**：执行 DROP TABLE + RENAME（< 1 秒）

**总的影响时间**：通常 < 2 秒，偶尔可能几秒，但不会影响后端服务的正常运行。
