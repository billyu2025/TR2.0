# 数据库更新脚本使用说明

## 脚本文件

### 1. `auto_update_with_service_control.bat`（推荐）
**功能：** 自动停止后端服务 → 运行更新 → 重启服务

**使用方法：**
1. **右键点击** `auto_update_with_service_control.bat`
2. 选择 **"以管理员身份运行"**
3. 等待更新完成

**注意：** 此脚本需要管理员权限

### 2. `auto_update_all_tables.bat`
**功能：** 直接运行更新（不控制服务）

**使用方法：**
- 双击运行即可
- 如果后端服务正在运行，可能会失败

## 常见问题

### Q1: 点击脚本后窗口立即关闭
**原因：** 脚本执行出错或需要管理员权限

**解决方法：**
1. 打开命令提示符（CMD）或PowerShell
2. 切换到脚本目录：
   ```cmd
   cd "C:\TR-master\TR database"
   ```
3. 运行脚本：
   ```cmd
   auto_update_with_service_control.bat
   ```
   或
   ```powershell
   .\auto_update_with_service_control.bat
   ```

### Q2: 提示"需要管理员权限"
**解决方法：**
1. 右键点击脚本文件
2. 选择"以管理员身份运行"

或在管理员PowerShell中运行：
```powershell
cd "C:\TR-master\TR database"
.\auto_update_with_service_control.bat
```

### Q3: 提示"无法找到Python"
**解决方法：**
1. 检查Python是否已安装：
   ```cmd
   python --version
   ```
2. 如果未安装，请安装Python 3.10或更高版本
3. 确保Python已添加到系统PATH

### Q4: 提示"Python脚本不存在"
**解决方法：**
1. 确保 `auto_update_all_tables.py` 文件在同一目录下
2. 检查文件路径是否正确

## 手动操作步骤

如果脚本无法运行，可以手动执行：

### 步骤1：停止后端服务
```powershell
Stop-Service TR-Backend
```

### 步骤2：运行更新脚本
```powershell
cd "C:\TR-master\TR database"
python auto_update_all_tables.py
```

### 步骤3：启动后端服务
```powershell
Start-Service TR-Backend
```

## 查看日志

更新日志保存在：
```
C:\TR-master\TR database\logs\
```

查看最新的日志文件：
```powershell
Get-ChildItem "C:\TR-master\TR database\logs\auto_update_all_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
```
