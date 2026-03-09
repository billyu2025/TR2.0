# 如何手动启动后端服务

## 方法1：使用Windows服务（推荐）

后端服务已安装为Windows服务，服务名为：**TR-Backend**

### 启动服务

#### PowerShell（推荐）
```powershell
Start-Service TR-Backend
```

#### 命令提示符（CMD）
```cmd
net start TR-Backend
```

#### 图形界面
1. 按 `Win + R`，输入 `services.msc`，回车
2. 找到 **TR Report System Backend (TR-Backend)**
3. 右键点击，选择 **"启动"**

### 停止服务

#### PowerShell
```powershell
Stop-Service TR-Backend
```

#### 命令提示符（CMD）
```cmd
net stop TR-Backend
```

### 重启服务

#### PowerShell
```powershell
Restart-Service TR-Backend
```

#### 命令提示符（CMD）
```cmd
net stop TR-Backend
net start TR-Backend
```

### 检查服务状态

#### PowerShell
```powershell
Get-Service TR-Backend
```

#### 命令提示符（CMD）
```cmd
sc query TR-Backend
```

## 方法2：直接运行Python脚本（开发/测试用）

如果服务无法启动，可以临时直接运行Python脚本：

### 步骤1：打开命令提示符或PowerShell

### 步骤2：切换到后端目录
```cmd
cd "C:\TR-master\TR UI\backend"
```

### 步骤3：运行启动脚本
```cmd
python start_waitress.py
```

**注意：** 
- 这种方式会在当前窗口运行，关闭窗口会停止服务
- 仅用于开发/测试，生产环境应使用Windows服务

## 方法3：使用批处理脚本

如果存在启动脚本，可以直接运行：

```cmd
cd "C:\TR-master\TR UI\backend"
start_waitress.bat
```

## 验证服务是否启动成功

### 检查端口
```powershell
netstat -ano | findstr ":5000"
```

如果看到类似以下输出，说明服务已启动：
```
TCP    0.0.0.0:5000           0.0.0.0:0              LISTENING       xxxxx
```

### 测试API
在浏览器中访问：
```
http://localhost:5000/api/health
```

或使用PowerShell：
```powershell
Invoke-WebRequest -Uri "http://localhost:5000/api/health" -UseBasicParsing
```

## 常见问题

### Q1: 服务无法启动，提示"拒绝访问"
**解决方法：** 需要管理员权限
- 右键点击PowerShell或CMD
- 选择"以管理员身份运行"
- 然后再执行启动命令

### Q2: 服务启动后立即停止
**解决方法：** 查看日志文件
```powershell
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Tail 50
```

### Q3: 端口5000已被占用
**解决方法：** 查找占用端口的进程
```powershell
netstat -ano | findstr ":5000"
```
然后结束该进程，或修改后端服务的端口配置

## 服务配置信息

- **服务名称：** TR-Backend
- **显示名称：** TR Report System Backend
- **可执行文件：** `C:\TR-master\TR UI\backend\start_waitress.py`
- **工作目录：** `C:\TR-master\TR UI\backend`
- **监听地址：** 0.0.0.0:5000

## 快速命令参考

```powershell
# 启动
Start-Service TR-Backend

# 停止
Stop-Service TR-Backend

# 重启
Restart-Service TR-Backend

# 查看状态
Get-Service TR-Backend

# 查看日志（最后50行）
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_output.log" -Tail 50
```
