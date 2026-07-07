#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF Task Manager
Manages asynchronous PDF generation tasks, including creation, progress updates, and task processing
"""

import os
import uuid
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, Optional

from db_adapter import get_connection as get_db_connection, is_postgres
from logger_config import get_logger

# 获取日志器
logger = get_logger('pdf_task')


class PDFTaskManager:
    """PDF Task Manager"""
    
    def __init__(self, db_path: str):
        """
        Initialize task manager
        
        Args:
            db_path: SQLite database path
        """
        self.db_path = db_path
    
    def _get_connection(self):
        """Get database connection"""
        return get_db_connection()

    def _sql(self, sql_text: str) -> str:
        if is_postgres():
            return sql_text.replace('?', '%s')
        return sql_text

    def _execute(self, cursor, sql_text: str, params=()):
        return cursor.execute(self._sql(sql_text), params)

    def _pdf_status_table(self) -> str:
        return '"PDF_Status"' if is_postgres() else 'PDF_Status'

    def _upsert_pdf_status(self, cursor, order_no: int, pdf_status: str, pdf_path: Optional[str] = None, generated: bool = False):
        table_name = self._pdf_status_table()
        logger.debug(f"_upsert_pdf_status: order_no={order_no}, pdf_status={pdf_status}, pdf_path={pdf_path}, generated={generated}, table={table_name}, is_postgres={is_postgres()}")
        if is_postgres():
            if generated:
                sql = f"""
                    INSERT INTO {table_name} ("Order_No", pdf_status, pdf_path, generated_at, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT ("Order_No") DO UPDATE SET
                        pdf_status = EXCLUDED.pdf_status,
                        pdf_path = EXCLUDED.pdf_path,
                        generated_at = EXCLUDED.generated_at,
                        updated_at = CURRENT_TIMESTAMP
                    """
                logger.debug(f"Executing PostgreSQL INSERT ... ON CONFLICT for Order {order_no}")
                self._execute(
                    cursor,
                    sql,
                    (order_no, pdf_status, pdf_path)
                )
                logger.debug(f"PostgreSQL INSERT ... ON CONFLICT executed successfully for Order {order_no}")
            else:
                self._execute(
                    cursor,
                    f"""
                    INSERT INTO {table_name} ("Order_No", pdf_status, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT ("Order_No") DO UPDATE SET
                        pdf_status = EXCLUDED.pdf_status,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (order_no, pdf_status)
                )
            return

        if generated:
            self._execute(
                cursor,
                f"""
                INSERT OR REPLACE INTO {table_name}
                (Order_No, pdf_status, pdf_path, generated_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (order_no, pdf_status, pdf_path)
            )
        else:
            self._execute(
                cursor,
                f"""
                INSERT OR REPLACE INTO {table_name}
                (Order_No, pdf_status, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (order_no, pdf_status)
            )
    
    def create_task(self, user_id: int, order_no: int) -> str:
        """
        Create PDF generation task
        
        Args:
            user_id: User ID
            order_no: Order number
            
        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())
        expires_at = (datetime.now() + timedelta(days=1)).isoformat()  # PDF task expires after 1 day
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        self._execute(cursor, """
            INSERT INTO pdf_tasks 
            (task_id, user_id, order_no, status, progress, expires_at, created_at)
            VALUES (?, ?, ?, 'pending', 0, ?, CURRENT_TIMESTAMP)
        """, (
            task_id,
            user_id,
            order_no,
            expires_at
        ))
        
        conn.commit()
        conn.close()
        
        # Log task creation
        logger.info(f"Created PDF task: task_id={task_id}, order_no={order_no}, user_id={user_id}")
        return task_id
    
    def get_task_status(self, task_id: str, user_id: int) -> Optional[Dict]:
        """
        Get task status
        
        Args:
            task_id: Task ID
            user_id: User ID (for permission verification)
            
        Returns:
            Task status dictionary, or None if task doesn't exist or user has no access
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        self._execute(cursor, """
            SELECT * FROM pdf_tasks 
            WHERE task_id = ? AND user_id = ?
        """, (task_id, user_id))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return dict(row)
    
    def update_progress(self, task_id: str, progress: int, message: str = None):
        """
        Update task progress
        
        Args:
            task_id: Task ID
            progress: Progress percentage (0-100)
            message: Progress message (optional)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if message:
            self._execute(cursor, """
                UPDATE pdf_tasks 
                SET progress = ?, message = ?
                WHERE task_id = ?
            """, (progress, message, task_id))
        else:
            self._execute(cursor, """
                UPDATE pdf_tasks 
                SET progress = ?
                WHERE task_id = ?
            """, (progress, task_id))
        
        conn.commit()
        conn.close()
    
    def update_status(self, task_id: str, status: str, **kwargs):
        """
        Update task status
        
        Args:
            task_id: Task ID
            status: New status
            **kwargs: Other fields to update (e.g., pdf_path, error_message, started_at, completed_at)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        updates = ["status = ?"]
        params = [status]
        
        if status == 'processing' and 'started_at' not in kwargs:
            kwargs['started_at'] = datetime.now().isoformat()
        
        if status == 'completed' and 'completed_at' not in kwargs:
            kwargs['completed_at'] = datetime.now().isoformat()
        
        for key, value in kwargs.items():
            if key in ['pdf_path', 'error_message', 'started_at', 'completed_at', 'progress', 'message']:
                updates.append(f"{key} = ?")
                params.append(value)
        
        params.append(task_id)
        
        self._execute(cursor, f"""
            UPDATE pdf_tasks 
            SET {', '.join(updates)}
            WHERE task_id = ?
        """, params)
        
        conn.commit()
        conn.close()
    
    def process_task(self, task_id: str, order_no: int):
        """
        Process PDF generation task (called in background thread)
        
        Args:
            task_id: Task ID
            order_no: Order number
        """
        try:
            logger.info(f"Processing PDF task: task_id={task_id}, order_no={order_no}")
            self.update_status(task_id, 'processing', started_at=datetime.now().isoformat())
            self.update_progress(task_id, 10, 'Initializing PDF generator...')
            
            # Import PDF generator - ensure backend directory is in path
            backend_dir = os.path.dirname(os.path.abspath(__file__))
            if backend_dir not in sys.path:
                sys.path.insert(0, backend_dir)
            
            # Add TR database directory to path (if needed)
            db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'TR database'))
            if db_dir not in sys.path:
                sys.path.insert(0, db_dir)
            
            # Try to import WeasyPrint first to get better error message
            try:
                import weasyprint
            except ImportError as weasy_err:
                error_msg = (
                    f"WeasyPrint is not available in the current Python environment.\n"
                    f"Python executable: {sys.executable}\n"
                    f"Python path: {sys.path[:3]}\n"
                    f"Original error: {weasy_err}\n\n"
                    f"SOLUTION:\n"
                    f"1. Install WeasyPrint: {sys.executable} -m pip install weasyprint\n"
                    f"2. On Windows, ensure GTK+ runtime is installed and in PATH:\n"
                    f"   Download from: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases\n"
                    f"   Add to PATH: C:\\Program Files\\GTK3-Runtime Win64\\bin\n"
                    f"3. Restart your backend service"
                )
                raise ImportError(error_msg) from weasy_err
            
            # Try to import PDF generator with better error handling
            try:
                from generate_landscape_pdf import OrderTraceabilityPDFGenerator
            except ImportError as import_err:
                error_msg = f"Failed to import PDF generator: {import_err}"
                if "weasyprint" in str(import_err).lower() or "WEASYPRINT_AVAILABLE" in str(import_err):
                    error_msg = (
                        f"Failed to import PDF generator: WeasyPrint is not available.\n"
                        f"Original error: {import_err}\n\n"
                        f"SOLUTION:\n"
                        f"1. Install WeasyPrint: {sys.executable} -m pip install weasyprint\n"
                        f"2. On Windows, install GTK+ runtime:\n"
                        f"   Download from: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases\n"
                        f"   Add to PATH: C:\\Program Files\\GTK3-Runtime Win64\\bin\n"
                        f"3. Restart your terminal and backend service"
                    )
                raise ImportError(error_msg) from import_err
            
            self.update_progress(task_id, 20, 'Creating PDF generator...')
            logger.debug(f"Creating PDF generator for order {order_no}")
            
            # Create PDF generator (PostgreSQL TR_Report)
            generator = OrderTraceabilityPDFGenerator()
            
            self.update_progress(task_id, 30, 'Generating PDF...')
            logger.info(f"Starting PDF generation for order {order_no}")
            
            # Generate PDF
            logger.debug(f"Calling generator.generate_pdf() for order {order_no}")
            generation_result = generator.generate_pdf(int(order_no))
            warning_message = None
            if isinstance(generation_result, tuple):
                if len(generation_result) >= 3:
                    success, pdf_path, warning_message = generation_result[0], generation_result[1], generation_result[2]
                else:
                    success, pdf_path = generation_result[0], generation_result[1]
            else:
                success, pdf_path = bool(generation_result), None
            
            if success:
                logger.info(f"PDF generation successful for order {order_no}, pdf_path={pdf_path}")
                self.update_progress(task_id, 90, 'PDF generated, updating status...')
                
                # Update PDF_Status table
                # Use lazy import to avoid circular import
                logger.info(f"Starting PDF_Status update for Order {order_no}")
                try:
                    import importlib
                    tr_api = importlib.import_module('tr_fill_in_api')
                    get_db_connection = tr_api.get_db_connection
                    cache = tr_api.cache
                    logger.info(f"Successfully imported tr_fill_in_api module for Order {order_no}")
                except Exception as import_error:
                    logger.error(f"Failed to import tr_fill_in_api for Order {order_no}: {import_error}")
                    import traceback
                    logger.error(f"Import traceback: {traceback.format_exc()}")
                    raise
                
                conn = get_db_connection()
                cursor = conn.cursor()
                conn_closed = False
                logger.info(f"Got database connection for Order {order_no}")
                
                try:
                    logger.info(f"Calling _upsert_pdf_status for Order {order_no}, pdf_path={pdf_path}")
                    self._upsert_pdf_status(cursor, order_no, 'generated', pdf_path, generated=True)
                    logger.info(f"_upsert_pdf_status completed for Order {order_no}")
                    
                    # 检查是否有行被影响（PostgreSQL 的 execute 返回受影响的行数）
                    try:
                        if hasattr(cursor, 'rowcount'):
                            logger.info(f"Rows affected by _upsert_pdf_status: {cursor.rowcount}")
                    except Exception:
                        pass
                    
                    logger.info(f"Committing transaction for Order {order_no}")
                    conn.commit()
                    logger.info(f"Transaction committed for Order {order_no}")
                    
                    # 在关闭连接前，再次验证数据是否已提交
                    try:
                        verify_cursor = conn.cursor()
                        table_name = self._pdf_status_table()
                        if is_postgres():
                            self._execute(verify_cursor, f'SELECT pdf_status, pdf_path FROM {table_name} WHERE "Order_No" = ?', (order_no,))
                        else:
                            self._execute(verify_cursor, f'SELECT pdf_status, pdf_path FROM {table_name} WHERE Order_No = ?', (order_no,))
                        verify_row = verify_cursor.fetchone()
                        if verify_row:
                            verify_dict = dict(verify_row) if not isinstance(verify_row, dict) else verify_row
                            logger.info(f"PDF_Status verified (same connection) for Order {order_no}: status={verify_dict.get('pdf_status')}, path={verify_dict.get('pdf_path')}")
                        else:
                            logger.error(f"PDF_Status NOT found (same connection) for Order {order_no} after commit!")
                        verify_cursor.close()
                    except Exception as verify_error:
                        logger.warning(f"PDF_Status verification (same connection) error: {verify_error}")
                    
                    conn.close()
                    conn_closed = True
                    logger.info(f"Connection closed for Order {order_no}")
                    
                    # 验证更新是否成功（使用新连接确保看到已提交的数据）
                    try:
                        # 等待一小段时间，确保事务已完全提交
                        import time
                        time.sleep(0.1)  # 等待 100ms
                        
                        verify_conn = get_db_connection()
                        # 对于 PostgreSQL，确保连接能看到最新的已提交数据
                        if is_postgres():
                            try:
                                verify_conn.rollback()  # 回滚任何未提交的事务
                            except Exception:
                                pass
                        verify_cursor = verify_conn.cursor()
                        table_name = self._pdf_status_table()
                        if is_postgres():
                            self._execute(verify_cursor, f'SELECT pdf_status, pdf_path, updated_at FROM {table_name} WHERE "Order_No" = ?', (order_no,))
                        else:
                            self._execute(verify_cursor, f'SELECT pdf_status, pdf_path, updated_at FROM {table_name} WHERE Order_No = ?', (order_no,))
                        verify_row = verify_cursor.fetchone()
                        if verify_row:
                            verify_dict = dict(verify_row) if not isinstance(verify_row, dict) else verify_row
                            logger.info(f"PDF_Status verified for Order {order_no}: status={verify_dict.get('pdf_status')}, path={verify_dict.get('pdf_path')}, updated_at={verify_dict.get('updated_at')}")
                        else:
                            logger.warning(f"PDF_Status verification failed: Order {order_no} not found in PDF_Status table")
                            # 再次尝试查询（可能是连接池的问题）
                            logger.warning(f"Retrying PDF_Status verification for Order {order_no}...")
                            time.sleep(0.2)  # 再等待 200ms
                            verify_conn2 = get_db_connection()
                            if is_postgres():
                                try:
                                    verify_conn2.rollback()
                                except Exception:
                                    pass
                            verify_cursor2 = verify_conn2.cursor()
                            if is_postgres():
                                self._execute(verify_cursor2, f'SELECT pdf_status, pdf_path, updated_at FROM {table_name} WHERE "Order_No" = ?', (order_no,))
                            else:
                                self._execute(verify_cursor2, f'SELECT pdf_status, pdf_path, updated_at FROM {table_name} WHERE Order_No = ?', (order_no,))
                            verify_row2 = verify_cursor2.fetchone()
                            if verify_row2:
                                verify_dict2 = dict(verify_row2) if not isinstance(verify_row2, dict) else verify_row2
                                logger.info(f"PDF_Status verified (retry) for Order {order_no}: status={verify_dict2.get('pdf_status')}, path={verify_dict2.get('pdf_path')}")
                            else:
                                logger.error(f"PDF_Status verification (retry) failed: Order {order_no} still not found")
                            verify_cursor2.close()
                            verify_conn2.close()
                        verify_cursor.close()
                        verify_conn.close()
                    except Exception as verify_error:
                        logger.warning(f"PDF_Status verification error for Order {order_no}: {verify_error}")
                        import traceback
                        logger.warning(f"Verification traceback: {traceback.format_exc()}")
                    
                    # Invalidate order list cache
                    try:
                        # 清除所有以 orders:list: 开头的缓存
                        deleted = cache.delete('orders:list:*')
                        logger.info(f"Cache invalidated for orders:list:* after PDF generation for Order {order_no}, result={deleted}")
                    except Exception as cache_error:
                        logger.warning(f"Cache invalidation failed: {cache_error}")
                        import traceback
                        logger.warning(f"Cache invalidation traceback: {traceback.format_exc()}")
                    
                    logger.info(f"PDF_Status updated for Order {order_no}: generated")
                    
                except Exception as db_error:
                    logger.error(f"Failed to update PDF_Status for Order {order_no}: {db_error}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    if not conn_closed:
                        try:
                            conn.rollback()
                            conn.close()
                        except Exception:
                            pass
                
                # Update task to completed status
                final_message = warning_message if warning_message else 'PDF generated successfully'
                self.update_status(
                    task_id,
                    'completed',
                    pdf_path=pdf_path,
                    completed_at=datetime.now().isoformat(),
                    progress=100,
                    message=final_message
                )
                
                logger.info(f"PDF task completed: task_id={task_id}, order_no={order_no}, pdf_path={pdf_path}")
            else:
                logger.warning(f"PDF generation failed for order {order_no}: Order not found in database")
                # Update PDF_Status table to failed
                import importlib
                tr_api = importlib.import_module('tr_fill_in_api')
                get_db_connection = tr_api.get_db_connection
                cache = tr_api.cache
                
                conn = get_db_connection()
                cursor = conn.cursor()
                
                try:
                    self._upsert_pdf_status(cursor, order_no, 'failed')
                    
                    conn.commit()
                    
                    # Invalidate order list cache
                    try:
                        cache.delete('orders:list:*')
                    except Exception:
                        pass
                    
                except Exception as db_error:
                    logger.error(f"Failed to update PDF_Status for Order {order_no}: {db_error}")
                    conn.rollback()
                finally:
                    conn.close()
                
                # Update task to failed status
                error_msg = f'Order {order_no} not found in database'
                self.update_status(
                    task_id,
                    'failed',
                    error_message=error_msg,
                    completed_at=datetime.now().isoformat(),
                    progress=0,
                    message='PDF generation failed'
                )
                
                logger.error(f"PDF task failed: task_id={task_id}, order_no={order_no}, error={error_msg}")
                
        except Exception as e:
            error_msg = str(e)
            logger.exception(f"PDF task exception: task_id={task_id}, order_no={order_no}, error={error_msg}")
            import traceback
            traceback.print_exc()
            
            # Update PDF_Status table to failed
            try:
                import importlib
                tr_api = importlib.import_module('tr_fill_in_api')
                get_db_connection = tr_api.get_db_connection
                cache = tr_api.cache
                
                conn = get_db_connection()
                cursor = conn.cursor()
                self._upsert_pdf_status(cursor, order_no, 'failed')
                conn.commit()
                
                # Invalidate order list cache
                try:
                    cache.delete('orders:list:*')
                except Exception:
                    pass
                
                conn.close()
            except:
                pass  # Ignore database update errors
            
            # Update task to failed status
            self.update_status(
                task_id,
                'failed',
                error_message=error_msg,
                completed_at=datetime.now().isoformat(),
                progress=0,
                message=f'PDF generation failed: {error_msg}'
            )
    
    def cleanup_expired_tasks(self):
        """Clean up expired tasks"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Find expired tasks
        if is_postgres():
            self._execute(cursor, """
                SELECT task_id
                FROM pdf_tasks
                WHERE expires_at < CURRENT_TIMESTAMP
            """)
        else:
            self._execute(cursor, """
                SELECT task_id 
                FROM pdf_tasks 
                WHERE expires_at < datetime('now')
            """)
        
        expired_tasks = cursor.fetchall()
        
        deleted_count = 0
        for task in expired_tasks:
            # Delete task record
            self._execute(cursor, "DELETE FROM pdf_tasks WHERE task_id = ?", (task['task_id'],))
            deleted_count += 1
        
        conn.commit()
        conn.close()
        
        if deleted_count > 0:
            logger.info(f"PDF task cleanup: cleaned {deleted_count} expired tasks")
        
        return deleted_count
