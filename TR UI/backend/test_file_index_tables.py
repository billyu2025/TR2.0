#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试文件索引缓存表是否创建成功
"""

import sqlite3
import os
from dotenv import load_dotenv

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


def test_file_index_tables():
    """测试文件索引缓存表"""
    print("=" * 60)
    print("测试文件索引缓存表")
    print("=" * 60)
    print(f"数据库路径: {DB_PATH}")
    print(f"数据库存在: {os.path.exists(DB_PATH)}")
    print()
    
    if not os.path.exists(DB_PATH):
        print("❌ 错误: 数据库文件不存在!")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 检查 file_index_cache 表
        print("1. 检查 file_index_cache 表...")
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='file_index_cache'
        """)
        if cursor.fetchone():
            print("   ✅ file_index_cache 表存在")
            
            # 获取表结构
            cursor.execute("PRAGMA table_info(file_index_cache)")
            columns = cursor.fetchall()
            print(f"   📋 表结构 ({len(columns)} 个字段):")
            for col in columns:
                print(f"      - {col['name']}: {col['type']} {'NOT NULL' if col['notnull'] else 'NULL'} {'PRIMARY KEY' if col['pk'] else ''}")
            
            # 获取索引信息
            cursor.execute("""
                SELECT name, sql FROM sqlite_master 
                WHERE type='index' AND tbl_name='file_index_cache'
            """)
            indexes = cursor.fetchall()
            print(f"   📊 索引数量: {len(indexes)}")
            for idx in indexes:
                print(f"      - {idx['name']}")
            
            # 获取记录数
            cursor.execute("SELECT COUNT(*) as cnt FROM file_index_cache")
            count = cursor.fetchone()['cnt']
            print(f"   📈 当前记录数: {count}")
        else:
            print("   ❌ file_index_cache 表不存在!")
            return False
        
        print()
        
        # 检查 file_index_metadata 表
        print("2. 检查 file_index_metadata 表...")
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='file_index_metadata'
        """)
        if cursor.fetchone():
            print("   ✅ file_index_metadata 表存在")
            
            # 获取表结构
            cursor.execute("PRAGMA table_info(file_index_metadata)")
            columns = cursor.fetchall()
            print(f"   📋 表结构 ({len(columns)} 个字段):")
            for col in columns:
                print(f"      - {col['name']}: {col['type']} {'NOT NULL' if col['notnull'] else 'NULL'} {'PRIMARY KEY' if col['pk'] else ''}")
            
            # 获取元数据
            cursor.execute("SELECT * FROM file_index_metadata ORDER BY key")
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
