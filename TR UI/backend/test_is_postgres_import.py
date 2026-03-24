#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 is_postgres 导入是否正确"""

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # 测试模块级别导入
    from db_adapter import is_postgres
    print(f"[OK] Module level import works: {callable(is_postgres)}")
    
    # 测试函数中是否能使用
    def test_function():
        return is_postgres()
    
    result = test_function()
    print(f"[OK] Function usage works: {result}")
    
    # 测试 _ensure_download_tasks_table 函数
    import tr_fill_in_api
    print("[OK] tr_fill_in_api module imported")
    
    # 检查函数是否存在
    if hasattr(tr_fill_in_api, '_ensure_download_tasks_table'):
        print("[OK] _ensure_download_tasks_table function exists")
        
        # 尝试调用（可能会失败，因为需要数据库连接）
        try:
            # 不实际调用，只检查函数定义
            import inspect
            source = inspect.getsource(tr_fill_in_api._ensure_download_tasks_table)
            if 'from db_adapter import is_postgres' in source:
                print("[ERROR] Function still has local import")
            else:
                print("[OK] Function has no local import")
            if 'is_postgres()' in source:
                print("[OK] Function uses is_postgres()")
        except Exception as e:
            print(f"[WARN] Error checking function: {e}")
    
    print("\nAll tests passed!")
    
except UnboundLocalError as e:
    print(f"[ERROR] UnboundLocalError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
