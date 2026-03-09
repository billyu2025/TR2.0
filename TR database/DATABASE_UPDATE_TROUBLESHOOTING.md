# 数据库更新故障排除指南

## 问题：数据库只读错误

### 错误信息
```
attempt to write a readonly database
```

### 可能的原因

1. **后端服务正在运行**
   - 后端服务（TR-Backend）正在使用数据库
   - WAL模式下虽然支持并发读写，但某些操作（如DROP TABLE）可能需要独占锁

2. **数据库文件权限**
   - 数据库文件或目录没有写权限
   - WAL文件（data_3years.db-wal）或SHM文件（data_3years.db-shm）权限问题

3. **文件系统锁定**
   - 其他进程正在访问数据库文件
   - 防病毒软件或备份软件正在扫描文件

### 解决方案

#### 方案1：使用自动服务控制脚本（推荐）
使用新创建的 `auto_update_with_service_control.bat` 脚本：
- 自动停止后端服务
- 运行更新脚本
- 自动重启后端服务

**使用方法：**
1. 右键点击 `auto_update_with_service_control.bat`
2. 选择"以管理员身份运行"
3. 脚本会自动处理服务停止和启动

**注意：** 此脚本需要管理员权限

#### 方案2：手动停止后端服务
如果方案1不可用，可以手动操作：

```powershell
# 停止后端服务
Stop-Service TR-Backend

# 运行更新脚本
cd "C:\TR-master\TR database"
python auto_update_all_tables.py

# 启动后端服务
Start-Service TR-Backend
```

#### 方案3：等待后端服务释放锁（不推荐）
更新脚本已经添加了重试机制：
- 自动重试最多15次
- 每次重试间隔5秒（指数退避）
- 超时时间增加到60秒

**注意：** 此方法可能需要很长时间，且可能仍然失败

#### 方案3：检查文件权限
```powershell
# 检查数据库文件权限
Get-Acl "C:\TR-master\TR database\data_3years.db" | Format-List

# 检查目录权限
Get-Acl "C:\TR-master\TR database" | Format-List

# 确保当前用户有写权限
```

#### 方案4：检查WAL文件
```powershell
# 检查WAL文件是否存在且可写
Get-ChildItem "C:\TR-master\TR database\data_3years.db*" | Select-Object Name, IsReadOnly
```

### 已实施的改进

1. **后端服务状态检查**
   - 更新开始时自动检查后端服务状态
   - 如果服务正在运行，提供明确的警告和建议

2. **增加超时时间**
   - 连接超时：30秒 → 60秒
   - busy_timeout：30秒 → 60秒

3. **增强重试机制**
   - 自动重试最多15次（DROP TABLE操作）
   - 每次重试间隔5秒（指数退避）
   - 针对只读错误和锁定错误

4. **改进DROP TABLE操作**
   - 使用 `BEGIN IMMEDIATE` 明确获取写锁
   - 更好的错误处理和回滚机制

5. **自动服务控制脚本**
   - 创建了 `auto_update_with_service_control.bat`
   - 自动停止/启动后端服务
   - 简化更新流程

### 最佳实践

1. **在系统负载较低时运行更新**
   - 避免在业务高峰期运行
   - 建议在夜间或周末运行

2. **监控更新日志**
   - 查看 `logs/auto_update_all_*.log` 文件
   - 检查是否有错误或警告

3. **定期检查数据库**
   - 确保数据库文件权限正确
   - 检查WAL文件状态

### 联系支持

如果问题持续存在，请提供：
1. 完整的错误日志（`logs/auto_update_all_*.log`）
2. 数据库文件权限信息
3. 后端服务状态
4. 系统负载情况
