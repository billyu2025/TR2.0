#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Celery 任务定义
"""

from celery_app import celery_app
import os
import sys
from datetime import datetime


@celery_app.task(bind=True, name='tasks.generate_pdf')
def generate_pdf_task(self, order_no):
    """
    异步生成 PDF 任务
    
    Args:
        order_no: 订单号
        
    Returns:
        dict: 包含成功状态和 PDF 路径的字典
    """
    try:
        # 更新任务状态
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 10,
                'message': '正在初始化 PDF 生成器...'
            }
        )
        
        # 导入PDF生成器 - 添加TR database目录到路径
        db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'TR database'))
        if db_dir not in sys.path:
            sys.path.insert(0, db_dir)
        
        from generate_landscape_pdf import OrderTraceabilityPDFGenerator
        
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 20,
                'message': '正在创建 PDF 生成器...'
            }
        )
        
        # 创建PDF生成器
        generator = OrderTraceabilityPDFGenerator()
        
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 30,
                'message': '正在生成 PDF...'
            }
        )
        
        # 生成PDF
        success, pdf_path = generator.generate_pdf(int(order_no))
        
        if success:
            self.update_state(
                state='PROGRESS',
                meta={
                    'progress': 90,
                    'message': 'PDF 生成完成，正在更新状态...'
                }
            )
            
            # 更新 PDF_Status 表
            # 使用延迟导入避免循环导入
            import importlib
            tr_api = importlib.import_module('tr_fill_in_api')
            get_db_connection = tr_api.get_db_connection
            cache = tr_api.cache
            upsert_pdf_status = tr_api._upsert_pdf_status
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                upsert_pdf_status(cursor, order_no, 'generated', pdf_path=pdf_path, generated_at=True)
                
                conn.commit()
                
                # 失效订单列表缓存
                try:
                    cache.delete('orders:list:*')
                except Exception:
                    pass
                
                print(f"[Celery PDF任务] PDF_Status updated for Order {order_no}: generated")
                
            except Exception as db_error:
                print(f"[Celery PDF任务] Failed to update PDF_Status: {db_error}")
                conn.rollback()
            finally:
                conn.close()
            
            return {
                'success': True,
                'order_no': order_no,
                'pdf_path': pdf_path,
                'progress': 100,
                'message': 'PDF 生成成功'
            }
        else:
            # 更新 PDF_Status 表为失败
            import importlib
            tr_api = importlib.import_module('tr_fill_in_api')
            get_db_connection = tr_api.get_db_connection
            cache = tr_api.cache
            upsert_pdf_status = tr_api._upsert_pdf_status
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                upsert_pdf_status(cursor, order_no, 'failed')
                
                conn.commit()
                
                try:
                    cache.delete('orders:list:*')
                except Exception:
                    pass
                
            except Exception as db_error:
                print(f"[Celery PDF任务] Failed to update PDF_Status: {db_error}")
                conn.rollback()
            finally:
                conn.close()
            
            error_msg = f'Order {order_no} not found in database'
            raise Exception(error_msg)
            
    except Exception as e:
        error_msg = str(e)
        print(f"[Celery PDF任务] 任务失败: Order {order_no}, 错误: {error_msg}")
        
        # 更新 PDF_Status 表为失败
        try:
            import importlib
            tr_api = importlib.import_module('tr_fill_in_api')
            get_db_connection = tr_api.get_db_connection
            cache = tr_api.cache
            upsert_pdf_status = tr_api._upsert_pdf_status
            
            conn = get_db_connection()
            cursor = conn.cursor()
            upsert_pdf_status(cursor, order_no, 'failed')
            conn.commit()
            
            try:
                cache.delete('orders:list:*')
            except Exception:
                pass
            
            conn.close()
        except:
            pass
        
        # 重新抛出异常，让 Celery 处理重试
        raise


@celery_app.task(bind=True, name='tasks.batch_download')
def batch_download_task(self, order_nos, user_id, task_type='order'):
    """
    异步批量下载任务
    
    Args:
        order_nos: 订单号列表
        user_id: 用户ID
        task_type: 任务类型（'order', 'dd_no', 'date'）
        
    Returns:
        dict: 包含成功状态和 ZIP 路径的字典
    """
    try:
        from download_task_manager import DownloadTaskManager
        import os
        
        total = len(order_nos)
        
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 0,
                'message': f'开始处理 {total} 个订单...',
                'total': total,
                'processed': 0
            }
        )
        
        # 获取基础文件夹路径
        base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
        
        # 创建任务管理器
        import importlib
        tr_api = importlib.import_module('tr_fill_in_api')
        DB_PATH = tr_api.DB_PATH
        
        task_manager = DownloadTaskManager(DB_PATH, base_folder)
        
        # 创建任务记录（用于跟踪）
        request_params = {'order_nos': order_nos}
        task_id = task_manager.create_task(user_id, task_type, request_params)
        
        # 处理任务
        task_manager.process_task(task_id, task_type, request_params)
        
        # 获取任务状态
        task_status = task_manager.get_task_status(task_id, user_id)
        
        if task_status and task_status['status'] == 'completed':
            return {
                'success': True,
                'task_id': task_id,
                'zip_path': task_status['zip_path'],
                'zip_size': task_status['zip_size'],
                'file_count': task_status.get('processed_files', 0),
                'progress': 100,
                'message': '下载完成'
            }
        else:
            error_msg = task_status.get('error_message', '下载失败') if task_status else '任务不存在'
            raise Exception(error_msg)
            
    except Exception as e:
        error_msg = str(e)
        print(f"[Celery 下载任务] 任务失败: {error_msg}")
        raise
