# NSSM 服务管理命令（完整版）

## 重要说明

**NSSM 路径：** `nssm-2.24\win64\nssm.exe`（不是 `nssm\win64\nssm.exe`）

**服务名称：** `TR-Backend`（不是显示名称 "TR Report System Backend"）

---

## 启动服务

### 方法一：使用 PowerShell（推荐）

```powershell
# 启动服务
Start-Service TR-Backend

# 或使用完整路径的 NSSM
cd "C:\TR-master\TR UI\backend"
.\nssm-2.24\win64\nssm.exe start TR-Backend
```

### 方法二：使用 CMD

```cmd
# 启动服务
net start TR-Backend

# 或使用完整路径的 NSSM
cd "C:\TR-master\TR UI\backend"
nssm-2.24\win64\nssm.exe start TR-Backend
```

### 方法三：使用脚本

**PowerShell 脚本：**
```powershell
cd "C:\TR-master\TR UI\backend"
.\start_nssm_service.ps1
```

**CMD 批处理：**
```cmd
cd "C:\TR-master\TR UI\backend"
start_nssm_service.bat
```

---

## 完整命令列表

### PowerShell 命令

```powershell
# 设置变量（PowerShell）
$nssm = "C:\TR-master\TR UI\backend\nssm-2.24\win64\nssm.exe"

# 启动服务
& $nssm start TR-Backend
# 或
Start-Service TR-Backend

# 停止服务
& $nssm stop TR-Backend
# 或
Stop-Service TR-Backend

# 重启服务
& $nssm restart TR-Backend
# 或
Restart-Service TR-Backend

# 查看状态
& $nssm status TR-Backend
# 或
Get-Service TR-Backend

# 查看配置
& $nssm get TR-Backend Application
& $nssm get TR-Backend AppDirectory
& $nssm get TR-Backend AppParameters
```

### CMD 命令

```cmd
# 启动服务
net start TR-Backend

# 停止服务
net stop TR-Backend

# 查看状态
sc query TR-Backend

# 使用 NSSM（完整路径）
cd "C:\TR-master\TR UI\backend"
nssm-2.24\win64\nssm.exe start TR-Backend
nssm-2.24\win64\nssm.exe stop TR-Backend
nssm-2.24\win64\nssm.exe restart TR-Backend
nssm-2.24\win64\nssm.exe status TR-Backend
```

---

## 快速启动（一键命令）

### PowerShell

```powershell
cd "C:\TR-master\TR UI\backend"
Start-Service TR-Backend
Get-Service TR-Backend
```

### CMD

```cmd
cd "C:\TR-master\TR UI\backend"
net start TR-Backend
sc query TR-Backend
```

---

## 验证服务运行

```powershell
# 1. 检查服务状态
Get-Service TR-Backend

# 2. 检查端口监听
netstat -ano | findstr ":5000"

# 3. 测试 API
Invoke-WebRequest -Uri "http://localhost:5000/health" -UseBasicParsing
```

---

## 常见错误解决

### 错误 1：`'$nssm' is not recognized`

**原因：** 在 CMD 中使用了 PowerShell 语法

**解决：** 
- 使用 CMD 命令：`net start TR-Backend`
- 或切换到 PowerShell

### 错误 2：`找不到服务`

**原因：** 服务未安装

**解决：**
```powershell
cd "C:\TR-master\TR UI\backend"
.\install_nssm_service.ps1
```

### 错误 3：`拒绝访问`

**原因：** 需要管理员权限

**解决：** 以管理员身份运行 PowerShell 或 CMD

---

## 推荐使用方式

**最简单的方式：**

```powershell
# 以管理员身份运行 PowerShell
Start-Service TR-Backend
```

**或者使用脚本：**

```powershell
cd "C:\TR-master\TR UI\backend"
.\start_nssm_service.ps1
```

---

**现在你可以启动服务了！**
