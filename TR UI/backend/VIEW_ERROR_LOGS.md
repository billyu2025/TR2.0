# 查看错误日志指南

## 错误日志位置

### 后端错误日志

**位置：** `C:\TR-master\TR UI\backend\logs\`

**主要日志文件：**

1. **应用错误日志** - `error.log`
   - 包含所有 ERROR 级别的错误
   - **这是查看 PDF 生成/下载错误的主要日志**

2. **应用运行日志** - `app.log`
   - 包含 INFO、WARNING、ERROR 级别
   - 包含所有操作记录

3. **NSSM 错误日志** - `nssm_error.log`
   - NSSM 服务错误输出
   - 包含启动错误和异常

---

## 快速查看错误日志

### 方法一：使用 PowerShell（推荐）

#### 查看 PDF 生成/下载错误

```powershell
cd "C:\TR-master\TR UI\backend"
Get-Content "logs\error.log" -Tail 50
```

#### 查看应用日志中的错误

```powershell
cd "C:\TR-master\TR UI\backend"
Get-Content "logs\app.log" -Tail 50 | Select-String -Pattern "PDF|pdf|download|Download|STOCKIST|stockist|error|Error|ERROR|failed|Failed"
```

#### 查看 NSSM 错误日志

```powershell
cd "C:\TR-master\TR UI\backend"
Get-Content "logs\nssm_error.log" -Tail 50
```

### 方法二：使用批处理脚本

**查看错误日志：**
```
双击运行：C:\TR-master\TR UI\backend\view_logs.ps1
```

**实时监控日志：**
```
双击运行：C:\TR-master\TR UI\backend\monitor_logs.bat
```

### 方法三：直接打开文件

1. 打开文件资源管理器
2. 导航到：`C:\TR-master\TR UI\backend\logs\`
3. 打开 `error.log` 或 `app.log`
4. 使用文本编辑器查看（推荐使用支持 UTF-8 的编辑器，如 Notepad++）

---

## 常见错误类型

### 1. PDF 生成错误

**错误位置：** `error.log` 或 `app.log`

**搜索关键词：**
- `PDF`
- `pdf`
- `generate`
- `pdf_task_manager`

**示例错误：**
```
UnicodeEncodeError: 'charmap' codec can't encode characters
File "C:\TR-master\TR UI\backend\pdf_task_manager.py", line 69
```

### 2. 下载错误

**错误位置：** `error.log` 或 `app.log`

**搜索关键词：**
- `download`
- `Download`
- `STOCKIST`
- `download_task_manager`

**示例错误：**
```
UnicodeEncodeError: 'charmap' codec can't encode characters
File "C:\TR-master\TR UI\backend\download_task_manager.py", line 76
```

### 3. STOCKIST & TEST REPORT 错误

**错误位置：** `error.log` 或 `app.log`

**搜索关键词：**
- `STOCKIST`
- `stockist`
- `download_stockist_test`

---

## 实时监控日志

### 使用 PowerShell 实时监控

```powershell
cd "C:\TR-master\TR UI\backend"
Get-Content "logs\error.log" -Wait -Tail 20
```

### 使用批处理脚本

```
双击运行：C:\TR-master\TR UI\backend\monitor_logs.bat
```

---

## 日志文件说明

### error.log
- **用途：** 记录所有 ERROR 级别的错误
- **格式：** 时间戳 + 错误级别 + 错误信息 + 堆栈跟踪
- **查看方式：** 从文件末尾向前查看（最新的错误在最后）

### app.log
- **用途：** 记录所有操作（INFO、WARNING、ERROR）
- **格式：** 时间戳 + 日志级别 + 操作信息
- **查看方式：** 从文件末尾向前查看（最新的操作在最后）

### nssm_error.log
- **用途：** 记录 NSSM 服务的错误输出
- **格式：** 标准错误输出格式
- **查看方式：** 从文件末尾向前查看（最新的错误在最后）

---

## 故障排查步骤

1. **查看最新的错误：**
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\error.log" -Tail 30
   ```

2. **搜索特定错误：**
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\error.log" | Select-String -Pattern "PDF|pdf|download"
   ```

3. **查看服务状态：**
   ```powershell
   Get-Service TR-Backend
   ```

4. **如果服务未运行，查看启动错误：**
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 50
   ```

---

## 注意事项

1. **日志文件可能很大**：使用 `-Tail` 参数只查看最后几行
2. **日志文件使用 UTF-8 编码**：使用支持 UTF-8 的编辑器查看
3. **日志文件会自动轮转**：旧日志会被备份为 `.log.1`, `.log.2` 等
4. **实时监控会占用终端**：按 `Ctrl+C` 停止监控

---

**提示：** 如果遇到编码问题，建议使用 PowerShell 的 `Get-Content` 命令查看，它会自动处理编码。
