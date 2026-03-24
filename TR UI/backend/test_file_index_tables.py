#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试文件索引缓存表是否创建成功
"""

import os
from dotenv import load_dotenv
from db_adapter import get_connection as get_db_connection, is_postgres

# 加载环境变量
load_dotenv()

# 获取数据库路径（与 tr_fill_in_api.py 中的逻辑一致）
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.normpath(os.path.join(_current_dir, '..', '..'))
_default_db_path = os.path.join(_project_root, 'TR database', 'data_3years.db')
_default_db_path = os.path.abspath(_default_db_path)
DB_PATH = os.getenv('DB_PATH', _default_db_path)

if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.abspath(os.path.join(_project_root, DB_PATH))


def _sql(sql_text):
    if is_postgres():
        return sql_text.replace('?', '%s')
    return sql_text


def _execute(cursor, sql_text, params=()):
    return cursor.execute(_sql(sql_text), params)


def _table_exists(cursor, table_name):
    if is_postgres():
        _execute(
            cursor,
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = ?
            ) AS exists
            """,
            (table_name.lower(),)
        )
    else:
        _execute(
            cursor,
            """
            SELECT EXISTS (
                SELECT 1 FROM sqlite_master
                WHERE type='table' AND name=?
            ) AS exists
            """,
            (table_name,)
        )
    row = cursor.fetchone()
    if isinstance(row, dict):
        return bool(row.get('exists'))
    if hasattr(row, 'keys'):
        return bool(row['exists'])
    return bool(row[0]) if row else False


def _get_table_columns(cursor, table_name):
    if is_postgres():
        _execute(
            cursor,
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            ORDER BY ordinal_position
            """,
            (table_name.lower(),)
        )
        return cursor.fetchall()
    _execute(cursor, f"PRAGMA table_info({table_name})")
    return cursor.fetchall()


def _get_indexes(cursor, table_name):
    if is_postgres():
        _execute(
            cursor,
            """
            SELECT indexname AS name, indexdef AS sql
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = ?
            ORDER BY indexname
            """,
            (table_name.lower(),)
        )
        return cursor.fetchall()
    _execute(
        cursor,
        """
        SELECT name, sql FROM sqlite_master
        WHERE type='index' AND tbl_name=?
        """,
        (table_name,)
    )
    return cursor.fetchall()


def test_file_index_tables():
    """测试文件索引缓存表"""
    print("=" * 60)
    print("测试文件索引缓存表")
    print("=" * 60)
    print(f"数据库路径: {DB_PATH}")
    print(f"数据库存在: {os.path.exists(DB_PATH)}")
    print()
    
    if not is_postgres() and not os.path.exists(DB_PATH):
        print("❌ 错误: 数据库文件不存在!")
        return False
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查 file_index_cache 表
        print("1. 检查 file_index_cache 表...")
        if _table_exists(cursor, 'file_index_cache'):
            print("   ✅ file_index_cache 表存在")
            
            # 获取表结构
            columns = _get_table_columns(cursor, 'file_index_cache')
            print(f"   📋 表结构 ({len(columns)} 个字段):")
            for col in columns:
                if is_postgres():
                    col_name = col['column_name']
                    col_type = col['data_type']
                    nullable = col['is_nullable'] != 'NO'
                    print(f"      - {col_name}: {col_type} {'NULL' if nullable else 'NOT NULL'}")
                else:
                    print(f"      - {col['name']}: {col['type']} {'NOT NULL' if col['notnull'] else 'NULL'} {'PRIMARY KEY' if col['pk'] else ''}")
            
            # 获取索引信息
            indexes = _get_indexes(cursor, 'file_index_cache')
            print(f"   📊 索引数量: {len(indexes)}")
            for idx in indexes:
                print(f"      - {idx['name']}")
            
            # 获取记录数
            _execute(cursor, "SELECT COUNT(*) as cnt FROM file_index_cache")
            count = cursor.fetchone()['cnt']
            print(f"   📈 当前记录数: {count}")
        else:
            print("   ❌ file_index_cache 表不存在!")
            return False
        
        print()
        
        # 检查 file_index_metadata 表
        print("2. 检查 file_index_metadata 表...")
        if _table_exists(cursor, 'file_index_metadata'):
            print("   ✅ file_index_metadata 表存在")
            
            # 获取表结构
            columns = _get_table_columns(cursor, 'file_index_metadata')
            print(f"   📋 表结构 ({len(columns)} 个字段):")
            for col in columns:
                if is_postgres():
                    col_name = col['column_name']
                    col_type = col['data_type']
                    nullable = col['is_nullable'] != 'NO'
                    print(f"      - {col_name}: {col_type} {'NULL' if nullable else 'NOT NULL'}")
                else:
                    print(f"      - {col['name']}: {col['type']} {'NOT NULL' if col['notnull'] else 'NULL'} {'PRIMARY KEY' if col['pk'] else ''}")
            
            # 获取元数据
            _execute(cursor, "SELECT * FROM file_index_metadata ORDER BY key")
            metadata = cursor.fetchall()
            print(f"   📊 元数据记录 ({len(metadata)} 条):")
            for row in metadata:
                print(f"      - {row['key']}: {row['value']} (更新于: {row['updated_at']})")
        else:
            print("   ❌ file_index_metadata 表不存在!")
            return False
        
        print()
        print("=" * 60)
        print("✅ 所有表检查通过!")
        print("=" * 60)
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    test_file_index_tables()
