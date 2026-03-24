#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试文件索引查询功能
用于诊断 Order 134617 找不到文件的问题
"""

import os
import sys

# 设置输出编码为 UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from db_adapter import get_connection, is_postgres
from file_index_query import FileIndexQuery

def test_basic_query():
    """测试基本查询功能"""
    print("=" * 80)
    print("测试 1: 基本查询功能")
    print("=" * 80)
    
    try:
        fq = FileIndexQuery('')
        print(f"✓ FileIndexQuery 初始化成功")
        print(f"✓ is_postgres: {is_postgres()}")
        print(f"✓ _bool_value(False): {fq._bool_value(False)}")
        print(f"✓ is_index_available: {fq.is_index_available()}")
    except Exception as e:
        print(f"✗ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def test_index_stats():
    """测试索引统计信息"""
    print("\n" + "=" * 80)
    print("测试 2: 索引统计信息")
    print("=" * 80)
    
    try:
        fq = FileIndexQuery('')
        stats = fq.get_index_stats()
        print(f"✓ 索引可用: {stats.get('available', False)}")
        print(f"✓ 总文件数: {stats.get('total_files', 0)}")
        print(f"✓ 文件夹统计: {stats.get('folder_stats', {})}")
        if 'error' in stats:
            print(f"✗ 错误: {stats['error']}")
    except Exception as e:
        print(f"✗ 获取统计信息失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def test_single_keyword(keyword, folder_type=None):
    """测试单个关键词查询"""
    print(f"\n" + "=" * 80)
    print(f"测试 3: 查询关键词 '{keyword}' (folder_type: {folder_type})")
    print("=" * 80)
    
    try:
        fq = FileIndexQuery('')
        folder_types = [folder_type] if folder_type else None
        
        # 先测试直接 SQL 查询
        print(f"\n--- 直接 SQL 查询测试 ---")
        conn = fq._get_connection()
        cursor = conn.cursor()
        
        if is_postgres():
            test_query = """
                SELECT file_path, file_name, identifiers
                FROM file_index_cache
                WHERE (identifiers LIKE %s OR file_name LIKE %s)
                  AND folder_type = %s
                  AND is_deleted = FALSE
                LIMIT 5
            """
            cursor.execute(test_query, (f'%{keyword}%', f'%{keyword}%', folder_type))
        else:
            test_query = """
                SELECT file_path, file_name, identifiers
                FROM file_index_cache
                WHERE (identifiers LIKE ? OR file_name LIKE ?)
                  AND folder_type = ?
                  AND is_deleted = 0
                LIMIT 5
            """
            cursor.execute(test_query, (f'%{keyword}%', f'%{keyword}%', folder_type))
        
        direct_rows = cursor.fetchall()
        print(f"直接 SQL 查询找到 {len(direct_rows)} 条记录")
        for row in direct_rows[:3]:
            file_name = row.get('file_name', 'N/A') if hasattr(row, 'get') else row[1]
            print(f"  - {file_name}")
        conn.close()
        
        # 再测试 FileIndexQuery
        print(f"\n--- FileIndexQuery 查询测试 ---")
        results = fq.find_files_by_keywords([keyword], folder_types=folder_types, verify_files=False)
        print(f"✓ 找到 {len(results)} 个文件")
        if results:
            print("前 5 个文件:")
            for i, file_path in enumerate(results[:5], 1):
                file_name = os.path.basename(file_path)
                print(f"  {i}. {file_name}")
                print(f"     路径: {file_path}")
        else:
            print("✗ 未找到文件")
        return results
    except Exception as e:
        print(f"✗ 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return []

def test_order_134617_keywords():
    """测试 Order 134617 的关键词"""
    print("\n" + "=" * 80)
    print("测试 4: Order 134617 的关键词查询")
    print("=" * 80)
    
    keywords = ['ZZ4140', 'KL2951', 'ZZ3782', 'ZZ4272', 'ZZ3838', 'ZZ4264', 'KL2955', 'HL2322',
                'SS79340', 'SS79409', 'SS79365', 'SS79916', 'SS79908', 'SS79778', 'SS79634', 'SS79630']
    
    print(f"关键词列表: {keywords}")
    print(f"关键词数量: {len(keywords)}")
    
    # 测试 Stockist Cert 文件夹
    print("\n--- 测试 Stockist Cert 文件夹 ---")
    try:
        fq = FileIndexQuery('')
        results = fq.find_files_by_keywords(keywords, folder_types=['Stockist Cert'], verify_files=False)
        print(f"✓ 找到 {len(results)} 个文件")
        if results:
            print("前 10 个文件:")
            for i, file_path in enumerate(results[:10], 1):
                file_name = os.path.basename(file_path)
                print(f"  {i}. {file_name}")
        else:
            print("✗ 未找到文件")
            # 尝试单个关键词查询
            print("\n尝试单个关键词查询:")
            for keyword in ['KL2951', 'SS79630', 'HL2322']:
                single_results = fq.find_files_by_keywords([keyword], folder_types=['Stockist Cert'], verify_files=False)
                print(f"  {keyword}: {len(single_results)} 个文件")
                if single_results:
                    for file_path in single_results[:3]:
                        print(f"    - {os.path.basename(file_path)}")
    except Exception as e:
        print(f"✗ 查询失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试 IAT Formal 文件夹
    print("\n--- 测试 IAT Formal 文件夹 ---")
    try:
        fq = FileIndexQuery('')
        results = fq.find_files_by_keywords(keywords, folder_types=['IAT Formal'], verify_files=False)
        print(f"✓ 找到 {len(results)} 个文件")
        if results:
            print("前 10 个文件:")
            for i, file_path in enumerate(results[:10], 1):
                file_name = os.path.basename(file_path)
                print(f"  {i}. {file_name}")
    except Exception as e:
        print(f"✗ 查询失败: {e}")
        import traceback
        traceback.print_exc()

def test_direct_sql_query():
    """直接使用 SQL 查询测试"""
    print("\n" + "=" * 80)
    print("测试 5: 直接 SQL 查询")
    print("=" * 80)
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # 测试查询 KL2951
        if is_postgres():
            query = """
                SELECT file_name, identifiers, folder_type, file_path
                FROM file_index_cache
                WHERE (identifiers LIKE %s OR file_name LIKE %s)
                  AND folder_type = %s
                  AND is_deleted = FALSE
                LIMIT 10
            """
            cursor.execute(query, ('%KL2951%', '%KL2951%', 'Stockist Cert'))
        else:
            query = """
                SELECT file_name, identifiers, folder_type, file_path
                FROM file_index_cache
                WHERE (identifiers LIKE ? OR file_name LIKE ?)
                  AND folder_type = ?
                  AND is_deleted = 0
                LIMIT 10
            """
            cursor.execute(query, ('%KL2951%', '%KL2951%', 'Stockist Cert'))
        
        rows = cursor.fetchall()
        print(f"✓ 找到 {len(rows)} 条记录")
        for i, row in enumerate(rows[:5], 1):
            file_name = row.get('file_name', 'N/A') if hasattr(row, 'get') else row[0]
            identifiers = row.get('identifiers', 'N/A') if hasattr(row, 'get') else row[1]
            folder_type = row.get('folder_type', 'N/A') if hasattr(row, 'get') else row[2]
            print(f"  {i}. {file_name}")
            print(f"     identifiers: {identifiers}")
            print(f"     folder_type: {folder_type}")
        
        conn.close()
    except Exception as e:
        print(f"✗ SQL 查询失败: {e}")
        import traceback
        traceback.print_exc()

def test_keyword_in_identifiers():
    """测试 identifiers 字段中的关键词"""
    print("\n" + "=" * 80)
    print("测试 6: 检查 identifiers 字段")
    print("=" * 80)
    
    keywords = ['KL2951', 'SS79630', 'HL2322']
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        for keyword in keywords:
            if is_postgres():
                query = """
                    SELECT file_name, identifiers, folder_type
                    FROM file_index_cache
                    WHERE identifiers LIKE %s
                      AND is_deleted = FALSE
                    LIMIT 5
                """
                cursor.execute(query, (f'%{keyword}%',))
            else:
                query = """
                    SELECT file_name, identifiers, folder_type
                    FROM file_index_cache
                    WHERE identifiers LIKE ?
                      AND is_deleted = 0
                    LIMIT 5
                """
                cursor.execute(query, (f'%{keyword}%',))
            
            rows = cursor.fetchall()
            print(f"\n关键词 '{keyword}': 找到 {len(rows)} 条记录")
            for row in rows:
                file_name = row.get('file_name', 'N/A') if hasattr(row, 'get') else row[0]
                identifiers = row.get('identifiers', 'N/A') if hasattr(row, 'get') else row[1]
                folder_type = row.get('folder_type', 'N/A') if hasattr(row, 'get') else row[2]
                print(f"  - {file_name} (identifiers: {identifiers}, folder_type: {folder_type})")
        
        conn.close()
    except Exception as e:
        print(f"✗ 查询失败: {e}")
        import traceback
        traceback.print_exc()

def main():
    """主测试函数"""
    print("\n" + "=" * 80)
    print("文件索引查询测试脚本")
    print("=" * 80)
    print(f"数据库类型: {'PostgreSQL' if is_postgres() else 'SQLite'}")
    print(f"当前时间: {os.popen('date /t').read().strip() if sys.platform == 'win32' else ''}")
    
    # 运行所有测试
    if not test_basic_query():
        print("\n✗ 基本查询测试失败，停止后续测试")
        return
    
    if not test_index_stats():
        print("\n✗ 索引统计测试失败")
    
    # 测试单个关键词
    test_single_keyword('KL2951', 'Stockist Cert')
    test_single_keyword('SS79630', 'Stockist Cert')
    
    # 测试 Order 134617
    test_order_134617_keywords()
    
    # 直接 SQL 查询
    test_direct_sql_query()
    
    # 测试 identifiers 字段
    test_keyword_in_identifiers()
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)

if __name__ == "__main__":
    main()
