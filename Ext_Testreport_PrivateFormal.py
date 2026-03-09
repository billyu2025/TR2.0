#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extract Private Formal PDF files from source directory
抽取Private Formal PDF文件脚本

功能：
- 从源目录中查找匹配命名模式的文件
  - 纯DN_No格式：如SS78156.pdf
  - DN_No组合格式（无空格）：如SS71064&SS71063.pdf或SS71451~SS71452.pdf
  - DN_No组合格式（带空格）：如SS73300 ~ SS73302.pdf或SS73305 & SS73306.pdf
  - Chemical test report格式：如Chemical test report of SS73165.pdf
  - Physical, geometry test report格式：如Physical, geometry test report of SS73165.pdf
  - DN_No + 空格 + 文本格式：如SS74168 Test Report.pdf、SS74168 Chemical Test Report.pdf、SS74168 Test Report (Bond Property).pdf
  - DN_No + 括号 + 文本格式：如SS76293(Latest).pdf
- 只复制PDF文件到目标目录
- 如果目标文件已存在则覆盖
- 不删除源文件
"""

import os
import shutil
import re
import sys
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime

# 添加 backend 目录到路径，以便导入 file_index_query
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'TR UI', 'backend')
if os.path.exists(backend_dir):
    sys.path.insert(0, backend_dir)
    try:
        from file_index_query import FileIndexQuery
        INDEX_AVAILABLE = True
    except ImportError:
        INDEX_AVAILABLE = False
        print("[警告] 无法导入 file_index_query，将跳过文件存在性检查")
else:
    INDEX_AVAILABLE = False
    print("[警告] backend 目录不存在，将跳过文件存在性检查")


# 源目录
SOURCE_DIR = r"\\192.168.32.212\TVSC-Internal\Dp-Supply Chain\Inventory\07 Stockist and Mill cert Packages to Customer\02 - With Private Report"

# 目标目录
TARGET_DIR = r"D:\Stockist&Test Report\Private Formal"

# 数据库路径（用于文件索引查询）
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.normpath(os.path.join(_current_dir))
_default_db_path = os.path.join(_project_root, 'TR UI', 'backend', 'tr_system.db')
DB_PATH = os.getenv('DB_PATH', _default_db_path)

# 如果环境变量是相对路径，转换为绝对路径
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.abspath(os.path.join(_project_root, DB_PATH))

# 文件命名模式：支持多种格式
# 1. 纯DN_No命名：SS78156.pdf
# 2. DN_No组合命名（无空格）：SS71064&SS71063.pdf 或 SS71451~SS71452.pdf
# 3. DN_No组合命名（带空格）：SS73300 ~ SS73302.pdf（~前后有空格）或 SS73305 & SS73306.pdf（&前后有空格）
# 4. Chemical test report格式：Chemical test report of SS73165.pdf
# 5. Physical, geometry test report格式：Physical, geometry test report of SS73165.pdf
# 6. DN_No + 空格 + 文本格式：SS74168 Test Report.pdf、SS74168 Chemical Test Report.pdf、SS74168 Test Report (Bond Property).pdf
# 7. DN_No + 括号 + 文本格式：SS76293(Latest).pdf
FILE_PATTERN = re.compile(
    r'^([A-Z0-9]+([&~][A-Z0-9]+)*|[A-Z0-9]+(\s*[&~]\s*[A-Z0-9]+)+|Chemical test report of [A-Z0-9]+|Physical, geometry test report of [A-Z0-9]+|[A-Z0-9]+\([A-Za-z0-9\s()]+\)|[A-Z0-9]+ [A-Za-z0-9\s()]+)\.pdf$',
    re.IGNORECASE
)


def is_prelim_file(filename):
    """
    检测文件是否是 Prelim 文件（不是 Formal 文件）
    通过检查文件名中是否包含 "Physical, chemical & geometry test report" 关键字（不区分大小写）
    
    例如：
    - Physical, chemical & geometry test report of SS79591.pdf
    """
    filename_lower = filename.lower()
    return 'physical, chemical & geometry test report' in filename_lower

def ensure_target_dir():
    """确保目标目录存在"""
    target_path = Path(TARGET_DIR)
    target_path.mkdir(parents=True, exist_ok=True)
    print(f"[信息] 目标目录: {TARGET_DIR}")
    return target_path


def find_matching_files(source_dir: str) -> Tuple[List[Tuple[str, str]], List[str]]:
    """
    在源目录中查找匹配命名模式的PDF文件
    
    Args:
        source_dir: 源目录路径
        
    Returns:
        Tuple of (matching_files, empty_subfolders)
        matching_files: List of tuples: (file_path, file_name)
        empty_subfolders: List of subfolder paths that have no matching files
    """
    matching_files = []
    source_path = Path(source_dir)
    
    if not source_path.exists():
        print(f"[警告] 源目录不存在: {source_dir}")
        return matching_files, []
    
    print(f"\n[搜索] 正在搜索目录: {source_dir}")
    
    # 按子文件夹组织文件
    files_by_subfolder = {}  # {subfolder_path: [file_paths]}
    
    # 递归搜索所有PDF文件
    for pdf_file in source_path.rglob("*.pdf"):
        file_name = pdf_file.name
        
        # 跳过 Prelim 文件（Physical, chemical & geometry test report 格式）
        if is_prelim_file(file_name):
            continue
        
        # 检查文件名是否匹配模式（纯DN_No命名或DN_No组合命名）
        if FILE_PATTERN.match(file_name):
            matching_files.append((str(pdf_file), file_name))
            
            # 获取相对于源目录的路径（子文件夹路径）
            try:
                relative_path = pdf_file.relative_to(source_path)
                # 获取父目录（子文件夹名称）
                parent_dir = relative_path.parent
                
                if parent_dir and str(parent_dir) != '.':
                    # 文件在子文件夹中
                    subfolder_path = str(parent_dir).replace('\\', '/')
                    if subfolder_path not in files_by_subfolder:
                        files_by_subfolder[subfolder_path] = []
                    files_by_subfolder[subfolder_path].append((str(pdf_file), file_name))
                else:
                    # 文件直接在源目录中，使用特殊键
                    if '.' not in files_by_subfolder:
                        files_by_subfolder['.'] = []
                    files_by_subfolder['.'].append((str(pdf_file), file_name))
            except ValueError:
                # 如果无法计算相对路径，使用父目录路径
                parent_str = str(pdf_file.parent)
                if parent_str not in files_by_subfolder:
                    files_by_subfolder[parent_str] = []
                files_by_subfolder[parent_str].append((str(pdf_file), file_name))
    
    # 获取所有子文件夹（包括没有匹配文件的子文件夹）
    all_subfolders = set()
    for item in source_path.iterdir():
        if item.is_dir():
            try:
                relative_path = item.relative_to(source_path)
                subfolder_path = str(relative_path).replace('\\', '/')
                all_subfolders.add(subfolder_path)
            except ValueError:
                pass
    
    # 合并已找到文件的子文件夹和所有子文件夹
    all_subfolders.update(files_by_subfolder.keys())
    
    # 按字母顺序排序子文件夹
    sorted_subfolders = sorted(all_subfolders)
    
    # 收集未找到匹配文件的子文件夹（完整路径）
    empty_subfolders = []
    
    # 输出每个子文件夹的内容
    for subfolder in sorted_subfolders:
        if subfolder == '.':
            # 根目录中的文件
            if subfolder in files_by_subfolder:
                print(f"\n[子文件夹] 根目录")
                for file_path, file_name in files_by_subfolder[subfolder]:
                    print(f"  ✓ {file_name}")
        else:
            # 构建完整的子文件夹路径用于显示
            full_subfolder_path = f"{source_dir}\\{subfolder}".replace('/', '\\')
            print(f"\n[子文件夹] {full_subfolder_path}")
            
            if subfolder in files_by_subfolder:
                # 子文件夹中有匹配的文件
                for file_path, file_name in files_by_subfolder[subfolder]:
                    print(f"  ✓ {file_name}")
            else:
                # 子文件夹中没有匹配的文件（或者只有 Prelim 文件）
                # 检查子文件夹中是否有任何 PDF 文件（包括 Prelim 文件）
                subfolder_path = source_path / subfolder.replace('/', os.sep)
                has_any_pdf = False
                if subfolder_path.exists():
                    for pdf_file in subfolder_path.glob("*.pdf"):
                        has_any_pdf = True
                        break
                
                if has_any_pdf:
                    # 有 PDF 文件但都是 Prelim 文件，不输出文件夹位置
                    print(f"  (未找到匹配的文件，跳过 Prelim 文件)")
                else:
                    # 完全没有 PDF 文件
                print(f"  (未找到匹配的文件)")
                empty_subfolders.append(full_subfolder_path)
    
    return matching_files, empty_subfolders


def check_file_exists_in_target(file_name: str, base_folder: str = TARGET_DIR) -> Optional[str]:
    """
    检查 Private Formal 文件夹中是否已存在对应文件
    
    例如："C0146.pdf" 和 "C0146_Private_Formal.pdf" 是同一个文件
    
    Args:
        file_name: 源文件名（例如："C0146.pdf" 或 "SS78156.pdf"）
        base_folder: Stockist&Test Report 基础文件夹路径
        
    Returns:
        如果找到对应文件，返回文件路径；否则返回 None
    """
    if not INDEX_AVAILABLE:
        return None
    
    try:
        # 创建文件索引查询器
        index_query = FileIndexQuery(DB_PATH)
        
        # 检查 Private Formal 文件夹中是否已存在对应文件
        existing_file = index_query.check_file_exists_in_private_formal(file_name, base_folder)
        
        return existing_file
    except Exception as e:
        print(f"  [警告] 检查文件存在性失败: {str(e)}")
        return None


def copy_file_to_target(source_file: str, target_dir: Path) -> Tuple[bool, str]:
    """
    复制文件到目标目录（如果已存在则跳过）
    在复制前会先检查 Private Formal 文件夹中是否已存在对应文件
    
    Args:
        source_file: 源文件路径
        target_dir: 目标目录路径
        
    Returns:
        (success: bool, status: str)
        success: True if successful or skipped, False otherwise
        status: 'copied', 'skipped_existing', 'skipped_matched', or 'failed'
    """
    try:
        source_path = Path(source_file)
        file_name = source_path.name
        target_file = target_dir / file_name
        
        # 先检查目标文件夹中是否已存在对应文件
        # base_folder 应该是 "D:\Stockist&Test Report"，而不是 "Private Formal" 子目录
        base_folder = os.path.dirname(str(target_dir))  # 获取 "D:\Stockist&Test Report"
        existing_file = check_file_exists_in_target(file_name, base_folder)
        
        if existing_file:
            existing_path = Path(existing_file)
            if existing_path.exists():
                print(f"  [跳过] {file_name} - 对应文件已存在: {existing_path.name}")
                return True, 'skipped_matched'
        
        # 如果目标文件已存在，也跳过（避免重复复制）
        if target_file.exists():
            print(f"  [跳过] {file_name} - 目标文件已存在")
            return True, 'skipped_existing'
        
        # 复制文件
        shutil.copy2(source_path, target_file)
        
        # 验证文件是否成功复制
        if target_file.exists():
            print(f"  [复制成功] {file_name}")
            return True, 'copied'
        else:
            print(f"  [复制失败] {file_name} - 目标文件不存在")
            return False, 'failed'
            
    except Exception as e:
        print(f"  [错误] 复制文件失败 {source_path.name}: {str(e)}")
        return False, 'failed'


def save_empty_subfolders_to_file(empty_subfolders: List[str], output_file: str):
    """
    将未找到匹配文件的子文件夹路径保存到txt文件
    
    Args:
        empty_subfolders: 未找到匹配文件的子文件夹路径列表
        output_file: 输出文件路径
    """
    if not empty_subfolders:
        print(f"\n[信息] 所有子文件夹都包含匹配的文件，无需生成报告文件")
        return
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("未找到匹配文件的子文件夹列表\n")
            f.write("=" * 80 + "\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"源目录: {SOURCE_DIR}\n")
            f.write(f"总计: {len(empty_subfolders)} 个子文件夹\n")
            f.write("=" * 80 + "\n\n")
            
            for subfolder_path in sorted(empty_subfolders):
                f.write(f"{subfolder_path}\n")
        
        print(f"\n[完成] 已将 {len(empty_subfolders)} 个未找到匹配文件的子文件夹路径保存到: {output_file}")
    except Exception as e:
        print(f"\n[错误] 保存文件失败: {str(e)}")


def main():
    """主函数"""
    
    print("=" * 80)
    print("Private Formal PDF 文件提取脚本")
    print("=" * 80)
    
    # 确保目标目录存在
    target_dir = ensure_target_dir()
    
    # 查找所有匹配的文件和未找到匹配文件的子文件夹
    matching_files, empty_subfolders = find_matching_files(SOURCE_DIR)
    
    if not matching_files:
        print("\n[结果] 未找到匹配的文件")
        # 即使没有匹配的文件，也保存未找到匹配文件的子文件夹列表
        if empty_subfolders:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            output_file = os.path.join(script_dir, f"empty_subfolders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            save_empty_subfolders_to_file(empty_subfolders, output_file)
        return
    
    print(f"\n[统计] 共找到 {len(matching_files)} 个匹配的PDF文件")
    print(f"[目标] 将复制到: {TARGET_DIR}\n")
    
    # 复制文件
    copied_count = 0
    skipped_matched_count = 0  # 跳过：找到对应文件
    skipped_existing_count = 0  # 跳过：目标文件已存在
    fail_count = 0
    
    for source_file, file_name in matching_files:
        success, status = copy_file_to_target(source_file, target_dir)
        if success:
            if status == 'copied':
                copied_count += 1
            elif status == 'skipped_matched':
                skipped_matched_count += 1
            elif status == 'skipped_existing':
                skipped_existing_count += 1
        else:
            fail_count += 1
    
    # 输出结果统计
    print("\n" + "=" * 80)
    print("[完成] 文件提取完成")
    print(f"  已复制: {copied_count} 个文件")
    print(f"  跳过（找到对应文件）: {skipped_matched_count} 个文件")
    print(f"  跳过（目标文件已存在）: {skipped_existing_count} 个文件")
    print(f"  失败: {fail_count} 个文件")
    print(f"  总计: {len(matching_files)} 个文件")
    print("=" * 80)
    
    # 保存未找到匹配文件的子文件夹列表到txt文件
    if empty_subfolders:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_file = os.path.join(script_dir, f"empty_subfolders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        save_empty_subfolders_to_file(empty_subfolders, output_file)


if __name__ == "__main__":
    main()

