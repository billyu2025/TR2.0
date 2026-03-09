# NSSM 快速设置指南（基础版）

## 目标

使用 NSSM 将 Flask 后端作为 Windows 服务运行，实现：
- ✅ 系统启动时自动启动
- ✅ 服务崩溃时自动重启
- ✅ 后台运行，无需手动启动
- ✅ 更好的资源管理

**注意：** 继续使用当前的 Threading 异步方案，不使用 Celery。

---

## 快速开始（5 分钟）

### 步骤 1：下载 NSSM（1 分钟）

**方法一：使用 PowerShell 自动下载**

```powershell
# 以管理员身份运行 PowerShell
cd "C:\TR-master\TR UI\backend"

# 创建 nssm 目录
New-Item -ItemType Directory -Force -Path "nssm"

# 下载 NSSM
$nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
$zipPath = "nssm\nssm.zip"
Invoke-WebRequest -Uri $nssmUrl -OutFile $zipPath -UseBasicParsing

# 解压
Expand-Archive -Path $zipPath -DestinationPath "nssm" -Force

# 清理
Remove-Item $zipPath
```

**方法二：手动下载**

1. 访问：https://nssm.cc/download
2. 下载：nssm-2.24.zip
3. 解压到：`C:\TR-master\TR UI\backend\nssm\`

### 步骤 2：检查 Python 路径（30 秒）

```powershell
# 查找 Python 路径
where.exe python

# 或
python -c "import sys; print(sys.executable)"
```

**记录下 Python 的完整路径**，例如：
- `C:\Python39\python.exe`
- `C:\Users\tradmin\AppData\Local\Programs\Python\Python39\python.exe`

### 步骤 3：使用自动化脚本安装（推荐，2 分钟）

```powershell
# 以管理员身份运行 PowerShell
cd "C:\TR-master\TR UI\backend"

# 运行安装脚本
.\install_nssm_service.ps1
```

脚本会自动：
- ✅ 检测 Python 路径
- ✅ 下载 NSSM（如需要）
- ✅ 安装并配置服务
- ✅ 启动服务
- ✅ 验证安装

### 步骤 4：手动安装（如果脚本失败，3 分钟）

#### 4.1 打开 NSSM 图形界面

```powershell
cd "C:\TR-master\TR UI\backend\nssm\win64"
.\nssm.exe install TR-Backend
```

#### 4.2 配置服务参数

在打开的窗口中配置：

**Application 标签页：**
- **Path**: `C:\Python39\python.exe`（你的 Python 路径）
- **Startup directory**: `C:\TR-master\TR UI\backend`
- **Arguments**: `start_waitress.py`

**Details 标签页：**
- **Display name**: `TR Report System Backend`
- **Description**: `TR Report System Backend API Server`
- **Startup type**: `Automatic`

**I/O 标签页：**
- **Output (stdout)**: `C:\TR-master\TR UI\backend\logs\nssm_output.log`
- **Error (stderr)**: `C:\TR-master\TR UI\backend\logs\nssm_error.log`

**Environment 标签页：**
点击 "Add" 添加环境变量：
- `API_HOST` = `0.0.0.0`
- `API_PORT` = `5000`
- `DEBUG` = `False`
- `WAITRESS_THREADS` = `8`

**Exit Actions 标签页：**
- **Exit action**: `Restart Application`
- **Restart delay**: `5 seconds`

#### 4.3 保存配置

点击 "Install service" 按钮

#### 4.4 启动服务

```powershell
Start-Service TR-Backend
```

---

## 验证安装

### 检查服务状态

```powershell
Get-Service TR-Backend
```

应该显示：
- **Status**: `Running`
- **StartType**: `Automatic`

### 检查端口监听

```powershell
netstat -ano | findstr ":5000"
```

应该看到类似：
```
TCP    0.0.0.0:5000           0.0.0.0:0              LISTENING       12345
```

### 测试 API

```powershell
# 测试健康检查
Invoke-WebRequest -Uri "http://localhost:5000/health" -UseBasicParsing
```

---

## 常用命令

### 服务管理

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

### 查看日志

```powershell
# 输出日志
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Tail 50

# 错误日志
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 50

# 实时监控
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Wait -Tail 20
```

### 使用 NSSM 命令

```powershell
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"

# 启动
& $nssm start TR-Backend

# 停止
& $nssm stop TR-Backend

# 重启
& $nssm restart TR-Backend

# 状态
& $nssm status TR-Backend
```

---

## 故障排除

### 问题 1：服务无法启动

**检查步骤：**

1. **查看错误日志**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 50
   ```

2. **检查 Python 路径**：
   ```powershell
   $nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"
   & $nssm get TR-Backend Application
   ```

3. **手动测试启动脚本**：
   ```powershell
   cd "C:\TR-master\TR UI\backend"
   python start_waitress.py
   ```

### 问题 2：服务启动后立即停止

**可能原因：**
- Python 脚本有错误
- 依赖未安装
- 端口被占用

**解决方法：**

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

**检查步骤：**

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

4. **查看应用日志**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Tail 50
   ```

---

## 优化配置

### 调整线程数

```powershell
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"

# 设置线程数为 8（可根据 CPU 核心数调整）
& $nssm set TR-Backend AppEnvironmentExtra "API_HOST=0.0.0.0" "API_PORT=5000" "DEBUG=False" "WAITRESS_THREADS=8"

# 重启服务使配置生效
& $nssm restart TR-Backend
```

**线程数建议：**
- 2-4 核心 CPU：4-6 线程
- 4-8 核心 CPU：8-12 线程
- 8+ 核心 CPU：12-16 线程

### 配置日志轮转

```powershell
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"

# 启用日志轮转
& $nssm set TR-Backend AppRotateFiles 1
& $nssm set TR-Backend AppRotateOnline 1
& $nssm set TR-Backend AppRotateSeconds 86400  # 每天轮转
& $nssm set TR-Backend AppRotateBytes 10485760  # 或 10MB 轮转
```

---

## 卸载服务

如果需要卸载服务：

```powershell
$nssm = "C:\TR-master\TR UI\backend\nssm\win64\nssm.exe"

# 停止服务
& $nssm stop TR-Backend

# 卸载服务
& $nssm remove TR-Backend confirm
```

---

## 完整流程总结

1. ✅ **下载 NSSM**（自动或手动）
2. ✅ **检查 Python 路径**
3. ✅ **运行安装脚本**（`install_nssm_service.ps1`）
4. ✅ **验证服务运行**
5. ✅ **测试 API**

---

## 预期效果

使用 NSSM 后：

- ✅ **自动启动**：系统启动时自动运行后端服务
- ✅ **自动重启**：服务崩溃时自动重启
- ✅ **后台运行**：无需手动启动，后台运行
- ✅ **稳定性提升**：更好的资源管理和监控
- ✅ **配合异步方案**：与 Threading 异步方案完美配合

---

## 下一步

1. **立即行动**：运行 `install_nssm_service.ps1` 安装服务
2. **验证运行**：检查服务状态和 API 响应
3. **监控日志**：定期查看日志确保正常运行

**完成！现在你的后端服务已配置为 Windows 服务，可以自动启动和重启！**
