# Stockist Cert 文件重命名脚本使用说明

## 功能说明

此脚本用于将 Stockist Cert 文件夹中的文件重命名为统一格式：`DD_No_Stockist_No_Date`

### 支持的输入格式

脚本可以处理以下格式的文件名：

1. **Stockist + MIll Cert_C0483** → `SS79988_C0483_06_FEB_2026`
2. **Stockist + MIll Cert_C0475** → `SS79988_C0475_06_FEB_2026`
3. **SS76288_SS76288_30_MAY_2024** → `SS76288_SS76288_30_MAY_2024`（已符合格式，跳过）
4. **Stockist cert & mill cert of SS73441** → `SS73441_ZZ4306_06_FEB_2026`

### 目标格式

```
DD_No_Stockist_No_Date
```

示例：`SS79988_ZZ4306_06_FEB_2026`

- **DD_No**: RM DN 编号（如 SS79988）
- **Stockist_No**: Stockist 证书编号（如 ZZ4306 或 C0483）
- **Date**: 日期（格式：DD_MON_YYYY，如 06_FEB_2026）

## 使用方法

### 1. 试运行模式（推荐先使用）

预览重命名结果，不会实际修改文件：

```bash
cd C:\TR-master
python rename_stockist_files.py
```

### 2. 执行重命名

实际执行文件重命名：

```bash
python rename_stockist_files.py --execute
```

### 3. 指定文件夹

如果 Stockist Cert 文件夹不在默认位置：

```bash
python rename_stockist_files.py --folder "D:\Stockist&Test Report\Stockist Cert" --execute
```

### 4. 指定数据库路径

如果数据库不在默认位置：

```bash
python rename_stockist_files.py --db "C:\path\to\tr_system.db" --execute
```

### 5. 过滤特定文件

只处理匹配特定模式的文件：

```bash
# 只处理包含 "Stockist" 的文件
python rename_stockist_files.py --pattern "Stockist.*Cert" --execute
```

## 工作原理

### 1. 信息提取

脚本会从文件名中提取以下信息：
- **DD_No**: 从文件名中提取（如 SS76288, SS73441）
- **Stockist_No**: 从文件名中提取（如 C0483, C0475, ZZ4306）
- **Date**: 从文件名中提取（如 30_MAY_2024），如果不存在则使用文件修改日期

### 2. 数据库查询

如果从文件名中无法提取完整信息，脚本会：
- 如果只有 **Stockist_No**，从 `TR_Report` 表查询对应的 **DD_No**
- 如果只有 **DD_No**，从 `TR_Report` 表查询对应的 **Stockist_No**

**默认数据库路径**：`C:\TR-master\TR database\data_3years.db`

### 3. 日期处理

如果文件名中没有日期信息：
- 使用文件的修改时间（`os.path.getmtime()`）
- 格式化为 `DD_MON_YYYY` 格式（如 `06_FEB_2026`）

### 4. 重命名规则

- 如果新文件名与旧文件名相同，跳过
- 如果目标文件已存在，跳过并报告错误
- 保留文件扩展名（.pdf）

## 输出示例

### 试运行模式输出

```
================================================================================
Stockist Cert 文件重命名脚本
================================================================================
文件夹: D:\Stockist&Test Report\Stockist Cert
数据库: C:\TR-master\TR database\data_3years.db
模式: 试运行模式（不会实际重命名）
================================================================================

[统计] 找到 5 个 PDF 文件

[处理] Stockist + MIll Cert_C0483.pdf
  [查询] 从数据库获取 DD_No: SS79988 (Stockist_No: C0483)
  [日期] 使用文件修改日期: 06_FEB_2026
  [预览] Stockist + MIll Cert_C0483.pdf -> SS79988_C0483_06_FEB_2026.pdf

[处理] SS76288_SS76288_30_MAY_2024.pdf
  [跳过] 文件名已符合格式

...

================================================================================
[完成] 文件处理完成
  成功: 3 个文件
  跳过: 1 个文件
  失败: 1 个文件
  总计: 5 个文件

[提示] 这是试运行模式，未实际重命名文件
       使用 --execute 参数执行实际重命名
================================================================================
```

## 注意事项

1. **备份文件**：在执行重命名前，建议先备份文件或使用试运行模式预览结果

2. **数据库连接**：脚本需要访问 `tr_system.db` 数据库来查询 DD_No 和 Stockist_No 的关联关系

3. **文件路径**：确保 Stockist Cert 文件夹路径正确，默认路径为：
   ```
   D:\Stockist&Test Report\Stockist Cert
   ```
   可通过环境变量 `STOCKIST_TEST_FOLDER` 设置

4. **权限**：确保对目标文件夹有写入权限

5. **重复文件**：如果目标文件名已存在，脚本会跳过并报告错误

## 故障排除

### 问题：无法提取 DD_No 或 Stockist_No

**原因**：文件名格式不匹配或数据库中无对应记录

**解决**：
- 检查文件名是否符合支持的格式
- 检查数据库中是否有对应的记录
- 手动重命名文件

### 问题：数据库查询失败

**原因**：数据库路径不正确或数据库文件损坏

**解决**：
- 默认数据库路径：`C:\TR-master\TR database\data_3years.db`
- 使用 `--db` 参数指定正确的数据库路径
- 检查数据库文件是否存在且可访问

### 问题：权限错误

**原因**：没有对文件夹的写入权限

**解决**：
- 以管理员身份运行脚本
- 检查文件夹权限设置

## 支持的日期格式

脚本可以识别以下日期格式：
- `30_MAY_2024`
- `06_FEB_2026`
- `15_JAN_2025`

月份缩写（3个字母，大写）：
- JAN, FEB, MAR, APR, MAY, JUN
- JUL, AUG, SEP, OCT, NOV, DEC

## 示例命令

```bash
# 1. 先预览结果
python rename_stockist_files.py

# 2. 确认无误后执行
python rename_stockist_files.py --execute

# 3. 指定自定义路径
python rename_stockist_files.py --folder "E:\My Files\Stockist Cert" --execute

# 4. 只处理特定文件
python rename_stockist_files.py --pattern "Stockist.*C0483" --execute
```
