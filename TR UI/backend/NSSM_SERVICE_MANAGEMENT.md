# NSSM 服务管理指南

## 服务名称说明

**重要：** Windows 服务有两个名称：
- **服务名称（Service Name）**：用于命令行操作，通常是 `TR-Backend`
- **显示名称（Display Name）**：在服务管理器中显示的名称，是 `TR Report System Backend`

**在命令行中，必须使用服务名称（`TR-Backend`），而不是显示名称！**

---

## 启动服务

### 方法一：使用 PowerShell（推荐）

```powershell
# 启动服务
Start-Service TR-Backend

# 检查状态
Get-Service TR-Backend
```

### 方法二：使用 NSSM 命令

```powershell
cd "C:\TR-master\TR UI\backend"
$nssm = "nssm\win64\nssm.exe"

# 启动服务
& $nssm start TR-Backend

# 检查状态
& $nssm status TR-Backend
```

### 方法三：使用 Windows 服务管理器

1. **打开服务管理器**：
   - 按 `Win + R`
   - 输入：`services.msc`
   - 按 Enter

2. **找到服务**：
   - 查找 "TR Report System Backend"（显示名称）

3. **启动服务**：
   - 右键点击服务
   - 选择 "启动"

---

## 常用服务管理命令

### 启动服务

```powershell
Start-Service TR-Backend
```

### 停止服务

```powershell
Stop-Service TR-Backend
```

### 重启服务

```powershell
Restart-Service TR-Backend
```

### 查看服务状态

```powershell
Get-Service TR-Backend
```

### 查看详细信息

```powershell
Get-Service TR-Backend | Format-List *
```

---

## 验证服务运行

### 1. 检查服务状态

```powershell
Get-Service TR-Backend
```

应该显示：
```
Status   Name               DisplayName
------   ----               -----------
Running  TR-Backend         TR Report System Backend
```

### 2. 检查端口监听

```powershell
netstat -ano | findstr ":5000"
```

应该看到类似：
```
TCP    0.0.0.0:5000           0.0.0.0:0              LISTENING       12345
```

### 3. 测试 API

```powershell
# 测试健康检查
Invoke-WebRequest -Uri "http://localhost:5000/health" -UseBasicParsing

# 或使用浏览器访问
# http://localhost:5000/health
```

---

## 查看日志

### 输出日志

```powershell
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Tail 50
```

### 错误日志

```powershell
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 50
```

### 实时监控日志

```powershell
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Wait -Tail 20
```

---

## 故障排除

### 问题 1：服务无法启动

**检查步骤：**

1. **查看错误日志**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 50
   ```

2. **检查服务配置**：
   ```powershell
   cd "C:\TR-master\TR UI\backend"
   $nssm = "nssm\win64\nssm.exe"
   
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

### 问题 2：服务启动后立即停止

**可能原因：**
- Python 脚本有错误
- 端口被占用
- 依赖未安装

**解决方法：**

1. **检查端口占用**：
   ```powershell
   netstat -ano | findstr ":5000"
   # 如果端口被占用，停止占用端口的进程
   ```

2. **查看详细错误**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log"
   ```

3. **检查依赖**：
   ```powershell
   cd "C:\TR-master\TR UI\backend"
   python -m pip install -r requirements.txt
   ```

### 问题 3：找不到服务

**如果服务未安装，先安装：**

```powershell
# 运行安装脚本
cd "C:\TR-master\TR UI\backend"
.\install_nssm_service.ps1
```

---

## 完整操作流程

### 第一次安装和启动

```powershell
# 1. 以管理员身份运行 PowerShell
# 2. 运行安装脚本
cd "C:\TR-master\TR UI\backend"
.\install_nssm_service.ps1

# 3. 脚本会自动启动服务
# 4. 验证服务运行
Get-Service TR-Backend
netstat -ano | findstr ":5000"
```

### 日常使用

```powershell
# 启动服务
Start-Service TR-Backend

# 停止服务
Stop-Service TR-Backend

# 重启服务
Restart-Service TR-Backend

# 查看状态
Get-Service TR-Backend
```

---

## 服务自动启动

**如果服务已配置为自动启动，系统重启后会自动运行。**

**检查启动类型：**

```powershell
Get-Service TR-Backend | Select-Object Name, StartType
```

**如果显示 `Manual`，设置为自动启动：**

```powershell
Set-Service TR-Backend -StartupType Automatic
```

---

## 快速参考

| 操作 | 命令 |
|------|------|
| **启动服务** | `Start-Service TR-Backend` |
| **停止服务** | `Stop-Service TR-Backend` |
| **重启服务** | `Restart-Service TR-Backend` |
| **查看状态** | `Get-Service TR-Backend` |
| **查看日志** | `Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Tail 50` |
| **测试 API** | `Invoke-WebRequest -Uri "http://localhost:5000/health" -UseBasicParsing` |

---

## 注意事项

1. **服务名称**：命令行使用 `TR-Backend`，不是显示名称
2. **管理员权限**：启动/停止服务需要管理员权限
3. **端口冲突**：确保端口 5000 未被其他程序占用
4. **日志位置**：日志文件在 `C:\TR-master\TR UI\backend\logs\`

---

**现在你可以启动服务了！**
