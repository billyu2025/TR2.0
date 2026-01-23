#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extract Private Formal PDF files from source directory
抽取Private Formal PDF文件脚本

功能：
- 从源目录中查找匹配命名模式的文件（纯DN_No格式，如SS78156.pdf）
- 只复制PDF文件到目标目录
- 如果目标文件已存在则覆盖
- 不删除源文件
"""

import os
import shutil
import re
from pathlib import Path
from typing import List, Tuple


# 源目录
SOURCE_DIR = r"\\192.168.32.212\TVSC-Internal\Dp-Supply Chain\Inventory\07 Stockist and Mill cert Packages to Customer\02 - With Private Report"

# 目标目录
TARGET_DIR = r"D:\Stockist&Test Report\Private Formal"

# 文件命名模式：纯DN_No命名
# 例如：SS78156.pdf
# 模式：字母数字组合，以.pdf结尾
FILE_PATTERN = re.compile(
    r'^[A-Z0-9]+\.pdf$',
    re.IGNORECASE
)


def ensure_target_dir():
    """确保目标目录存在"""
    target_path = Path(TARGET_DIR)
    target_path.mkdir(parents=True, exist_ok=True)
    print(f"[信息] 目标目录: {TARGET_DIR}")
    return target_path


def find_matching_files(source_dir: str) -> List[Tuple[str, str]]:
    """
    在源目录中查找匹配命名模式的PDF文件
    
    Args:
        source_dir: 源目录路径
        
    Returns:
        List of tuples: (file_path, file_name)
    """
    matching_files = []
    source_path = Path(source_dir)
    
    if not source_path.exists():
        print(f"[警告] 源目录不存在: {source_dir}")
        return matching_files
    
    print(f"\n[搜索] 正在搜索目录: {source_dir}")
    
    # 递归搜索所有PDF文件
    for pdf_file in source_path.rglob("*.pdf"):
        file_name = pdf_file.name
        
        # 检查文件名是否匹配模式（纯DN_No命名）
        if FILE_PATTERN.match(file_name):
            matching_files.append((str(pdf_file), file_name))
            print(f"  [找到] {file_name}")
    
    return matching_files


def copy_file_to_target(source_file: str, target_dir: Path) -> bool:
    """
    复制文件到目标目录（如果已存在则跳过）
    
    Args:
        source_file: 源文件路径
        target_dir: 目标目录路径
        
    Returns:
        True if successful or skipped, False otherwise
    """
    try:
        source_path = Path(source_file)
        file_name = source_path.name
        target_file = target_dir / file_name
        
        # 如果目标文件已存在，直接跳过
        if target_file.exists():
            print(f"  [跳过] 目标文件已存在，跳过: {file_name}")
            return True
        
        # 复制文件
        shutil.copy2(source_path, target_file)
        
        # 验证文件是否成功复制
        if target_file.exists():
            print(f"  [复制成功] {file_name}")
            return True
        else:
            print(f"  [复制失败] {file_name} - 目标文件不存在")
            return False
            
    except Exception as e:
        print(f"  [错误] 复制文件失败 {source_path.name}: {str(e)}")
        return False


def main():
    """主函数"""
    print("=" * 80)
    print("Private Formal PDF 文件提取脚本")
    print("=" * 80)
    
    # 确保目标目录存在
    target_dir = ensure_target_dir()
    
    # 查找所有匹配的文件
    matching_files = find_matching_files(SOURCE_DIR)
    
    if not matching_files:
        print("\n[结果] 未找到匹配的文件")
        return
    
    print(f"\n[统计] 共找到 {len(matching_files)} 个匹配的PDF文件")
    print(f"[目标] 将复制到: {TARGET_DIR}\n")
    
    # 复制文件
    success_count = 0
    fail_count = 0
    
    for source_file, file_name in matching_files:
        if copy_file_to_target(source_file, target_dir):
            success_count += 1
        else:
            fail_count += 1
    
    # 输出结果统计
    print("\n" + "=" * 80)
    print("[完成] 文件提取完成")
    print(f"  成功: {success_count} 个文件")
    print(f"  失败: {fail_count} 个文件")
    print(f"  总计: {len(matching_files)} 个文件")
    print("=" * 80)


if __name__ == "__main__":
    main()

