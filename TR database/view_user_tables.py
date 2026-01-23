#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查看3年数据库中的用户表 - 可视化输出"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'data_3years.db')
db_path = os.path.abspath(db_path)

print("=" * 80)
print("3-Year Database: User Tables Verification")
print("=" * 80)
print()
print(f"Database: {db_path}")
print(f"Exists: {os.path.exists(db_path)}")
print()

if not os.path.exists(db_path):
    print("ERROR: Database file not found!")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 1. 列出所有表
print("=" * 80)
print("STEP 1: All Tables in Database")
print("=" * 80)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [row[0] for row in cursor.fetchall()]
for i, table in enumerate(tables, 1):
    marker = " [USER TABLE]" if 'user' in table.lower() else ""
    print(f"  {i}. {table}{marker}")
print()
print(f"Total: {len(tables)} tables")
print()

# 2. 检查用户表
print("=" * 80)
print("STEP 2: User Tables Details")
print("=" * 80)
print()

user_tables = ['user_accounts', 'user_job_access', 'user_sessions']
for table_name in user_tables:
    print(f"Table: {table_name}")
    print("-" * 80)
    
    # 检查表是否存在
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name=?
    """, (table_name,))
    exists = cursor.fetchone() is not None
    
    if not exists:
        print(f"  [NOT FOUND] Table '{table_name}' does not exist!")
        print()
        continue
    
    print(f"  [EXISTS] Table '{table_name}' found")
    
    # 获取表结构
    cursor.execute("""
        SELECT sql FROM sqlite_master 
        WHERE type='table' AND name=?
    """, (table_name,))
    result = cursor.fetchone()
    if result:
        sql = result[0]
        # 简化显示
        lines = sql.split('\n')
        print(f"  Structure ({len(lines)} lines):")
        for line in lines[:5]:  # 只显示前5行
            print(f"    {line.strip()}")
        if len(lines) > 5:
            print(f"    ... ({len(lines) - 5} more lines)")
    
    # 获取记录数
    try:
        cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
        count = cursor.fetchone()['count']
        print(f"  Records: {count}")
        
        # 如果是user_accounts，显示用户详情
        if table_name == 'user_accounts' and count > 0:
            cursor.execute("""
                SELECT id, username, role, is_active, created_at 
                FROM user_accounts
            """)
            users = cursor.fetchall()
            print("  Users:")
            for user in users:
                status = "Active" if user['is_active'] else "Inactive"
                print(f"    - ID: {user['id']}, Username: {user['username']}, "
                      f"Role: {user['role']}, Status: {status}")
                print(f"      Created: {user['created_at']}")
        
        # 如果是user_job_access，显示权限
        if table_name == 'user_job_access' and count > 0:
            cursor.execute("""
                SELECT ua.username, uja.job_no 
                FROM user_job_access uja
                JOIN user_accounts ua ON uja.user_id = ua.id
                ORDER BY ua.username, uja.job_no
            """)
            accesses = cursor.fetchall()
            print("  Job Access:")
            for access in accesses:
                print(f"    - {access['username']} -> {access['job_no']}")
        
        # 如果是user_sessions，显示会话
        if table_name == 'user_sessions' and count > 0:
            cursor.execute("""
                SELECT ua.username, us.expires_at 
                FROM user_sessions us
                JOIN user_accounts ua ON us.user_id = ua.id
            """)
            sessions = cursor.fetchall()
            print("  Active Sessions:")
            for session in sessions:
                print(f"    - {session['username']} (expires: {session['expires_at']})")
    except Exception as e:
        print(f"  [ERROR] Cannot read data: {e}")
    
    print()

conn.close()

print("=" * 80)
print("Verification Complete!")
print("=" * 80)
print()
print("If you don't see user tables in your database viewer:")
print("1. Refresh/reload the database connection")
print("2. Make sure you're viewing: data_3years.db (not data_180days.db)")
print("3. Try running this script to verify: python view_user_tables.py")
print()

