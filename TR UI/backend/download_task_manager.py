#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Download Task Manager
Manages asynchronous download tasks, including creation, progress updates, and task processing
"""

import os
import uuid
import json
import threading
import time
from queue import Queue, Empty, Full
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
import zipfile
import tempfile

from db_adapter import get_connection as get_db_connection, is_postgres

# 导入 logger
try:
    from logger_config import get_logger
    logger = get_logger('download_task_manager')
except ImportError:
    import logging
    logger = logging.getLogger('download_task_manager')


class DownloadTaskManager:
    """Download Task Manager"""
    
    def __init__(self, db_path: str, base_folder: str = None):
        """
        Initialize task manager
        
        Args:
            db_path: SQLite database path
            base_folder: Base path for Stockist&Test Report folder
        """
        self.db_path = db_path
        self.base_folder = base_folder
        self.worker_count = max(1, int(os.getenv('DOWNLOAD_TASK_WORKERS', '4')))
        self.queue_maxsize = max(1, int(os.getenv('DOWNLOAD_TASK_QUEUE_MAXSIZE', '200')))
        self.task_queue = Queue(maxsize=self.queue_maxsize)
        self._workers_started = False
        self._workers_lock = threading.Lock()
        self._workers = []

    def _ensure_workers_started(self):
        """Start fixed-size worker pool once per manager instance."""
        if self._workers_started:
            return
        with self._workers_lock:
            if self._workers_started:
                return
            for idx in range(self.worker_count):
                worker = threading.Thread(
                    target=self._worker_loop,
                    name=f"download-task-worker-{idx + 1}",
                    daemon=True
                )
                worker.start()
                self._workers.append(worker)
            self._workers_started = True
            try:
                print(f"[Download Task] Worker pool started: workers={self.worker_count}, queue_maxsize={self.queue_maxsize}")
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass

    def _worker_loop(self):
        """Consume tasks from queue and process in background workers."""
        while True:
            try:
                task = self.task_queue.get(timeout=1.0)
            except Empty:
                continue
            try:
                task_id, task_type, request_params = task
                self.process_task(task_id, task_type, request_params)
            except Exception:
                # process_task already handles and persists task failure
                pass
            finally:
                self.task_queue.task_done()

    def enqueue_task(self, task_id: str, task_type: str, request_params: Dict):
        """Enqueue an existing task id for background processing."""
        self._ensure_workers_started()
        try:
            self.task_queue.put_nowait((task_id, task_type, request_params))
            try:
                print(f"[Download Task] Queued task: {task_id}, type={task_type}, queue_size={self.task_queue.qsize()}")
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
        except Full:
            # Keep task state explicit so caller can return meaningful error immediately.
            self.update_status(
                task_id,
                'failed',
                error_message='Task queue is full, please retry later',
                completed_at=datetime.now().isoformat()
            )
            raise RuntimeError('Task queue is full, please retry later')
    
    def _get_connection(self):
        """Get database connection"""
        return get_db_connection()

    def _sql(self, sql_text: str) -> str:
        if is_postgres():
            return sql_text.replace('?', '%s')
        return sql_text

    def _execute(self, cursor, sql_text: str, params=()):
        return cursor.execute(self._sql(sql_text), params)

    def _is_path_under_folder(self, file_path: str, folder_path: str) -> bool:
        """Check whether file_path is under folder_path (case-insensitive on Windows)."""
        if not file_path or not folder_path:
            return False
        abs_file = os.path.abspath(file_path).lower()
        abs_folder = os.path.abspath(folder_path).lower()
        if not abs_folder.endswith(os.sep):
            abs_folder = abs_folder + os.sep
        return abs_file.startswith(abs_folder)

    def _append_warning_file_to_zip(self, zip_path: str, warning_message: Optional[str], task_type: str) -> str:
        """Write warning message into ZIP as a text file and return the internal file path."""
        if not zip_path or not warning_message or not os.path.exists(zip_path):
            return ""

        warning_filename_map = {
            'order': 'missing_summary_by_order.txt',
            'order_stockist_flat': 'missing_summary_by_order.txt',
            'dd_no': 'missing_summary_by_dd_no.txt',
            'date': 'missing_summary_by_date.txt'
        }
        warning_filename = warning_filename_map.get(task_type, 'missing_summary.txt')

        lines = [
            "TR Stockist & Test Report Missing Summary",
            f"Task Type: {task_type}",
            f"Generated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            warning_message
        ]
        warning_content = "\n".join(lines)

        with zipfile.ZipFile(zip_path, 'a', zipfile.ZIP_STORED) as zipf:
            zipf.writestr(warning_filename, warning_content.encode('utf-8-sig'))

        return warning_filename

    def _format_missing_summary_by_order(
        self,
        cert_presence: Dict,
        order_to_group: Optional[Dict[int, str]] = None,
        group_title: str = "DD No",
        unmatched_group_label: str = "Unmatched DD No"
    ) -> str:
        """Build warning summary grouped by group title then order number."""
        if not cert_presence:
            return ""

        order_to_issues = {}
        for (order_no, cert), presence in cert_presence.items():
            if not cert:
                continue
            entry = order_to_issues.setdefault(order_no, {
                'missing_stockist_files': [],
                'missing_stockist_cert_content': [],
                'missing_test_report_content': []
            })
            if not presence.get('has_any_file'):
                entry['missing_stockist_files'].append(cert)
            else:
                if not presence.get('has_stockist_cert'):
                    entry['missing_stockist_cert_content'].append(cert)
                if not presence.get('has_test_report'):
                    entry['missing_test_report_content'].append(cert)

        lines = []
        if not order_to_group:
            for order_no in sorted(order_to_issues.keys()):
                issues = order_to_issues[order_no]
                msf = sorted(set(issues['missing_stockist_files']))
                msc = sorted(set(issues['missing_stockist_cert_content']))
                mtr = sorted(set(issues['missing_test_report_content']))
                if not msf and not msc and not mtr:
                    continue
                lines.append(f"Order {order_no}:")
                if msf:
                    try:
                        lines.append("  - 缺失Stockist文件：" + "、".join(msf))
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        lines.append("  - Missing Stockist files: " + ", ".join(msf))
                if msc:
                    try:
                        lines.append("  - 缺少Stockist Cert内容：" + "、".join(msc))
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        lines.append("  - Missing Stockist Cert content: " + ", ".join(msc))
                if mtr:
                    try:
                        lines.append("  - 缺少Test Report内容：" + "、".join(mtr))
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        lines.append("  - Missing Test Report content: " + ", ".join(mtr))
            return "\n".join(lines)

        dd_to_orders = {}
        for order_no in order_to_issues.keys():
            group_value = order_to_group.get(order_no)
            dd_key = str(group_value).strip() if group_value else unmatched_group_label
            dd_to_orders.setdefault(dd_key, []).append(order_no)

        def _dd_sort_key(dd_key: str):
            if dd_key == unmatched_group_label:
                return (1, dd_key)
            return (0, dd_key)

        for dd_key in sorted(dd_to_orders.keys(), key=_dd_sort_key):
            valid_order_lines = []
            for order_no in sorted(dd_to_orders[dd_key]):
                issues = order_to_issues[order_no]
                msf = sorted(set(issues['missing_stockist_files']))
                msc = sorted(set(issues['missing_stockist_cert_content']))
                mtr = sorted(set(issues['missing_test_report_content']))
                if not msf and not msc and not mtr:
                    continue
                valid_order_lines.append(f"  Order {order_no}:")
                if msf:
                    try:
                        valid_order_lines.append("    - 缺失Stockist文件：" + "、".join(msf))
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        valid_order_lines.append("    - Missing Stockist files: " + ", ".join(msf))
                if msc:
                    try:
                        valid_order_lines.append("    - 缺少Stockist Cert内容：" + "、".join(msc))
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        valid_order_lines.append("    - Missing Stockist Cert content: " + ", ".join(msc))
                if mtr:
                    try:
                        valid_order_lines.append("    - 缺少Test Report内容：" + "、".join(mtr))
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        valid_order_lines.append("    - Missing Test Report content: " + ", ".join(mtr))

            if valid_order_lines:
                lines.append(f"{group_title} {dd_key}:")
                lines.extend(valid_order_lines)

        return "\n".join(lines)

    def _collect_warning_for_selected_orders(
        self,
        downloader,
        order_nos: list,
        order_to_group: Optional[Dict[int, str]] = None,
        group_title: str = "DD No",
        unmatched_group_label: str = "未匹配DD No"
    ) -> Optional[str]:
        """
        Collect missing warnings for exactly the selected orders.
        Note: Do not expand to all orders under the same DD_No; scope follows user selection.
        """
        if not order_nos:
            return None

        orders_info = downloader.get_orders_info_batch(order_nos)
        cert_dn_values = downloader.get_all_cert_dn_values_batch(order_nos)
        rm_dn_maps = downloader.get_rm_dn_to_stockist_cert_map_batch(order_nos)
        cert_presence = {}

        for order_no in order_nos:
            try:
                order_info = orders_info.get(order_no)
                if not order_info:
                    continue

                cert_dn = cert_dn_values.get(order_no)
                if not cert_dn:
                    continue
                stockist_certs, rm_dn_nos = cert_dn
                expected_certs = [cert for cert in stockist_certs if cert]
                if not expected_certs:
                    continue

                for cert in expected_certs:
                    cert_presence.setdefault((order_no, cert), {
                        'has_any_file': False,
                        'has_stockist_cert': False,
                        'has_test_report': False
                    })

                rm_dn_to_stockist_map = rm_dn_maps.get(order_no, {})
                all_keywords = [k for k in (stockist_certs + rm_dn_nos) if k]
                if not all_keywords:
                    continue

                stockist_files = downloader.find_files_by_keywords(downloader.stockist_folder, all_keywords)

                jobsite_type = order_info['jobsite_type'] or ''
                is_iat, is_private = downloader.check_jobsite_type(jobsite_type)
                additional_files = []

                if is_iat:
                    iat_formal_files = downloader.find_files_by_keywords(downloader.iat_formal_folder, all_keywords, search_subfolders=False)
                    if iat_formal_files:
                        additional_files.extend(iat_formal_files)
                        formal_files_by_cert = {}
                        for file_path in iat_formal_files:
                            file_name = os.path.basename(file_path)
                            matched_cert = downloader.match_file_to_stockist_cert(
                                file_name, file_path, stockist_certs, rm_dn_nos, rm_dn_to_stockist_map
                            )
                            if matched_cert:
                                formal_files_by_cert.setdefault(matched_cert, []).append(file_path)

                        missing_certs = [cert for cert in stockist_certs if cert and cert not in formal_files_by_cert]
                        if missing_certs:
                            missing_keywords = []
                            for cert in missing_certs:
                                missing_keywords.append(cert)
                                for rm_dn_no, mapped_cert in rm_dn_to_stockist_map.items():
                                    if mapped_cert == cert:
                                        missing_keywords.append(rm_dn_no)
                            if missing_keywords:
                                iat_prelim_files = downloader.find_files_by_keywords(
                                    downloader.iat_prelim_folder, missing_keywords, search_subfolders=True
                                )
                                if iat_prelim_files:
                                    valid_prelim_files = []
                                    for file_path in iat_prelim_files:
                                        file_name = os.path.basename(file_path)
                                        matched_cert = downloader.match_file_to_stockist_cert(
                                            file_name, file_path, missing_certs, rm_dn_nos, rm_dn_to_stockist_map
                                        )
                                        if matched_cert and matched_cert in missing_certs:
                                            valid_prelim_files.append(file_path)
                                    additional_files.extend(valid_prelim_files)
                    else:
                        iat_prelim_files = downloader.find_files_by_keywords(
                            downloader.iat_prelim_folder, all_keywords, search_subfolders=True
                        )
                        if iat_prelim_files:
                            additional_files.extend(iat_prelim_files)
                elif is_private:
                    private_formal_files = downloader.find_files_by_keywords(
                        downloader.private_formal_folder, all_keywords, search_subfolders=True
                    )
                    if private_formal_files:
                        additional_files.extend(private_formal_files)
                        formal_files_by_cert = {}
                        for file_path in private_formal_files:
                            file_name = os.path.basename(file_path)
                            matched_cert = downloader.match_file_to_stockist_cert(
                                file_name, file_path, stockist_certs, rm_dn_nos, rm_dn_to_stockist_map
                            )
                            if matched_cert:
                                formal_files_by_cert.setdefault(matched_cert, []).append(file_path)

                        missing_certs = [cert for cert in stockist_certs if cert and cert not in formal_files_by_cert]
                        if missing_certs:
                            missing_keywords = []
                            for cert in missing_certs:
                                missing_keywords.append(cert)
                                for rm_dn_no, mapped_cert in rm_dn_to_stockist_map.items():
                                    if mapped_cert == cert:
                                        missing_keywords.append(rm_dn_no)

                            if missing_keywords:
                                private_prelim_files = downloader.find_files_by_keywords(
                                    downloader.private_prelim_folder, missing_keywords, search_subfolders=True
                                )
                                if private_prelim_files:
                                    valid_prelim_files = []
                                    for file_path in private_prelim_files:
                                        file_name = os.path.basename(file_path)
                                        matched_cert = downloader.match_file_to_stockist_cert(
                                            file_name, file_path, missing_certs, rm_dn_nos, rm_dn_to_stockist_map
                                        )
                                        if matched_cert and matched_cert in missing_certs:
                                            valid_prelim_files.append(file_path)
                                    additional_files.extend(valid_prelim_files)
                    else:
                        private_prelim_files = downloader.find_files_by_keywords(
                            downloader.private_prelim_folder, all_keywords, search_subfolders=True
                        )
                        if private_prelim_files:
                            additional_files.extend(private_prelim_files)

                order_files = stockist_files + additional_files
                for file_path in order_files:
                    file_name = os.path.basename(file_path)
                    matched_stockist_cert = downloader.match_file_to_stockist_cert(
                        file_name, file_path, stockist_certs, rm_dn_nos, rm_dn_to_stockist_map
                    )
                    if not matched_stockist_cert:
                        continue

                    key = (order_no, matched_stockist_cert)
                    presence = cert_presence.setdefault(key, {
                        'has_any_file': False,
                        'has_stockist_cert': False,
                        'has_test_report': False
                    })
                    presence['has_any_file'] = True
                    if self._is_path_under_folder(file_path, downloader.stockist_folder):
                        presence['has_stockist_cert'] = True
                    if (
                        self._is_path_under_folder(file_path, downloader.iat_formal_folder) or
                        self._is_path_under_folder(file_path, downloader.iat_prelim_folder) or
                        self._is_path_under_folder(file_path, downloader.private_formal_folder) or
                        self._is_path_under_folder(file_path, downloader.private_prelim_folder)
                    ):
                        presence['has_test_report'] = True
            except Exception:
                continue

        warning_message = self._format_missing_summary_by_order(
            cert_presence,
            order_to_group=order_to_group,
            group_title=group_title,
            unmatched_group_label=unmatched_group_label
        )
        return warning_message or None

    def _build_order_to_date_map(self, downloader, order_nos: list) -> Dict[int, str]:
        """Build normalized order -> date map for selected orders only."""
        result = {}
        if not order_nos:
            return result

        orders_info = downloader.get_orders_info_batch(order_nos)
        for order_no in order_nos:
            info = orders_info.get(order_no)
            if not info:
                continue
            del_date = info.get('del_date')
            if not del_date:
                continue
            date_str = str(del_date).strip()
            if ' ' in date_str:
                date_str = date_str.split(' ')[0]
            date_str = date_str.replace('/', '-')
            result[order_no] = date_str
        return result
    
    def create_task(self, user_id: int, task_type: str, request_params: Dict) -> str:
        """
        Create download task
        
        Args:
            user_id: User ID
            task_type: Task type ('order', 'dd_no', 'date')
            request_params: Request parameters
            
        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())
        expires_at = (datetime.now() + timedelta(days=7)).isoformat()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        request_params_json = json.dumps(request_params)
        if is_postgres():
            self._execute(cursor, """
                INSERT INTO download_tasks 
                (task_id, user_id, task_type, request_params, status, expires_at)
                VALUES (?, ?, ?, ?::jsonb, 'pending', ?)
            """, (
                task_id,
                user_id,
                task_type,
                request_params_json,
                expires_at
            ))
        else:
            self._execute(cursor, """
                INSERT INTO download_tasks 
                (task_id, user_id, task_type, request_params, status, expires_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
            """, (
                task_id,
                user_id,
                task_type,
                request_params_json,
                expires_at
            ))
        
        conn.commit()
        conn.close()
        
        # Use safe output method to avoid encoding errors
        try:
            msg = "[Download Task] Created task: " + str(task_id) + ", Type: " + str(task_type) + ", User: " + str(user_id)
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
        
        self._execute(cursor, """
            SELECT * FROM download_tasks 
            WHERE task_id = ? AND user_id = ?
        """, (task_id, user_id))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return dict(row)
    
    def update_progress(self, task_id: str, progress: int, processed_files: int, total_files: int = None):
        """
        Update task progress
        
        Args:
            task_id: Task ID
            progress: Progress percentage (0-100)
            processed_files: Number of processed files
            total_files: Total number of files (optional, updated if provided)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if total_files is not None:
            self._execute(cursor, """
                UPDATE download_tasks 
                SET progress = ?, processed_files = ?, total_files = ?
                WHERE task_id = ?
            """, (progress, processed_files, total_files, task_id))
        else:
            self._execute(cursor, """
                UPDATE download_tasks 
                SET progress = ?, processed_files = ?
                WHERE task_id = ?
            """, (progress, processed_files, task_id))
        
        conn.commit()
        conn.close()
    
    def update_status(self, task_id: str, status: str, **kwargs):
        """
        Update task status
        
        Args:
            task_id: Task ID
            status: New status
            **kwargs: Other fields to update (e.g., zip_path, zip_size, error_message)
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
            if key in ['zip_path', 'zip_size', 'error_message', 'warning_message', 'started_at', 'completed_at', 'total_files']:
                updates.append(f"{key} = ?")
                params.append(value)
        
        params.append(task_id)
        
        self._execute(cursor, f"""
            UPDATE download_tasks 
            SET {', '.join(updates)}
            WHERE task_id = ?
        """, params)
        
        conn.commit()
        conn.close()
    
    def process_task(self, task_id: str, task_type: str, request_params: Dict):
        """
        Process download task (called in background thread)
        
        Args:
            task_id: Task ID
            task_type: Task type
            request_params: Request parameters
        """
        try:
            try:
                msg = "[Download Task] Processing task: " + str(task_id)
                print(msg)
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            self.update_status(task_id, 'processing', started_at=datetime.now().isoformat())
            
            from stockist_test_download import StockistTestDownloader
            
            # 获取基础文件夹路径
            base_folder = self.base_folder or os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
            
            # 创建下载器
            downloader = StockistTestDownloader(self.db_path, base_folder)
            
            # 根据任务类型调用不同的下载方法
            warning_message = None

            if task_type == 'order':
                order_nos = request_params.get('order_nos', [])
                zip_path, file_count, warning_message = self._process_order_download(
                    task_id, downloader, order_nos
                )
            elif task_type == 'order_stockist_flat':
                order_nos = request_params.get('order_nos', [])
                zip_path, file_count, warning_message = self._process_order_download(
                    task_id, downloader, order_nos, flat_by_stockist=True
                )
            elif task_type == 'dd_no':
                order_nos = request_params.get('order_nos', [])
                zip_path, file_count, warning_message = self._process_dd_no_download(
                    task_id, downloader, order_nos
                )
            elif task_type == 'date':
                order_nos = request_params.get('order_nos', [])
                zip_path, file_count, warning_message = self._process_date_download(
                    task_id, downloader, order_nos
                )
            else:
                raise ValueError(f"Unknown task type: {task_type}")
            
            # 获取文件大小
            warning_file_in_zip = self._append_warning_file_to_zip(zip_path, warning_message, task_type)
            zip_size = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
            
            # 更新任务为完成状态
            self.update_status(
                task_id, 
                'completed',
                zip_path=zip_path,
                zip_size=zip_size,
                completed_at=datetime.now().isoformat(),
                progress=100,
                processed_files=file_count,
                total_files=file_count,
                warning_message=warning_message
            )
            
            try:
                msg1 = "[Download Task] Task completed: " + str(task_id) + ", Files: " + str(file_count) + ", Size: " + str(zip_size) + " bytes, ZIP path: " + str(zip_path)
                print(msg1)
                if warning_file_in_zip:
                    print("[Download Task] Warning summary written to ZIP: " + warning_file_in_zip)
                msg2 = "[Download Task] ZIP file exists: " + str(os.path.exists(zip_path))
                print(msg2)
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            
        except Exception as e:
            error_msg = str(e)
            try:
                msg = "[Download Task] Task failed: " + str(task_id) + ", Error: " + str(error_msg)
                print(msg)
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            import traceback
            traceback.print_exc()
            
            self.update_status(
                task_id,
                'failed',
                error_message=error_msg,
                completed_at=datetime.now().isoformat()
            )
    
    def _process_order_download(self, task_id: str, downloader, order_nos: list, flat_by_stockist: bool = False) -> Tuple[str, int, Optional[str]]:
        """Process download by Order"""
        # 使用订单数量作为进度单位（每个订单算一个处理单位）
        total_orders = len(order_nos)
        self.update_status(task_id, 'processing', total_files=total_orders)
        self.update_progress(task_id, 0, 0, total_orders)
        
        # 批量查询所有订单信息（一次性查询，提高效率）
        orders_info = downloader.get_orders_info_batch(order_nos)
        cert_dn_values = downloader.get_all_cert_dn_values_batch(order_nos)
        rm_dn_maps = downloader.get_rm_dn_to_stockist_cert_map_batch(order_nos)
        
        # 为每个订单收集文件
        files_by_order_and_cert = {}
        all_files_set = set()
        processed_orders = 0
        cert_presence = {}
        
        for idx, order_no in enumerate(order_nos):
            try:
                # 更新进度：已处理的订单数
                processed_orders += 1
                
                # 优化：每处理10个订单或每10%更新一次进度（避免过于频繁）
                update_interval = max(1, total_orders // 20)  # 至少更新20次
                if processed_orders % update_interval == 0 or processed_orders == total_orders:
                    progress = int((processed_orders / total_orders) * 90)  # 90%用于文件收集，10%用于ZIP打包
                    self.update_progress(task_id, progress, processed_orders, total_orders)
                
                # 从批量查询结果中获取订单信息
                order_info = orders_info.get(order_no)
                if not order_info:
                    try:
                        print(f"[Download Task] Order {order_no}: No order info found in database")
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                    continue
                
                # 从批量查询结果中获取 stockist_cert 和 rm_dn_no
                cert_dn = cert_dn_values.get(order_no)
                if not cert_dn:
                    try:
                        print(f"[Download Task] Order {order_no}: No cert_dn values found (stockist_cert or rm_dn_no)")
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                    continue
                stockist_certs, rm_dn_nos = cert_dn
                expected_certs = [cert for cert in stockist_certs if cert]
                for cert in expected_certs:
                    cert_presence.setdefault((order_no, cert), {
                        'has_any_file': False,
                        'has_stockist_cert': False,
                        'has_test_report': False
                    })
                
                # 从批量查询结果中获取 rm_dn_no 到 stockist_cert 映射
                rm_dn_to_stockist_map = rm_dn_maps.get(order_no, {})
                
                # 合并所有关键词
                all_keywords = stockist_certs + rm_dn_nos
                all_keywords = [k for k in all_keywords if k]  # 移除空值
                
                if not all_keywords:
                    try:
                        print(f"[Download Task] Order {order_no}: No keywords found (stockist_certs={stockist_certs}, rm_dn_nos={rm_dn_nos})")
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                    continue
                
                try:
                    print(f"[Download Task] Order {order_no}: Processing with keywords={all_keywords}, jobsite_type={order_info.get('jobsite_type')}")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
                
                # 从 Stockist 文件夹下载所有相关 PDF
                try:
                    print(f"[Download Task] Order {order_no}: Searching stockist folder: {downloader.stockist_folder}")
                    print(f"[Download Task] Order {order_no}: Stockist folder exists: {os.path.exists(downloader.stockist_folder) if downloader.stockist_folder else False}")
                    print(f"[Download Task] Order {order_no}: Using keywords: {all_keywords}")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
                
                stockist_files = downloader.find_files_by_keywords(downloader.stockist_folder, all_keywords)
                try:
                    print(f"[Download Task] Order {order_no}: Found {len(stockist_files)} files in stockist folder")
                    if len(stockist_files) == 0:
                        print(f"[Download Task] Order {order_no}: No files found in stockist folder with keywords: {all_keywords}")
                        # 检查文件夹中是否有任何文件
                        if downloader.stockist_folder and os.path.exists(downloader.stockist_folder):
                            try:
                                sample_files = []
                                for root, dirs, files in os.walk(downloader.stockist_folder):
                                    for f in files[:5]:  # 只检查前5个文件作为示例
                                        if f.lower().endswith('.pdf'):
                                            sample_files.append(os.path.join(root, f))
                                if sample_files:
                                    print(f"[Download Task] Order {order_no}: Sample files in stockist folder (first 5): {[os.path.basename(f) for f in sample_files]}")
                                else:
                                    print(f"[Download Task] Order {order_no}: No PDF files found in stockist folder at all")
                            except Exception as e:
                                print(f"[Download Task] Order {order_no}: Error checking stockist folder: {e}")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
                
                # 判断类型并查找对应文件夹
                jobsite_type = order_info['jobsite_type'] or ''
                is_iat, is_private = downloader.check_jobsite_type(jobsite_type)
                try:
                    print(f"[Download Task] Order {order_no}: jobsite_type={jobsite_type}, is_iat={is_iat}, is_private={is_private}")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
                
                additional_files = []
                
                if is_iat:
                    # IAT 类型：按每个 stockist_cert 单独判断，有 Formal 就用 Formal，没有就立即查 Prelim
                    certs_norm = [c.strip() for c in stockist_certs if c and str(c).strip()]
                    formal_files_by_cert = {}
                    prelim_files_by_cert = {}
                    
                    # 对每个 cert 单独处理
                    for cert in certs_norm:
                        # 1. 先检查该 cert 是否有对应的 IAT Formal 目录
                        formal_folder = os.path.join(downloader.iat_formal_folder, cert)
                        cert_has_formal = False
                        
                        try:
                            print(f"[Download Task][IAT] Order {order_no}: Checking cert {cert}, formal_folder={formal_folder}")
                            print(f"[Download Task][IAT] Order {order_no}: Formal folder exists: {os.path.exists(formal_folder) if formal_folder else False}")
                        except (UnicodeEncodeError, UnicodeDecodeError):
                            pass
                        
                        if os.path.exists(formal_folder) and os.path.isdir(formal_folder):
                            # 检查目录里是否有 PDF
                            cert_formal_files = []
                            for root, _dirs, files in os.walk(formal_folder):
                                for fn in files:
                                    if fn.lower().endswith(".pdf"):
                                        fp = os.path.join(root, fn)
                                        if os.path.exists(fp):
                                            cert_formal_files.append(fp)
                            
                            try:
                                print(f"[Download Task][IAT] Order {order_no}: Cert {cert} IAT Formal folder has {len(cert_formal_files)} PDFs")
                            except (UnicodeEncodeError, UnicodeDecodeError):
                                pass
                            
                            if cert_formal_files:
                                cert_has_formal = True
                                formal_files_by_cert[cert] = cert_formal_files
                                additional_files.extend(cert_formal_files)
                                try:
                                    logger.info(f"[Download Task][IAT] Order {order_no}: Cert {cert} has IAT Formal folder with {len(cert_formal_files)} PDFs")
                                except Exception:
                                    pass
                        
                        # 2. 如果该 cert 没有 Formal，立即去 IAT Prelim 搜索
                        if not cert_has_formal:
                            # 为该 cert 构建关键词（cert + 对应的 rm_dn_no）
                            cert_keywords = [cert]
                            for rm_dn_no, mapped_cert in rm_dn_to_stockist_map.items():
                                if mapped_cert == cert:
                                    cert_keywords.append(rm_dn_no)
                            
                            try:
                                print(f"[Download Task][IAT] Order {order_no}: Cert {cert} no Formal, searching IAT Prelim with keywords={cert_keywords}")
                                print(f"[Download Task][IAT] Order {order_no}: IAT Prelim folder path: {downloader.iat_prelim_folder}")
                                print(f"[Download Task][IAT] Order {order_no}: IAT Prelim folder exists: {os.path.exists(downloader.iat_prelim_folder) if downloader.iat_prelim_folder else False}")
                            except (UnicodeEncodeError, UnicodeDecodeError):
                                pass
                            
                            if cert_keywords:
                                cert_prelim_files = downloader.find_files_by_keywords(
                                    downloader.iat_prelim_folder,
                                    cert_keywords,
                                    search_subfolders=True
                                )
                                
                                try:
                                    print(f"[Download Task][IAT] Order {order_no}: Cert {cert} found {len(cert_prelim_files)} files in IAT Prelim (before validation)")
                                except (UnicodeEncodeError, UnicodeDecodeError):
                                    pass
                                
                                if cert_prelim_files:
                                    # 验证这些文件确实属于这个 cert
                                    valid_prelim_for_cert = []
                                    for file_path in cert_prelim_files:
                                        file_name = os.path.basename(file_path)
                                        matched_cert = downloader.match_file_to_stockist_cert(
                                            file_name, file_path, [cert], rm_dn_nos, rm_dn_to_stockist_map
                                        )
                                        if matched_cert == cert:
                                            valid_prelim_for_cert.append(file_path)
                                    
                                    try:
                                        print(f"[Download Task][IAT] Order {order_no}: Cert {cert} has {len(valid_prelim_for_cert)} valid IAT Prelim files (after validation)")
                                    except (UnicodeEncodeError, UnicodeDecodeError):
                                        pass
                                    
                                    if valid_prelim_for_cert:
                                        prelim_files_by_cert[cert] = valid_prelim_for_cert
                                        additional_files.extend(valid_prelim_for_cert)
                                        try:
                                            logger.info(f"[Download Task][IAT] Order {order_no}: Cert {cert} has no IAT Formal, using {len(valid_prelim_for_cert)} IAT Prelim files")
                                        except Exception:
                                            pass
                                    else:
                                        try:
                                            logger.info(f"[Download Task][IAT] Order {order_no}: Cert {cert} has no IAT Formal and no valid IAT Prelim files")
                                            print(f"[Download Task][IAT] Order {order_no}: Cert {cert} - IAT Prelim files found but none matched this cert")
                                        except Exception:
                                            pass
                                else:
                                    try:
                                        logger.info(f"[Download Task][IAT] Order {order_no}: Cert {cert} has no IAT Formal and no IAT Prelim files found")
                                    except Exception:
                                        pass
                            
                elif is_private:
                    # Private 类型
                    private_formal_files = downloader.find_files_by_keywords(downloader.private_formal_folder, all_keywords, search_subfolders=True)
                    
                    # 将 Private Formal 中找到的文件按 stockist_cert 分组
                    formal_files_by_cert = {}
                    for file_path in private_formal_files:
                        file_name = os.path.basename(file_path)
                        matched_cert = downloader.match_file_to_stockist_cert(
                            file_name, file_path, stockist_certs, rm_dn_nos, rm_dn_to_stockist_map
                        )
                        if matched_cert:
                            if matched_cert not in formal_files_by_cert:
                                formal_files_by_cert[matched_cert] = []
                            formal_files_by_cert[matched_cert].append(file_path)
                    
                    # 找出哪些 stockist_cert 在 Private Formal 中没有文件
                    missing_certs = [cert for cert in stockist_certs if cert and cert not in formal_files_by_cert]
                    
                    if private_formal_files:
                        additional_files.extend(private_formal_files)
                        
                        if missing_certs:
                            # 为缺失的 stockist_cert 构建关键词
                            missing_keywords = []
                            for cert in missing_certs:
                                missing_keywords.append(cert)
                                for rm_dn_no, mapped_cert in rm_dn_to_stockist_map.items():
                                    if mapped_cert == cert:
                                        missing_keywords.append(rm_dn_no)
                            
                            if missing_keywords:
                                private_prelim_files = downloader.find_files_by_keywords(downloader.private_prelim_folder, missing_keywords, search_subfolders=True)
                                if private_prelim_files:
                                    # 只添加属于缺失 stockist_cert 的文件
                                    valid_prelim_files = []
                                    for file_path in private_prelim_files:
                                        file_name = os.path.basename(file_path)
                                        matched_cert = downloader.match_file_to_stockist_cert(
                                            file_name, file_path, missing_certs, rm_dn_nos, rm_dn_to_stockist_map
                                        )
                                        if matched_cert and matched_cert in missing_certs:
                                            valid_prelim_files.append(file_path)
                                    additional_files.extend(valid_prelim_files)
                    else:
                        private_prelim_files = downloader.find_files_by_keywords(downloader.private_prelim_folder, all_keywords, search_subfolders=True)
                        if private_prelim_files:
                            additional_files.extend(private_prelim_files)
                
                # 合并该 Order 的所有文件
                order_files = stockist_files + additional_files
                try:
                    print(f"[Download Task] Order {order_no}: Total files found: {len(order_files)} (stockist: {len(stockist_files)}, additional: {len(additional_files)})")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
                
                # 按 stockist_cert 组织该 Order 的文件
                for file_path in order_files:
                    file_name = os.path.basename(file_path)
                    
                    # 使用通用匹配方法
                    matched_stockist_cert = downloader.match_file_to_stockist_cert(
                        file_name, file_path, stockist_certs, rm_dn_nos, rm_dn_to_stockist_map
                    )
                    
                    if matched_stockist_cert:
                        key = (order_no, matched_stockist_cert)
                        if key not in files_by_order_and_cert:
                            files_by_order_and_cert[key] = []
                        files_by_order_and_cert[key].append(file_path)
                        all_files_set.add(file_path)  # 用于统计总文件数
                        presence = cert_presence.setdefault(key, {
                            'has_any_file': False,
                            'has_stockist_cert': False,
                            'has_test_report': False
                        })
                        presence['has_any_file'] = True
                        if self._is_path_under_folder(file_path, downloader.stockist_folder):
                            presence['has_stockist_cert'] = True
                        if (
                            self._is_path_under_folder(file_path, downloader.iat_formal_folder) or
                            self._is_path_under_folder(file_path, downloader.iat_prelim_folder) or
                            self._is_path_under_folder(file_path, downloader.private_formal_folder) or
                            self._is_path_under_folder(file_path, downloader.private_prelim_folder)
                        ):
                            presence['has_test_report'] = True
                
            except Exception as e:
                try:
                    msg = "[Download Task] Order " + str(order_no) + " processing failed: " + str(e)
                    print(msg)
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
                import traceback
                traceback.print_exc()
                continue
        
        if not files_by_order_and_cert:
            # 添加更详细的错误信息
            error_details = []
            for order_no in order_nos:
                order_info = orders_info.get(order_no)
                cert_dn = cert_dn_values.get(order_no)
                if not order_info:
                    error_details.append(f"Order {order_no}: No order info in database")
                elif not cert_dn:
                    error_details.append(f"Order {order_no}: No stockist_cert or rm_dn_no found")
                else:
                    stockist_certs, rm_dn_nos = cert_dn
                    all_keywords = stockist_certs + rm_dn_nos
                    all_keywords = [k for k in all_keywords if k]
                    if not all_keywords:
                        error_details.append(f"Order {order_no}: No valid keywords (stockist_certs={stockist_certs}, rm_dn_nos={rm_dn_nos})")
                    else:
                        error_details.append(f"Order {order_no}: Keywords={all_keywords}, but no files found")
            
            error_msg = f"All Orders {order_nos} have no related PDF files found. Details: {'; '.join(error_details)}"
            try:
                print(f"[Download Task] ERROR: {error_msg}")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            raise ValueError(error_msg)

        # 生成缺失提示（不中断下载），按 Order 分组
        warning_message = self._format_missing_summary_by_order(cert_presence)
        
        # 更新进度：90% - 文件收集完成，开始打包
        self.update_progress(task_id, 90, total_orders, total_orders)
        
        # 创建ZIP文件
        if flat_by_stockist:
            zip_path = self._create_zip_from_files_flat_by_stockist(files_by_order_and_cert)
        else:
            zip_path = self._create_zip_from_files(files_by_order_and_cert, order_nos)
        file_count = len(all_files_set)
        
        # 更新进度：100% - 完成
        self.update_progress(task_id, 100, total_orders, total_orders)
        
        # 直接返回ZIP文件路径（不移动到缓存）
        return zip_path, file_count, (warning_message or None)

    def _create_zip_from_files_flat_by_stockist(self, files_by_order_and_cert: Dict) -> str:
        """
        Create ZIP file flattened by Stockist No.

        ZIP structure:
        - Stockist_No_1/file1.pdf
        - Stockist_No_1/file2.pdf
        - Stockist_No_2/file3.pdf
        """
        import tempfile
        import zipfile

        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_zip_path = temp_zip.name
        temp_zip.close()

        try:
            # Aggregate and deduplicate by (stockist_cert, file_path)
            files_by_cert = {}
            for (_, stockist_cert), files in files_by_order_and_cert.items():
                if not stockist_cert or not files:
                    continue
                cert_files = files_by_cert.setdefault(stockist_cert, set())
                for file_path in files:
                    if file_path and os.path.exists(file_path):
                        cert_files.add(file_path)

            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                written_paths = set()
                for stockist_cert, file_paths in files_by_cert.items():
                    used_names = set()
                    for file_path in sorted(file_paths):
                        file_name = os.path.basename(file_path)
                        if not file_name:
                            continue

                        # Ensure unique filename inside the same stockist folder
                        base_name, ext = os.path.splitext(file_name)
                        candidate_name = file_name
                        counter = 1
                        while candidate_name.lower() in used_names:
                            candidate_name = f"{base_name}_dup{counter}{ext}"
                            counter += 1
                        used_names.add(candidate_name.lower())

                        zip_path = f"{stockist_cert}/{candidate_name}"
                        zip_path_key = zip_path.lower()
                        if zip_path_key in written_paths:
                            continue
                        written_paths.add(zip_path_key)
                        zipf.write(file_path, zip_path)

            return temp_zip_path

        except Exception as e:
            if os.path.exists(temp_zip_path):
                try:
                    os.remove(temp_zip_path)
                except:
                    pass
            raise e
    
    def _create_zip_from_files(self, files_by_order_and_cert: Dict, order_nos: list) -> str:
        """Create ZIP file from file dictionary (consistent with original logic)"""
        import tempfile
        import zipfile
        
        # 获取基础文件夹路径（用于判断文件来源）
        base_folder = self.base_folder or os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
        stockist_folder = os.path.join(base_folder, 'Stockist Cert')
        private_formal_folder = os.path.join(base_folder, 'Private Formal')
        private_prelim_folder = os.path.join(base_folder, 'Private Prelim')
        iat_formal_folder = os.path.join(base_folder, 'IAT Formal')
        iat_prelim_folder = os.path.join(base_folder, 'IAT Prelim')
        
        # 创建临时ZIP文件
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_zip_path = temp_zip.name
        temp_zip.close()
        
        try:
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                # 为每个 (Order_No, stockist_cert) 组合创建文件夹并添加文件
                for (order_no, stockist_cert), files in files_by_order_and_cert.items():
                    if not files or not stockist_cert:
                        continue
                    
                    for file_path in files:
                        abs_file_path = os.path.abspath(file_path)
                        file_name = os.path.basename(file_path)
                        
                        # 判断文件来源（Stockist Cert、Private Formal、IAT Formal 等）
                        source_folder = None
                        base_folder_path = None
                        preserve_folder_structure = False  # 是否保留文件夹结构
                        
                        if abs_file_path.startswith(os.path.abspath(stockist_folder)):
                            source_folder = "Stockist Cert"
                            base_folder_path = stockist_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        elif abs_file_path.startswith(os.path.abspath(private_formal_folder)):
                            source_folder = "Private Formal"
                            base_folder_path = private_formal_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        elif abs_file_path.startswith(os.path.abspath(private_prelim_folder)):
                            source_folder = "Private Prelim"
                            base_folder_path = private_prelim_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        elif abs_file_path.startswith(os.path.abspath(iat_formal_folder)):
                            source_folder = "IAT Formal"
                            base_folder_path = iat_formal_folder
                            preserve_folder_structure = True  # 保留文件夹结构
                        elif abs_file_path.startswith(os.path.abspath(iat_prelim_folder)):
                            source_folder = "IAT Prelim"
                            base_folder_path = iat_prelim_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        else:
                            source_folder = "Other"
                            base_folder_path = None
                            preserve_folder_structure = False
                        
                        if not os.path.exists(file_path):
                            continue
                        
                        # 构建 ZIP 中的路径：Order_No/stockist_cert/...
                        try:
                            if preserve_folder_structure:
                                # IAT Formal：保留文件夹结构，但去掉第一层的 stockist_cert 文件夹
                                if base_folder_path:
                                    rel_path = os.path.relpath(file_path, base_folder_path)
                                    # 确保路径使用正斜杠（ZIP 标准）
                                    rel_path = rel_path.replace('\\', '/')
                                    
                                    # 如果路径的第一层是 stockist_cert 名称，去掉这一层
                                    path_parts = rel_path.split('/')
                                    if path_parts and path_parts[0] == stockist_cert:
                                        # 去掉第一层（stockist_cert 文件夹）
                                        rel_path = '/'.join(path_parts[1:])
                                    
                                    zip_path = f"{order_no}/{stockist_cert}/{source_folder}/{rel_path}"
                                else:
                                    zip_path = f"{order_no}/{stockist_cert}/{source_folder}/{file_name}"
                            else:
                                # 其他文件夹（IAT Prelim、Private Formal、Private Prelim、Stockist Cert）：
                                # 直接放在 Order_No/stockist_cert 文件夹下，只放文件名
                                zip_path = f"{order_no}/{stockist_cert}/{file_name}"
                            
                            zipf.write(file_path, zip_path)
                        except ValueError:
                            # 如果 relpath 失败（不同驱动器），使用文件名
                            if preserve_folder_structure:
                                zip_path = f"{order_no}/{stockist_cert}/{source_folder}/{file_name}"
                            else:
                                # 其他文件夹直接放在 Order_No/stockist_cert 文件夹下
                                zip_path = f"{order_no}/{stockist_cert}/{file_name}"
                            zipf.write(file_path, zip_path)
            
            return temp_zip_path
            
        except Exception as e:
            # 如果创建 ZIP 失败，清理临时文件
            if os.path.exists(temp_zip_path):
                try:
                    os.remove(temp_zip_path)
                except:
                    pass
            raise e
    
    def _process_dd_no_download(self, task_id: str, downloader, order_nos: list) -> Tuple[str, int, Optional[str]]:
        """Process download by DD_No"""
        # 使用订单数量作为进度单位
        total_orders = len(order_nos)
        self.update_status(task_id, 'processing', total_files=total_orders)
        self.update_progress(task_id, 0, 0, total_orders)
        
        # 更新进度：50% - 开始处理
        self.update_progress(task_id, 50, total_orders // 2, total_orders)
        
        zip_path, file_count = downloader.download_by_order_nos_grouped_by_dd_no(order_nos)
        order_to_dd_no = downloader.get_dd_no_by_orders_batch(order_nos)
        warning_message = self._collect_warning_for_selected_orders(
            downloader,
            order_nos,
            order_to_group=order_to_dd_no,
            group_title="DD No",
            unmatched_group_label="Unmatched DD No"
        )
        
        # 更新进度：90% - 文件收集完成，开始打包
        self.update_progress(task_id, 90, total_orders, total_orders)
        
        # 更新进度：100% - 完成
        self.update_progress(task_id, 100, total_orders, total_orders)
        
        # 直接返回ZIP文件路径（不移动到缓存）
        return zip_path, file_count, warning_message
    
    def _process_date_download(self, task_id: str, downloader, order_nos: list) -> Tuple[str, int, Optional[str]]:
        """Process download by date"""
        # 使用订单数量作为进度单位
        total_orders = len(order_nos)
        self.update_status(task_id, 'processing', total_files=total_orders)
        self.update_progress(task_id, 0, 0, total_orders)
        
        # 更新进度：50% - 开始处理
        self.update_progress(task_id, 50, total_orders // 2, total_orders)
        
        # 调用下载方法
        zip_path, file_count = downloader.download_by_order_nos_grouped_by_date(order_nos)
        order_to_date = self._build_order_to_date_map(downloader, order_nos)
        warning_message = self._collect_warning_for_selected_orders(
            downloader,
            order_nos,
            order_to_group=order_to_date,
            group_title="Date",
            unmatched_group_label="Unmatched Date"
        )
        
        # 更新进度：90% - 文件收集完成，开始打包
        self.update_progress(task_id, 90, total_orders, total_orders)
        
        # 更新进度：100% - 完成
        self.update_progress(task_id, 100, total_orders, total_orders)
        
        # 直接返回ZIP文件路径（不移动到缓存）
        return zip_path, file_count, warning_message
    
    def _move_to_cache(self, zip_path: str, task_id: str) -> str:
        """
        Move ZIP file to cache directory
        
        Args:
            zip_path: Original ZIP file path
            task_id: Task ID
            
        Returns:
            New ZIP file path
        """
        # 按日期组织缓存目录
        date_dir = datetime.now().strftime('%Y%m%d')
        cache_date_dir = os.path.join(self.download_cache_dir, date_dir)
        os.makedirs(cache_date_dir, exist_ok=True)
        
        # 新的文件路径
        new_zip_path = os.path.join(cache_date_dir, f"{task_id}.zip")
        
        # 移动文件
        if os.path.exists(zip_path):
            import shutil
            shutil.move(zip_path, new_zip_path)
            return new_zip_path
        else:
            return zip_path
    
    def cleanup_expired_tasks(self):
        """Clean up expired tasks and files"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 查找过期任务
        if is_postgres():
            self._execute(cursor, """
                SELECT task_id, zip_path
                FROM download_tasks
                WHERE expires_at < CURRENT_TIMESTAMP
            """)
        else:
            self._execute(cursor, """
                SELECT task_id, zip_path
                FROM download_tasks
                WHERE expires_at < datetime('now')
            """)
        
        expired_tasks = cursor.fetchall()
        
        deleted_count = 0
        for task in expired_tasks:
            # 删除ZIP文件
            if task['zip_path'] and os.path.exists(task['zip_path']):
                try:
                    os.remove(task['zip_path'])
                except Exception as e:
                    try:
                        msg = "[Cleanup] Failed to delete file " + str(task.get('zip_path', '')) + ": " + str(e)
                        print(msg)
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
            
            # 删除任务记录
            self._execute(cursor, "DELETE FROM download_tasks WHERE task_id = ?", (task['task_id'],))
            deleted_count += 1
        
        conn.commit()
        conn.close()
        
        if deleted_count > 0:
            try:
                msg = "[Cleanup] Cleaned " + str(deleted_count) + " expired tasks"
                print(msg)
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
        
        return deleted_count
