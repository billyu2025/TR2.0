# 服务重启说明

## 问题修复

已修复 `UnboundLocalError: local variable 'is_postgres' referenced before assignment` 错误。

**修复内容**：
1. 在模块级别导入 `is_postgres`（第 250 行）
2. 移除了 `_ensure_download_tasks_table()` 和 `_ensure_pdf_tasks_table()` 函数内部的局部导入
3. 所有函数现在使用模块级别的 `is_postgres` 函数

## 重启步骤

### 方法 1：使用自动脚本（推荐）

**以管理员身份运行 PowerShell**，执行：

```powershell
cd "C:\TR-master\TR UI\backend"
.\force_restart_complete.ps1
```

### 方法 2：手动重启

**以管理员身份运行 PowerShell**，执行：

```powershell
cd "C:\TR-master\TR UI\backend"

# 1. 停止服务
.\nssm-2.24\win64\nssm.exe stop TR-Backend
Start-Sleep -Seconds 3

# 2. 关闭占用端口 5000 的进程（如果有）
$portInfo = netstat -ano | Select-String ":5000.*LISTENING"
if ($portInfo) {
    $pid = ($portInfo -split '\s+')[-1]
    if ($pid -match '^\d+$') {
        taskkill /F /PID $pid
        Start-Sleep -Seconds 2
    }
}

# 3. 清理 Python 缓存
Get-ChildItem -Path . -Filter "*.pyc" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem -Path . -Filter "__pycache__" -Recurse -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

# 4. 验证端口已释放
$portCheck = netstat -ano | Select-String ":5000.*LISTENING"
if (-not $portCheck) {
    Write-Host "端口 5000 已释放" -ForegroundColor Green
} else {
    Write-Host "警告: 端口 5000 仍被占用" -ForegroundColor Red
    exit 1
}

# 5. 启动服务
.\nssm-2.24\win64\nssm.exe start TR-Backend
Start-Sleep -Seconds 5

# 6. 检查状态
.\nssm-2.24\win64\nssm.exe status TR-Backend
netstat -ano | findstr ":5000"

# 7. 查看最新日志
Get-Content "logs\nssm_error.log" -Tail 10
Get-Content "logs\app.log" -Tail 10
```

## 验证

服务成功启动后，应该看到：
- ✅ 服务状态为 `SERVICE_RUNNING`
- ✅ 端口 5000 正在监听
- ✅ 日志中没有 `UnboundLocalError` 错误
- ✅ 日志显示 "download_tasks table already exists" 或 "download_tasks table created successfully"

## 如果仍有问题

1. **检查权限**：确保以管理员身份运行 PowerShell
2. **检查进程**：使用 `tasklist | findstr python` 查看是否有残留的 Python 进程
3. **检查日志**：查看 `logs\nssm_error.log` 和 `logs\app.log` 获取详细错误信息
4. **强制停止**：如果服务无法停止，使用 `sc stop TR-Backend` 或 `taskkill /F /PID <进程ID>`
