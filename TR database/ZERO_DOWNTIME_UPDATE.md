# 零停机时间数据库更新策略

## 概述

为了在不中断后端服务的情况下更新数据库表，我们采用了**表重命名策略**（Table Renaming Strategy）。这种方法可以避免 `DROP TABLE` 操作需要独占锁的问题，从而允许在服务运行期间更新数据库。

## 问题背景

在 SQLite 中，`DROP TABLE` 操作需要获取**独占锁**（EXCLUSIVE lock），这意味着：
- 所有其他连接（包括后端服务的连接）必须等待
- 如果后端服务正在使用该表，会导致 "attempt to write a readonly database" 错误
- 需要停止后端服务才能执行更新

## 解决方案：表重命名策略

### 核心思路

**关键点**：将耗时操作（创建新表、写入数据）与需要锁的操作（删除旧表、重命名）分离：

1. **创建临时表并写入数据**（**不需要锁定旧表**，可以并发进行）
   - 创建新表（如 `TR_Report_new`）
   - 写入所有新数据到新表
   - 这个过程可能需要几分钟，但**不影响后端服务读取旧表**

2. **在最短事务中完成表交换**（**这里才需要锁**，但时间极短）
   - 使用 `BEGIN IMMEDIATE` 快速获取锁
   - 删除旧表（需要 EXCLUSIVE 锁，但操作本身很快，通常 < 100ms）
   - 重命名新表（原子操作，几乎瞬间完成）
   - 整个事务通常在 < 1 秒内完成

### 实现步骤

```python
def replace_table():
    cursor = self.sqlite_conn.cursor()
    
    # 步骤1-2：创建新表并写入数据（不需要锁定旧表，可以并发进行）
    temp_table_name = "TR_Report_new"
    cursor.execute("DROP TABLE IF EXISTS " + temp_table_name)
    self.sqlite_conn.commit()  # 先提交，释放锁
    
    # 将数据写入新表（这个过程可能需要几分钟，但不需要锁定旧表）
    df.to_sql(temp_table_name, self.sqlite_conn, if_exists='replace', index=False)
    self.sqlite_conn.commit()  # 提交，释放锁
    
    # 步骤3-4：在最短的事务中完成表交换（这里才需要锁）
    # 使用 BEGIN IMMEDIATE 快速获取锁，然后立即执行删除和重命名
    cursor.execute("BEGIN IMMEDIATE")
    try:
        # 删除旧表（需要 EXCLUSIVE 锁，但操作本身很快，通常 < 100ms）
        cursor.execute("DROP TABLE IF EXISTS TR_Report")
        
        # 重命名新表（原子操作，几乎瞬间完成）
        cursor.execute(f"ALTER TABLE {temp_table_name} RENAME TO TR_Report")
        
        self.sqlite_conn.commit()
        return True
    except sqlite3.OperationalError as e:
        self.sqlite_conn.rollback()
        # 清理临时表
        try:
            cursor.execute("DROP TABLE IF EXISTS " + temp_table_name)
            self.sqlite_conn.commit()
        except:
            pass
        raise
```

### 优势

1. **零停机时间**：后端服务可以继续运行，无需停止
2. **最小锁定时间**：
   - **大部分时间（创建新表、写入数据）不需要锁定旧表**，后端服务可以正常读取
   - **只有最后交换表的瞬间需要锁**（删除旧表 + 重命名新表，通常 < 1 秒）
3. **原子性**：表交换操作在事务中完成，要么全部成功，要么全部回滚
4. **自动清理**：如果操作失败，会自动清理临时表

### 为什么锁定时间很短？

**关键理解：等待时间 vs 锁定时间**

```
总时间 = 等待时间（等待后端释放锁） + 锁定时间（执行 DROP TABLE + RENAME）
```

1. **等待时间**（可能几毫秒到几秒）：
   - `BEGIN IMMEDIATE` 会尝试获取 RESERVED 锁
   - 如果后端正在执行查询，需要等待查询完成
   - 在 WAL 模式下，查询通常很快（几毫秒到几百毫秒）
   - `busy_timeout=30000` 会等待最多 30 秒

2. **锁定时间**（< 1 秒）：
   - 一旦获取到 EXCLUSIVE 锁，执行 DROP TABLE 和 RENAME 非常快
   - DROP TABLE：删除表结构（元数据操作，< 100ms）
   - RENAME：重命名表（元数据操作，< 10ms）
   - **总共 < 1 秒**

**为什么等待时间不会太长？**

- 后端服务只在执行查询时持有锁，查询完成后立即释放
- 在 WAL 模式下，查询通常很快（几毫秒到几百毫秒）
- 连接池会快速释放连接，不会长时间持有锁
- 如果 30 秒内无法获取锁，会抛出错误（可以重试）

**实际影响**：
- **大部分时间**（创建新表、写入数据）：不需要锁，后端服务可以正常使用
- **等待时间**：等待后端查询完成（通常 < 1 秒，偶尔几秒）
- **锁定时间**：执行 DROP TABLE + RENAME（< 1 秒）

**总的影响时间**：通常 < 2 秒，偶尔可能几秒，但不会影响后端服务的正常运行。

## 已应用的表

以下表已使用表重命名策略更新：

- ✅ `TR_Report`
- ✅ `TR_Report_Deduplication`
- ✅ `bbs_dd`
- ⚠️ `file_index`（通过 `FileIndexUpdater` 更新，可能使用不同的策略）

## 使用方式

现在可以直接运行更新脚本，**无需停止后端服务**：

```batch
cd "C:\TR-master\TR database"
python auto_update_all_tables.py
```

或者使用批处理脚本：

```batch
cd "C:\TR-master\TR database"
auto_update_all_tables.bat
```

## 注意事项

1. **WAL 模式**：数据库应启用 WAL（Write-Ahead Logging）模式以支持更好的并发访问
2. **重试机制**：如果遇到锁定，脚本会自动重试（最多 15 次，每次延迟 5 秒）
3. **临时表清理**：如果操作失败，临时表会被自动清理
4. **监控日志**：建议监控更新日志，确保操作成功

## 技术细节

### SQLite 锁定模式

SQLite 有几种锁定模式：
- **SHARED**：多个连接可以同时读取
- **RESERVED**：一个连接可以写入，其他连接可以读取
- **PENDING**：等待其他读取连接完成
- **EXCLUSIVE**：独占访问，其他连接无法读取或写入

`DROP TABLE` 需要 EXCLUSIVE 锁，而 `ALTER TABLE ... RENAME TO` 只需要很短的 RESERVED 锁。

### 事务处理

所有操作都在 `BEGIN IMMEDIATE` 事务中执行，确保：
- 原子性：要么全部成功，要么全部回滚
- 快速获取锁：`BEGIN IMMEDIATE` 会立即尝试获取 RESERVED 锁
- 错误恢复：如果失败，自动回滚并清理临时表

## 故障排除

如果仍然遇到 "readonly database" 错误：

1. **检查后端服务**：确保后端服务正在运行（它应该能正常使用数据库）
2. **检查数据库文件权限**：确保数据库文件有写入权限
3. **检查 WAL 模式**：运行 `PRAGMA journal_mode;` 确认是 WAL 模式
4. **查看日志**：检查更新脚本的详细日志，了解具体失败原因
5. **手动重试**：如果只是临时锁定，可以稍后重试

## 性能影响

- **对后端服务的影响**：几乎为零，因为大部分时间都在写入临时表
- **锁定时间**：通常 < 1 秒（仅删除旧表和重命名新表时）
- **更新速度**：与停止服务后更新相同，但无需停机

## 未来改进

可以考虑的进一步优化：
1. **增量更新**：只更新变化的数据，而不是重建整个表
2. **并行更新**：对于独立的表，可以并行更新
3. **版本控制**：为表添加版本号，支持回滚
