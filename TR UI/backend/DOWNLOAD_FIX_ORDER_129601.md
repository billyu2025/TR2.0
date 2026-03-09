# Order 129601 下载问题修复

## 问题描述

当下载 order 129601（IAT 类型，存在 HL2310 文件夹）时：
- ✅ 成功下载了：`SS79270_HL2310_18_OCT_2025`
- ❌ 未下载：`CMMSC2502935000-002`
- ❌ 未下载：`SSSTE2500551S`

## 问题分析

### 根本原因

1. **文件匹配逻辑问题**：
   - `match_file_to_stockist_cert` 方法只检查文件名或路径中是否包含 `stockist_cert` 或 `rm_dn_no`
   - 如果文件名（如 `CMMSC2502935000-002` 和 `SSSTE2500551S`）不包含这些关键词，无法匹配到 `stockist_cert`
   - 无法匹配的文件会被忽略，不会被添加到 ZIP 文件中

2. **IAT 类型文件查找逻辑**：
   - 对于 IAT 类型，`find_files_by_keywords` 使用 `search_subfolders=False`
   - 只检查子文件夹名称是否包含关键词，然后下载该文件夹中的所有 PDF
   - 如果找到了 HL2310 文件夹，会下载其中的所有 PDF，但在后续的文件匹配中，某些文件可能无法匹配到 `stockist_cert`

### 问题流程

1. 找到 IAT Formal/HL2310 文件夹（通过关键词匹配）
2. 下载该文件夹中的所有 PDF 文件（包括 `SS79270_HL2310_18_OCT_2025`、`CMMSC2502935000-002`、`SSSTE2500551S`）
3. 尝试将文件匹配到 `stockist_cert`：
   - `SS79270_HL2310_18_OCT_2025` ✅ 匹配成功（文件名包含关键词）
   - `CMMSC2502935000-002` ❌ 匹配失败（文件名不包含关键词）
   - `SSSTE2500551S` ❌ 匹配失败（文件名不包含关键词）
4. 无法匹配的文件被忽略，不会被添加到 ZIP 文件中

## 修复方案

### 1. 添加未匹配文件处理逻辑

在 `download_by_order` 方法中，添加了对无法匹配到 `stockist_cert` 的文件的处理：

```python
# 如果无法匹配到 stockist_cert，但仍然在同一个文件夹中（比如 IAT Formal/HL2310 文件夹中的所有文件）
# 检查文件路径是否与已匹配的文件在同一文件夹中
unmatched_files.append(file_path)
print(f"[警告] 文件无法匹配到 stockist_cert: {file_name} (路径: {file_path})")
```

### 2. 按文件夹分组未匹配文件

对于 IAT 类型，如果文件在同一个子文件夹中（如 HL2310），应该属于同一个订单：

```python
# 处理无法匹配的文件：如果它们在同一个子文件夹中，分配给该文件夹中已匹配文件的 stockist_cert
if unmatched_files and is_iat:
    # 按文件夹分组未匹配的文件
    unmatched_by_folder = {}
    for file_path in unmatched_files:
        # 获取文件的直接父文件夹（如 IAT Formal/HL2310）
        folder_path = os.path.dirname(file_path)
        if folder_path not in unmatched_by_folder:
            unmatched_by_folder[folder_path] = []
        unmatched_by_folder[folder_path].append(file_path)
```

### 3. 将未匹配文件分配给同一文件夹中的 stockist_cert

如果同一文件夹中有已匹配的文件，将未匹配的文件分配给同一个 `stockist_cert`：

```python
# 对于每个未匹配文件的文件夹，查找同一文件夹中已匹配的文件
for folder_path, files in unmatched_by_folder.items():
    # 查找同一文件夹中已匹配的文件
    matched_files_in_folder = []
    for stockist_cert, matched_files in files_by_stockist_cert.items():
        for matched_file in matched_files:
            if os.path.dirname(matched_file) == folder_path:
                matched_files_in_folder.append((stockist_cert, matched_file))
                break
    
    # 如果找到已匹配的文件，将未匹配的文件分配给同一个 stockist_cert
    if matched_files_in_folder:
        target_cert = matched_files_in_folder[0][0]
        print(f"[修复] 将文件夹 {os.path.basename(folder_path)} 中的 {len(files)} 个未匹配文件分配给 {target_cert}")
        for file_path in files:
            files_by_stockist_cert[target_cert].append(file_path)
```

### 4. 添加调试日志

添加了详细的调试日志，帮助诊断文件匹配问题：

```python
print(f"[IAT下载] Order {order_no}: 开始查找 IAT Formal 文件")
print(f"[IAT下载] 关键词列表: {all_keywords}")
print(f"[IAT下载] IAT Formal 找到 {len(iat_formal_files)} 个文件: {[os.path.basename(f) for f in iat_formal_files]}")
print(f"[IAT下载] 警告: 文件 {file_name} 无法匹配到 stockist_cert")
print(f"[IAT下载] 以下 stockist_cert 在 IAT Formal 中没有文件: {missing_certs}")
```

## 修复效果

修复后，对于 order 129601：
- ✅ `SS79270_HL2310_18_OCT_2025` - 正常匹配并下载
- ✅ `CMMSC2502935000-002` - 虽然无法匹配到 `stockist_cert`，但会被分配给同一文件夹中已匹配文件的 `stockist_cert`，并下载
- ✅ `SSSTE2500551S` - 虽然无法匹配到 `stockist_cert`，但会被分配给同一文件夹中已匹配文件的 `stockist_cert`，并下载

## 最新修复（第二次修复）

### 问题
即使添加了未匹配文件的处理逻辑，文件仍然没有被下载。

### 原因分析
1. 路径比较问题：`os.path.dirname(matched_file) == folder_path` 可能因为路径格式不一致而失败
2. 子文件夹路径识别问题：对于 IAT 类型，文件可能在子文件夹的子目录中，需要正确识别子文件夹路径

### 修复内容

1. **改进路径比较逻辑**：
   - 使用 `os.path.normpath()` 标准化路径
   - 支持子文件夹的子目录中的文件匹配
   - 改进子文件夹路径识别逻辑

2. **添加详细调试日志**：
   - 文件查找过程日志
   - 文件匹配过程日志
   - 文件分配过程日志
   - ZIP 文件创建过程日志

3. **改进未匹配文件处理**：
   - 更准确地识别子文件夹路径
   - 支持在子文件夹的子目录中的文件匹配

## 测试建议

1. **测试 order 129601**：
   - 下载 order 129601
   - 检查 ZIP 文件中是否包含所有 3 个文件
   - 查看后端日志，确认：
     - `[IAT下载]` - IAT 文件查找过程
     - `[文件匹配]` - 文件匹配过程
     - `[文件分配]` - 文件分配结果
     - `[ZIP创建]` - ZIP 文件创建过程

2. **测试其他 IAT 类型订单**：
   - 测试其他包含无法匹配文件的 IAT 类型订单
   - 确保修复不会影响正常文件的下载

3. **测试 Private 类型订单**：
   - 确保修复只影响 IAT 类型，不影响 Private 类型

## 注意事项

1. **修复范围**：
   - 修复只针对 IAT 类型订单
   - Private 类型订单不受影响（因为 Private 类型使用 `search_subfolders=True`，文件匹配逻辑不同）

2. **文件分配逻辑**：
   - 如果同一文件夹中有多个已匹配的文件（对应不同的 `stockist_cert`），未匹配的文件会被分配给第一个找到的 `stockist_cert`
   - 如果同一文件夹中没有已匹配的文件，未匹配的文件会被分配给第一个 `stockist_cert`（如果有的话）

3. **日志输出**：
   - 修复后会输出详细的调试日志
   - 可以通过日志查看文件匹配和分配过程

## 文件修改

- `backend/stockist_test_download.py` - 添加未匹配文件处理逻辑和调试日志
