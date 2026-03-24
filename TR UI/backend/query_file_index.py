#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询文件索引表中的 file_path 数据
"""

import os
import sys

from db_adapter import get_connection as get_db_connection, is_postgres

# 设置输出编码为 UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 获取数据库路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.normpath(os.path.join(_current_dir, '..', '..'))
_default_db_path = os.path.join(_project_root, 'TR database', 'data_3years.db')
DB_PATH = os.path.abspath(_default_db_path)


def _sql(sql_text):
    if is_postgres():
        return sql_text.replace('?', '%s')
    return sql_text


def _execute(cursor, sql_text, params=()):
    return cursor.execute(_sql(sql_text), params)

def query_file_paths(limit=50, folder_type=None, folder_path_filter=None):
    """
    查询索引表中的 file_path 数据
    
    Args:
        limit: 返回的最大记录数
        folder_type: 文件夹类型过滤（如 'IAT Formal'）
        folder_path_filter: 文件夹路径过滤（如包含 'HL2310'）
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 构建查询
        query = "SELECT file_path, folder_path, folder_type, file_name FROM file_index_cache WHERE is_deleted = 0"
        params = []
        
        if folder_type:
            query += " AND folder_type = ?"
            params.append(folder_type)
        
        if folder_path_filter:
            query += " AND folder_path LIKE ?"
            params.append(f'%{folder_path_filter}%')
        
        query += " LIMIT ?"
        params.append(limit)
        
        _execute(cursor, query, params)
        rows = cursor.fetchall()
        
        print(f"数据库路径: {DB_PATH}")
        print(f"查询结果: {len(rows)} 条记录\n")
        print("=" * 100)
        print(f"{'序号':<6} {'file_path':<80} {'folder_type':<15} {'file_name':<30}")
        print("=" * 100)
        
        for i, row in enumerate(rows, 1):
            file_path = row['file_path']
            folder_path = row['folder_path']
            folder_type = row['folder_type']
            file_name = row['file_name']
            
            # 截断过长的路径
            display_path = file_path if len(file_path) <= 80 else file_path[:77] + "..."
            display_name = file_name if len(file_name) <= 30 else file_name[:27] + "..."
            
            print(f"{i:<6} {display_path:<80} {folder_type:<15} {display_name:<30}")
            if len(file_path) > 80:
                print(f"      (完整路径: {file_path})")
        
        print("=" * 100)
        
        # 统计信息
        _execute(cursor, "SELECT COUNT(*) as cnt FROM file_index_cache WHERE is_deleted = 0")
        total = cursor.fetchone()['cnt']
        print(f"\n总记录数: {total}")
        
        if folder_type:
            _execute(cursor, "SELECT COUNT(*) as cnt FROM file_index_cache WHERE is_deleted = 0 AND folder_type = ?", (folder_type,))
            filtered_total = cursor.fetchone()['cnt']
            print(f"{folder_type} 类型记录数: {filtered_total}")
        
        conn.close()
        
    except Exception as e:
        print(f"查询失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 查询 HL2310 文件夹（通过 file_name）
    print("查询 file_name 包含 HL2310 的记录:")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        _execute(cursor, """
            SELECT file_path, folder_path, folder_type, file_name 
            FROM file_index_cache 
            WHERE is_deleted = 0 AND file_name LIKE '%HL2310%'
        """)
        rows = cursor.fetchall()
        print(f"找到 {len(rows)} 条记录:\n")
        for row in rows:
            print(f"  file_path: {row['file_path']}")
            print(f"  folder_path: {row['folder_path']}")
            print(f"  folder_type: {row['folder_type']}")
            print(f"  file_name: {row['file_name']}")
            print()
        conn.close()
    except Exception as e:
        print(f"查询失败: {e}")
    
    print("\n\n" + "=" * 100)
    print("\n查询所有 IAT Formal 类型的记录（前50条）:")
    query_file_paths(limit=50, folder_type='IAT Formal')
