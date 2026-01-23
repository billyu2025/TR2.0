#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extract IAT Formal folders from source directory
抽取IAT Formal文件夹脚本

功能：
- 从源目录中查找匹配命名模式的文件夹（纯Stockist No格式，如ZZ3274）
- 复制整个文件夹及其内容到目标目录
- 如果目标文件夹已存在则覆盖
- 不删除源文件夹
"""

import os
import shutil
import re
from pathlib import Path
from typing import List, Tuple


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


def copy_folder_to_target(source_folder: str, target_dir: Path) -> bool:
    """
    复制文件夹到目标目录（如果已存在则覆盖）
    
    Args:
        source_folder: 源文件夹路径
        target_dir: 目标目录路径
        
    Returns:
        True if successful, False otherwise
    """
    try:
        source_path = Path(source_folder)
        folder_name = source_path.name
        target_folder = target_dir / folder_name
        
        # 如果目标文件夹已存在，先删除它（以实现覆盖）
        if target_folder.exists():
            print(f"  [覆盖] 目标文件夹已存在，正在删除: {folder_name}/")
            shutil.rmtree(target_folder)
        
        # 复制整个文件夹及其内容
        shutil.copytree(source_path, target_folder)
        
        # 验证文件夹是否成功复制
        if target_folder.exists():
            # 统计文件夹中的文件数量
            file_count = sum(1 for _ in target_folder.rglob('*') if _.is_file())
            print(f"  [复制成功] {folder_name}/ (包含 {file_count} 个文件)")
            return True
        else:
            print(f"  [复制失败] {folder_name}/ - 目标文件夹不存在")
            return False
            
    except Exception as e:
        print(f"  [错误] 复制文件夹失败 {source_path.name}/: {str(e)}")
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
    
    for source_folder, folder_name in matching_folders:
        if copy_folder_to_target(source_folder, target_dir):
            success_count += 1
        else:
            fail_count += 1
    
    # 输出结果统计
    print("\n" + "=" * 80)
    print("[完成] 文件夹提取完成")
    print(f"  成功: {success_count} 个文件夹")
    print(f"  失败: {fail_count} 个文件夹")
    print(f"  总计: {len(matching_folders)} 个文件夹")
    print("=" * 80)


if __name__ == "__main__":
    main()

