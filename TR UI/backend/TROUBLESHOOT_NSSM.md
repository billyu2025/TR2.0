# NSSM 服务故障排除

## 当前问题：端口 5000 未监听

**症状：** `netstat -ano | findstr ":5000"` 没有输出

**可能原因：**
1. 服务未安装
2. 服务已安装但未启动
3. 服务启动失败

---

## 诊断步骤

### 步骤 1：检查服务是否存在

```powershell
# 检查服务是否存在
Get-Service -Name "TR-Backend" -ErrorAction SilentlyContinue
```

**如果服务不存在：**
- 需要先安装服务
- 运行：`.\install_nssm_service.ps1`

**如果服务存在：**
- 继续步骤 2

### 步骤 2：检查服务状态

```powershell
Get-Service TR-Backend
```

**可能的状态：**
- `Stopped` - 服务已停止，需要启动
- `Running` - 服务在运行，但端口未监听（可能是启动失败）
- `StartPending` - 服务正在启动
- `StopPending` - 服务正在停止

### 步骤 3：如果服务已停止，尝试启动

```powershell
Start-Service TR-Backend
```

### 步骤 4：如果启动失败，查看错误日志

```powershell
cd "C:\TR-master\TR UI\backend"
Get-Content "logs\nssm_error.log" -Tail 50
```

---

## 常见问题解决

### 问题 1：服务不存在

**解决方法：安装服务**

```powershell
cd "C:\TR-master\TR UI\backend"
.\install_nssm_service.ps1
```

### 问题 2：服务存在但无法启动

**检查步骤：**

1. **查看错误日志**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 50
   ```

2. **检查服务配置**：
   ```powershell
   cd "C:\TR-master\TR UI\backend"
   $nssm = "nssm-2.24\win64\nssm.exe"
   
   # 查看 Python 路径
   & $nssm get TR-Backend Application
   
   # 查看工作目录
   & $nssm get TR-Backend AppDirectory
   
   # 查看启动参数
   & $nssm get TR-Backend AppParameters
   ```

3. **手动测试启动脚本**：
   ```powershell
   cd "C:\TR-master\TR UI\backend"
   python start_waitress.py
   ```

### 问题 3：服务启动但端口未监听

**可能原因：**
- 启动脚本有错误
- 端口被占用
- 配置错误

**解决方法：**

1. **检查端口占用**：
   ```powershell
   netstat -ano | findstr ":5000"
   ```

2. **查看应用日志**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Tail 50
   ```

3. **检查防火墙**：
   - 确保 Windows 防火墙允许端口 5000

---

## 快速诊断脚本

**运行以下命令进行完整诊断：**

```powershell
cd "C:\TR-master\TR UI\backend"

Write-Host "=== 服务状态 ===" -ForegroundColor Cyan
$service = Get-Service -Name "TR-Backend" -ErrorAction SilentlyContinue
if ($service) {
    Write-Host "服务存在" -ForegroundColor Green
    Write-Host "状态: $($service.Status)" -ForegroundColor Yellow
    Write-Host "启动类型: $($service.StartType)" -ForegroundColor Yellow
} else {
    Write-Host "服务不存在，需要安装" -ForegroundColor Red
}

Write-Host "`n=== 端口监听 ===" -ForegroundColor Cyan
$port = netstat -ano | Select-String ":5000" | Select-String "LISTENING"
if ($port) {
    Write-Host "端口 5000 正在监听" -ForegroundColor Green
    Write-Host $port
} else {
    Write-Host "端口 5000 未监听" -ForegroundColor Red
}

Write-Host "`n=== 错误日志（最后 20 行）===" -ForegroundColor Cyan
if (Test-Path "logs\nssm_error.log") {
    Get-Content "logs\nssm_error.log" -Tail 20
} else {
    Write-Host "错误日志文件不存在" -ForegroundColor Yellow
}

Write-Host "`n=== 输出日志（最后 20 行）===" -ForegroundColor Cyan
if (Test-Path "logs\nssm_output.log") {
    Get-Content "logs\nssm_output.log" -Tail 20
} else {
    Write-Host "输出日志文件不存在" -ForegroundColor Yellow
}
```

---

## 重新安装服务

**如果服务配置有问题，可以重新安装：**

```powershell
cd "C:\TR-master\TR UI\backend"
$nssm = "nssm-2.24\win64\nssm.exe"

# 停止并删除现有服务
$service = Get-Service -Name "TR-Backend" -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -eq 'Running') {
        Stop-Service TR-Backend -Force
    }
    & $nssm remove TR-Backend confirm
}

# 重新运行安装脚本
.\install_nssm_service.ps1
```

---

## 下一步

根据诊断结果：
1. **如果服务不存在** → 运行 `install_nssm_service.ps1`
2. **如果服务存在但未启动** → 运行 `Start-Service TR-Backend`
3. **如果服务启动失败** → 查看错误日志并修复问题
