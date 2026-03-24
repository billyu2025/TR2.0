# 修复 TR-Backend 服务暂停状态

## 问题
服务处于 `SERVICE_PAUSED` 状态，无法直接启动。

## 解决方案

### 方法 1：使用服务管理器（最简单，推荐）

1. 按 `Win + R`，输入 `services.msc`，回车
2. 找到 **"TR Report System Backend (TR-Backend)"**
3. 右键点击服务
4. 如果显示"继续"，点击"继续"
5. 然后右键点击 → **"重新启动"** 或先"停止"再"启动"

### 方法 2：使用批处理脚本（需要管理员权限）

1. **右键点击** `force_restart_service.bat`
2. 选择 **"以管理员身份运行"**
3. 按照提示操作

### 方法 3：手动 PowerShell 命令（需要管理员权限）

以管理员身份打开 PowerShell，执行：

```powershell
cd "C:\TR-master\TR UI\backend"

# 1. 恢复服务（如果暂停）
sc continue TR-Backend

# 2. 等待2秒
Start-Sleep -Seconds 2

# 3. 停止服务
sc stop TR-Backend

# 4. 等待5秒
Start-Sleep -Seconds 5

# 5. 清理缓存
Get-ChildItem -Path . -Filter "*.pyc" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem -Path . -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

# 6. 启动服务
.\nssm-2.24\win64\nssm.exe start TR-Backend

# 7. 检查状态
.\nssm-2.24\win64\nssm.exe status TR-Backend
```

### 方法 4：如果以上都不行

1. 打开服务管理器（`services.msc`）
2. 找到 TR-Backend 服务
3. 右键 → **属性**
4. 点击 **"停止"** 按钮
5. 等待服务完全停止
6. 点击 **"启动"** 按钮

## 验证

服务启动后，检查日志：

```powershell
# 查看最新日志
Get-Content "C:\TR-master\TR UI\backend\logs\app.log" -Tail 20

# 应该看到服务启动信息，而不是连接池错误
```

## 常见问题

**Q: 为什么服务会进入暂停状态？**
A: 通常是因为服务在启动时遇到错误，或者被手动暂停。

**Q: 需要管理员权限吗？**
A: 是的，所有服务操作都需要管理员权限。

**Q: 如何确保使用最新代码？**
A: 清理 Python 缓存（删除 `*.pyc` 文件和 `__pycache__` 文件夹）。
