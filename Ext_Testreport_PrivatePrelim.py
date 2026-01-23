#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extract Private Prelim test report files from source directory
抽取Private Prelim测试报告文件脚本

功能：
- 从源目录中查找以DN_No命名的文件夹（如SS77820）
- 在这些文件夹下的 Test report/Private test report 中查找对应的测试报告文件
- 复制文件到目标目录
- 如果目标文件已存在则覆盖
- 不删除源文件
"""

import os
import shutil
import re
from pathlib import Path
from typing import List, Tuple


# 源目录列表
SOURCE_DIRS = [
    r"\\192.168.32.212\TVSC-Internal\Dp-Supply Chain\Inventory\04 Rebar PO DN\Rebar DN",
    r"\\192.168.32.212\TVSC-Internal\Dp-Supply Chain\Inventory\04 Rebar PO DN\Rebar DN\00 - Passed record"
]

# 目标目录
TARGET_DIR = r"D:\Stockist&Test Report\Private Prelim"

# 文件夹命名模式：DN_No命名
# 例如：SS77820
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


def find_test_report_files(source_dir: str) -> List[Tuple[str, str, str]]:
    """
    在源目录中查找测试报告文件
    
    Args:
        source_dir: 源目录路径
        
    Returns:
        List of tuples: (file_path, file_name, dn_no)
    """
    matching_files = []
    source_path = Path(source_dir)
    
    if not source_path.exists():
        print(f"[警告] 源目录不存在: {source_dir}")
        return matching_files
    
    print(f"\n[搜索] 正在搜索目录: {source_dir}")
    
    # 搜索源目录下的所有直接子文件夹
    for item in source_path.iterdir():
        if item.is_dir():
            folder_name = item.name
            
            # 检查文件夹名是否匹配DN_No模式（如SS77820）
            if FOLDER_PATTERN.match(folder_name):
                dn_no = folder_name
                
                # 构建测试报告文件路径
                # Test report/Private test report/Physical, chemical & geometry test report of {DN_No}.*
                test_report_dir = item / "Test report" / "Private test report"
                
                if test_report_dir.exists():
                    # 查找以 "Physical, chemical & geometry test report of {DN_No}" 开头的文件
                    pattern_prefix = f"Physical, chemical & geometry test report of {dn_no}"
                    
                    for file in test_report_dir.iterdir():
                        if file.is_file() and file.name.startswith(pattern_prefix):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                else:
                    print(f"  [跳过] {dn_no}/ - Test report/Private test report 目录不存在")
    
    return matching_files


def copy_file_to_target(source_file: str, target_dir: Path, file_name: str) -> bool:
    """
    复制文件到目标目录（如果已存在则跳过）
    
    Args:
        source_file: 源文件路径
        target_dir: 目标目录路径
        file_name: 文件名
        
    Returns:
        True if successful or skipped, False otherwise
    """
    try:
        source_path = Path(source_file)
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
        print(f"  [错误] 复制文件失败 {file_name}: {str(e)}")
        return False


def main():
    """主函数"""
    print("=" * 80)
    print("Private Prelim 测试报告文件提取脚本")
    print("=" * 80)
    
    # 确保目标目录存在
    target_dir = ensure_target_dir()
    
    # 查找所有匹配的测试报告文件（从所有源目录）
    matching_files = []
    for source_dir in SOURCE_DIRS:
        files = find_test_report_files(source_dir)
        matching_files.extend(files)
    
    if not matching_files:
        print("\n[结果] 未找到匹配的测试报告文件")
        return
    
    print(f"\n[统计] 共找到 {len(matching_files)} 个测试报告文件")
    print(f"[目标] 将复制到: {TARGET_DIR}\n")
    
    # 复制文件
    success_count = 0
    fail_count = 0
    
    for source_file, file_name, dn_no in matching_files:
        if copy_file_to_target(source_file, target_dir, file_name):
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

