# Stockist & Test Report 下载逻辑说明

## 问题：为什么 Order 133909 能下载到 ZZ3855 相关的文件？

### 下载流程

当下载 Order 133909 的 Stockist & Test Report 时，系统按以下步骤工作：

#### 1. 获取订单信息

从 `TR_Report` 表中查询 Order 133909 的相关信息：
- `stockist_cert`：证书编号（如 ZZ3855）
- `rm_dn_no`：RM DN 编号
- `jobsite_type`：工地类型（用于判断是 IAT 还是 PRIVATE）

#### 2. 构建关键词列表

系统会将所有相关的标识符合并为关键词列表：
```python
all_keywords = stockist_certs + rm_dn_nos
# 例如：['ZZ3855', 'SS79438', ...]
```

#### 3. 查找文件（IAT 类型）

对于 IAT 类型的订单，系统会：

**步骤 3.1：查找 IAT Formal 子文件夹**
- 在 `D:\Stockist&Test Report\IAT Formal` 中查找**子文件夹名称**包含关键词的文件夹
- 例如：如果关键词包含 "ZZ3855"，会查找名称包含 "ZZ3855" 的子文件夹
- **重要**：即使没有名为 "ZZ3855" 的文件夹，只要某个子文件夹名称中包含 "ZZ3855"（如 "SS79438_ZZ3855"），就会被匹配到

**步骤 3.2：下载匹配文件夹中的所有文件**
- 一旦找到匹配的子文件夹，系统会下载该文件夹中的**所有 PDF 文件**
- 这包括：
  - `Physical, chemical & geometry test report of SS79438.pdf`
  - `SS79438_ZZ3855_11_NOV_2025.pdf`
  - 以及其他任何在该文件夹中的 PDF 文件

#### 4. 文件查找机制

系统使用两种方式查找文件：

**方式 1：使用文件索引（file_index_cache）**
```python
# 如果索引可用，使用索引查询
if self.index_query and self.index_query.is_index_available():
    # 找到匹配的子文件夹
    matching_subfolders = []
    for item in os.listdir(folder):
        if os.path.isdir(item_path):
            for keyword in keywords:
                if keyword.lower() in item.lower():
                    matching_subfolders.append(item_path)
    
    # 查询该子文件夹中的所有文件
    for subfolder in matching_subfolders:
        subfolder_files = self.index_query.find_files_in_subfolder(
            folder_path=subfolder,
            keywords=[]  # 不限制关键词，获取所有文件
        )
```

**方式 2：文件系统遍历（回退方案）**
```python
# 如果索引不可用，遍历文件系统
for subfolder in subfolders:
    for root, dirs, files in os.walk(subfolder):
        for file in files:
            if file.lower().endswith('.pdf'):
                found_files.append(file_path)
```

### 关键点

1. **子文件夹匹配**：系统不是查找名为 "ZZ3855" 的文件夹，而是查找**名称中包含 "ZZ3855"** 的文件夹
   - ✅ 匹配：`SS79438_ZZ3855` 文件夹
   - ✅ 匹配：`ZZ3855_Test` 文件夹
   - ❌ 不匹配：`ZZ3856` 文件夹（不包含 ZZ3855）

2. **下载所有文件**：一旦找到匹配的子文件夹，会下载该文件夹中的**所有 PDF 文件**，不管文件名是什么

3. **关键词来源**：关键词来自 `TR_Report` 表的 `stockist_cert` 和 `rm_dn_no` 字段

### 示例：Order 133909

假设 Order 133909 在 `TR_Report` 表中的数据：
- `stockist_cert` = "ZZ3855"
- `rm_dn_no` = "SS79438"

**下载过程**：

1. 关键词列表：`['ZZ3855', 'SS79438']`

2. 在 `IAT Formal` 中查找：
   - 查找子文件夹名称包含 "ZZ3855" 或 "SS79438" 的文件夹
   - 找到：`D:\Stockist&Test Report\IAT Formal\SS79438_ZZ3855`（假设存在）

3. 下载该文件夹中的所有 PDF：
   - `Physical, chemical & geometry test report of SS79438.pdf`
   - `SS79438_ZZ3855_11_NOV_2025.pdf`
   - 其他任何 PDF 文件

### 代码位置

主要逻辑在 `backend/stockist_test_download.py`：

- `download_by_order()`：主下载方法（第 756 行）
- `find_files_by_keywords()`：文件查找方法（第 518 行）
- `get_all_cert_dn_values()`：获取关键词列表（第 396 行）

### 实际文件路径来源

#### 基础路径配置

系统从环境变量 `STOCKIST_TEST_FOLDER` 读取基础路径，默认值为：
```
D:\Stockist&Test Report
```

#### IAT Formal 文件夹路径

```
D:\Stockist&Test Report\IAT Formal
```

#### 实际文件路径示例

对于 Order 133909，如果找到匹配的子文件夹 `SS79438_ZZ3855`，实际下载的文件路径可能是：

1. **Physical, chemical & geometry test report of SS79438.pdf**
   - 完整路径：`D:\Stockist&Test Report\IAT Formal\SS79438_ZZ3855\Physical, chemical & geometry test report of SS79438.pdf`
   - 或者：`D:\Stockist&Test Report\IAT Formal\SS79438_ZZ3855\子文件夹\Physical, chemical & geometry test report of SS79438.pdf`

2. **SS79438_ZZ3855_11_NOV_2025.pdf**
   - 完整路径：`D:\Stockist&Test Report\IAT Formal\SS79438_ZZ3855\SS79438_ZZ3855_11_NOV_2025.pdf`
   - 或者：`D:\Stockist&Test Report\IAT Formal\SS79438_ZZ3855\子文件夹\SS79438_ZZ3855_11_NOV_2025.pdf`

#### 文件查找方式

**方式 1：使用文件索引（file_index_cache）**
- 从 `file_index_cache` 表中查询 `file_path`
- 对于 IAT Formal，`file_path` 可能是文件夹路径
- 然后遍历该文件夹获取所有 PDF 文件

**方式 2：文件系统遍历（回退方案）**
- 如果索引不可用，直接遍历文件系统
- 使用 `os.walk()` 递归遍历匹配的子文件夹

#### 如何查看实际文件路径

运行检查脚本：
```bash
cd C:\TR-master\TR UI\backend
python check_download_file_sources.py 133909
```

该脚本会：
1. 显示订单信息（stockist_cert, rm_dn_no）
2. 列出所有关键词
3. 查找匹配的 IAT Formal 子文件夹
4. 显示每个子文件夹中的所有 PDF 文件及其完整路径
5. 检查文件索引中的信息

### 总结

**为什么能找到 ZZ3855 相关的文件？**

因为系统不是查找名为 "ZZ3855" 的文件夹，而是查找**名称中包含 "ZZ3855"** 的子文件夹（如 `SS79438_ZZ3855`），然后下载该文件夹中的所有 PDF 文件。这就是为什么即使 IAT Formal 中没有名为 "ZZ3855" 的文件夹，也能下载到相关文件的原因。

**实际文件来自哪里？**

文件来自 `D:\Stockist&Test Report\IAT Formal\` 下匹配的子文件夹中。系统会遍历这些子文件夹（包括子文件夹的子文件夹），下载所有找到的 PDF 文件。
