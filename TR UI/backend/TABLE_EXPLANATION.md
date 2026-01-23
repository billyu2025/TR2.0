# 文件索引缓存表说明

## 📊 两个表的作用和区别

### 1. `file_index_cache` - 主索引表（数据表）

#### 🎯 作用
**存储所有文件的索引信息，用于快速查询文件**

#### 📋 表结构

```sql
CREATE TABLE file_index_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,      -- 主键
    file_path TEXT NOT NULL UNIQUE,            -- 文件完整路径（唯一）
    file_name TEXT NOT NULL,                   -- 文件名
    folder_path TEXT NOT NULL,                 -- 文件夹路径
    folder_type TEXT NOT NULL,                 -- 文件夹类型
    file_size INTEGER,                         -- 文件大小
    modified_time REAL,                        -- 修改时间（Unix时间戳）
    created_time TEXT NOT NULL,                -- 索引创建时间
    last_checked TEXT NOT NULL,                -- 最后检查时间
    extracted_keywords TEXT,                   -- 提取的关键词（JSON）
    file_hash TEXT,                            -- 文件哈希（可选）
    is_deleted INTEGER NOT NULL DEFAULT 0      -- 是否已删除
)
```

#### 💾 存储内容
- **每条记录 = 一个文件（或文件夹）的索引信息**
- 例如：如果有 10,000 个文件，就有 10,000 条记录

#### 🔍 使用场景
- **查询文件时**：根据关键词在表中查找匹配的文件
- **更新索引时**：对比文件系统，更新表中的记录
- **清理索引时**：删除或标记已删除的记录

#### 📈 数据量
- **大表**：可能包含数万到数十万条记录
- **增长**：随着文件数量增加而增长

---

### 2. `file_index_metadata` - 元数据表（配置表）

#### 🎯 作用
**存储索引系统的配置和状态信息，用于管理和监控**

#### 📋 表结构

```sql
CREATE TABLE file_index_metadata (
    key TEXT PRIMARY KEY,      -- 配置键名
    value TEXT,                -- 配置值
    updated_at TEXT NOT NULL  -- 更新时间
)
```

#### 💾 存储内容
- **只有几条记录**：存储系统配置和状态
- **键值对格式**：类似配置文件

#### 📝 默认存储的信息

| key | value | 说明 |
|-----|-------|------|
| `last_full_scan` | `2024-01-15T02:00:00` | 最后一次全量扫描的时间 |
| `total_files_indexed` | `12345` | 索引的文件总数 |
| `index_version` | `1.0` | 索引版本号（用于兼容性检查） |
| `scan_status` | `idle` | 扫描状态：`idle`（空闲）、`scanning`（扫描中）、`updating`（更新中） |

#### 🔍 使用场景
- **查看索引状态**：查询最后扫描时间、文件总数等
- **管理索引**：设置扫描状态、更新版本号
- **监控系统**：检查索引是否健康

#### 📈 数据量
- **小表**：只有几条到十几条记录
- **固定**：不会随文件数量增长

---

## 🔄 两个表的关系

```
file_index_cache (主表)
    ↓
    存储：每个文件的信息
    用途：快速查询文件
    数据量：大（数万条）
    
    ↓ 配合使用 ↓
    
file_index_metadata (辅助表)
    ↓
    存储：索引系统的状态
    用途：管理和监控
    数据量：小（几条）
```

## 📊 对比表

| 特性 | `file_index_cache` | `file_index_metadata` |
|------|-------------------|---------------------|
| **作用** | 存储文件索引数据 | 存储系统配置和状态 |
| **数据量** | 大（数万条） | 小（几条） |
| **记录数** | 每个文件一条记录 | 每个配置项一条记录 |
| **主要用途** | 快速查询文件 | 管理和监控索引 |
| **更新频率** | 高（文件变化时） | 低（状态变化时） |
| **查询方式** | 复杂查询（关键词匹配） | 简单查询（键值查询） |
| **类比** | 图书馆的图书目录卡 | 图书馆的管理记录本 |

## 💡 实际使用示例

### 查询文件（使用 file_index_cache）

```python
# 在 file_index_query.py 中
SELECT file_path 
FROM file_index_cache 
WHERE folder_type = 'Stockist Cert' 
  AND file_name LIKE '%12345%'
  AND is_deleted = 0
```

### 查看索引状态（使用 file_index_metadata）

```python
# 在 tr_fill_in_api.py 中
SELECT key, value 
FROM file_index_metadata 
WHERE key IN ('last_full_scan', 'total_files_indexed', 'scan_status')
```

### 更新索引状态（使用 file_index_metadata）

```python
# 在 file_index_builder.py 中
UPDATE file_index_metadata 
SET value = '2024-01-15T02:00:00', updated_at = CURRENT_TIMESTAMP 
WHERE key = 'last_full_scan'
```

## 🎯 总结

### `file_index_cache`
- ✅ **主表**：存储所有文件的索引信息
- ✅ **查询用**：用于快速查找文件
- ✅ **数据量大**：可能数万条记录
- ✅ **频繁更新**：文件变化时更新

### `file_index_metadata`
- ✅ **辅助表**：存储系统配置和状态
- ✅ **管理用**：用于监控和管理索引
- ✅ **数据量小**：只有几条记录
- ✅ **偶尔更新**：状态变化时更新

**简单记忆：**
- `file_index_cache` = 文件索引数据（大表）
- `file_index_metadata` = 索引系统状态（小表）
