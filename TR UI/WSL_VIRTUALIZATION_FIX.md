# WSL 虚拟化错误修复指南

## 错误信息
```
WslRegisterDistribution failed with error: 0x80370102
Please enable the Virtual Machine Platform Windows feature and ensure virtualization is enabled in the BIOS.
```

## 解决方案

### 方法一：使用 PowerShell 启用功能（推荐）

**以管理员身份运行 PowerShell**，然后执行：

```powershell
# 启用 Windows Subsystem for Linux
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart

# 启用 Virtual Machine Platform
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# 启用 Hyper-V（如果需要）
dism.exe /online /enable-feature /featurename:Microsoft-Hyper-V-All /all /norestart
```

**重要：执行完成后必须重启计算机！**

```powershell
# 重启计算机
shutdown /r /t 0
```

### 方法二：使用图形界面启用

1. **打开"启用或关闭 Windows 功能"**
   - 按 `Win + R`
   - 输入：`optionalfeatures`
   - 按 Enter

2. **勾选以下功能**
   - ✅ **Windows Subsystem for Linux**
   - ✅ **Virtual Machine Platform**
   - ✅ **Hyper-V**（如果可用）

3. **点击"确定"**
   - 系统会提示重启，选择"立即重新启动"

### 方法三：使用设置应用

1. **打开设置**
   - 按 `Win + I`
   - 或点击开始菜单 → 设置

2. **进入"应用"**
   - 左侧菜单选择"应用"
   - 点击"可选功能"或"程序和功能"

3. **启用功能**
   - 点击"更多 Windows 功能"
   - 勾选所需功能
   - 重启计算机

## 检查 BIOS 虚拟化设置

### 步骤 1：检查虚拟化是否已启用

在 PowerShell（管理员）中运行：

```powershell
# 检查虚拟化支持
systeminfo | findstr /C:"Hyper-V 要求"

# 或者
Get-ComputerInfo | Select-Object -Property "HyperV*"
```

如果显示 "已检测到 Hypervisor"，说明虚拟化已启用。

### 步骤 2：进入 BIOS 设置

1. **重启计算机**
2. **在启动时按 BIOS 键**（通常是以下之一）：
   - `F2`（最常见）
   - `F1`
   - `F10`
   - `Del`
   - `Esc`
   - 查看启动画面上的提示

3. **查找虚拟化选项**
   - 选项名称可能为：
     - **Intel**: "Intel Virtualization Technology" 或 "Intel VT-x"
     - **AMD**: "AMD-V" 或 "SVM Mode"
   - 通常在以下位置：
     - Advanced → CPU Configuration
     - Advanced → Processor Configuration
     - Security → Virtualization
     - System Configuration

4. **启用虚拟化**
   - 找到选项后，设置为 **Enabled**
   - 保存并退出（通常是 `F10`）

### 步骤 3：验证虚拟化已启用

重启后，在 PowerShell（管理员）中运行：

```powershell
# 方法 1：使用 systeminfo
systeminfo | findstr /C:"Hyper-V 要求"

# 方法 2：使用 Get-ComputerInfo
Get-ComputerInfo | Select-Object -Property "HyperV*"

# 方法 3：检查 CPU 虚拟化支持
Get-WmiObject -Class Win32_Processor | Select-Object -Property Name, VirtualizationFirmwareEnabled
```

## 完整修复流程

### 步骤 1：启用 Windows 功能

```powershell
# 以管理员身份运行 PowerShell
# 启用 WSL
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart

# 启用虚拟化平台
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

### 步骤 2：重启计算机

```powershell
shutdown /r /t 0
```

### 步骤 3：验证功能已启用

重启后，在 PowerShell（管理员）中：

```powershell
# 检查功能状态
Get-WindowsOptionalFeature -Online | Where-Object {$_.FeatureName -like "*VirtualMachine*" -or $_.FeatureName -like "*Subsystem*"} | Select-Object FeatureName, State
```

应该看到：
- `Microsoft-Windows-Subsystem-Linux` - **Enabled**
- `VirtualMachinePlatform` - **Enabled**

### 步骤 4：检查虚拟化支持

```powershell
# 检查 CPU 虚拟化
Get-WmiObject -Class Win32_Processor | Select-Object Name, VirtualizationFirmwareEnabled
```

如果 `VirtualizationFirmwareEnabled` 为 `False`，需要进入 BIOS 启用。

### 步骤 5：重新安装 Ubuntu

```powershell
# 安装 Ubuntu 22.04
wsl --install -d Ubuntu-22.04
```

## 常见问题

### Q1: 找不到 Virtual Machine Platform 选项

**可能原因：**
- Windows 版本不支持（需要 Windows 10 版本 2004 或更高）
- 功能名称不同

**解决方法：**
- 检查 Windows 版本：`winver`
- 如果版本过低，需要更新 Windows

### Q2: 启用功能后仍然报错

**解决方法：**
1. 确保已重启计算机
2. 检查 BIOS 虚拟化设置
3. 运行 Windows Update 更新系统

```powershell
# 检查更新
Get-WindowsUpdate
```

### Q3: BIOS 中没有虚拟化选项

**可能原因：**
- CPU 不支持虚拟化（较老的 CPU）
- 选项名称不同
- 选项在其他位置

**解决方法：**
- 查看 CPU 型号和规格
- 搜索你的主板型号 + "enable virtualization"
- 联系计算机制造商支持

### Q4: 启用 Hyper-V 后无法使用其他虚拟化软件

**说明：**
- Hyper-V 和 VMware/VirtualBox 可能冲突
- WSL2 需要 Hyper-V 或 Virtual Machine Platform

**解决方法：**
- 如果只需要 WSL2，可以只启用 Virtual Machine Platform
- 如果同时需要其他虚拟化软件，可能需要禁用 Hyper-V

## 验证安装成功

完成所有步骤后，验证 WSL 是否正常工作：

```powershell
# 检查 WSL 版本
wsl --version

# 检查 WSL 状态
wsl --status

# 尝试安装 Ubuntu
wsl --install -d Ubuntu-22.04
```

如果安装成功，会自动打开 Ubuntu 终端，提示创建用户。

## 快速修复命令（一键执行）

**以管理员身份运行 PowerShell**，复制粘贴以下命令：

```powershell
# 启用所需功能
Write-Host "正在启用 Windows Subsystem for Linux..." -ForegroundColor Yellow
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart

Write-Host "正在启用 Virtual Machine Platform..." -ForegroundColor Yellow
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

Write-Host "`n功能已启用，需要重启计算机才能生效。" -ForegroundColor Green
Write-Host "重启后，运行以下命令安装 Ubuntu:" -ForegroundColor Cyan
Write-Host "  wsl --install -d Ubuntu-22.04" -ForegroundColor White

# 询问是否立即重启
$restart = Read-Host "`n是否立即重启计算机? (Y/N)"
if ($restart -eq 'Y' -or $restart -eq 'y') {
    Write-Host "正在重启..." -ForegroundColor Yellow
    shutdown /r /t 0
} else {
    Write-Host "请稍后手动重启计算机。" -ForegroundColor Yellow
}
```

---

## 检查清单

- [ ] 以管理员身份运行 PowerShell
- [ ] 启用 Windows Subsystem for Linux
- [ ] 启用 Virtual Machine Platform
- [ ] 重启计算机
- [ ] 检查 BIOS 虚拟化设置（如需要）
- [ ] 验证功能已启用
- [ ] 重新尝试安装 Ubuntu

---

**完成这些步骤后，WSL 应该可以正常工作了！**
