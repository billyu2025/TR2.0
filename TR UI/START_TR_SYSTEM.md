# TR 系统启动指南

## 系统架构

TR 系统由两部分组成：

1. **后端服务（NSSM）** - 已在运行 ✅
   - 端口：5000
   - 服务名：TR-Backend
   - 状态：自动启动

2. **前端服务器（Nginx）** - 需要启动
   - 端口：8000
   - 提供前端界面和静态文件
   - 反向代理后端 API

---

## 启动步骤

### 步骤 1：启动 Nginx（前端服务器）

**方法一：使用命令行（推荐）**

```powershell
# 以管理员身份运行 PowerShell
cd "C:\TR-master\TR UI\nginx-1.28.0"
.\nginx.exe -p "C:\TR-master\TR UI\nginx-1.28.0" -c conf\nginx.conf
```

**方法二：使用批处理脚本**

创建 `start_nginx.bat` 文件：

```batch
@echo off
cd /d "C:\TR-master\TR UI\nginx-1.28.0"
start nginx.exe -p "C:\TR-master\TR UI\nginx-1.28.0" -c conf\nginx.conf
```

### 步骤 2：验证服务运行

```powershell
# 检查后端服务
Get-Service TR-Backend
netstat -ano | findstr ":5000"

# 检查前端服务
netstat -ano | findstr ":8000"
```

### 步骤 3：访问系统

打开浏览器，访问：

- **本地访问**：http://localhost:8000
- **内网访问**：http://192.168.32.97:8000（你的服务器 IP）

---

## 服务管理

### 后端服务（NSSM）

```powershell
# 查看状态
Get-Service TR-Backend

# 启动
Start-Service TR-Backend

# 停止
Stop-Service TR-Backend

# 重启
Restart-Service TR-Backend
```

### 前端服务（Nginx）

```powershell
cd "C:\TR-master\TR UI\nginx-1.28.0"

# 启动
.\nginx.exe -p "C:\TR-master\TR UI\nginx-1.28.0" -c conf\nginx.conf

# 停止
.\nginx.exe -s stop

# 重新加载配置
.\nginx.exe -s reload

# 检查配置
.\nginx.exe -p "C:\TR-master\TR UI\nginx-1.28.0" -c conf\nginx.conf -t
```

---

## 快速启动脚本

创建 `start_tr_system.bat`：

```batch
@echo off
echo ========================================
echo Starting TR System
echo ========================================
echo.

echo [1/2] Checking backend service...
sc query TR-Backend | findstr "RUNNING" >nul
if errorlevel 1 (
    echo Backend service is not running!
    echo Starting backend service...
    net start TR-Backend
    timeout /t 3 /nobreak >nul
) else (
    echo Backend service is running.
)

echo.
echo [2/2] Starting Nginx...
cd /d "C:\TR-master\TR UI\nginx-1.28.0"
start nginx.exe -p "C:\TR-master\TR UI\nginx-1.28.0" -c conf\nginx.conf
timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo TR System started!
echo ========================================
echo.
echo Access the system at:
echo   - Local: http://localhost:8000
echo   - Network: http://192.168.32.97:8000
echo.
pause
```

---

## 故障排除

### 问题 1：无法访问前端

**检查步骤：**

1. **检查 Nginx 是否运行**：
   ```powershell
   netstat -ano | findstr ":8000"
   ```

2. **检查 Nginx 进程**：
   ```powershell
   tasklist | findstr nginx
   ```

3. **查看 Nginx 错误日志**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\nginx-1.28.0\logs\error.log" -Tail 20
   ```

### 问题 2：前端可以访问但 API 无响应

**检查步骤：**

1. **检查后端服务**：
   ```powershell
   Get-Service TR-Backend
   netstat -ano | findstr ":5000"
   ```

2. **测试后端 API**：
   ```powershell
   Invoke-WebRequest -Uri "http://localhost:5000/health" -UseBasicParsing
   ```

3. **检查后端日志**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Tail 20
   ```

### 问题 3：端口被占用

**解决方法：**

```powershell
# 查找占用端口的进程
netstat -ano | findstr ":8000"
netstat -ano | findstr ":5000"

# 停止占用端口的进程（替换 PID）
taskkill /F /PID <PID>
```

---

## 系统访问地址

- **登录页面**：http://localhost:8000/login.html
- **主界面**：http://localhost:8000/dashboard.html
- **TR记录管理**：http://localhost:8000/tr-records.html
- **用户管理**：http://localhost:8000/user-management.html

**默认登录信息：**
- 用户名：admin
- 密码：Vschk!8866

---

## 自动启动配置

### 后端服务（已配置）

后端服务已通过 NSSM 配置为自动启动，系统重启后会自动运行。

### 前端服务（Nginx）

如果需要 Nginx 也自动启动，可以：

1. **使用任务计划程序**
2. **使用 NSSM 将 Nginx 也配置为服务**
3. **创建启动脚本并添加到启动文件夹**

---

**现在启动 Nginx 就可以访问 TR 系统了！**
