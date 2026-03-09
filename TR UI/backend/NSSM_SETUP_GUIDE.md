# NSSM 服务配置指南

## 什么是 NSSM？

NSSM (Non-Sucking Service Manager) 是一个 Windows 服务包装器，可以将任何应用程序作为 Windows 服务运行。使用 NSSM 可以：
- ✅ 自动启动后端服务（系统启动时）
- ✅ 自动重启崩溃的服务
- ✅ 更好的资源管理和监控
- ✅ 解决后端拥堵和卡顿问题
- ✅ 无需手动启动，后台运行

---

## 步骤 1：下载 NSSM

### 方法一：直接下载（推荐）

1. **访问 NSSM 官网**：
   - https://nssm.cc/download
   - 或直接下载：https://nssm.cc/release/nssm-2.24.zip

2. **解压文件**：
   - 下载后解压到：`C:\TR-master\TR UI\backend\nssm\`
   - 或任何你方便的位置

3. **选择版本**：
   - 64位系统：使用 `win64` 文件夹中的 `nssm.exe`
   - 32位系统：使用 `win32` 文件夹中的 `nssm.exe`

### 方法二：使用 PowerShell 下载

```powershell
# 创建 nssm 目录
New-Item -ItemType Directory -Force -Path "C:\TR-master\TR UI\backend\nssm"

# 下载 NSSM
$nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
$zipPath = "C:\TR-master\TR UI\backend\nssm\nssm.zip"
Invoke-WebRequest -Uri $nssmUrl -OutFile $zipPath

# 解压
Expand-Archive -Path $zipPath -DestinationPath "C:\TR-master\TR UI\backend\nssm" -Force

# 清理
Remove-Item $zipPath
```

---

## 步骤 2：准备 Python 环境

### 检查 Python 路径

在 PowerShell 中运行：

```powershell
# 查找 Python 路径
where.exe python

# 或
python -c "import sys; print(sys.executable)"
```

记录下 Python 的完整路径，例如：`C:\Python39\python.exe`

### 检查 Python 依赖

确保已安装所有依赖：

```powershell
cd "C:\TR-master\TR UI\backend"
python -m pip install -r requirements.txt
```

---

## 步骤 3：安装 NSSM 服务

### 3.1 打开管理员 PowerShell

1. 按 `Win + X`
2. 选择 "Windows PowerShell (管理员)" 或 "终端 (管理员)"
3. 如果提示 UAC，点击"是"

### 3.2 导航到 NSSM 目录

```powershell
cd "C:\TR-master\TR UI\backend\nssm\win64"
```

（如果使用 32 位系统，使用 `win32` 文件夹）

### 3.3 安装服务

```powershell
# 安装服务（服务名：TR-Backend）
.\nssm.exe install TR-Backend
```

这会打开 NSSM 的图形界面配置窗口。

---

## 步骤 4：配置服务参数

在 NSSM 配置窗口中，按以下步骤配置：

### 4.1 Application 标签页

| 配置项 | 值 | 说明 |
|--------|-----|------|
| **Path** | `C:\Python39\python.exe` | Python 可执行文件的完整路径（替换为你的实际路径） |
| **Startup directory** | `C:\TR-master\TR UI\backend` | 后端工作目录 |
| **Arguments** | `start_waitress.py` | 启动脚本 |

**示例**：
- Path: `C:\Users\tradmin\AppData\Local\Programs\Python\Python39\python.exe`
- Startup directory: `C:\TR-master\TR UI\backend`
- Arguments: `start_waitress.py`

### 4.2 Details 标签页

| 配置项 | 值 | 说明 |
|--------|-----|------|
| **Display name** | `TR Report System Backend` | 服务显示名称 |
| **Description** | `TR Report System Backend API Server` | 服务描述 |
| **Startup type** | `Automatic` | 自动启动（系统启动时自动运行） |

### 4.3 I/O 标签页（日志配置）

| 配置项 | 值 | 说明 |
|--------|-----|------|
| **Input (stdin)** | `C:\TR-master\TR UI\backend\logs\nssm_input.log` | 标准输入日志 |
| **Output (stdout)** | `C:\TR-master\TR UI\backend\logs\nssm_output.log` | 标准输出日志 |
| **Error (stderr)** | `C:\TR-master\TR UI\backend\logs\nssm_error.log` | 错误日志 |

**注意**：确保 `logs` 目录存在：

```powershell
New-Item -ItemType Directory -Force -Path "C:\TR-master\TR UI\backend\logs"
```

### 4.4 Environment 标签页（环境变量）

点击 "Add" 按钮，添加以下环境变量：

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `API_HOST` | `0.0.0.0` | 监听所有网络接口 |
| `API_PORT` | `5000` | API 端口 |
| `DEBUG` | `False` | 生产模式 |
| `WAITRESS_THREADS` | `8` | Waitress 线程数（可根据需要调整） |

**添加方法**：
1. 在 "Variable" 输入框输入变量名（如 `API_HOST`）
2. 在 "Value" 输入框输入变量值（如 `0.0.0.0`）
3. 点击 "Add" 按钮
4. 重复添加其他环境变量

### 4.5 Exit Actions 标签页（退出行为）

| 配置项 | 值 | 说明 |
|--------|-----|------|
| **Exit action** | `Restart Application` | 服务崩溃时自动重启 |
| **Throttle restart** | `Restart delay: 5 seconds` | 重启延迟 5 秒 |

### 4.6 Process 标签页（进程管理）

| 配置项 | 值 | 说明 |
|--------|-----|------|
| **Priority** | `NORMAL_PRIORITY_CLASS` | 正常优先级（或根据需要调整） |
| **Affinity** | （留空） | 使用所有 CPU 核心 |

### 4.7 保存配置

点击 "Install service" 按钮保存配置。

---

## 步骤 5：使用命令行配置（可选，更快速）

如果你熟悉命令行，可以使用以下命令快速配置：

```powershell
# 设置变量
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"
$pythonPath = "C:\Python39\python.exe"  # 替换为你的 Python 路径
$workDir = "C:\TR-master\TR UI\backend"
$logDir = "C:\TR-master\TR UI\backend\logs"

# 确保日志目录存在
New-Item -ItemType Directory -Force -Path $logDir

# 安装服务
& $nssm install TR-Backend $pythonPath "start_waitress.py"

# 设置工作目录
& $nssm set TR-Backend AppDirectory $workDir

# 设置服务详情
& $nssm set TR-Backend DisplayName "TR Report System Backend"
& $nssm set TR-Backend Description "TR Report System Backend API Server"
& $nssm set TR-Backend Start SERVICE_AUTO_START

# 设置日志
& $nssm set TR-Backend AppStdout "$logDir\nssm_output.log"
& $nssm set TR-Backend AppStderr "$logDir\nssm_error.log"
& $nssm set TR-Backend AppRotateFiles 1
& $nssm set TR-Backend AppRotateOnline 1
& $nssm set TR-Backend AppRotateSeconds 86400
& $nssm set TR-Backend AppRotateBytes 10485760

# 设置环境变量
& $nssm set TR-Backend AppEnvironmentExtra "API_HOST=0.0.0.0" "API_PORT=5000" "DEBUG=False" "WAITRESS_THREADS=8"

# 设置退出行为（自动重启）
& $nssm set TR-Backend AppExit Default Restart
& $nssm set TR-Backend AppRestartDelay 5000

# 设置进程优先级
& $nssm set TR-Backend AppPriority NORMAL_PRIORITY_CLASS
```

---

## 步骤 6：启动和管理服务

### 6.1 启动服务

```powershell
# 方法一：使用 NSSM
& $nssm start TR-Backend

# 方法二：使用 Windows 服务管理器
Start-Service TR-Backend

# 方法三：使用 services.msc
# 按 Win + R，输入 services.msc，找到 "TR Report System Backend"，右键启动
```

### 6.2 检查服务状态

```powershell
# 检查服务状态
Get-Service TR-Backend

# 或使用 NSSM
& $nssm status TR-Backend
```

### 6.3 停止服务

```powershell
# 方法一：使用 NSSM
& $nssm stop TR-Backend

# 方法二：使用 Windows 服务管理器
Stop-Service TR-Backend
```

### 6.4 重启服务

```powershell
# 方法一：使用 NSSM
& $nssm restart TR-Backend

# 方法二：使用 Windows 服务管理器
Restart-Service TR-Backend
```

### 6.5 查看服务日志

```powershell
# 查看输出日志
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Tail 50

# 查看错误日志
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 50

# 实时监控日志
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Wait -Tail 20
```

---

## 步骤 7：验证服务运行

### 7.1 检查服务状态

```powershell
# 检查服务是否运行
Get-Service TR-Backend | Select-Object Name, Status, StartType
```

应该显示：
- **Status**: `Running`
- **StartType**: `Automatic`

### 7.2 测试 API 端点

```powershell
# 测试健康检查端点（如果有）
Invoke-WebRequest -Uri "http://localhost:5000/api/health" -UseBasicParsing

# 或测试其他端点
Invoke-WebRequest -Uri "http://localhost:5000/api/orders/list?page=1&per_page=10" -UseBasicParsing
```

### 7.3 检查端口监听

```powershell
# 检查端口 5000 是否被监听
netstat -ano | findstr ":5000"
```

应该看到类似：
```
TCP    0.0.0.0:5000           0.0.0.0:0              LISTENING       12345
```

---

## 步骤 8：配置服务自动启动

服务已设置为 `Automatic`，系统启动时会自动运行。如果需要修改：

```powershell
# 设置为自动启动
& $nssm set TR-Backend Start SERVICE_AUTO_START

# 或使用 Windows 服务管理器
Set-Service TR-Backend -StartupType Automatic
```

---

## 步骤 9：优化配置（解决拥堵问题）

### 9.1 调整 Waitress 线程数

根据服务器性能调整线程数：

```powershell
# 设置线程数为 8（可根据 CPU 核心数调整）
& $nssm set TR-Backend AppEnvironmentExtra "API_HOST=0.0.0.0" "API_PORT=5000" "DEBUG=False" "WAITRESS_THREADS=8"

# 重启服务使配置生效
& $nssm restart TR-Backend
```

**线程数建议**：
- 2-4 核心 CPU：4-6 线程
- 4-8 核心 CPU：8-12 线程
- 8+ 核心 CPU：12-16 线程

### 9.2 调整进程优先级

如果需要更高优先级（谨慎使用）：

```powershell
# 设置为高优先级（可能影响其他程序）
& $nssm set TR-Backend AppPriority HIGH_PRIORITY_CLASS

# 或正常优先级（推荐）
& $nssm set TR-Backend AppPriority NORMAL_PRIORITY_CLASS
```

### 9.3 配置日志轮转

防止日志文件过大：

```powershell
# 启用日志轮转
& $nssm set TR-Backend AppRotateFiles 1
& $nssm set TR-Backend AppRotateOnline 1
& $nssm set TR-Backend AppRotateSeconds 86400  # 每天轮转
& $nssm set TR-Backend AppRotateBytes 10485760  # 或 10MB 轮转

# 保留的日志文件数量
& $nssm set TR-Backend AppRotateDelay 0
```

---

## 步骤 10：卸载服务（如需要）

如果需要卸载服务：

```powershell
# 停止服务
& $nssm stop TR-Backend

# 卸载服务
& $nssm remove TR-Backend confirm
```

---

## 故障排除

### 问题 1：服务无法启动

**检查步骤**：

1. **查看错误日志**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 50
   ```

2. **检查 Python 路径是否正确**：
   ```powershell
   # 验证 Python 路径
   & $nssm get TR-Backend Application
   ```

3. **检查工作目录**：
   ```powershell
   & $nssm get TR-Backend AppDirectory
   ```

4. **手动测试启动脚本**：
   ```powershell
   cd "C:\TR-master\TR UI\backend"
   python start_waitress.py
   ```

### 问题 2：服务启动后立即停止

**可能原因**：
- Python 脚本有错误
- 依赖未安装
- 端口被占用

**解决方法**：

1. **检查端口占用**：
   ```powershell
   netstat -ano | findstr ":5000"
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

### 问题 3：服务运行但 API 无响应

**检查步骤**：

1. **检查服务是否运行**：
   ```powershell
   Get-Service TR-Backend
   ```

2. **检查端口监听**：
   ```powershell
   netstat -ano | findstr ":5000"
   ```

3. **检查防火墙**：
   - 确保 Windows 防火墙允许端口 5000
   - 或临时关闭防火墙测试

4. **查看应用日志**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Tail 50
   ```

### 问题 4：服务频繁重启

**可能原因**：
- 应用崩溃
- 资源不足
- 配置错误

**解决方法**：

1. **查看错误日志**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 100
   ```

2. **增加重启延迟**：
   ```powershell
   & $nssm set TR-Backend AppRestartDelay 10000  # 10 秒
   ```

3. **检查系统资源**：
   ```powershell
   # 查看内存和 CPU 使用
   Get-Process | Where-Object {$_.ProcessName -like "*python*"} | Select-Object ProcessName, CPU, WorkingSet
   ```

### 问题 5：修改配置后不生效

**解决方法**：

1. **重启服务**：
   ```powershell
   & $nssm restart TR-Backend
   ```

2. **验证配置**：
   ```powershell
   # 查看所有配置
   & $nssm get TR-Backend Application
   & $nssm get TR-Backend AppDirectory
   & $nssm get TR-Backend AppEnvironmentExtra
   ```

---

## 快速参考命令

```powershell
# 设置变量
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"

# 服务管理
& $nssm start TR-Backend      # 启动
& $nssm stop TR-Backend        # 停止
& $nssm restart TR-Backend     # 重启
& $nssm status TR-Backend      # 状态

# 查看配置
& $nssm get TR-Backend Application
& $nssm get TR-Backend AppDirectory
& $nssm get TR-Backend AppEnvironmentExtra

# 查看日志
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Tail 50
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 50

# Windows 服务管理器
Get-Service TR-Backend
Start-Service TR-Backend
Stop-Service TR-Backend
Restart-Service TR-Backend
```

---

## 下一步

服务配置完成后：

1. ✅ 验证服务正常运行
2. ✅ 测试 API 端点
3. ✅ 配置 Nginx 反向代理（如果使用）
4. ✅ 监控服务日志
5. ✅ 根据需要调整性能参数

---

## 注意事项

1. **权限**：NSSM 操作需要管理员权限
2. **路径**：所有路径使用绝对路径，避免相对路径问题
3. **日志**：定期清理日志文件，防止磁盘空间不足
4. **备份**：修改配置前备份 NSSM 配置
5. **测试**：在生产环境部署前，先在测试环境验证

---

**完成！现在你的后端服务已配置为 Windows 服务，可以自动启动和重启，解决拥堵问题！**
