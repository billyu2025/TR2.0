# WSL 初始设置步骤

## 步骤 1：安装 Linux 发行版

### 查看可用的发行版

```powershell
# 在 PowerShell 中运行
wsl --list --online
```

### 安装 Ubuntu（推荐）

```powershell
# 安装 Ubuntu 22.04 LTS（推荐，稳定且兼容性好）
wsl --install -d Ubuntu-22.04

# 或者安装 Ubuntu（最新版）
wsl --install -d Ubuntu
```

### 其他可选发行版

```powershell
# Debian
wsl --install -d Debian

# 或者从 Microsoft Store 安装
# 打开 Microsoft Store，搜索 "Ubuntu" 或 "Debian"
```

## 步骤 2：首次启动和配置

安装完成后，会自动打开一个新的终端窗口，或者你可以运行：

```powershell
wsl
```

### 首次启动配置

1. **创建用户名**：输入你想要的 Linux 用户名（建议使用小写字母和数字）
2. **设置密码**：输入密码（输入时不会显示，这是正常的）
3. **确认密码**：再次输入密码

**示例：**
```
Enter new UNIX username: tradmin
New password: 
Retype new password: 
```

## 步骤 3：更新系统

首次登录后，立即更新系统：

```bash
# 更新包列表
sudo apt update

# 升级系统
sudo apt upgrade -y

# 安装基础工具
sudo apt install -y build-essential curl wget git
```

## 步骤 4：验证安装

```bash
# 检查系统信息
uname -a

# 检查 Python 版本
python3 --version

# 检查当前用户
whoami

# 检查当前目录
pwd
```

## 步骤 5：设置 WSL 默认发行版（可选）

如果你安装了多个发行版，可以设置默认：

```powershell
# 在 PowerShell 中
wsl --list --verbose

# 设置默认发行版
wsl --set-default Ubuntu-22.04
```

## 步骤 6：配置 WSL 内存限制（可选，推荐）

如果系统内存有限，可以限制 WSL 使用的内存：

```powershell
# 在 PowerShell 中创建或编辑配置文件
notepad $env:USERPROFILE\.wslconfig
```

添加以下内容（根据你的系统内存调整）：

```ini
[wsl2]
memory=4GB          # 限制 WSL 使用 4GB 内存（根据你的系统调整）
processors=2        # 限制使用 2 个 CPU 核心
swap=2GB            # 交换空间
localhostForwarding=true
```

保存后，重启 WSL：

```powershell
wsl --shutdown
wsl
```

## 步骤 7：配置 WSL 自动挂载 Windows 驱动器（可选）

WSL 默认会自动挂载 Windows 驱动器（C:, D: 等），挂载点在 `/mnt/c/`, `/mnt/d/` 等。

验证挂载：

```bash
# 查看挂载的驱动器
ls /mnt/

# 应该能看到 c, d 等驱动器
```

## 常见问题

### 问题 1：安装失败

**错误信息：**
```
WslRegisterDistribution failed with error: 0x800701bc
```

**解决方法：**
```powershell
# 启用 WSL 和虚拟机平台功能
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# 重启计算机
shutdown /r /t 0
```

### 问题 2：无法启动 WSL

**解决方法：**
```powershell
# 检查 WSL 状态
wsl --status

# 如果状态异常，尝试重启
wsl --shutdown
wsl
```

### 问题 3：忘记密码

**解决方法：**
```powershell
# 在 PowerShell 中，以 root 身份运行 WSL
wsl -u root

# 在 WSL 中重置密码
passwd 用户名

# 退出
exit
```

### 问题 4：网络连接问题

如果 WSL 无法访问网络：

```bash
# 在 WSL 中检查网络
ping 8.8.8.8

# 如果无法连接，尝试重启 WSL
# 在 PowerShell 中
wsl --shutdown
wsl
```

## 下一步

完成以上步骤后，继续按照 `WSL_DEPLOYMENT_GUIDE.md` 或 `WSL_QUICK_START.md` 进行项目部署。

---

## 快速检查清单

- [ ] WSL2 已安装
- [ ] Linux 发行版已安装（Ubuntu/Debian）
- [ ] 首次登录并创建用户
- [ ] 系统已更新（`sudo apt update && sudo apt upgrade -y`）
- [ ] 基础工具已安装（build-essential, curl, wget, git）
- [ ] Python3 已安装（`python3 --version`）
- [ ] Windows 驱动器可以访问（`ls /mnt/c/`）
- [ ] 准备开始项目部署

---

**完成这些步骤后，你就可以开始部署 TR Report System 了！**
