# 文件索引缓存使用说明

## 📋 概述

文件索引缓存功能已经实现，可以大幅提升文件查找速度。本文档说明如何使用这个功能。

## 🚀 快速开始

### 1. 确保表已创建

表会在应用启动时自动创建。如果还没有创建，启动 Flask 应用即可：

```bash
python tr_fill_in_api.py
```

启动时会看到：
```
[INFO] file_index_cache table created successfully
[INFO] file_index_metadata table created successfully
```

### 2. 建立索引

有两种方式建立索引：

#### 方式1：使用命令行脚本（推荐）

```bash
cd backend
python file_index_builder.py
```

这会：
- 扫描所有配置的文件夹
- 提取文件信息和关键词
- 批量插入到数据库
- 显示进度和统计信息

#### 方式2：使用 API 接口

```bash
# 获取索引状态
curl -X GET http://localhost:5000/api/file-index/status \
  -H "Authorization: Bearer YOUR_TOKEN"

# 重建索引（需要管理员权限）
curl -X POST http://localhost:5000/api/file-index/rebuild \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"clear_existing": true}'
```

## 📊 API 接口说明

### 1. 获取索引状态

**接口：** `GET /api/file-index/status`

**权限：** 需要登录

**返回示例：**
```json
{
  "success": true,
  "total_files": 12345,
  "last_full_scan": "2024-01-15T02:00:00",
  "total_files_indexed": 12345,
  "index_version": "1.0",
  "scan_status": "idle",
  "index_size_mb": 12.5,
  "status": "healthy"
}
```

### 2. 重建索引

**接口：** `POST /api/file-index/rebuild`

**权限：** 仅管理员

**请求体（可选）：**
```json
{
  "clear_existing": true  // 是否清空现有索引
}
```

**返回示例：**
```json
{
  "success": true,
  "message": "索引重建已启动，将在后台执行",
  "clear_existing": true
}
```

**注意：** 索引重建在后台线程中执行，不会阻塞 API 响应。

### 3. 清理无效记录

**接口：** `POST /api/file-index/cleanup`

**权限：** 仅管理员

**功能：** 检查所有索引记录，删除文件系统中已不存在的文件记录

**返回示例：**
```json
{
  "success": true,
  "records_deleted": 15
}
```

## 🔧 配置

### 环境变量

在 `.env` 文件中配置：

```env
# Stockist&Test Report 文件夹路径
STOCKIST_TEST_FOLDER=D:\Stockist&Test Report

# 数据库路径
DB_PATH=C:/TR-master/TR database/data_3years.db
```

### 扫描的文件夹

系统会自动扫描以下文件夹：
- `{STOCKIST_TEST_FOLDER}/Stockist Cert`
- `{STOCKIST_TEST_FOLDER}/Private Formal`
- `{STOCKIST_TEST_FOLDER}/Private Prelim`
- `{STOCKIST_TEST_FOLDER}/IAT Formal`
- `{STOCKIST_TEST_FOLDER}/IAT Prelim`

## 📝 关键词提取规则

系统会从文件名中提取以下类型的关键词：

1. **数字序列**：长度>=3的数字
   - 例如：`ABC12345DEF` → `["12345"]`

2. **字母数字组合**：字母+数字的组合
   - 例如：`STOCKIST001` → `["STOCKIST001"]`

3. **分隔符分割**：按 `-`, `_`, 空格, `.` 分割
   - 例如：`STOCKIST_CERT_12345` → `["STOCKIST", "CERT", "12345"]`

4. **路径提取**：从文件路径中提取关键词

所有关键词会转换为大写并去重，存储为 JSON 格式。

## ⚙️ 性能优化

### 批量插入

- 默认批量大小：1000 条记录
- 使用事务批量插入，提高性能
- 使用 `INSERT OR REPLACE` 处理重复

### 数据库优化

- 启用 WAL 模式（Write-Ahead Logging）
- 创建多个索引优化查询
- 使用连接池（如果配置）

## 🔍 监控和维护

### 检查索引健康度

定期检查索引状态：

```bash
# 使用 API
curl http://localhost:5000/api/file-index/status

# 或使用测试脚本
python test_file_index_tables.py
```

### 定期维护

建议定期执行以下操作：

1. **每周清理无效记录**
   ```bash
   curl -X POST http://localhost:5000/api/file-index/cleanup \
     -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
   ```

2. **每月重建索引**（如果文件变化频繁）
   ```bash
   curl -X POST http://localhost:5000/api/file-index/rebuild \
     -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"clear_existing": false}'
   ```

## 🐛 故障排查

### 问题1：索引建立失败

**可能原因：**
- 文件夹路径不存在
- 数据库权限问题
- 磁盘空间不足

**解决方法：**
1. 检查环境变量 `STOCKIST_TEST_FOLDER` 是否正确
2. 检查数据库文件权限
3. 查看错误日志

### 问题2：索引不完整

**可能原因：**
- 扫描过程中断
- 文件访问权限问题

**解决方法：**
1. 重新运行索引建立
2. 检查文件权限
3. 查看扫描日志中的错误信息

### 问题3：查询速度没有提升

**可能原因：**
- 索引未建立
- 索引表为空
- 查询功能尚未使用索引

**解决方法：**
1. 检查索引状态：`GET /api/file-index/status`
2. 确认索引中有数据
3. 等待查询优化功能实现（下一步）

## 📈 下一步

索引建立功能已完成，接下来可以：

1. ✅ **索引建立** - 已完成
2. ⏳ **查询优化** - 将 `find_files_by_keywords` 改为使用数据库查询
3. ⏳ **增量更新** - 实现定期自动更新索引
4. ⏳ **维护机制** - 实现自动清理和优化

## 📚 相关文档

- [实现指导文档](../FILE_INDEX_CACHE_IMPLEMENTATION_GUIDE.md)
- [测试脚本](test_file_index_tables.py)
- [索引建立器](file_index_builder.py)
