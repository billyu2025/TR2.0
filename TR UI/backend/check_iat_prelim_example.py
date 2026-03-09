#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
示例：在提取文件前检查 IAT Prelim 文件夹中是否已存在对应文件

使用方法：
1. 在 Ext_Testreport_IATPrelim.py 中导入此函数
2. 在复制文件前调用 check_before_copy 检查是否已存在
3. 如果已存在，跳过复制，直接使用现有文件
"""

import os
import sys

# 添加 backend 目录到路径
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

from file_index_query import FileIndexQuery

# 数据库路径（根据实际情况修改）
# 如果使用默认路径，可以从环境变量或配置文件读取
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.normpath(os.path.join(_current_dir, '..', '..'))
_default_db_path = os.path.join(_project_root, 'TR database', 'data_3years.db')
DB_PATH = os.getenv('DB_PATH', _default_db_path)

# 如果环境变量是相对路径，转换为绝对路径
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.abspath(os.path.join(_project_root, DB_PATH))


def check_before_copy(source_file_path: str, base_folder: str = r"D:\Stockist&Test Report") -> tuple:
    """
    在复制文件前，检查 IAT Prelim 文件夹中是否已存在对应文件
    
    例如："Physical, chemical & geometry test report of C0146.pdf" 
    和 "C0146_IAT_Prelim.pdf" 是同一个文件
    
    Args:
        source_file_path: 源文件路径（例如："Physical, chemical & geometry test report of C0146.pdf"）
        base_folder: Stockist&Test Report 基础文件夹路径
        
    Returns:
        (exists: bool, existing_file_path: str or None)
        如果找到对应文件，返回 (True, 文件路径)
        否则返回 (False, None)
    """
    # 创建文件索引查询器
    index_query = FileIndexQuery(DB_PATH)
    
    # 获取源文件名
    source_filename = os.path.basename(source_file_path)
    
    # 检查 IAT Prelim 文件夹中是否已存在对应文件
    existing_file = index_query.check_file_exists_in_iat_prelim(source_filename, base_folder)
    
    if existing_file:
        print(f"[检查] 找到对应文件: {existing_file}")
        print(f"[检查] 源文件: {source_file_path}")
        print(f"[检查] 无需复制，使用现有文件")
        return True, existing_file
    else:
        print(f"[检查] 未找到对应文件，需要复制: {source_file_path}")
        return False, None


# 使用示例
if __name__ == '__main__':
    # 示例1：检查 "Physical, chemical & geometry test report of C0146.pdf"
    source_file = r"C:\TR-master\Ext_Testreport_IATPrelim\Physical, chemical & geometry test report of C0146.pdf"
    
    exists, existing_path = check_before_copy(source_file)
    
    if exists:
        print(f"使用现有文件: {existing_path}")
        # 不需要复制，直接使用 existing_path
    else:
        print(f"需要复制文件: {source_file}")
        # 执行复制操作
        # import shutil
        # target_path = os.path.join(r"D:\Stockist&Test Report\IAT Prelim", os.path.basename(source_file))
        # shutil.copy2(source_file, target_path)
