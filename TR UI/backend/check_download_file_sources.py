#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查下载文件的来源路径
用于查看 Order 133909 实际下载的文件来自哪里
"""

import os
import sqlite3
import sys

# 添加当前目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from stockist_test_download import StockistTestDownloader

# 数据库路径（TR_Report 表在 data_3years.db 中）
# 从 backend 目录向上两级到项目根目录
_project_root = os.path.normpath(os.path.join(current_dir, '..', '..'))
_default_db_path = os.path.join(_project_root, 'TR database', 'data_3years.db')
DB_PATH = os.getenv('DB_PATH', _default_db_path)
# 确保路径是绝对路径
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.abspath(os.path.join(_project_root, DB_PATH))

# 基础文件夹路径
BASE_FOLDER = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')

def check_order_files(order_no: int):
    """检查订单的文件来源"""
    print("=" * 80)
    print(f"检查 Order {order_no} 的文件来源")
    print("=" * 80)
    print(f"数据库路径: {DB_PATH}")
    print(f"数据库是否存在: {os.path.exists(DB_PATH)}")
    print(f"基础文件夹: {BASE_FOLDER}")
    print(f"基础文件夹是否存在: {os.path.exists(BASE_FOLDER)}")
    print()
    
    # 检查数据库是否存在
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库文件不存在: {DB_PATH}")
        print(f"   请检查数据库路径是否正确")
        return
    
    # 创建下载器
    downloader = StockistTestDownloader(DB_PATH, BASE_FOLDER)
    
    # 1. 获取订单信息
    print("[步骤 1] 获取订单信息...")
    order_info = downloader.get_order_info(order_no)
    if not order_info:
        print(f"❌ Order {order_no} 在 TR_Report 表中不存在")
        return
    
    print(f"  stockist_cert: {order_info.get('stockist_cert', 'N/A')}")
    print(f"  rm_dn_no: {order_info.get('rm_dn_no', 'N/A')}")
    print(f"  jobsite_type: {order_info.get('jobsite_type', 'N/A')}")
    print()
    
    # 2. 获取所有关键词
    print("[步骤 2] 获取所有 stockist_cert 和 rm_dn_no...")
    stockist_certs, rm_dn_nos = downloader.get_all_cert_dn_values(order_no)
    all_keywords = stockist_certs + rm_dn_nos
    all_keywords = [k for k in all_keywords if k]
    print(f"  关键词列表: {all_keywords}")
    print()
    
    # 3. 检查 IAT Formal 文件夹
    print("[步骤 3] 检查 IAT Formal 文件夹...")
    iat_formal_folder = downloader.iat_formal_folder
    print(f"  IAT Formal 路径: {iat_formal_folder}")
    
    if not os.path.exists(iat_formal_folder):
        print(f"  ❌ IAT Formal 文件夹不存在")
        return
    
    # 查找匹配的子文件夹
    print(f"  查找包含关键词的子文件夹...")
    matching_subfolders = []
    try:
        items = os.listdir(iat_formal_folder)
        for item in items:
            item_path = os.path.join(iat_formal_folder, item)
            if os.path.isdir(item_path):
                item_lower = item.lower()
                for keyword in all_keywords:
                    keyword_lower = keyword.lower() if keyword else ''
                    if keyword and keyword_lower in item_lower:
                        matching_subfolders.append(item_path)
                        print(f"    ✅ 找到匹配的子文件夹: {item} (包含关键词: {keyword})")
                        break
    except Exception as e:
        print(f"  ❌ 读取文件夹失败: {e}")
        return
    
    if not matching_subfolders:
        print(f"  ⚠️  未找到匹配的子文件夹")
        return
    
    print()
    
    # 4. 列出每个匹配文件夹中的所有 PDF 文件
    print("[步骤 4] 列出每个匹配文件夹中的所有 PDF 文件...")
    all_files = []
    for subfolder in matching_subfolders:
        print(f"\n  子文件夹: {os.path.basename(subfolder)}")
        print(f"  完整路径: {subfolder}")
        
        pdf_files = []
        try:
            for root, dirs, files in os.walk(subfolder):
                for file in files:
                    if file.lower().endswith('.pdf'):
                        file_path = os.path.join(root, file)
                        pdf_files.append(file_path)
                        all_files.append(file_path)
            
            print(f"  找到 {len(pdf_files)} 个 PDF 文件:")
            for i, file_path in enumerate(pdf_files, 1):
                file_name = os.path.basename(file_path)
                rel_path = os.path.relpath(file_path, BASE_FOLDER)
                print(f"    {i}. {file_name}")
                print(f"       路径: {file_path}")
                print(f"       相对路径: {rel_path}")
        except Exception as e:
            print(f"  ❌ 遍历文件夹失败: {e}")
    
    print()
    print("=" * 80)
    print(f"总结: 共找到 {len(all_files)} 个 PDF 文件")
    print("=" * 80)
    
    # 5. 检查索引中的信息
    if downloader.index_query and downloader.index_query.is_index_available():
        print("\n[步骤 5] 检查文件索引中的信息...")
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            for file_path in all_files[:5]:  # 只检查前5个文件
                file_name = os.path.basename(file_path)
                cursor.execute("""
                    SELECT file_path, file_name, folder_path, folder_type, identifiers
                    FROM file_index_cache
                    WHERE file_path = ? AND is_deleted = 0
                """, (file_path,))
                row = cursor.fetchone()
                if row:
                    print(f"  ✅ {file_name}")
                    print(f"     索引中的路径: {row['file_path']}")
                    print(f"     文件夹类型: {row['folder_type']}")
                    print(f"     标识符: {row.get('identifiers', 'N/A')}")
                else:
                    print(f"  ⚠️  {file_name} 不在索引中")
            
            conn.close()
        except Exception as e:
            print(f"  ❌ 查询索引失败: {e}")


if __name__ == "__main__":
    # 检查 Order 133909
    order_no = 133909
    if len(sys.argv) > 1:
        try:
            order_no = int(sys.argv[1])
        except ValueError:
            print(f"错误: 无效的订单号: {sys.argv[1]}")
            sys.exit(1)
    
    check_order_files(order_no)
