# 验证定时任务是否运行

## ✅ 检查清单

### 1. 验证 .env 配置

确认 `.env` 文件中已正确配置：

```env
# 启用文件索引定时任务
ENABLE_FILE_INDEX_SCHEDULER=true

# 更新间隔（小时）
FILE_INDEX_UPDATE_INTERVAL_HOURS=1
```

### 2. 启动 API 服务器时检查日志

启动 API 服务器时，应该看到类似的输出：

```
[调度器] 文件索引定时任务已启动，更新间隔: 1 小时
```

或者如果没有看到，检查是否在启动代码中：

```python
# 在 tr_fill_in_api.py 的 __main__ 部分
enable_scheduler = os.getenv('ENABLE_FILE_INDEX_SCHEDULER', 'False').lower() == 'true'
if enable_scheduler:
    # 应该看到启动日志
```

### 3. 验证定时任务是否在工作

#### 方法1：查看控制台日志

定时任务运行时会输出日志：

```
[调度器] 2024-01-15 15:00:00 - 开始执行增量更新
[更新] 处理文件夹类型: Stockist Cert
  [1/3] 扫描文件系统: D:\Stockist&Test Report\Stockist Cert
  [1/3] 找到 1234 个文件
  [2/3] 查询数据库记录...
  [3/3] 对比差异...
[调度器] 增量更新完成: 新增 5, 更新 2, 删除 1
```

#### 方法2：查看索引状态

使用 API 查看最后更新时间：

```bash
GET /api/file-index/status
```

检查返回的 `last_incremental_update` 字段，应该会定期更新。

#### 方法3：检查数据库元数据

查询 `file_index_metadata` 表：

```sql
SELECT key, value, updated_at 
FROM file_index_metadata 
WHERE key = 'last_incremental_update' 
   OR key = 'scan_status'
```

`scan_status` 应该大部分时间是 `idle`，更新时会变成 `updating`。

### 4. 测试定时任务

#### 手动触发一次更新（验证功能）

使用 API 手动触发更新，确认功能正常：

```bash
POST /api/file-index/update
```

如果手动更新成功，说明定时任务也会正常工作。

---

## 🔍 故障排查

### 问题1：没有看到启动日志

**可能原因：**
- `.env` 文件未正确加载
- 环境变量值不是 `true`（注意大小写）
- 启动代码有问题

**解决方法：**
1. 确认 `.env` 文件在正确位置
2. 确认值是小写 `true`
3. 重启 API 服务器

### 问题2：定时任务未执行

**可能原因：**
- 线程未启动
- 程序异常退出
- 时间间隔设置错误

**解决方法：**
1. 检查服务器是否持续运行
2. 查看是否有错误日志
3. 确认更新间隔设置合理（如 1 小时）

### 问题3：更新日志未出现

**可能原因：**
- 时间间隔太长（如 24 小时）
- 更新时出错
- 日志被重定向

**解决方法：**
1. 缩短更新间隔测试（如 0.1 小时 = 6 分钟）
2. 查看错误日志
3. 检查控制台输出

---

## 📊 监控建议

### 定期检查（每周）

1. **查看索引状态**
   ```bash
   GET /api/file-index/status
   ```

2. **检查最后更新时间**
   - `last_incremental_update` 应该定期更新
   - 如果超过更新间隔 * 2 未更新，可能有问题

3. **查看日志**
   - 确认没有错误
   - 确认更新正常执行

---

## 🎯 下一步

定时任务已启用后，系统会：
- ✅ 每小时自动更新索引
- ✅ 保持索引与文件系统同步
- ✅ 无需人工干预

你可以：
1. 等待第一次自动更新（最多等 1 小时）
2. 或手动触发一次更新测试功能
3. 定期检查索引状态确认正常运行

享受自动化的索引维护吧！🚀
