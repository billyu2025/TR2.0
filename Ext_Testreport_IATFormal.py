#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extract IAT Formal folders from source directory
抽取IAT Formal文件夹脚本

功能：
- 从源目录中查找匹配命名模式的文件夹（纯Stockist No格式，如ZZ3274）
- 复制整个文件夹及其内容到目标目录
- 如果目标文件夹已存在则跳过
- 不删除源文件夹
"""

import os
import shutil
import re
from pathlib import Path
from typing import List, Tuple, Optional


# 源目录
SOURCE_DIR = r"\\192.168.32.212\TVSC-Internal\Dp-Supply Chain\Inventory\07 Stockist and Mill cert Packages to Customer\01 - With IAT Report"

# 目标目录
TARGET_DIR = r"D:\Stockist&Test Report\IAT Formal"

# 文件夹命名模式：纯Stockist No命名
# 例如：ZZ3274
# 模式：字母数字组合
FOLDER_PATTERN = re.compile(
    r'^[A-Z0-9]+$',
    re.IGNORECASE
)


def ensure_target_dir():
    """确保目标目录存在"""
    target_path = Path(TARGET_DIR)
    target_path.mkdir(parents=True, exist_ok=True)
    print(f"[信息] 目标目录: {TARGET_DIR}")
    return target_path


def find_matching_folders(source_dir: str) -> List[Tuple[str, str]]:
    """
    在源目录中查找匹配命名模式的文件夹
    
    Args:
        source_dir: 源目录路径
        
    Returns:
        List of tuples: (folder_path, folder_name)
    """
    matching_folders = []
    source_path = Path(source_dir)
    
    if not source_path.exists():
        print(f"[警告] 源目录不存在: {source_dir}")
        return matching_folders
    
    print(f"\n[搜索] 正在搜索目录: {source_dir}")
    
    # 搜索源目录下的所有直接子文件夹
    for item in source_path.iterdir():
        if item.is_dir():
            folder_name = item.name
            
            # 检查文件夹名是否匹配模式（纯Stockist No命名）
            if FOLDER_PATTERN.match(folder_name):
                matching_folders.append((str(item), folder_name))
                print(f"  [找到] {folder_name}/")
    
    return matching_folders


def should_skip_file(file_name: str) -> bool:
    """
    判断是否应该跳过该文件
    
    Args:
        file_name: 文件名（包含扩展名）
        
    Returns:
        True if should skip, False otherwise
    """
    file_name_lower = file_name.lower()
    
    # 模式1: 包含 "Stockist" 和 "Mill Cert" 或 "MIll Cert" 的文件
    # 例如: Stockist + MIll Cert_C0478.pdf
    if 'stockist' in file_name_lower and 'mill cert' in file_name_lower:
        return True
    
    # 模式2: SS数字_字母数字_日期.pdf 格式的文件
    # 例如: SS79461_KL2929_14_NOV_2025.pdf
    # 模式: SS开头，后面是数字，下划线，字母数字组合，下划线，日期格式（数字_月份_年份）
    # 月份可能是 JAN, FEB, MAR, APR, MAY, JUN, JUL, AUG, SEP, OCT, NOV, DEC
    ss_pattern = re.compile(r'^SS\d+_[A-Z0-9]+_\d+_(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)_\d+\.pdf$', re.IGNORECASE)
    if ss_pattern.match(file_name):
        return True
    
    # 模式2b: SS数字_日期.pdf 格式的文件
    # 例如: SS74967_02_NOV_2023.pdf
    # 模式: SS开头，后面是数字，下划线，日期格式（数字_月份_年份）
    # 月份可能是 JAN, FEB, MAR, APR, MAY, JUN, JUL, AUG, SEP, OCT, NOV, DEC
    ss_date_pattern = re.compile(r'^SS\d+_\d+_(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)_\d+\.pdf$', re.IGNORECASE)
    if ss_date_pattern.match(file_name):
        return True
    
    # 模式3: 包含 "Physical, chemical & geometry test report" 的文件（可能是文件夹或文件）
    # 例如: Physical, chemical & geometry test report of SS79658
    if 'physical, chemical & geometry test report' in file_name_lower:
        return True
    
    # 模式4: 包含 "Stockist cert & mill cert" 的文件（可能是文件夹或文件）
    # 例如: Stockist cert & mill cert of SS66328
    if 'stockist cert & mill cert' in file_name_lower:
        return True
    
    return False


def copy_folder_to_target(source_folder: str, target_dir: Path) -> Optional[bool]:
    """
    复制文件夹到目标目录（如果已存在则跳过）
    过滤掉不需要的文件，如果过滤后文件夹为空则不复制
    
    Args:
        source_folder: 源文件夹路径
        target_dir: 目标目录路径
        
    Returns:
        True if successful, None if skipped (target exists or empty after filtering), False if failed
    """
    try:
        source_path = Path(source_folder)
        folder_name = source_path.name
        target_folder = target_dir / folder_name
        
        # 收集需要复制的文件（排除需要跳过的文件）
        files_to_copy = []
        skipped_files = []
        
        # 遍历源文件夹中的所有文件
        for root, dirs, files in os.walk(source_path):
            # 过滤掉需要跳过的文件夹（在遍历时排除）
            dirs[:] = [d for d in dirs if not should_skip_file(d)]
            
            for file in files:
                file_path = Path(root) / file
                relative_path = file_path.relative_to(source_path)
                
                # 检查是否应该跳过该文件
                if should_skip_file(file):
                    skipped_files.append(str(relative_path))
                    continue
                
                # 添加到复制列表
                files_to_copy.append((file_path, relative_path))
        
        # 如果目标文件夹已存在，直接跳过
        if target_folder.exists():
            print(f"  [跳过] {folder_name}/ - 目标文件夹已存在")
            return None  # 返回 None 表示跳过（不是失败）
        
        # 如果过滤后没有文件，不复制该文件夹
        if not files_to_copy:
            print(f"  [跳过] {folder_name}/ - 过滤后文件夹为空（已跳过 {len(skipped_files)} 个文件）")
            if skipped_files:
                print(f"    跳过的文件: {', '.join(skipped_files[:5])}" + 
                      (f" 等共 {len(skipped_files)} 个" if len(skipped_files) > 5 else ""))
            return None  # 返回 None 表示跳过（不是失败）
        
        # 创建目标文件夹
        target_folder.mkdir(parents=True, exist_ok=True)
        
        # 复制文件（保持目录结构）
        copied_count = 0
        for source_file, relative_path in files_to_copy:
            target_file = target_folder / relative_path
            # 确保目标文件的父目录存在
            target_file.parent.mkdir(parents=True, exist_ok=True)
            # 复制文件
            shutil.copy2(source_file, target_file)
            copied_count += 1
        
        # 验证文件夹是否成功复制
        if target_folder.exists():
            # 统计文件夹中的文件数量
            file_count = sum(1 for _ in target_folder.rglob('*') if _.is_file())
            print(f"  [复制成功] {folder_name}/ (包含 {file_count} 个文件")
            if skipped_files:
                print(f"    已跳过 {len(skipped_files)} 个文件)")
            else:
                print(")")
            return True
        else:
            print(f"  [复制失败] {folder_name}/ - 目标文件夹不存在")
            return False
            
    except Exception as e:
        print(f"  [错误] 复制文件夹失败 {source_path.name}/: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("=" * 80)
    print("IAT Formal 文件夹提取脚本")
    print("=" * 80)
    
    # 确保目标目录存在
    target_dir = ensure_target_dir()
    
    # 查找所有匹配的文件夹
    matching_folders = find_matching_folders(SOURCE_DIR)
    
    if not matching_folders:
        print("\n[结果] 未找到匹配的文件夹")
        return
    
    print(f"\n[统计] 共找到 {len(matching_folders)} 个匹配的文件夹")
    print(f"[目标] 将复制到: {TARGET_DIR}\n")
    
    # 复制文件夹
    success_count = 0
    fail_count = 0
    skipped_count = 0
    
    for source_folder, folder_name in matching_folders:
        result = copy_folder_to_target(source_folder, target_dir)
        if result is True:
            success_count += 1
        elif result is None:
            # 返回 None 表示因为过滤后为空而跳过
            skipped_count += 1
        else:
            # 返回 False 表示复制失败
            fail_count += 1
    
    # 输出结果统计
    print("\n" + "=" * 80)
    print("[完成] 文件夹提取完成")
    print(f"  成功: {success_count} 个文件夹")
    print(f"  跳过（目标已存在或过滤后为空）: {skipped_count} 个文件夹")
    print(f"  失败: {fail_count} 个文件夹")
    print(f"  总计: {len(matching_folders)} 个文件夹")
    print("=" * 80)


if __name__ == "__main__":
    main()

