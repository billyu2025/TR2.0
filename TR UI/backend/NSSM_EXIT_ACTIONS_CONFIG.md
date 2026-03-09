# NSSM Exit Actions 配置说明

## Exit Actions 标签页配置

### 配置项说明

#### 1. Exit action（退出行为）

**选项：**
- `Restart Application` - **推荐**：服务崩溃时自动重启
- `Exit` - 服务崩溃时退出（不重启）
- `Restart Computer` - 服务崩溃时重启计算机（不推荐）

**推荐设置：** `Restart Application`

#### 2. Throttle（节流/限制）

**作用：** 防止服务频繁崩溃重启，避免系统资源耗尽

**配置项：**

1. **Restart delay（重启延迟）**
   - **含义**：服务崩溃后，等待多长时间再重启
   - **推荐值**：`5000` 毫秒（5 秒）
   - **原因**：给系统时间恢复，避免立即重启导致的问题

2. **Throttle restart（节流重启）**
   - **含义**：如果服务在短时间内多次崩溃，增加重启延迟
   - **推荐值**：`60000` 毫秒（60 秒）
   - **原因**：如果服务在 1 分钟内多次崩溃，说明有严重问题，应该等待更长时间再重启

---

## 推荐配置

### 图形界面配置

在 NSSM 的 Exit Actions 标签页中：

1. **Exit action**：
   - 选择：`Restart Application`

2. **Restart delay**：
   - 输入：`5000`（毫秒，即 5 秒）

3. **Throttle restart**：
   - 输入：`60000`（毫秒，即 60 秒）

### 命令行配置（推荐）

**使用命令行配置更简单：**

```powershell
# 以管理员身份运行 PowerShell
cd "C:\TR-master\TR UI\backend"
$nssm = "nssm\win64\nssm.exe"

# 设置退出行为：自动重启
& $nssm set TR-Backend AppExit Default Restart

# 设置重启延迟：5 秒
& $nssm set TR-Backend AppRestartDelay 5000

# 设置节流：如果 1 分钟内多次崩溃，等待 60 秒再重启
& $nssm set TR-Backend AppThrottle 60000
```

---

## 配置详解

### 场景 1：正常崩溃（偶尔）

```
服务崩溃
    ↓
等待 5 秒（Restart delay）
    ↓
自动重启
```

### 场景 2：频繁崩溃（短时间内多次）

```
第 1 次崩溃 → 等待 5 秒 → 重启
第 2 次崩溃（1 分钟内）→ 等待 5 秒 → 重启
第 3 次崩溃（1 分钟内）→ 触发节流 → 等待 60 秒 → 重启
```

**好处：**
- 避免频繁重启导致系统资源耗尽
- 给管理员时间查看日志和修复问题

---

## 完整配置示例

### 方法一：使用命令行（推荐）

```powershell
# 以管理员身份运行 PowerShell
cd "C:\TR-master\TR UI\backend"
$nssm = "nssm\win64\nssm.exe"

# Exit Actions 配置
& $nssm set TR-Backend AppExit Default Restart
& $nssm set TR-Backend AppRestartDelay 5000
& $nssm set TR-Backend AppThrottle 60000

# 重启服务使配置生效
Restart-Service TR-Backend
```

### 方法二：图形界面配置

1. **打开 NSSM 编辑窗口**：
   ```powershell
   cd "C:\TR-master\TR UI\backend\nssm\win64"
   .\nssm.exe edit TR-Backend
   ```

2. **Exit Actions 标签页**：
   - **Exit action**：选择 `Restart Application`
   - **Restart delay**：输入 `5000`（5 秒）
   - **Throttle restart**：输入 `60000`（60 秒）

3. **保存**：点击 "Edit service" 或 "OK"

---

## 参数说明

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| **Exit action** | `Restart Application` | 服务崩溃时自动重启 |
| **Restart delay** | `5000` 毫秒 | 崩溃后等待 5 秒再重启 |
| **Throttle restart** | `60000` 毫秒 | 频繁崩溃时，等待 60 秒再重启 |

---

## 验证配置

**检查配置是否正确：**

```powershell
cd "C:\TR-master\TR UI\backend"
$nssm = "nssm\win64\nssm.exe"

# 查看退出行为
& $nssm get TR-Backend AppExit

# 查看重启延迟
& $nssm get TR-Backend AppRestartDelay

# 查看节流设置
& $nssm get TR-Backend AppThrottle
```

---

## 常见问题

### Q: Restart delay 应该设置多少？

**A:** 
- **推荐**：5000 毫秒（5 秒）
- **最小**：1000 毫秒（1 秒）
- **最大**：30000 毫秒（30 秒）

**原因：**
- 太短：可能立即重启导致问题未解决
- 太长：用户等待时间过长

### Q: Throttle restart 应该设置多少？

**A:**
- **推荐**：60000 毫秒（60 秒）
- **范围**：30000-120000 毫秒（30 秒 - 2 分钟）

**原因：**
- 如果服务频繁崩溃，说明有严重问题
- 应该等待更长时间，给管理员时间查看日志

### Q: 如果服务一直崩溃怎么办？

**A:**
1. **查看错误日志**：
   ```powershell
   Get-Content "C:\TR-master\TR UI\backend\logs\nssm_error.log" -Tail 100
   ```

2. **检查服务配置**：
   - Python 路径是否正确
   - 工作目录是否正确
   - 环境变量是否正确

3. **手动测试**：
   ```powershell
   cd "C:\TR-master\TR UI\backend"
   python start_waitress.py
   ```

4. **如果问题持续**：
   - 可以临时禁用自动重启
   - 修复问题后再启用

---

## 完整配置命令（一键执行）

**复制粘贴以下命令，一次性配置所有 Exit Actions：**

```powershell
# 以管理员身份运行 PowerShell
cd "C:\TR-master\TR UI\backend"
$nssm = "nssm\win64\nssm.exe"

# Exit Actions 配置
Write-Host "配置 Exit Actions..." -ForegroundColor Yellow
& $nssm set TR-Backend AppExit Default Restart
& $nssm set TR-Backend AppRestartDelay 5000
& $nssm set TR-Backend AppThrottle 60000

Write-Host "Exit Actions 配置完成！" -ForegroundColor Green
Write-Host "  - 退出行为: 自动重启" -ForegroundColor Cyan
Write-Host "  - 重启延迟: 5 秒" -ForegroundColor Cyan
Write-Host "  - 节流设置: 60 秒" -ForegroundColor Cyan

# 验证配置
Write-Host ""
Write-Host "验证配置..." -ForegroundColor Yellow
& $nssm get TR-Backend AppExit
& $nssm get TR-Backend AppRestartDelay
& $nssm get TR-Backend AppThrottle
```

---

## 总结

### 推荐配置

```
Exit action: Restart Application
Restart delay: 5000 毫秒（5 秒）
Throttle restart: 60000 毫秒（60 秒）
```

### 配置方法

1. **命令行方式**（推荐）：快速、准确
2. **图形界面方式**：直观，但需要手动输入

### 效果

- ✅ 服务崩溃时自动重启
- ✅ 避免频繁重启导致资源耗尽
- ✅ 给管理员时间查看日志和修复问题
