# 查看 TR 系统日志指南

## 日志文件位置

### 后端日志

**位置：** `C:\TR-master\TR UI\backend\logs\`

**主要日志文件：**

1. **应用日志** - `app.log` 或 `tr_system.log`
   - 应用程序运行日志
   - 包含 INFO、WARNING、ERROR 级别

2. **NSSM 输出日志** - `nssm_output.log`
   - NSSM 服务标准输出
   - 包含 print 语句输出

3. **NSSM 错误日志** - `nssm_error.log`
   - NSSM 服务错误输出
   - 包含异常和错误信息

### 前端日志（Nginx）

**位置：** `C:\TR-master\TR UI\nginx-1.28.0\logs\`

**主要日志文件：**

1. **访问日志** - `access.log`
   - HTTP 请求记录

2. **错误日志** - `error.log`
   - Nginx 错误信息

---

## 查看日志的方法

### 方法一：使用 PowerShell（推荐）

#### 查看最近的错误

```powershell
cd "C:\TR-master\TR UI\backend"
Get-Content "logs\nssm_error.log" -Tail 50
```

#### 查看应用日志

```powershell
Get-Content "logs\app.log" -Tail 50
```

#### 实时监控日志（类似 tail -f）

```powershell
# 监控错误日志
Get-Content "logs\nssm_error.log" -Wait -Tail 20

# 监控输出日志
Get-Content "logs\nssm_output.log" -Wait -Tail 20

# 监控应用日志
Get-Content "logs\app.log" -Wait -Tail 20
```

### 方法二：使用文本编辑器

直接打开日志文件：
- `C:\TR-master\TR UI\backend\logs\nssm_error.log`
- `C:\TR-master\TR UI\backend\logs\nssm_output.log`
- `C:\TR-master\TR UI\backend\logs\app.log`

### 方法三：使用日志查看脚本

创建 `view_logs.ps1`：

```powershell
# 日志查看脚本
param(
    [string]$Type = "error",
    [int]$Lines = 50
)

$logDir = "C:\TR-master\TR UI\backend\logs"

switch ($Type.ToLower()) {
    "error" {
        $logFile = Join-Path $logDir "nssm_error.log"
        Write-Host "=== NSSM Error Log (Last $Lines lines) ===" -ForegroundColor Red
    }
    "output" {
        $logFile = Join-Path $logDir "nssm_output.log"
        Write-Host "=== NSSM Output Log (Last $Lines lines) ===" -ForegroundColor Cyan
    }
    "app" {
        $logFile = Join-Path $logDir "app.log"
        Write-Host "=== Application Log (Last $Lines lines) ===" -ForegroundColor Yellow
    }
    default {
        Write-Host "Usage: .\view_logs.ps1 -Type [error|output|app] -Lines [number]"
        exit 1
    }
}

if (Test-Path $logFile) {
    Get-Content $logFile -Tail $Lines
} else {
    Write-Host "Log file not found: $logFile" -ForegroundColor Red
}
```

**使用方法：**

```powershell
# 查看错误日志（最后 50 行）
.\view_logs.ps1 -Type error

# 查看输出日志（最后 100 行）
.\view_logs.ps1 -Type output -Lines 100

# 查看应用日志
.\view_logs.ps1 -Type app
```

---

## 实时监控日志

### 使用 PowerShell 实时监控

```powershell
# 监控所有日志（新窗口）
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Get-Content 'C:\TR-master\TR UI\backend\logs\nssm_error.log' -Wait -Tail 20"
```

### 使用批处理脚本监控

创建 `monitor_logs.bat`：

```batch
@echo off
echo Monitoring TR System Logs...
echo Press Ctrl+C to stop
echo.

cd /d "C:\TR-master\TR UI\backend\logs"

:loop
cls
echo ========================================
echo TR System Logs - %date% %time%
echo ========================================
echo.
echo [ERROR LOG - Last 20 lines]
echo ----------------------------------------
powershell -Command "Get-Content 'nssm_error.log' -Tail 20 -ErrorAction SilentlyContinue"
echo.
echo [OUTPUT LOG - Last 20 lines]
echo ----------------------------------------
powershell -Command "Get-Content 'nssm_output.log' -Tail 20 -ErrorAction SilentlyContinue"
echo.
echo ========================================
timeout /t 5 /nobreak >nul
goto loop
```

---

## 常见错误类型

### 1. 编码错误

**症状：**
```
UnicodeEncodeError: 'charmap' codec can't encode characters
```

**解决方法：** 已修复，如果仍有问题，检查相关文件

### 2. 数据库连接错误

**症状：**
```
sqlite3.OperationalError: database is locked
```

**解决方法：** 检查数据库文件权限和连接池配置

### 3. 端口占用

**症状：**
```
OSError: [WinError 10048] 通常每个套接字地址只允许使用一次
```

**解决方法：** 检查端口占用，停止冲突的进程

### 4. 模块导入错误

**症状：**
```
ModuleNotFoundError: No module named 'xxx'
```

**解决方法：** 安装缺失的 Python 模块

---

## 日志级别说明

### ERROR（错误）
- 严重错误，需要立即处理
- 通常会导致功能无法使用

### WARNING（警告）
- 潜在问题，不影响主要功能
- 建议检查但非紧急

### INFO（信息）
- 正常运行信息
- 用于跟踪程序执行流程

### DEBUG（调试）
- 详细的调试信息
- 仅在开发时使用

---

## 快速诊断命令

```powershell
cd "C:\TR-master\TR UI\backend"

# 查看最近的错误
Write-Host "=== Recent Errors ===" -ForegroundColor Red
Get-Content "logs\nssm_error.log" -Tail 30

# 查看服务状态
Write-Host "`n=== Service Status ===" -ForegroundColor Cyan
Get-Service TR-Backend

# 查看端口监听
Write-Host "`n=== Port Status ===" -ForegroundColor Cyan
netstat -ano | findstr ":5000"

# 查看最近的输出
Write-Host "`n=== Recent Output ===" -ForegroundColor Yellow
Get-Content "logs\nssm_output.log" -Tail 20
```

---

## 日志文件大小管理

如果日志文件过大，可以：

### 方法一：清空日志

```powershell
# 清空错误日志（保留备份）
Copy-Item "logs\nssm_error.log" "logs\nssm_error.log.backup"
Clear-Content "logs\nssm_error.log"
```

### 方法二：配置日志轮转

NSSM 已配置日志轮转：
- 每天轮转
- 或文件大小达到 10MB 时轮转

---

## 在代码中改进错误显示

如果需要在前端或控制台显示错误，可以：

1. **添加错误通知 API**
2. **使用 WebSocket 实时推送错误**
3. **在前端添加错误日志查看页面**

---

**现在你可以方便地查看和监控日志了！**
