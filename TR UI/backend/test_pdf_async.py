#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF 异步生成测试脚本
用于测试 PDF 异步生成功能是否正常工作
"""

import sqlite3
import sys
import os
from pdf_task_manager import PDFTaskManager

# 获取数据库路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.normpath(os.path.join(_current_dir, '..', '..'))
_db_path = os.path.join(_project_root, 'TR database', 'data_3years.db')

def test_pdf_task_manager():
    """测试 PDF 任务管理器"""
    print("=" * 60)
    print("PDF 异步生成功能测试")
    print("=" * 60)
    print()
    
    # 检查数据库是否存在
    if not os.path.exists(_db_path):
        print(f"❌ 错误：数据库不存在: {_db_path}")
        return False
    
    print(f"✅ 数据库路径: {_db_path}")
    print()
    
    # 创建任务管理器
    try:
        task_manager = PDFTaskManager(_db_path)
        print("✅ PDF 任务管理器创建成功")
    except Exception as e:
        print(f"❌ 创建任务管理器失败: {e}")
        return False
    
    # 检查表是否存在
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='pdf_tasks'
    """)
    table_exists = cursor.fetchone() is not None
    conn.close()
    
    if not table_exists:
        print("❌ 错误：pdf_tasks 表不存在")
        print("   请确保应用已启动，表会自动创建")
        return False
    
    print("✅ pdf_tasks 表存在")
    print()
    
    # 测试创建任务
    print("测试 1: 创建任务")
    try:
        test_user_id = 1
        test_order_no = 123456  # 使用测试订单号
        task_id = task_manager.create_task(test_user_id, test_order_no)
        print(f"✅ 任务创建成功: {task_id}")
    except Exception as e:
        print(f"❌ 创建任务失败: {e}")
        return False
    
    # 测试查询任务状态
    print()
    print("测试 2: 查询任务状态")
    try:
        task_status = task_manager.get_task_status(task_id, test_user_id)
        if task_status:
            print(f"✅ 任务状态查询成功")
            print(f"   任务ID: {task_status['task_id']}")
            print(f"   订单号: {task_status['order_no']}")
            print(f"   状态: {task_status['status']}")
            print(f"   进度: {task_status['progress']}%")
        else:
            print("❌ 任务状态查询失败：任务不存在")
            return False
    except Exception as e:
        print(f"❌ 查询任务状态失败: {e}")
        return False
    
    # 测试更新进度
    print()
    print("测试 3: 更新任务进度")
    try:
        task_manager.update_progress(task_id, 50, "测试进度更新")
        task_status = task_manager.get_task_status(task_id, test_user_id)
        if task_status['progress'] == 50:
            print("✅ 进度更新成功")
        else:
            print(f"❌ 进度更新失败：期望 50，实际 {task_status['progress']}")
            return False
    except Exception as e:
        print(f"❌ 更新进度失败: {e}")
        return False
    
    # 测试更新状态
    print()
    print("测试 4: 更新任务状态")
    try:
        task_manager.update_status(task_id, 'processing', message="测试处理中")
        task_status = task_manager.get_task_status(task_id, test_user_id)
        if task_status['status'] == 'processing':
            print("✅ 状态更新成功")
        else:
            print(f"❌ 状态更新失败：期望 processing，实际 {task_status['status']}")
            return False
    except Exception as e:
        print(f"❌ 更新状态失败: {e}")
        return False
    
    print()
    print("=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
    print()
    print("注意：")
    print("1. 这只是基本功能测试，不包含实际的 PDF 生成")
    print("2. 实际 PDF 生成需要有效的订单号和数据库连接")
    print("3. 建议在实际环境中测试完整的 PDF 生成流程")
    print()
    
    return True

if __name__ == '__main__':
    success = test_pdf_task_manager()
    sys.exit(0 if success else 1)
