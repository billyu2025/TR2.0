#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF Task Manager
Manages asynchronous PDF generation tasks, including creation, progress updates, and task processing
"""

import os
import sqlite3
import uuid
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, Optional


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
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn
    
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
        
        cursor.execute("""
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
        
        # Use safe output method to avoid encoding errors
        try:
            msg = "[PDF Task] Created task: " + str(task_id) + ", Order No: " + str(order_no) + ", User: " + str(user_id)
            print(msg)
        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
            pass
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
        
        cursor.execute("""
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
            cursor.execute("""
                UPDATE pdf_tasks 
                SET progress = ?, message = ?
                WHERE task_id = ?
            """, (progress, message, task_id))
        else:
            cursor.execute("""
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
        
        cursor.execute(f"""
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
            try:
                msg = "[PDF Task] Processing task: " + str(task_id) + ", Order No: " + str(order_no)
                print(msg)
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            self.update_status(task_id, 'processing', started_at=datetime.now().isoformat())
            self.update_progress(task_id, 10, 'Initializing PDF generator...')
            
            # Import PDF generator - add TR database directory to path
            db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'TR database'))
            if db_dir not in sys.path:
                sys.path.insert(0, db_dir)
            
            from generate_landscape_pdf import OrderTraceabilityPDFGenerator
            
            self.update_progress(task_id, 20, 'Creating PDF generator...')
            
            # Create PDF generator (using SQL Server connection)
            generator = OrderTraceabilityPDFGenerator()
            
            self.update_progress(task_id, 30, 'Generating PDF...')
            
            # Generate PDF
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
                self.update_progress(task_id, 90, 'PDF generated, updating status...')
                
                # Update PDF_Status table
                # Use lazy import to avoid circular import
                import importlib
                tr_api = importlib.import_module('tr_fill_in_api')
                get_db_connection = tr_api.get_db_connection
                cache = tr_api.cache
                
                conn = get_db_connection()
                cursor = conn.cursor()
                
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO PDF_Status 
                        (Order_No, pdf_status, pdf_path, generated_at, updated_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, (order_no, 'generated', pdf_path))
                    
                    conn.commit()
                    
                    # Invalidate order list cache
                    try:
                        cache.delete('orders:list:*')
                    except Exception:
                        pass
                    
                    try:
                        msg = "[PDF Task] PDF_Status updated for Order " + str(order_no) + ": generated"
                        print(msg)
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                    
                except Exception as db_error:
                    try:
                        msg = "[PDF Task] Failed to update PDF_Status: " + str(db_error)
                        print(msg)
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                    conn.rollback()
                finally:
                    conn.close()
                
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
                
                try:
                    msg = "[PDF Task] Task completed: " + str(task_id) + ", Order No: " + str(order_no) + ", PDF path: " + str(pdf_path)
                    print(msg)
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
            else:
                # Update PDF_Status table to failed
                import importlib
                tr_api = importlib.import_module('tr_fill_in_api')
                get_db_connection = tr_api.get_db_connection
                cache = tr_api.cache
                
                conn = get_db_connection()
                cursor = conn.cursor()
                
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO PDF_Status 
                        (Order_No, pdf_status, updated_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    """, (order_no, 'failed'))
                    
                    conn.commit()
                    
                    # Invalidate order list cache
                    try:
                        cache.delete('orders:list:*')
                    except Exception:
                        pass
                    
                except Exception as db_error:
                    try:
                        print(f"[PDF Task] Failed to update PDF_Status: {db_error}")
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
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
                
                try:
                    msg = "[PDF Task] Task failed: " + str(task_id) + ", Order No: " + str(order_no) + ", Error: " + str(error_msg)
                    print(msg)
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
                
        except Exception as e:
            error_msg = str(e)
            try:
                msg = "[PDF Task] Task exception: " + str(task_id) + ", Order No: " + str(order_no) + ", Error: " + str(error_msg)
                print(msg)
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
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
                cursor.execute("""
                    INSERT OR REPLACE INTO PDF_Status 
                    (Order_No, pdf_status, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (order_no, 'failed'))
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
        cursor.execute("""
            SELECT task_id 
            FROM pdf_tasks 
            WHERE expires_at < datetime('now')
        """)
        
        expired_tasks = cursor.fetchall()
        
        deleted_count = 0
        for task in expired_tasks:
            # Delete task record
            cursor.execute("DELETE FROM pdf_tasks WHERE task_id = ?", (task['task_id'],))
            deleted_count += 1
        
        conn.commit()
        conn.close()
        
        if deleted_count > 0:
            try:
                msg = "[PDF Task Cleanup] Cleaned " + str(deleted_count) + " expired tasks"
                print(msg)
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
        
        return deleted_count
