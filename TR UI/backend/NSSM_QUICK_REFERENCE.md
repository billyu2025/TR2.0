# NSSM 快速参考

## 快速安装（一键脚本）

```powershell
# 以管理员身份运行 PowerShell
cd "C:\TR-master\TR UI\backend"
.\install_nssm_service.ps1
```

## 手动安装步骤

### 1. 下载 NSSM
- 访问：https://nssm.cc/download
- 解压到：`C:\TR-master\TR UI\backend\nssm\`

### 2. 安装服务（图形界面）
```powershell
cd "C:\TR-master\TR UI\backend\nssm\win64"
.\nssm.exe install TR-Backend
```

在打开的窗口中配置：
- **Path**: Python 路径（如 `C:\Python39\python.exe`）
- **Startup directory**: `C:\TR-master\TR UI\backend`
- **Arguments**: `start_waitress.py`
- **Environment**: 添加 `API_HOST=0.0.0.0`, `API_PORT=5000`, `DEBUG=False`, `WAITRESS_THREADS=8`

### 3. 启动服务
```powershell
Start-Service TR-Backend
```

---

## 常用命令

### 服务管理

```powershell
# 设置变量（只需设置一次）
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"

# 启动服务
Start-Service TR-Backend
# 或
& $nssm start TR-Backend

# 停止服务
Stop-Service TR-Backend
# 或
& $nssm stop TR-Backend

# 重启服务
Restart-Service TR-Backend
# 或
& $nssm restart TR-Backend

# 查看状态
Get-Service TR-Backend
# 或
& $nssm status TR-Backend
```

### 查看日志

```powershell
# 输出日志（最后 50 行）
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Tail 50

# 错误日志（最后 50 行）
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 50

# 实时监控日志
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Wait -Tail 20
```

### 查看配置

```powershell
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"

# 查看 Python 路径
& $nssm get TR-Backend Application

# 查看工作目录
& $nssm get TR-Backend AppDirectory

# 查看环境变量
& $nssm get TR-Backend AppEnvironmentExtra
```

### 修改配置

```powershell
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"

# 修改线程数
& $nssm set TR-Backend AppEnvironmentExtra "API_HOST=0.0.0.0" "API_PORT=5000" "DEBUG=False" "WAITRESS_THREADS=12"

# 修改后重启服务
& $nssm restart TR-Backend
```

### 卸载服务

```powershell
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"

# 停止服务
& $nssm stop TR-Backend

# 卸载服务
& $nssm remove TR-Backend confirm
```

---

## 故障排除

### 服务无法启动

```powershell
# 1. 查看错误日志
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 50

# 2. 手动测试启动脚本
cd "C:\TR-master\TR UI\backend"
python start_waitress.py

# 3. 检查端口占用
netstat -ano | findstr ":5000"
```

### 服务频繁重启

```powershell
# 1. 查看错误日志
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 100

# 2. 增加重启延迟
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"
& $nssm set TR-Backend AppRestartDelay 10000
& $nssm restart TR-Backend
```

### 验证服务运行

```powershell
# 检查服务状态
Get-Service TR-Backend

# 检查端口监听
netstat -ano | findstr ":5000"

# 测试 API
Invoke-WebRequest -Uri "http://localhost:5000/api/health" -UseBasicParsing
```

---

## 性能优化

### 调整线程数

```powershell
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"

# 根据 CPU 核心数调整（建议：核心数 × 2）
# 4 核心：8 线程
# 8 核心：16 线程
& $nssm set TR-Backend AppEnvironmentExtra "API_HOST=0.0.0.0" "API_PORT=5000" "DEBUG=False" "WAITRESS_THREADS=8"
& $nssm restart TR-Backend
```

### 调整进程优先级

```powershell
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"

# 正常优先级（推荐）
& $nssm set TR-Backend AppPriority NORMAL_PRIORITY_CLASS

# 高优先级（谨慎使用）
& $nssm set TR-Backend AppPriority HIGH_PRIORITY_CLASS
```

---

## Windows 服务管理器

### 打开服务管理器

```powershell
# 方法 1：命令行
services.msc

# 方法 2：开始菜单
# Win + R，输入 services.msc
```

### 在服务管理器中操作

1. 找到 "TR Report System Backend"
2. 右键可以：
   - 启动/停止/重启
   - 查看属性
   - 查看事件日志

---

## 完整文档

详细配置指南：`NSSM_SETUP_GUIDE.md`
