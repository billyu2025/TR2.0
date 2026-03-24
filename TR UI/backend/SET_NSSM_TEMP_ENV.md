# 设置 NSSM 服务临时目录环境变量

## 问题

之前部分文件被放在了 `C:\Windows\TEMP`，这是因为 NSSM 服务没有设置 `TEMP` 和 `TMP` 环境变量，导致 Python 使用系统默认的临时目录。

## 解决方案

在 NSSM 服务中设置 `TEMP` 和 `TMP` 环境变量，指向用户临时目录：
```
C:\Users\tradmin\AppData\Local\Temp\1
```

## 方法一：使用 PowerShell 脚本（推荐）

1. **以管理员身份运行 PowerShell**
2. **执行脚本**：
   ```powershell
   cd "C:\TR-master\TR UI\backend"
   .\set_nssm_temp_env.ps1
   ```

脚本会自动：
- 检查管理员权限
- 获取当前环境变量配置
- 添加 `TEMP` 和 `TMP` 环境变量
- 验证设置
- 询问是否重启服务

## 方法二：手动设置

**以管理员身份运行 PowerShell**，然后执行：

```powershell
cd "C:\TR-master\TR UI\backend"
$tempDir = "C:\Users\tradmin\AppData\Local\Temp\1"
& ".\nssm-2.24\win64\nssm.exe" set TR-Backend AppEnvironmentExtra `
    "API_HOST=0.0.0.0" `
    "API_PORT=5000" `
    "DEBUG=False" `
    "WAITRESS_THREADS=8" `
    "DB_BACKEND=postgres" `
    "POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/tr_db" `
    "TEMP=$tempDir" `
    "TMP=$tempDir"
```

## 验证设置

检查环境变量是否设置成功：

```powershell
cd "C:\TR-master\TR UI\backend"
& ".\nssm-2.24\win64\nssm.exe" get TR-Backend AppEnvironmentExtra
```

应该看到 `TEMP` 和 `TMP` 环境变量。

## 重启服务

设置完成后，需要重启服务以使新配置生效：

```powershell
cd "C:\TR-master\TR UI\backend"
& ".\nssm-2.24\win64\nssm.exe" restart TR-Backend
```

## 验证临时目录

重启服务后，可以通过以下方式验证：

1. **查看日志**：检查 ZIP 文件创建路径
2. **测试下载**：执行一次下载，查看临时文件位置
3. **Python 测试**：
   ```python
   import tempfile
   import os
   print("临时目录:", tempfile.gettempdir())
   print("TEMP 环境变量:", os.getenv('TEMP'))
   ```

## 注意事项

1. **必须使用管理员权限**：修改 NSSM 服务配置需要管理员权限
2. **重启服务**：设置环境变量后必须重启服务才能生效
3. **路径格式**：确保路径使用反斜杠或正斜杠，PowerShell 会自动处理
4. **现有文件**：`C:\Windows\TEMP` 中的旧文件不会被自动移动，需要手动清理

## 清理旧文件

如果需要清理 `C:\Windows\TEMP` 中的旧文件：

```powershell
# 查看文件
Get-ChildItem "C:\Windows\TEMP" -Filter "*.zip" -Recurse -ErrorAction SilentlyContinue

# 删除文件（谨慎操作）
# Get-ChildItem "C:\Windows\TEMP" -Filter "*.zip" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force
```
