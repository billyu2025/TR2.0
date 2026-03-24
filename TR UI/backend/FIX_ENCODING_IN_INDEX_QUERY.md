# 修复索引查询中的编码错误

## 问题描述

Order 134617 下载时报告 "All Orders [134617] have no related PDF files found"，但日志显示：
1. ✅ 索引查询成功找到了 8 个文件
2. ✅ `[INDEX QUERY] Query returned 8 rows`
3. ✅ `[INDEX QUERY] Extracted 8 file paths from 8 rows`
4. ❌ 但随后出现编码错误：`'charmap' codec can't encode characters in position 1-4`
5. ❌ 导致回退到文件系统遍历，但文件系统遍历没有找到文件

## 根本原因

在 `stockist_test_download.py` 和 `file_index_query.py` 中，使用了 f-string 记录日志，当文件路径或文件夹路径包含中文字符时，在 Windows NSSM 服务的 `charmap` 编码环境下会出现编码错误。

### 问题代码位置

1. **`stockist_test_download.py` 第 630 行**：
   ```python
   logger.debug(f"[INDEX QUERY] Searching folder_type={folder_type} with {len(keywords)} keywords, search_subfolders={search_subfolders}")
   ```

2. **`stockist_test_download.py` 第 641 行**：
   ```python
   logger.debug(f"[INDEX QUERY] Found {len(found_files)} files in folder_type={folder_type}")
   ```

3. **`stockist_test_download.py` 第 676 行**：
   ```python
   logger.debug(f"[INDEX QUERY] Subfolder {os.path.basename(subfolder)}: found {len(subfolder_files)} PDF files")
   ```

4. **`stockist_test_download.py` 第 689 行**：
   ```python
   logger.debug(f"[INDEX QUERY] {folder}: found {len(found_files)} matching PDFs")
   ```

5. **`file_index_query.py` 第 380 行**：
   ```python
   logger.info(f"[INDEX QUERY] Extracted {len(file_paths)} file paths from {len(rows)} rows")
   ```

6. **`file_index_query.py` 第 352 行**：
   ```python
   logger.warning(f"[INDEX QUERY] Row {i}: Cannot extract file_path, row type: {type(row)}, row keys: {list(row.keys()) if hasattr(row, 'keys') else 'N/A'}")
   ```

## 修复方案

将所有 f-string 日志改为字符串拼接，并对可能包含中文字符的路径进行 ASCII 编码处理。

### 修复后的代码

1. **`stockist_test_download.py`**：
   ```python
   # 修复前
   logger.debug(f"[INDEX QUERY] Searching folder_type={folder_type} with {len(keywords)} keywords, search_subfolders={search_subfolders}")
   
   # 修复后
   logger.debug("[INDEX QUERY] Searching folder_type=" + str(folder_type) + " with " + str(len(keywords)) + " keywords, search_subfolders=" + str(search_subfolders))
   ```

2. **`stockist_test_download.py`**：
   ```python
   # 修复前
   logger.debug(f"[INDEX QUERY] {folder}: found {len(found_files)} matching PDFs")
   
   # 修复后
   folder_safe = str(folder).encode('ascii', 'ignore').decode('ascii')
   logger.debug("[INDEX QUERY] " + folder_safe + ": found " + str(len(found_files)) + " matching PDFs")
   ```

3. **`file_index_query.py`**：
   ```python
   # 修复前
   logger.info(f"[INDEX QUERY] Extracted {len(file_paths)} file paths from {len(rows)} rows")
   
   # 修复后
   logger.info("[INDEX QUERY] Extracted " + str(len(file_paths)) + " file paths from " + str(len(rows)) + " rows")
   ```

## 测试结果

修复后，索引查询应该能够：
1. ✅ 成功找到文件（8 个文件）
2. ✅ 正确提取文件路径
3. ✅ 返回文件列表给调用者
4. ✅ 不再出现编码错误
5. ✅ 不再回退到文件系统遍历

## 验证步骤

1. 重启 NSSM 服务
2. 尝试下载 Order 134617
3. 检查日志，确认：
   - `[INDEX QUERY] Query returned 8 rows`
   - `[INDEX QUERY] Extracted 8 file paths from 8 rows`
   - 没有编码错误
   - 成功下载文件

## 相关文件

- `backend/stockist_test_download.py`
- `backend/file_index_query.py`
