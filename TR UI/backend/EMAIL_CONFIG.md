# 邮件通知配置指南

本指南说明如何配置 `update_tr_tables_postgres.bat` 脚本的邮件通知功能。

## 📧 邮件配置

### 方法 1：在批处理脚本中配置（推荐）

编辑 `update_tr_tables_postgres.bat`，修改以下变量：

```batch
REM 设置 SMTP 服务器
set SMTP_SERVER=smtp.example.com
REM 设置 SMTP 端口（默认 25，SSL 通常为 465 或 587）
set SMTP_PORT=25
REM 设置发件人邮箱
set EMAIL_FROM=tr_system@example.com
REM 设置收件人邮箱（多个收件人用逗号分隔）
set EMAIL_TO=admin@example.com,manager@example.com
REM 如果需要认证，设置用户名和密码
set SMTP_USERNAME=your_username
set SMTP_PASSWORD=your_password
REM 是否使用 SSL（设置为 true 或 false）
set USE_SSL=false
```

### 方法 2：使用环境变量

在系统环境变量或任务计划程序中设置：

- `SMTP_SERVER`: SMTP 服务器地址
- `SMTP_PORT`: SMTP 端口
- `EMAIL_FROM`: 发件人邮箱
- `EMAIL_TO`: 收件人邮箱（多个用逗号分隔）
- `SMTP_USERNAME`: SMTP 用户名（可选）
- `SMTP_PASSWORD`: SMTP 密码（可选）
- `USE_SSL`: 是否使用 SSL（true/false）

## 🔧 常见邮件服务商配置

### Gmail

```batch
set SMTP_SERVER=smtp.gmail.com
set SMTP_PORT=587
set EMAIL_FROM=your_email@gmail.com
set EMAIL_TO=recipient@gmail.com
set SMTP_USERNAME=your_email@gmail.com
set SMTP_PASSWORD=your_app_password
set USE_SSL=true
```

**注意**：Gmail 需要使用应用专用密码，不是普通密码。

### Outlook/Hotmail

```batch
set SMTP_SERVER=smtp-mail.outlook.com
set SMTP_PORT=587
set EMAIL_FROM=your_email@outlook.com
set EMAIL_TO=recipient@outlook.com
set SMTP_USERNAME=your_email@outlook.com
set SMTP_PASSWORD=your_password
set USE_SSL=true
```

### 企业邮箱（Exchange）

```batch
set SMTP_SERVER=smtp.company.com
set SMTP_PORT=25
set EMAIL_FROM=tr_system@company.com
set EMAIL_TO=admin@company.com
set USE_SSL=false
```

## 📝 邮件内容

脚本会自动生成邮件内容：

**成功时：**
- 主题：`TR 数据库表更新报告 - [日期]`
- 内容：包含更新时间、更新内容等信息

**失败时：**
- 主题：`TR 数据库表更新报告 - [日期]`
- 内容：包含错误信息和失败原因

## 🧪 测试邮件发送

### 方法 1：直接运行 PowerShell 脚本

```powershell
cd "C:\TR-master\TR UI\backend"
.\send_email.ps1 -Subject "测试邮件" -Body "这是一封测试邮件" -To "your_email@example.com" -SmtpServer "smtp.example.com" -Port 25 -From "tr_system@example.com"
```

### 方法 2：在批处理脚本中测试

临时修改 `update_tr_tables_postgres.bat`，在开头添加测试邮件发送：

```batch
REM 测试邮件发送
powershell -ExecutionPolicy Bypass -File "%~dp0send_email.ps1" -Subject "测试邮件" -Body "测试邮件内容" -SmtpServer "%SMTP_SERVER%" -Port %SMTP_PORT% -From "%EMAIL_FROM%"
pause
exit
```

## ⚠️ 注意事项

1. **SMTP 端口**：
   - 25：标准 SMTP（通常不需要认证）
   - 587：STARTTLS（需要认证）
   - 465：SSL/TLS（需要认证）

2. **安全性**：
   - 不要在批处理脚本中硬编码密码
   - 考虑使用环境变量或加密配置文件
   - 对于生产环境，建议使用应用专用密码

3. **防火墙**：
   - 确保防火墙允许访问 SMTP 服务器
   - 某些企业网络可能阻止外部 SMTP 连接

4. **邮件服务商限制**：
   - 某些邮件服务商（如 Gmail）有发送频率限制
   - 可能需要启用"允许不够安全的应用"或使用应用专用密码

## 🔍 故障排除

### 问题 1：邮件发送失败

**错误信息**：`无法连接到 SMTP 服务器`

**解决方案**：
- 检查 SMTP 服务器地址和端口是否正确
- 检查防火墙设置
- 检查网络连接

### 问题 2：认证失败

**错误信息**：`用户名或密码错误`

**解决方案**：
- 检查用户名和密码是否正确
- 对于 Gmail，确保使用应用专用密码
- 检查是否需要启用"允许不够安全的应用"

### 问题 3：PowerShell 执行策略限制

**错误信息**：`无法加载文件，因为在此系统上禁止运行脚本`

**解决方案**：
- 以管理员身份运行 PowerShell
- 执行：`Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`
- 或者在批处理脚本中使用 `-ExecutionPolicy Bypass` 参数（已包含）

## 📋 完整配置示例

```batch
REM 邮件配置示例
set SMTP_SERVER=smtp.gmail.com
set SMTP_PORT=587
set EMAIL_FROM=tr_system@gmail.com
set EMAIL_TO=admin@company.com,manager@company.com
set SMTP_USERNAME=tr_system@gmail.com
set SMTP_PASSWORD=your_app_password_here
set USE_SSL=true
```

## 🔐 安全建议

1. **使用环境变量存储敏感信息**：
   ```batch
   REM 从环境变量读取密码
   set SMTP_PASSWORD=%SMTP_PASSWORD_ENV%
   ```

2. **使用配置文件**（需要额外开发）：
   - 创建加密的配置文件
   - 使用 Python 脚本读取配置并发送邮件

3. **使用 Windows 凭据管理器**：
   - 使用 `cmdkey` 命令存储凭据
   - 在脚本中引用存储的凭据
