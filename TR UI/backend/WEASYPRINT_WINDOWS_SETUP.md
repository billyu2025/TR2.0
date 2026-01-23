# WeasyPrint Windows 安装指南

## 问题
WeasyPrint 在 Windows 上需要 GTK+ 运行时环境，否则会出现 `libgobject-2.0-0` 错误。

## 快速安装步骤

### 方法 1：使用预编译的 GTK+ 运行时（推荐，适合 64 位 Python）

你的 Python 是 **64 位**，请下载 **GTK3-Runtime Win64**：

1. **下载链接**：
   - 直接下载：https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases/latest
   - 或者搜索：`GTK3-Runtime Win64` 下载最新版本
   - 下载文件可能是 `.msi` 或 `.exe` 格式，两者都可以使用

2. **安装步骤**：
   - 运行下载的安装程序（`.msi` 或 `.exe` 都可以）
   - 按照安装向导提示完成安装
   - 默认安装到：`C:\Program Files\GTK3-Runtime Win64\` 或类似路径
   - **重要**：安装时如果有"Add to PATH"选项，请勾选它
   - 安装完成后，**关闭并重新打开命令提示符/PowerShell**（必须重启终端才能生效）

3. **添加到 PATH（如果没有自动添加）**：
   - 按 `Win + R`，输入 `sysdm.cpl`，回车
   - 点击"高级"选项卡 → "环境变量"
   - 在"系统变量"中找到 `Path`，点击"编辑"
   - 点击"新建"，添加：`C:\Program Files\GTK3-Runtime Win64\bin`
   - 点击"确定"保存所有对话框
   - **重启命令提示符**

4. **验证安装**：
   ```bash
   python generate_landscape_pdf.py
   ```

### 方法 2：使用安装脚本

1. **下载 GTK+ 运行时**
   - 访问：https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer
   - 或者直接下载：https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
   - 根据你的 Python 版本（32位/64位）下载对应版本
   - 推荐下载：GTK3-Runtime Win64（如果你的 Python 是 64 位）

2. **安装 GTK+ 运行时**
   - 运行下载的安装程序
   - 默认安装路径通常是：`C:\Program Files\GTK3-Runtime Win64\`
   - **重要**：安装时确保选择"Add GTK+ to PATH"选项（如果有的话）

3. **手动添加到 PATH（如果没有自动添加）**
   - 右键"此电脑" → 属性 → 高级系统设置 → 环境变量
   - 在"系统变量"中找到 `Path`，点击"编辑"
   - 添加 GTK+ 的 bin 目录，例如：`C:\Program Files\GTK3-Runtime Win64\bin`
   - 点击"确定"保存

4. **重启命令提示符**
   - 关闭并重新打开 PowerShell/CMD
   - 验证安装：
     ```bash
     python -c "from weasyprint import HTML; print('WeasyPrint installed successfully!')"
     ```

### 方法 2：使用安装脚本

运行提供的批处理脚本：
```bash
install_weasyprint_windows.bat
```

这个脚本会：
- 安装 Python 包（weasyprint, Jinja2）
- 显示 GTK+ 安装指南

### 方法 3：使用 Conda（如果有安装 Conda）

```bash
conda install -c conda-forge weasyprint
```

Conda 会自动处理 GTK+ 依赖。

### 方法 4：手动安装 Python 包

如果你已经安装了 GTK+，只需要安装 Python 包：
```bash
pip install weasyprint Jinja2
```

## 验证安装

运行以下命令验证：
```bash
python generate_landscape_pdf.py
```

如果成功，应该会看到 PDF 生成的消息。

## 常见问题

1. **错误仍然存在**
   - 确保 PATH 已正确设置
   - 重启命令提示符/PowerShell
   - 检查 GTK+ bin 目录中是否有 `libgobject-2.0-0.dll` 文件

2. **版本不匹配**
   - 确保下载的 GTK+ 版本与 Python 版本（32位/64位）匹配

## 备选方案

如果 GTK+ 安装太复杂，可以考虑：
- 使用 `pdfkit` + `wkhtmltopdf`（需要安装 wkhtmltopdf 二进制文件）
- 继续使用 `ReportLab`（但改进样式和布局）

