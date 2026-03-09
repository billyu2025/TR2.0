# 内网访问问题排查指南

## 问题：无法通过 `http://192.168.32.97:8000/` 访问系统

## 已解决的问题

✅ **Nginx 未启动** - 已启动 Nginx 服务，现在 8000 端口正在监听

## 系统架构

系统使用以下架构：
- **前端**：通过 Nginx 在 8000 端口提供静态文件服务
- **后端**：Flask API 服务在 5000 端口运行
- **反向代理**：Nginx 将 `/api/` 请求转发到后端 5000 端口

## 当前状态检查

### 1. 检查服务运行状态

```powershell
# 检查 Nginx 是否运行（8000 端口）
netstat -ano | findstr ":8000"

# 检查后端服务是否运行（5000 端口）
netstat -ano | findstr ":5000"

# 检查 Nginx 进程
tasklist | findstr nginx
```

**预期结果**：
- 8000 端口应该显示 `LISTENING` 状态
- 5000 端口应该显示 `LISTENING` 状态
- 应该能看到 `nginx.exe` 进程

### 2. 检查防火墙设置

Windows 防火墙可能阻止了 8000 端口的访问。

**解决方法**：
1. 打开"Windows Defender 防火墙"
2. 点击"高级设置"
3. 选择"入站规则" → "新建规则"
4. 选择"端口" → "TCP" → "特定本地端口" → 输入 `8000`
5. 选择"允许连接"
6. 应用规则

或者使用 PowerShell（管理员权限）：
```powershell
New-NetFirewallRule -DisplayName "TR System Port 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

### 3. 检查 IP 地址

确认服务器 IP 地址是否正确：

```powershell
# 查看本机 IP 地址
ipconfig

# 查看所有网络接口
Get-NetIPAddress | Where-Object {$_.AddressFamily -eq "IPv4"} | Select-Object IPAddress, InterfaceAlias
```

**确认**：`192.168.32.97` 是否是服务器的实际 IP 地址？

### 4. 测试本地访问

在服务器本地测试：

```powershell
# 测试前端页面
curl http://localhost:8000/

# 测试后端 API
curl http://localhost:5000/health
```

如果本地可以访问，但内网无法访问，可能是防火墙或网络配置问题。

### 5. 测试内网访问

从其他内网机器测试：

```powershell
# 在其他机器上测试
curl http://192.168.32.97:8000/

# 测试 API
curl http://192.168.32.97:8000/api/health
```

## 常见问题及解决方法

### 问题 1：Nginx 未启动

**症状**：8000 端口没有服务在监听

**解决方法**：
```powershell
cd "C:\TR-master\TR UI\nginx-1.28.0"
.\nginx.exe
```

**验证**：
```powershell
netstat -ano | findstr ":8000"
```

### 问题 2：后端服务未启动

**症状**：5000 端口没有服务在监听

**解决方法**：
```powershell
cd "C:\TR-master\TR UI\backend"
python tr_fill_in_api.py
```

或者如果使用虚拟环境：
```powershell
cd "C:\TR-master\TR UI\backend"
.\venv\Scripts\activate
python tr_fill_in_api.py
```

### 问题 3：防火墙阻止访问

**症状**：本地可以访问，但内网无法访问

**解决方法**：
1. 检查 Windows 防火墙规则
2. 检查是否有其他防火墙软件（如企业防火墙）
3. 临时关闭防火墙测试（仅用于排查，不建议长期关闭）

### 问题 4：Nginx 配置错误

**症状**：可以访问前端，但 API 请求失败

**检查配置**：
```powershell
cd "C:\TR-master\TR UI\nginx-1.28.0"
.\nginx.exe -t
```

**重新加载配置**：
```powershell
.\nginx.exe -s reload
```

### 问题 5：端口被占用

**症状**：启动服务时提示端口被占用

**检查端口占用**：
```powershell
netstat -ano | findstr ":8000"
netstat -ano | findstr ":5000"
```

**解决方法**：
- 找到占用端口的进程 ID（PID）
- 结束该进程：`taskkill /PID <进程ID> /F`
- 或者修改配置文件使用其他端口

## 启动服务脚本

### 启动 Nginx

```powershell
cd "C:\TR-master\TR UI\nginx-1.28.0"
Start-Process -FilePath ".\nginx.exe" -WorkingDirectory (Get-Location)
```

### 启动后端服务

```powershell
cd "C:\TR-master\TR UI\backend"
python tr_fill_in_api.py
```

### 停止服务

**停止 Nginx**：
```powershell
cd "C:\TR-master\TR UI\nginx-1.28.0"
.\nginx.exe -s stop
```

**停止后端服务**：
- 在运行后端服务的终端按 `Ctrl+C`
- 或使用任务管理器结束 Python 进程

## 验证系统正常运行

### 1. 检查所有服务

```powershell
# 检查端口监听
netstat -ano | findstr ":8000"
netstat -ano | findstr ":5000"

# 检查进程
tasklist | findstr nginx
tasklist | findstr python
```

### 2. 测试 API 健康检查

```powershell
curl http://localhost:8000/api/health
```

**预期响应**：
```json
{"status":"ok"}
```

### 3. 测试前端页面

在浏览器中访问：
- 本地：`http://localhost:8000/`
- 内网：`http://192.168.32.97:8000/`

## 日志文件位置

- **Nginx 访问日志**：`C:\TR-master\TR UI\nginx-1.28.0\logs\access.log`
- **Nginx 错误日志**：`C:\TR-master\TR UI\nginx-1.28.0\logs\error.log`
- **后端日志**：后端服务运行时的控制台输出

## 联系支持

如果以上方法都无法解决问题，请提供以下信息：
1. 所有服务的运行状态（netstat 输出）
2. 防火墙配置情况
3. Nginx 错误日志内容
4. 后端服务日志内容
5. 网络配置信息（ipconfig 输出）
