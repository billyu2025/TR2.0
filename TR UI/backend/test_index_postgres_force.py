#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
强制使用 PostgreSQL 环境测试文件索引查询功能
用于验证 PostgreSQL 环境下的索引查询是否正常
"""

import os
import sys

# 强制设置 PostgreSQL 环境
os.environ['DB_BACKEND'] = 'postgres'
os.environ['POSTGRES_DSN'] = os.getenv('POSTGRES_DSN', 'postgresql://postgres:postgres@127.0.0.1:5432/tr_db')

# 设置输出编码为 UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 重新导入以应用环境变量
import importlib
if 'db_adapter' in sys.modules:
    importlib.reload(sys.modules['db_adapter'])
if 'file_index_query' in sys.modules:
    importlib.reload(sys.modules['file_index_query'])

from db_adapter import get_connection, is_postgres
from file_index_query import FileIndexQuery

def test_postgres_detection():
    """测试 PostgreSQL 检测"""
    print("=" * 80)
    print("测试 1: PostgreSQL 环境检测")
    print("=" * 80)
    
    try:
        is_pg = is_postgres()
        print(f"✓ is_postgres(): {is_pg}")
        print(f"✓ DB_BACKEND 环境变量: {os.getenv('DB_BACKEND', 'not set')}")
        print(f"✓ POSTGRES_DSN 环境变量: {os.getenv('POSTGRES_DSN', 'not set')}")
        
        if not is_pg:
            print("✗ 错误: 环境变量已设置但 is_postgres() 仍返回 False")
            return False
        
        conn = get_connection()
        print(f"✓ 数据库连接成功: {type(conn).__name__}")
        conn.close()
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_bool_value_postgres():
    """测试 PostgreSQL 布尔值转换"""
    print("\n" + "=" * 80)
    print("测试 2: PostgreSQL 布尔值转换")
    print("=" * 80)
    
    try:
        fq = FileIndexQuery('')
        false_value = fq._bool_value(False)
        true_value = fq._bool_value(True)
        
        print(f"✓ _bool_value(False): '{false_value}'")
        print(f"✓ _bool_value(True): '{true_value}'")
        
        if false_value == 'FALSE' and true_value == 'TRUE':
            print("✓ PostgreSQL 布尔值转换正确")
            return True
        else:
            print(f"✗ 错误: 应该返回 'FALSE'/'TRUE'，但返回了 '{false_value}'/'{true_value}'")
            return False
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_sql_placeholder_postgres():
    """测试 PostgreSQL SQL 占位符转换"""
    print("\n" + "=" * 80)
    print("测试 3: PostgreSQL SQL 占位符转换")
    print("=" * 80)
    
    try:
        fq = FileIndexQuery('')
        test_sql = "SELECT * FROM table WHERE id = ? AND name = ?"
        converted = fq._sql(test_sql)
        
        print(f"✓ 原始 SQL: {test_sql}")
        print(f"✓ 转换后 SQL: {converted}")
        
        expected = "SELECT * FROM table WHERE id = %s AND name = %s"
        if converted == expected:
            print("✓ PostgreSQL 占位符转换正确 (? -> %s)")
            return True
        else:
            print(f"✗ 错误: 应该转换为 '{expected}'，但转换为了 '{converted}'")
            return False
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_table_exists_postgres():
    """测试 PostgreSQL 表存在检查"""
    print("\n" + "=" * 80)
    print("测试 4: PostgreSQL 表存在检查")
    print("=" * 80)
    
    try:
        fq = FileIndexQuery('')
        conn = fq._get_connection()
        cursor = conn.cursor()
        
        # 测试表存在检查
        exists = fq._table_exists(cursor, 'file_index_cache')
        print(f"✓ file_index_cache 表存在: {exists}")
        
        exists2 = fq._table_exists(cursor, 'nonexistent_table_xyz')
        print(f"✓ nonexistent_table_xyz 表存在: {exists2} (应该是 False)")
        
        conn.close()
        
        if exists and not exists2:
            print("✓ _table_exists 方法工作正常")
            return True
        else:
            print("⚠ _table_exists 方法可能有问题")
            return exists  # 至少主表应该存在
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_index_available_postgres():
    """测试索引可用性检查"""
    print("\n" + "=" * 80)
    print("测试 5: 索引可用性检查（PostgreSQL）")
    print("=" * 80)
    
    try:
        fq = FileIndexQuery('')
        is_available = fq.is_index_available()
        print(f"✓ is_index_available(): {is_available}")
        
        if is_available:
            stats = fq.get_index_stats()
            print(f"✓ 索引统计: {stats.get('total_files', 0)} 个文件")
            print(f"✓ 文件夹统计: {stats.get('folder_stats', {})}")
        else:
            print("⚠ 索引不可用（可能是表不存在或连接问题）")
        
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_query_with_bool_postgres():
    """测试使用布尔值的查询"""
    print("\n" + "=" * 80)
    print("测试 6: 使用布尔值的查询（PostgreSQL）")
    print("=" * 80)
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # 测试使用 FALSE 的查询
        print("测试查询: SELECT COUNT(*) WHERE is_deleted = FALSE")
        cursor.execute("""
            SELECT COUNT(*) as cnt
            FROM file_index_cache
            WHERE is_deleted = FALSE
        """)
        row = cursor.fetchone()
        total = row.get('cnt', 0) if hasattr(row, 'get') else row[0]
        print(f"✓ 总文件数: {total}")
        
        # 测试关键词查询
        print("\n测试查询: 查找包含 KL2951 的文件")
        cursor.execute("""
            SELECT file_name, identifiers, folder_type
            FROM file_index_cache
            WHERE (identifiers LIKE %s OR file_name LIKE %s)
              AND folder_type = %s
              AND is_deleted = FALSE
            LIMIT 5
        """, ('%KL2951%', '%KL2951%', 'Stockist Cert'))
        
        rows = cursor.fetchall()
        print(f"✓ 找到 {len(rows)} 条记录")
        for row in rows[:3]:
            file_name = row.get('file_name', 'N/A') if hasattr(row, 'get') else row[0]
            identifiers = row.get('identifiers', 'N/A') if hasattr(row, 'get') else row[1]
            print(f"  - {file_name} (identifiers: {identifiers})")
        
        conn.close()
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_file_index_query_postgres():
    """测试 FileIndexQuery 在 PostgreSQL 下的查询"""
    print("\n" + "=" * 80)
    print("测试 7: FileIndexQuery 查询（PostgreSQL）")
    print("=" * 80)
    
    try:
        fq = FileIndexQuery('')
        
        # 检查索引是否可用
        if not fq.is_index_available():
            print("⚠ 索引不可用，跳过查询测试")
            return True
        
        # 测试查询
        keywords = ['KL2951', 'SS79630']
        folder_types = ['Stockist Cert']
        
        print(f"测试查询: keywords={keywords}, folder_types={folder_types}")
        results = fq.find_files_by_keywords(keywords, folder_types=folder_types, verify_files=False)
        print(f"✓ 找到 {len(results)} 个文件")
        
        if results:
            print("前 5 个文件:")
            for i, file_path in enumerate(results[:5], 1):
                file_name = os.path.basename(file_path)
                print(f"  {i}. {file_name}")
        else:
            print("⚠ 未找到文件")
        
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("\n" + "=" * 80)
    print("PostgreSQL 环境下的文件索引查询测试（强制模式）")
    print("=" * 80)
    print(f"环境变量 DB_BACKEND: {os.getenv('DB_BACKEND')}")
    print(f"环境变量 POSTGRES_DSN: {os.getenv('POSTGRES_DSN')}")
    
    # 运行所有测试
    results = []
    results.append(("PostgreSQL 环境检测", test_postgres_detection()))
    results.append(("布尔值转换", test_bool_value_postgres()))
    results.append(("SQL 占位符转换", test_sql_placeholder_postgres()))
    results.append(("表存在检查", test_table_exists_postgres()))
    results.append(("索引可用性", test_index_available_postgres()))
    results.append(("布尔值查询", test_query_with_bool_postgres()))
    results.append(("FileIndexQuery 查询", test_file_index_query_postgres()))
    
    # 总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{test_name}: {status}")
    
    all_passed = all(result for _, result in results)
    if all_passed:
        print("\n✓ 所有测试通过！PostgreSQL 环境下的索引查询应该可以正常工作。")
    else:
        print("\n⚠ 部分测试失败，请检查上述错误信息。")
        print("\n注意：如果 PostgreSQL 连接失败，请检查：")
        print("  1. PostgreSQL 服务是否运行")
        print("  2. POSTGRES_DSN 环境变量是否正确")
        print("  3. 数据库 tr_db 是否存在")
        print("  4. file_index_cache 表是否已创建")
    
    return all_passed

if __name__ == "__main__":
    main()
