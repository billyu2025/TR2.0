# 修复文件查找问题 - 添加调试日志

## 问题描述

用户报告 Order 134617 有关键词列表（如 KL2951, SS79630 等），但系统找不到文件。用户确认文件确实存在，例如 `SS79630_KL2951_10_DEC_2025.pdf` 包含关键词 `KL2951`。

## 修复内容

### 1. 修复 base_folder 配置（`stockist_test_download.py`）

**修复前：**
```python
def __init__(self, db_path: str, base_folder: str = r"C:\Henry\TR\TR\Stockist&Test Report"):
```

**修复后：**
```python
def __init__(self, db_path: str, base_folder: str = None):
    if base_folder is None:
        # 从环境变量读取，如果没有则使用默认值
        base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
```

**说明：** 现在会从环境变量 `STOCKIST_TEST_FOLDER` 读取基础路径，默认值为 `D:\Stockist&Test Report`。

### 2. 确保 Stockist Cert 文件夹递归搜索（`stockist_test_download.py`）

**修复前：**
```python
stockist_files = self.find_files_by_keywords(self.stockist_folder, all_keywords)
```

**修复后：**
```python
stockist_files = self.find_files_by_keywords(self.stockist_folder, all_keywords, search_subfolders=True)
```

**说明：** 明确指定 `search_subfolders=True`，确保递归搜索所有子文件夹。

### 3. 增强文件系统遍历的调试信息（`stockist_test_download.py`）

添加了详细的调试日志：
- 记录搜索的文件夹路径
- 记录使用的关键词列表
- 记录找到的文件数量和示例文件名
- 如果没有找到文件，记录扫描的文件数量和示例文件名

### 4. 增强索引查询的调试信息（`file_index_query.py`）

添加了详细的调试日志：
- 记录查询使用的关键词和文件夹类型
- 记录查询返回的行数
- 记录示例文件名

### 5. 增强文件匹配逻辑（`file_index_query.py`）

在索引查询中添加了 4 种匹配方式：
1. `file_name LIKE '%keyword%'` - 文件名匹配
2. `extracted_keywords LIKE '%keyword%'` - 提取的关键词匹配
3. `identifiers LIKE '%keyword%'` - 标识符字段匹配（新增）
4. `folder_path LIKE '%keyword%'` - 文件夹路径匹配（新增）

## 下一步：重启服务并查看日志

请重启服务以应用修复：

```powershell
cd "C:\TR-master\TR UI\backend"
.\nssm-2.24\win64\nssm.exe restart TR-Backend
```

重启后，请再次尝试下载 Order 134617，并查看日志文件 `logs\app.log`，查找包含以下关键字的日志条目：
- `[DOWNLOAD]` - 下载过程信息
- `[SEARCH]` - 文件搜索信息
- `[INDEX QUERY]` - 索引查询信息

这些日志会显示：
1. 搜索的文件夹路径是否正确
2. 使用的关键词列表
3. 扫描的文件数量
4. 找到的文件数量和示例文件名
5. 如果没有找到文件，会显示文件夹中的示例文件

## 可能的问题

如果仍然找不到文件，可能的原因包括：

1. **文件路径配置错误**：检查环境变量 `STOCKIST_TEST_FOLDER` 是否正确设置为 `D:\Stockist&Test Report`
2. **文件不在 Stockist Cert 文件夹中**：文件可能在 `IAT Formal`、`IAT Prelim`、`Private Formal` 或 `Private Prelim` 文件夹中
3. **文件索引未更新**：如果使用索引查询，可能需要重新构建文件索引
4. **文件权限问题**：检查服务账户是否有权限访问文件

根据日志信息，可以进一步诊断问题。
