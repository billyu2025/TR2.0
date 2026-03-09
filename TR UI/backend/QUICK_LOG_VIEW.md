# 快速查看日志指南

## 快速命令

### 查看最近的错误

```powershell
cd "C:\TR-master\TR UI\backend"
Get-Content "logs\nssm_error.log" -Tail 30
```

### 查看应用日志

```powershell
Get-Content "logs\app.log" -Tail 30
```

### 实时监控错误日志

```powershell
Get-Content "logs\nssm_error.log" -Wait -Tail 20
```

---

## 使用脚本查看

### 方法一：使用 PowerShell 脚本

```powershell
cd "C:\TR-master\TR UI\backend"

# 查看错误日志
.\view_logs.ps1 -Type error -Lines 50

# 查看所有日志
.\view_logs.ps1 -Type all -Lines 30

# 实时监控
.\view_logs.ps1 -Type error -Lines 20 -Follow
```

### 方法二：使用批处理脚本

```cmd
cd "C:\TR-master\TR UI\backend"
monitor_logs.bat
```

---

## 常见错误及解决方法

### 1. 编码错误（UnicodeEncodeError）

**错误信息：**
```
UnicodeEncodeError: 'charmap' codec can't encode characters
```

**状态：** 正在修复中

**临时解决：** 错误不影响功能，只是输出问题

### 2. 连接池初始化错误

**错误信息：**
```
[Connection Pool] Failed to initialize connection pool
```

**状态：** 已自动降级到直接连接模式，功能正常

### 3. 模块未安装

**错误信息：**
```
flask-limiter not installed, rate limiting disabled
```

**状态：** 警告，不影响主要功能

---

## 日志文件说明

| 文件 | 说明 | 大小 |
|------|------|------|
| `nssm_error.log` | NSSM 错误日志 | ~97 KB |
| `nssm_output.log` | NSSM 输出日志 | ~26 KB |
| `app.log` | 应用日志 | ~84 KB |
| `error.log` | 应用错误日志 | ~6 KB |

---

## 一键诊断

运行以下命令快速诊断：

```powershell
cd "C:\TR-master\TR UI\backend"

Write-Host "=== Service Status ===" -ForegroundColor Cyan
Get-Service TR-Backend

Write-Host "`n=== Port Status ===" -ForegroundColor Cyan
netstat -ano | findstr ":5000"

Write-Host "`n=== Recent Errors (Last 10 lines) ===" -ForegroundColor Red
Get-Content "logs\nssm_error.log" -Tail 10

Write-Host "`n=== Recent App Log (Last 5 lines) ===" -ForegroundColor Yellow
Get-Content "logs\app.log" -Tail 5
```

---

**现在你可以方便地查看日志了！**
