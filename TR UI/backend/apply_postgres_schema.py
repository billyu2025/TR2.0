#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
执行 PostgreSQL schema 脚本
用于创建所有表结构
"""

import os
import sys
from psycopg import connect

# 从环境变量读取 PostgreSQL DSN
POSTGRES_DSN = os.getenv('POSTGRES_DSN', 'postgresql://postgres:postgres@127.0.0.1:5432/tr_db')
SCHEMA_FILE = os.path.join(os.path.dirname(__file__), 'schema_postgres.sql')

def main():
    print(f"[SCHEMA] PostgreSQL DSN: {POSTGRES_DSN}")
    print(f"[SCHEMA] Schema file: {SCHEMA_FILE}")
    
    if not os.path.exists(SCHEMA_FILE):
        print(f"❌ Schema file not found: {SCHEMA_FILE}")
        sys.exit(1)
    
    print(f"[SCHEMA] Reading schema file...")
    with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
        schema_sql = f.read()
    
    print(f"[SCHEMA] Connecting to PostgreSQL...")
    try:
        with connect(POSTGRES_DSN) as conn:
            with conn.cursor() as cur:
                print(f"[SCHEMA] Executing schema SQL...")
                cur.execute(schema_sql)
                conn.commit()
                print(f"✅ Schema applied successfully!")
    except Exception as e:
        print(f"❌ Failed to apply schema: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
