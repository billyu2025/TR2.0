# NSSM 服务编码问题修复总结

## 问题

服务启动失败，错误信息显示：
```
UnicodeEncodeError: 'charmap' codec can't encode characters
```

**原因：** Windows 服务环境使用 cp1252 编码，无法直接输出中文字符。

## 已修复的文件

### 1. `cache_manager.py`
- ✅ 修复了第 61、63、66 行的 print 语句
- 使用英文消息或捕获编码错误

### 2. `start_waitress.py`
- ✅ 修复了第 19-25 行的 print 语句
- 使用英文消息

### 3. `tr_fill_in_api.py`
- ✅ 修复了第 212 行的 logger.info 语句
- 使用英文消息

## 重启服务（需要管理员权限）

### 方法一：使用 NSSM 命令

```powershell
# 以管理员身份运行 PowerShell
cd "C:\TR-master\TR UI\backend"
.\nssm-2.24\win64\nssm.exe restart TR-Backend
```

### 方法二：使用服务命令

```powershell
# 以管理员身份运行 PowerShell
Resume-Service TR-Backend
# 或
Restart-Service TR-Backend
```

### 方法三：使用服务管理器

1. 按 `Win + R`
2. 输入 `services.msc`
3. 找到 "TR Report System Backend"
4. 右键 → "重新启动"

## 验证服务运行

```powershell
# 检查服务状态
Get-Service TR-Backend

# 检查端口监听
netstat -ano | findstr ":5000"

# 测试 API
Invoke-WebRequest -Uri "http://localhost:5000/health" -UseBasicParsing
```

## 如果仍有编码问题

如果服务启动后仍有编码错误，检查错误日志：

```powershell
Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 30
```

然后修复相应的文件中的中文输出。

## 其他可能包含中文的文件

以下文件可能也包含中文输出，如果出现问题需要修复：

- `tr_fill_in_api.py` - 其他 logger 语句（第 83、86、184、217、248、290、292、294、753 行）
- `pdf_task_manager.py` - print 语句
- `download_task_manager.py` - print 语句

**建议：** 在 Windows 服务环境中，所有 print 和 logger 输出应使用英文，或使用 try-except 捕获编码错误。

## 快速修复脚本

如果需要批量修复所有中文输出，可以：

1. 将所有 print 和 logger 中的中文改为英文
2. 或使用 try-except 包装所有输出语句

**示例：**
```python
try:
    print("中文消息")
except (UnicodeEncodeError, UnicodeDecodeError):
    print("English message")
```

---

**现在请以管理员身份运行 PowerShell，然后重启服务！**
