#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 PostgreSQL 环境下的文件索引查询功能
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

def test_postgres_connection():
    """测试 PostgreSQL 连接"""
    print("=" * 80)
    print("测试 1: PostgreSQL 连接和基本检查")
    print("=" * 80)
    
    try:
        is_pg = is_postgres()
        print(f"✓ is_postgres(): {is_pg}")
        
        if not is_pg:
            print("⚠ 警告: 当前环境不是 PostgreSQL，将无法测试 PostgreSQL 特定功能")
            return False
        
        conn = get_connection()
        cursor = conn.cursor()
        print(f"✓ 数据库连接成功: {type(conn).__name__}")
        
        # 检查表是否存在
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'file_index_cache'
            ) AS exists
        """)
        row = cursor.fetchone()
        table_exists = row.get('exists', False) if hasattr(row, 'get') else row[0]
        print(f"✓ file_index_cache 表存在: {table_exists}")
        
        if table_exists:
            # 检查表结构
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'file_index_cache'
                ORDER BY ordinal_position
            """)
            columns = cursor.fetchall()
            print(f"✓ 表结构 ({len(columns)} 列):")
            for col in columns:
                col_name = col.get('column_name', 'N/A') if hasattr(col, 'get') else col[0]
                col_type = col.get('data_type', 'N/A') if hasattr(col, 'get') else col[1]
                print(f"    - {col_name}: {col_type}")
            
            # 检查 is_deleted 字段类型
            cursor.execute("""
                SELECT data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' 
                  AND table_name = 'file_index_cache'
                  AND column_name = 'is_deleted'
            """)
            row = cursor.fetchone()
            if row:
                deleted_type = row.get('data_type', 'N/A') if hasattr(row, 'get') else row[0]
                print(f"✓ is_deleted 字段类型: {deleted_type}")
                if deleted_type != 'boolean':
                    print(f"⚠ 警告: is_deleted 应该是 boolean 类型，但实际是 {deleted_type}")
        
        conn.close()
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_bool_value_conversion():
    """测试布尔值转换"""
    print("\n" + "=" * 80)
    print("测试 2: 布尔值转换 (_bool_value)")
    print("=" * 80)
    
    try:
        fq = FileIndexQuery('')
        is_pg = is_postgres()
        print(f"✓ is_postgres(): {is_pg}")
        
        false_value = fq._bool_value(False)
        true_value = fq._bool_value(True)
        
        print(f"✓ _bool_value(False): '{false_value}'")
        print(f"✓ _bool_value(True): '{true_value}'")
        
        if is_pg:
            if false_value == 'FALSE' and true_value == 'TRUE':
                print("✓ PostgreSQL 布尔值转换正确")
            else:
                print(f"✗ 错误: PostgreSQL 应该返回 'FALSE'/'TRUE'，但返回了 '{false_value}'/'{true_value}'")
                return False
        else:
            if false_value == '0' and true_value == '1':
                print("✓ SQLite 布尔值转换正确")
            else:
                print(f"✗ 错误: SQLite 应该返回 '0'/'1'，但返回了 '{false_value}'/'{true_value}'")
                return False
        
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_sql_placeholder_conversion():
    """测试 SQL 占位符转换"""
    print("\n" + "=" * 80)
    print("测试 3: SQL 占位符转换 (_sql)")
    print("=" * 80)
    
    try:
        fq = FileIndexQuery('')
        is_pg = is_postgres()
        
        test_sql = "SELECT * FROM table WHERE id = ? AND name = ?"
        converted = fq._sql(test_sql)
        
        print(f"✓ 原始 SQL: {test_sql}")
        print(f"✓ 转换后 SQL: {converted}")
        
        if is_pg:
            if converted == "SELECT * FROM table WHERE id = %s AND name = %s":
                print("✓ PostgreSQL 占位符转换正确 (? -> %s)")
            else:
                print(f"✗ 错误: PostgreSQL 应该将 ? 转换为 %s")
                return False
        else:
            if converted == test_sql:
                print("✓ SQLite 占位符保持不变")
            else:
                print(f"✗ 错误: SQLite 不应该转换占位符")
                return False
        
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_index_query_postgres():
    """测试 PostgreSQL 环境下的索引查询"""
    print("\n" + "=" * 80)
    print("测试 4: PostgreSQL 索引查询")
    print("=" * 80)
    
    try:
        fq = FileIndexQuery('')
        is_pg = is_postgres()
        
        if not is_pg:
            print("⚠ 跳过: 当前环境不是 PostgreSQL")
            return True
        
        # 检查索引是否可用
        is_available = fq.is_index_available()
        print(f"✓ is_index_available(): {is_available}")
        
        if not is_available:
            print("⚠ 警告: 索引不可用，无法进行查询测试")
            return False
        
        # 获取统计信息
        stats = fq.get_index_stats()
        print(f"✓ 索引统计: {stats.get('total_files', 0)} 个文件")
        print(f"✓ 文件夹统计: {stats.get('folder_stats', {})}")
        
        # 测试查询
        keywords = ['KL2951', 'SS79630']
        folder_types = ['Stockist Cert']
        
        print(f"\n测试查询: keywords={keywords}, folder_types={folder_types}")
        results = fq.find_files_by_keywords(keywords, folder_types=folder_types, verify_files=False)
        print(f"✓ 找到 {len(results)} 个文件")
        
        if results:
            print("前 5 个文件:")
            for i, file_path in enumerate(results[:5], 1):
                file_name = os.path.basename(file_path)
                print(f"  {i}. {file_name}")
        else:
            print("⚠ 未找到文件（可能是索引数据问题）")
        
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_direct_sql_postgres():
    """测试直接 SQL 查询（PostgreSQL）"""
    print("\n" + "=" * 80)
    print("测试 5: 直接 SQL 查询（PostgreSQL 语法）")
    print("=" * 80)
    
    try:
        is_pg = is_postgres()
        
        if not is_pg:
            print("⚠ 跳过: 当前环境不是 PostgreSQL")
            return True
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # 测试布尔值查询
        print("测试 1: 使用 FALSE 查询 is_deleted")
        cursor.execute("""
            SELECT COUNT(*) as cnt
            FROM file_index_cache
            WHERE is_deleted = FALSE
        """)
        row = cursor.fetchone()
        total = row.get('cnt', 0) if hasattr(row, 'get') else row[0]
        print(f"✓ 总文件数 (is_deleted = FALSE): {total}")
        
        # 测试关键词查询
        print("\n测试 2: 查询包含 KL2951 的文件")
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

def test_table_exists_postgres():
    """测试 _table_exists 在 PostgreSQL 下的表现"""
    print("\n" + "=" * 80)
    print("测试 6: _table_exists 方法（PostgreSQL）")
    print("=" * 80)
    
    try:
        is_pg = is_postgres()
        
        if not is_pg:
            print("⚠ 跳过: 当前环境不是 PostgreSQL")
            return True
        
        fq = FileIndexQuery('')
        conn = fq._get_connection()
        cursor = conn.cursor()
        
        # 测试表存在检查
        exists = fq._table_exists(cursor, 'file_index_cache')
        print(f"✓ file_index_cache 表存在: {exists}")
        
        exists2 = fq._table_exists(cursor, 'nonexistent_table')
        print(f"✓ nonexistent_table 表存在: {exists2} (应该是 False)")
        
        if exists and not exists2:
            print("✓ _table_exists 方法工作正常")
        else:
            print("✗ _table_exists 方法可能有问题")
            return False
        
        conn.close()
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("\n" + "=" * 80)
    print("PostgreSQL 环境下的文件索引查询测试")
    print("=" * 80)
    
    # 运行所有测试
    results = []
    results.append(("PostgreSQL 连接", test_postgres_connection()))
    results.append(("布尔值转换", test_bool_value_conversion()))
    results.append(("SQL 占位符转换", test_sql_placeholder_conversion()))
    results.append(("索引查询", test_index_query_postgres()))
    results.append(("直接 SQL 查询", test_direct_sql_postgres()))
    results.append(("表存在检查", test_table_exists_postgres()))
    
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
    
    return all_passed

if __name__ == "__main__":
    main()
