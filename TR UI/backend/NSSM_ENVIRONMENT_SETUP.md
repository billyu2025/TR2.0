# NSSM 环境变量配置方法

## 问题

在 NSSM 图形界面的 Environment 标签页中，可能没有明显的 "Add" 按钮。

## 解决方法

### 方法一：使用命令行配置（推荐，更简单）

**在安装服务后，使用命令行添加环境变量：**

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

# 设置环境变量（使用 AppEnvironmentExtra）
& $nssm set TR-Backend AppEnvironmentExtra "API_HOST=0.0.0.0" "API_PORT=5000" "DEBUG=False" "WAITRESS_THREADS=8"
```

### 方法二：在图形界面中配置

**如果使用图形界面，环境变量的配置方式：**

1. **打开 NSSM 配置窗口**：
   ```powershell
   cd "C:\TR-master\TR UI\backend\nssm\win64"
   .\nssm.exe edit TR-Backend
   ```

2. **Environment 标签页**：
   - 在 Environment 标签页中，你会看到一个**文本区域**或**列表**
   - **直接输入环境变量**，格式为：`变量名=值`
   - 每行一个环境变量
   - 或者使用分号分隔：`API_HOST=0.0.0.0;API_PORT=5000;DEBUG=False`

3. **输入以下环境变量**：
   ```
   API_HOST=0.0.0.0
   API_PORT=5000
   DEBUG=False
   WAITRESS_THREADS=8
   ```

4. **保存**：点击 "Edit service" 或 "OK" 按钮

### 方法三：使用完整命令行安装（最简单）

**直接使用命令行安装，一次性配置所有参数：**

```powershell
# 以管理员身份运行 PowerShell
cd "C:\TR-master\TR UI\backend"

# 设置变量
$nssm = "nssm\win64\nssm.exe"
$pythonPath = "C:\Users\tradmin\AppData\Local\Programs\Python\Python310\python.exe"
$workDir = "C:\TR-master\TR UI\backend"
$logDir = "C:\TR-master\TR UI\backend\logs"

# 确保日志目录存在
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# 如果 NSSM 还没解压，先解压
if (-not (Test-Path $nssm)) {
    if (Test-Path "nssm-2.24.zip") {
        Expand-Archive -Path "nssm-2.24.zip" -DestinationPath "nssm" -Force
        Write-Host "NSSM 已解压" -ForegroundColor Green
    } else {
        Write-Host "错误：找不到 nssm-2.24.zip" -ForegroundColor Red
        exit 1
    }
}

# 检查服务是否已存在
$existingService = Get-Service -Name "TR-Backend" -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Host "警告：服务 TR-Backend 已存在" -ForegroundColor Yellow
    $response = Read-Host "是否要删除现有服务并重新安装? (Y/N)"
    if ($response -eq 'Y' -or $response -eq 'y') {
        if ($existingService.Status -eq 'Running') {
            Stop-Service -Name "TR-Backend" -Force -ErrorAction SilentlyContinue
        }
        & $nssm remove TR-Backend confirm
        Start-Sleep -Seconds 1
    } else {
        Write-Host "已取消" -ForegroundColor Yellow
        exit 0
    }
}

# 安装服务
Write-Host "正在安装服务..." -ForegroundColor Yellow
& $nssm install TR-Backend $pythonPath "start_waitress.py"

# 设置工作目录
& $nssm set TR-Backend AppDirectory $workDir

# 设置服务详情
& $nssm set TR-Backend DisplayName "TR Report System Backend"
& $nssm set TR-Backend Description "TR Report System Backend API Server"
& $nssm set TR-Backend Start SERVICE_AUTO_START

# 设置日志
& $nssm set TR-Backend AppStdout (Join-Path $logDir "nssm_output.log")
& $nssm set TR-Backend AppStderr (Join-Path $logDir "nssm_error.log")
& $nssm set TR-Backend AppRotateFiles 1
& $nssm set TR-Backend AppRotateOnline 1
& $nssm set TR-Backend AppRotateSeconds 86400
& $nssm set TR-Backend AppRotateBytes 10485760

# 设置环境变量（关键步骤）
Write-Host "正在设置环境变量..." -ForegroundColor Yellow
& $nssm set TR-Backend AppEnvironmentExtra "API_HOST=0.0.0.0" "API_PORT=5000" "DEBUG=False" "WAITRESS_THREADS=8"

# 设置退出行为（自动重启）
& $nssm set TR-Backend AppExit Default Restart
& $nssm set TR-Backend AppRestartDelay 5000

# 设置进程优先级
& $nssm set TR-Backend AppPriority NORMAL_PRIORITY_CLASS

Write-Host "服务安装完成！" -ForegroundColor Green

# 启动服务
Write-Host "正在启动服务..." -ForegroundColor Yellow
Start-Service TR-Backend
Start-Sleep -Seconds 3

# 检查服务状态
$service = Get-Service TR-Backend
if ($service.Status -eq 'Running') {
    Write-Host "服务启动成功！" -ForegroundColor Green
} else {
    Write-Host "警告：服务状态: $($service.Status)" -ForegroundColor Yellow
    Write-Host "请查看错误日志: $(Join-Path $logDir 'nssm_error.log')" -ForegroundColor Yellow
}

# 验证
Write-Host ""
Write-Host "服务信息：" -ForegroundColor Cyan
Get-Service TR-Backend | Format-List Name, Status, StartType

Write-Host "端口监听：" -ForegroundColor Cyan
netstat -ano | findstr ":5000"
```

---

## 快速命令（复制粘贴）

**如果服务已安装，只需要添加环境变量：**

```powershell
cd "C:\TR-master\TR UI\backend"
$nssm = "nssm\win64\nssm.exe"

# 设置环境变量
& $nssm set TR-Backend AppEnvironmentExtra "API_HOST=0.0.0.0" "API_PORT=5000" "DEBUG=False" "WAITRESS_THREADS=8"

# 重启服务使配置生效
Restart-Service TR-Backend
```

---

## 验证环境变量

**检查环境变量是否设置成功：**

```powershell
cd "C:\TR-master\TR UI\backend"
$nssm = "nssm\win64\nssm.exe"

# 查看环境变量配置
& $nssm get TR-Backend AppEnvironmentExtra
```

应该显示：
```
API_HOST=0.0.0.0
API_PORT=5000
DEBUG=False
WAITRESS_THREADS=8
```

---

## 图形界面操作说明

**如果一定要使用图形界面：**

1. **打开编辑窗口**：
   ```powershell
   cd "C:\TR-master\TR UI\backend\nssm\win64"
   .\nssm.exe edit TR-Backend
   ```

2. **Environment 标签页**：
   - 在 Environment 标签页中，通常有一个**文本输入框**或**列表区域**
   - **直接输入**环境变量，格式：
     ```
     API_HOST=0.0.0.0
     API_PORT=5000
     DEBUG=False
     WAITRESS_THREADS=8
     ```
   - 每行一个，或者用分号分隔

3. **保存**：点击窗口底部的按钮（可能是 "Edit service"、"OK" 或 "Save"）

---

## 推荐方案

**建议使用命令行方式**，因为：
- ✅ 更快速
- ✅ 更准确
- ✅ 可以批量配置
- ✅ 易于脚本化

**完整的一键安装命令：**

```powershell
# 以管理员身份运行 PowerShell
cd "C:\TR-master\TR UI\backend"

# 解压 NSSM（如果还没解压）
if (-not (Test-Path "nssm\win64\nssm.exe")) {
    if (Test-Path "nssm-2.24.zip") {
        Expand-Archive -Path "nssm-2.24.zip" -DestinationPath "nssm" -Force
    }
}

# 运行完整安装脚本
.\install_nssm_service.ps1
```

脚本会自动配置所有环境变量，无需手动操作。
