# PostgreSQL 启动问题修复总结

## 问题诊断

服务启动失败，错误信息：
```
psycopg.errors.UndefinedTable: relation "sqlite_master" does not exist
```

**原因**：代码在 PostgreSQL 模式下仍在使用 SQLite 特有的 `sqlite_master` 查询。

## 已修复的问题

### 1. ✅ 连接池问题
- **问题**：`get_db_connection()` 在 PostgreSQL 模式下仍尝试使用 SQLite 连接池
- **修复**：在 PostgreSQL 模式下直接使用 `db_adapter.get_connection()`
- **位置**：`tr_fill_in_api.py` 第 329-379 行

### 2. ✅ 表存在检查
- **问题**：`_ensure_account_tables()` 等函数使用 `sqlite_master` 查询
- **修复**：创建了 `_table_exists()` 辅助函数，支持 SQLite 和 PostgreSQL
- **位置**：`tr_fill_in_api.py` 第 377-401 行

### 3. ✅ 所有表检查函数
- 修复了以下函数中的 `sqlite_master` 查询：
  - `_ensure_account_tables()` - 第 539-750 行
  - `_ensure_file_index_tables()` - 第 995-1091 行
  - `_ensure_pdf_tasks_table()` - 第 1122-1148 行
  - `_ensure_download_tasks_table()` - 第 1151-1177 行
  - `check_pdf_status_table_exists()` - 第 1268-1295 行
  - `_ensure_bbs_dd_indexes()` - 第 404-450 行

## 重启服务步骤

### 方法 1：使用服务管理器（最简单）

1. 按 `Win + R`，输入 `services.msc`，回车
2. 找到 **"TR Report System Backend (TR-Backend)"**
3. 右键点击 → **停止**（如果正在运行或暂停）
4. 等待几秒
5. 右键点击 → **启动**

### 方法 2：使用批处理脚本（需要管理员权限）

1. 右键点击 `force_restart_service.bat`
2. 选择 **"以管理员身份运行"**
3. 按照提示操作

### 方法 3：手动 PowerShell 命令（需要管理员权限）

```powershell
# 以管理员身份运行 PowerShell

cd "C:\TR-master\TR UI\backend"

# 1. 停止服务
sc stop TR-Backend

# 2. 等待5秒
Start-Sleep -Seconds 5

# 3. 清理 Python 缓存
Get-ChildItem -Path . -Filter "*.pyc" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem -Path . -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

# 4. 启动服务
.\nssm-2.24\win64\nssm.exe start TR-Backend

# 5. 检查状态
.\nssm-2.24\win64\nssm.exe status TR-Backend
```

## 验证修复

服务启动后，检查日志：

```powershell
# 查看最新日志（应该不再有 sqlite_master 错误）
Get-Content "C:\TR-master\TR UI\backend\logs\app.log" -Tail 30

# 查看错误日志
Get-Content "C:\TR-master\TR UI\backend\logs\error.log" -Tail 20

# 查看 NSSM 错误日志
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 20
```

## 预期结果

服务启动后，日志应该显示：
- ✅ 数据库连接成功（PostgreSQL）
- ✅ 表初始化成功
- ✅ 服务监听在端口 5000
- ❌ **不应该**再有 `sqlite_master` 相关错误
- ❌ **不应该**再有连接池初始化错误

## 如果仍有问题

如果服务仍然无法启动，请提供：
1. NSSM 错误日志：`logs\nssm_error.log` 的最后 50 行
2. 应用错误日志：`logs\error.log` 的最后 50 行
3. 服务状态：`.\nssm-2.24\win64\nssm.exe status TR-Backend`
