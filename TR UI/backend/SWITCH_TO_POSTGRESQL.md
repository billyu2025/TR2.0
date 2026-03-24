# 切换到 PostgreSQL 数据库完整指南

## 📋 前置条件

1. ✅ PostgreSQL 服务已安装并运行（端口 5432）
2. ✅ Python 环境已配置
3. ✅ 后端服务已安装（TR-Backend）

---

## 🔧 步骤 1：安装 PostgreSQL Python 驱动

```powershell
# 以管理员身份运行 PowerShell
cd "C:\TR-master\TR UI\backend"
pip install psycopg[binary] psycopg-pool
```

---

## 🗄️ 步骤 2：创建 PostgreSQL 数据库（如果还没有）

```powershell
# 连接到 PostgreSQL（使用默认 postgres 用户）
psql -U postgres

# 在 psql 中执行：
CREATE DATABASE tr_db;
\q
```

或者使用命令行：

```cmd
psql -U postgres -c "CREATE DATABASE tr_db;"
```

---

## 📐 步骤 3：创建表结构

```powershell
cd "C:\TR-master\TR UI\backend"

# 设置 PostgreSQL 连接字符串
$env:POSTGRES_DSN = "postgresql://postgres:postgres@127.0.0.1:5432/tr_db"

# 执行 schema 脚本
python apply_postgres_schema.py
```

**预期输出：**
```
[SCHEMA] PostgreSQL DSN: postgresql://postgres:postgres@127.0.0.1:5432/tr_db
[SCHEMA] Schema file: C:\TR-master\TR UI\backend\schema_postgres.sql
[SCHEMA] Reading schema file...
[SCHEMA] Connecting to PostgreSQL...
[SCHEMA] Executing schema SQL...
✅ Schema applied successfully!
```

---

## 📦 步骤 4：迁移 SQLite 数据到 PostgreSQL（可选）

如果你需要保留 SQLite 中的现有数据：

```powershell
cd "C:\TR-master\TR UI\backend"

# 设置环境变量
$env:SQLITE_DB_PATH = "C:\TR-master\TR database\data_3years.db"
$env:POSTGRES_DSN = "postgresql://postgres:postgres@127.0.0.1:5432/tr_db"

# 执行迁移
python migrate_sqlite_to_postgres.py
```

**迁移的表包括：**
- user_accounts（用户账户）
- user_job_access（用户工地权限）
- user_sessions（用户会话）
- download_tasks（下载任务）
- pdf_tasks（PDF 生成任务）
- PDF_Status（PDF 状态）
- file_index_cache（文件索引缓存）
- file_index_metadata（文件索引元数据）
- bbs_dd（BBS DD 表）
- TR_Report（TR 报告表）
- TR_Report_Deduplication（TR 报告去重表）

---

## ⚙️ 步骤 5：配置后端服务使用 PostgreSQL

### 方法 A：使用 NSSM 命令行（推荐）

```powershell
# 以管理员身份运行 PowerShell
cd "C:\TR-master\TR UI\backend"

# 设置 NSSM 路径
$nssm = "nssm\win64\nssm.exe"

# 如果 NSSM 还没解压，先解压
if (-not (Test-Path $nssm)) {
    if (Test-Path "nssm-2.24.zip") {
        Expand-Archive -Path "nssm-2.24.zip" -DestinationPath "nssm" -Force
    }
}

# 添加 PostgreSQL 环境变量
& $nssm set TR-Backend AppEnvironmentExtra "DB_BACKEND=postgres" "POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/tr_db"
```

### 方法 B：使用 NSSM 图形界面

```powershell
cd "C:\TR-master\TR UI\backend\nssm\win64"
.\nssm.exe edit TR-Backend
```

在 **Environment** 标签页中添加：
```
DB_BACKEND=postgres
POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/tr_db
```

---

## 🔄 步骤 6：重启后端服务

```powershell
# 停止服务
Stop-Service TR-Backend

# 等待几秒
Start-Sleep -Seconds 3

# 启动服务
Start-Service TR-Backend

# 检查状态
Get-Service TR-Backend
```

---

## ✅ 步骤 7：验证切换成功

### 7.1 检查服务日志

```powershell
# 查看日志文件
Get-Content "C:\TR-master\TR UI\backend\logs\app.log" -Tail 20
```

**应该看到：**
```
Database backend: postgres
Database: postgresql://postgres:postgres@127.0.0.1:5432/tr_db
```

### 7.2 测试 API 连接

在浏览器中访问：
```
http://localhost:5000/health
```

应该返回正常响应。

### 7.3 测试登录

访问前端登录页面：
```
http://localhost:8000/login.html
```

使用你的账户登录，验证数据库连接正常。

---

## 🔄 步骤 8：更新计划任务（如果需要）

如果计划任务需要更新数据，确保计划任务也使用 PostgreSQL：

### 8.1 检查计划任务

```cmd
schtasks /Query /TN "TR-Auto-Update-All-Tables"
```

### 8.2 修改批处理文件

编辑 `C:\TR-master\TR database\auto_update_all_tables.bat`，确保包含：

```batch
@echo off
set DB_BACKEND=postgres
set POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/tr_db

cd /d "C:\TR-master\TR UI\backend"
python generate_tr_report_3years.py
python update_tr_report_deduplication.py
```

---

## 🐛 故障排除

### 问题 1：psycopg 模块未找到

```powershell
pip install psycopg[binary] psycopg-pool
```

### 问题 2：PostgreSQL 连接失败

检查：
1. PostgreSQL 服务是否运行：`netstat -ano | findstr ":5432"`
2. 数据库是否存在：`psql -U postgres -l`
3. 用户名密码是否正确

### 问题 3：表结构创建失败

手动执行 SQL：

```powershell
psql -U postgres -d tr_db -f "C:\TR-master\TR UI\backend\schema_postgres.sql"
```

### 问题 4：服务启动失败

检查日志：
```powershell
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 50
```

### 问题 5：环境变量未生效

确保使用 NSSM 设置环境变量，而不是系统环境变量。

---

## 📝 注意事项

1. **备份数据**：切换前建议备份 SQLite 数据库
2. **测试环境**：建议先在测试环境验证
3. **用户账户**：如果迁移数据，用户账户和密码会一起迁移
4. **PDF 状态**：已生成的 PDF 状态会迁移，但 PDF 文件本身不会迁移
5. **文件索引**：文件索引缓存需要重新建立（或从 SQLite 迁移）

---

## 🔙 回退到 SQLite（如果需要）

如果切换后出现问题，可以回退：

```powershell
# 移除 PostgreSQL 环境变量
& $nssm set TR-Backend AppEnvironmentExtra "DB_BACKEND=sqlite"

# 重启服务
Restart-Service TR-Backend
```

---

## ✅ 切换完成检查清单

- [ ] PostgreSQL 服务运行正常
- [ ] psycopg 驱动已安装
- [ ] tr_db 数据库已创建
- [ ] 表结构已创建
- [ ] 数据已迁移（如需要）
- [ ] NSSM 环境变量已配置
- [ ] 后端服务已重启
- [ ] 日志显示使用 PostgreSQL
- [ ] API 测试通过
- [ ] 前端登录测试通过

---

**切换完成后，系统将完全使用 PostgreSQL 数据库！** 🎉
