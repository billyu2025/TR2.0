#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
删除 IAT Formal 文件夹中特定格式的文件

功能：
- 删除格式为 SS数字_日期_月份_年份.pdf 的文件（如 SS74584_30 AUG 2023.pdf）
- 删除格式为 SS数字_ZZ数字_日期_月份_年份.pdf 的文件（如 SS79438_ZZ3855_11_NOV_2025.pdf）
- 删除格式为 SS数字_ZZ数字_日期_月份_年份（UPDATE）.pdf 的文件（如 SS7861_ZZ3172_10_JUI_2025（UPDATE）.pdf）
"""
import sys
import io

# 设置输出编码为 UTF-8（Windows 控制台支持）
if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except AttributeError:
        # Python 2 或旧版本
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr)

import os
import re
from pathlib import Path
from typing import List, Tuple

# 目标目录
TARGET_DIR = r"D:\Stockist&Test Report\IAT Formal"

# 文件格式模式
# 模式1: SS数字_日期_月份_年份.pdf (如 SS74584_30 AUG 2023.pdf)
PATTERN1 = re.compile(
    r'^SS\d+_\d{1,2}\s+[A-Z]{3}\s+\d{4}\.pdf$',
    re.IGNORECASE
)

# 模式2: SS数字_ZZ数字_日期_月份_年份.pdf (如 SS79438_ZZ3855_11_NOV_2025.pdf)
# 注意：日期、月份、年份之间使用下划线分隔
PATTERN2 = re.compile(
    r'^SS\d+_ZZ\d+_\d{1,2}_[A-Z]{3}_\d{4}\.pdf$',
    re.IGNORECASE
)

# 模式3: SS数字_ZZ数字_日期_月份_年份(UPDATE).pdf
# 兼容中英文括号和可选空格：
# - SS7861_ZZ3172_10_JUI_2025（UPDATE）.pdf
# - SS7861_ZZ3172_10_JUI_2025(UPDATE).pdf
# - SS7861_ZZ3172_10_JUI_2025 (UPDATE).pdf
PATTERN3 = re.compile(
    r'^SS\d+_ZZ\d+_\d{1,2}_[A-Z]{3}_\d{4}\s*[（(]UPDATE[）)]\.pdf$',
    re.IGNORECASE
)


def find_matching_files(base_dir: str) -> List[Tuple[str, str]]:
    """
    在目标目录及其子目录中查找匹配的文件
    
    Args:
        base_dir: 基础目录路径
        
    Returns:
        List of tuples: (file_path, file_name)
    """
    matching_files = []
    base_path = Path(base_dir)
    
    if not base_path.exists():
        print(f"[错误] 目录不存在: {base_dir}")
        return matching_files
    
    print(f"[搜索] 正在搜索目录: {base_dir}")
    print(f"[搜索] 匹配模式1: SS数字_日期_月份_年份.pdf")
    print(f"[搜索] 匹配模式2: SS数字_ZZ数字_日期_月份_年份.pdf")
    print(f"[搜索] 匹配模式3: SS数字_ZZ数字_日期_月份_年份(UPDATE).pdf")
    
    # 递归搜索所有子目录
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if not file.lower().endswith('.pdf'):
                continue
            
            # 检查是否匹配模式1、模式2或模式3
            if PATTERN1.match(file) or PATTERN2.match(file) or PATTERN3.match(file):
                file_path = os.path.join(root, file)
                matching_files.append((file_path, file))
                print(f"  [找到] {file}")
    
    return matching_files


def delete_files(files: List[Tuple[str, str]], confirm: bool = True) -> Tuple[int, int]:
    """
    删除匹配的文件
    
    Args:
        files: 文件列表，每个元素为 (file_path, file_name)
        confirm: 是否在删除前确认
        
    Returns:
        (成功删除数, 失败数)
    """
    if not files:
        print("[结果] 没有找到匹配的文件")
        return 0, 0
    
    print(f"\n[统计] 找到 {len(files)} 个匹配的文件")
    
    if confirm:
        print("\n[确认] 即将删除以下文件:")
        for file_path, file_name in files[:10]:  # 只显示前10个
            print(f"  - {file_name}")
        if len(files) > 10:
            print(f"  ... 还有 {len(files) - 10} 个文件")
        
        response = input("\n[确认] 确定要删除这些文件吗？(yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("[取消] 操作已取消")
            return 0, 0
    
    deleted_count = 0
    failed_count = 0
    
    print(f"\n[删除] 开始删除 {len(files)} 个文件...")
    
    for file_path, file_name in files:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                deleted_count += 1
                print(f"  [删除成功] {file_name}")
            else:
                print(f"  [跳过] 文件不存在: {file_name}")
        except Exception as e:
            failed_count += 1
            print(f"  [删除失败] {file_name}: {str(e)}")
    
    return deleted_count, failed_count


def main():
    """主函数"""
    print("=" * 80)
    print("IAT Formal 特定格式文件删除脚本")
    print("=" * 80)
    print(f"[目标目录] {TARGET_DIR}")
    print()
    
    # 查找匹配的文件
    matching_files = find_matching_files(TARGET_DIR)
    
    if not matching_files:
        print("\n[结果] 未找到匹配的文件")
        return
    
    # 统计按模式分类
    pattern1_count = 0
    pattern2_count = 0
    pattern3_count = 0
    
    for file_path, file_name in matching_files:
        if PATTERN3.match(file_name):
            pattern3_count += 1
        elif PATTERN2.match(file_name):
            pattern2_count += 1
        elif PATTERN1.match(file_name):
            pattern1_count += 1
    
    print(f"\n[统计] 文件分类:")
    print(f"  - 模式1 (SS数字_日期_月份_年份.pdf): {pattern1_count} 个")
    print(f"  - 模式2 (SS数字_ZZ数字_日期_月份_年份.pdf): {pattern2_count} 个")
    print(f"  - 模式3 (SS数字_ZZ数字_日期_月份_年份(UPDATE).pdf): {pattern3_count} 个")
    print(f"  - 总计: {len(matching_files)} 个")
    
    # 删除文件
    deleted_count, failed_count = delete_files(matching_files, confirm=True)
    
    # 输出结果
    print("\n" + "=" * 80)
    print("[完成] 删除操作完成")
    print(f"  成功删除: {deleted_count} 个文件")
    print(f"  删除失败: {failed_count} 个文件")
    print(f"  总计: {len(matching_files)} 个文件")
    print("=" * 80)


if __name__ == "__main__":
    import sys
    # 检查是否有 --yes 或 -y 参数，自动确认删除
    auto_confirm = '--yes' in sys.argv or '-y' in sys.argv
    if auto_confirm:
        # 修改 main 函数以支持自动确认
        matching_files = find_matching_files(TARGET_DIR)
        if matching_files:
            pattern1_count = sum(1 for _, f in matching_files if PATTERN1.match(f))
            pattern2_count = sum(1 for _, f in matching_files if PATTERN2.match(f))
            pattern3_count = sum(1 for _, f in matching_files if PATTERN3.match(f))
            print(f"\n[统计] 文件分类:")
            print(f"  - 模式1 (SS数字_日期_月份_年份.pdf): {pattern1_count} 个")
            print(f"  - 模式2 (SS数字_ZZ数字_日期_月份_年份.pdf): {pattern2_count} 个")
            print(f"  - 模式3 (SS数字_ZZ数字_日期_月份_年份(UPDATE).pdf): {pattern3_count} 个")
            print(f"  - 总计: {len(matching_files)} 个")
            deleted_count, failed_count = delete_files(matching_files, confirm=False)
            print("\n" + "=" * 80)
            print("[完成] 删除操作完成")
            print(f"  成功删除: {deleted_count} 个文件")
            print(f"  删除失败: {failed_count} 个文件")
            print(f"  总计: {len(matching_files)} 个文件")
            print("=" * 80)
        else:
            print("\n[结果] 未找到匹配的文件")
    else:
        main()
