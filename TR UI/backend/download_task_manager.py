#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下载任务管理器
功能：管理异步下载任务，包括创建、更新进度、处理任务
"""

import os
import sqlite3
import uuid
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import zipfile
import tempfile


class DownloadTaskManager:
    """下载任务管理器"""
    
    def __init__(self, db_path: str, base_folder: str = None):
        """
        初始化任务管理器
        
        Args:
            db_path: SQLite 数据库路径
            base_folder: Stockist&Test Report 文件夹的基础路径
        """
        self.db_path = db_path
        self.base_folder = base_folder
        self.download_cache_dir = os.path.join(os.path.dirname(db_path), 'downloads', 'cache')
        # 确保缓存目录存在
        os.makedirs(self.download_cache_dir, exist_ok=True)
    
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn
    
    def create_task(self, user_id: int, task_type: str, request_params: Dict) -> str:
        """
        创建下载任务
        
        Args:
            user_id: 用户ID
            task_type: 任务类型（'order', 'dd_no', 'date'）
            request_params: 请求参数
            
        Returns:
            任务ID
        """
        task_id = str(uuid.uuid4())
        expires_at = (datetime.now() + timedelta(days=7)).isoformat()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO download_tasks 
            (task_id, user_id, task_type, request_params, status, expires_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
        """, (
            task_id,
            user_id,
            task_type,
            json.dumps(request_params),
            expires_at
        ))
        
        conn.commit()
        conn.close()
        
        print(f"[下载任务] 创建任务: {task_id}, 类型: {task_type}, 用户: {user_id}")
        return task_id
    
    def get_task_status(self, task_id: str, user_id: int) -> Optional[Dict]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            user_id: 用户ID（用于权限验证）
            
        Returns:
            任务状态字典，如果任务不存在或无权访问返回None
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
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
        更新任务进度
        
        Args:
            task_id: 任务ID
            progress: 进度百分比（0-100）
            processed_files: 已处理文件数
            total_files: 总文件数（可选，如果提供则更新）
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if total_files is not None:
            cursor.execute("""
                UPDATE download_tasks 
                SET progress = ?, processed_files = ?, total_files = ?
                WHERE task_id = ?
            """, (progress, processed_files, total_files, task_id))
        else:
            cursor.execute("""
                UPDATE download_tasks 
                SET progress = ?, processed_files = ?
                WHERE task_id = ?
            """, (progress, processed_files, task_id))
        
        conn.commit()
        conn.close()
    
    def update_status(self, task_id: str, status: str, **kwargs):
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
            **kwargs: 其他要更新的字段（如zip_path, zip_size, error_message等）
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
            if key in ['zip_path', 'zip_size', 'error_message', 'started_at', 'completed_at', 'total_files']:
                updates.append(f"{key} = ?")
                params.append(value)
        
        params.append(task_id)
        
        cursor.execute(f"""
            UPDATE download_tasks 
            SET {', '.join(updates)}
            WHERE task_id = ?
        """, params)
        
        conn.commit()
        conn.close()
    
    def process_task(self, task_id: str, task_type: str, request_params: Dict):
        """
        处理下载任务（在后台线程中调用）
        
        Args:
            task_id: 任务ID
            task_type: 任务类型
            request_params: 请求参数
        """
        try:
            print(f"[下载任务] 开始处理任务: {task_id}")
            self.update_status(task_id, 'processing', started_at=datetime.now().isoformat())
            
            from stockist_test_download import StockistTestDownloader
            
            # 获取基础文件夹路径
            base_folder = self.base_folder or os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
            
            # 创建下载器
            downloader = StockistTestDownloader(self.db_path, base_folder)
            
            # 根据任务类型调用不同的下载方法
            if task_type == 'order':
                order_nos = request_params.get('order_nos', [])
                zip_path, file_count = self._process_order_download(
                    task_id, downloader, order_nos
                )
            elif task_type == 'dd_no':
                order_nos = request_params.get('order_nos', [])
                zip_path, file_count = self._process_dd_no_download(
                    task_id, downloader, order_nos
                )
            elif task_type == 'date':
                order_nos = request_params.get('order_nos', [])
                zip_path, file_count = self._process_date_download(
                    task_id, downloader, order_nos
                )
            else:
                raise ValueError(f"未知的任务类型: {task_type}")
            
            # 获取文件大小
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
                total_files=file_count
            )
            
            print(f"[下载任务] 任务完成: {task_id}, 文件数: {file_count}, 大小: {zip_size} bytes")
            
        except Exception as e:
            error_msg = str(e)
            print(f"[下载任务] 任务失败: {task_id}, 错误: {error_msg}")
            import traceback
            traceback.print_exc()
            
            self.update_status(
                task_id,
                'failed',
                error_message=error_msg,
                completed_at=datetime.now().isoformat()
            )
    
    def _process_order_download(self, task_id: str, downloader, order_nos: list) -> Tuple[str, int]:
        """处理按Order下载"""
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
                    continue
                
                # 从批量查询结果中获取 stockist_cert 和 rm_dn_no
                cert_dn = cert_dn_values.get(order_no)
                if not cert_dn:
                    continue
                stockist_certs, rm_dn_nos = cert_dn
                
                # 从批量查询结果中获取 rm_dn_no 到 stockist_cert 映射
                rm_dn_to_stockist_map = rm_dn_maps.get(order_no, {})
                
                # 合并所有关键词
                all_keywords = stockist_certs + rm_dn_nos
                all_keywords = [k for k in all_keywords if k]  # 移除空值
                
                if not all_keywords:
                    continue
                
                # 从 Stockist 文件夹下载所有相关 PDF
                stockist_files = downloader.find_files_by_keywords(downloader.stockist_folder, all_keywords)
                
                # 判断类型并查找对应文件夹
                jobsite_type = order_info['jobsite_type'] or ''
                is_iat, is_private = downloader.check_jobsite_type(jobsite_type)
                
                additional_files = []
                
                if is_iat:
                    # IAT 类型
                    iat_formal_files = downloader.find_files_by_keywords(downloader.iat_formal_folder, all_keywords, search_subfolders=False)
                    
                    # 将 IAT Formal 中找到的文件按 stockist_cert 分组
                    formal_files_by_cert = {}
                    for file_path in iat_formal_files:
                        file_name = os.path.basename(file_path)
                        matched_cert = downloader.match_file_to_stockist_cert(
                            file_name, file_path, stockist_certs, rm_dn_nos, rm_dn_to_stockist_map
                        )
                        if matched_cert:
                            if matched_cert not in formal_files_by_cert:
                                formal_files_by_cert[matched_cert] = []
                            formal_files_by_cert[matched_cert].append(file_path)
                    
                    # 找出哪些 stockist_cert 在 IAT Formal 中没有文件
                    missing_certs = [cert for cert in stockist_certs if cert and cert not in formal_files_by_cert]
                    
                    if iat_formal_files:
                        additional_files.extend(iat_formal_files)
                        
                        if missing_certs:
                            # 为缺失的 stockist_cert 构建关键词
                            missing_keywords = []
                            for cert in missing_certs:
                                missing_keywords.append(cert)
                                for rm_dn_no, mapped_cert in rm_dn_to_stockist_map.items():
                                    if mapped_cert == cert:
                                        missing_keywords.append(rm_dn_no)
                            
                            if missing_keywords:
                                iat_prelim_files = downloader.find_files_by_keywords(downloader.iat_prelim_folder, missing_keywords, search_subfolders=False)
                                if iat_prelim_files:
                                    # 只添加属于缺失 stockist_cert 的文件
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
                        iat_prelim_files = downloader.find_files_by_keywords(downloader.iat_prelim_folder, all_keywords, search_subfolders=False)
                        if iat_prelim_files:
                            additional_files.extend(iat_prelim_files)
                            
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
                
            except Exception as e:
                print(f"[下载任务] Order {order_no} 处理失败: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        if not files_by_order_and_cert:
            raise ValueError(f"所有 Order {order_nos} 都没有找到相关 PDF 文件")
        
        # 更新进度：90% - 文件收集完成，开始打包
        self.update_progress(task_id, 90, total_orders, total_orders)
        
        # 创建ZIP文件
        zip_path = self._create_zip_from_files(files_by_order_and_cert, order_nos)
        file_count = len(all_files_set)
        
        # 更新进度：100% - 完成
        self.update_progress(task_id, 100, total_orders, total_orders)
        
        # 将ZIP文件移动到缓存目录
        cached_zip_path = self._move_to_cache(zip_path, task_id)
        
        return cached_zip_path, file_count
    
    def _create_zip_from_files(self, files_by_order_and_cert: Dict, order_nos: list) -> str:
        """从文件字典创建ZIP文件（与原始逻辑保持一致）"""
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
    
    def _process_dd_no_download(self, task_id: str, downloader, order_nos: list) -> Tuple[str, int]:
        """处理按DD_No下载"""
        estimated_files = len(order_nos) * 10
        self.update_status(task_id, 'processing', total_files=estimated_files)
        
        zip_path, file_count = downloader.download_by_order_nos_grouped_by_dd_no(order_nos)
        
        # 更新实际文件数
        self.update_status(task_id, 'processing', total_files=file_count)
        self.update_progress(task_id, 100, file_count, file_count)
        
        cached_zip_path = self._move_to_cache(zip_path, task_id)
        
        return cached_zip_path, file_count
    
    def _process_date_download(self, task_id: str, downloader, order_nos: list) -> Tuple[str, int]:
        """处理按日期下载"""
        # 使用订单数量作为进度单位
        total_orders = len(order_nos)
        self.update_status(task_id, 'processing', total_files=total_orders)
        self.update_progress(task_id, 0, 0, total_orders)
        
        # 调用下载方法（暂时使用同步方式，后续可以优化为带进度回调）
        zip_path, file_count = downloader.download_by_order_nos_grouped_by_date(order_nos)
        
        # 更新进度：100% - 完成
        self.update_progress(task_id, 100, total_orders, total_orders)
        self.update_status(task_id, 'processing', total_files=total_orders)
        
        cached_zip_path = self._move_to_cache(zip_path, task_id)
        
        return cached_zip_path, file_count
    
    def _move_to_cache(self, zip_path: str, task_id: str) -> str:
        """
        将ZIP文件移动到缓存目录
        
        Args:
            zip_path: 原始ZIP文件路径
            task_id: 任务ID
            
        Returns:
            新的ZIP文件路径
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
        """清理过期的任务和文件"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 查找过期任务
        cursor.execute("""
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
                    print(f"[清理] 删除文件失败 {task['zip_path']}: {e}")
            
            # 删除任务记录
            cursor.execute("DELETE FROM download_tasks WHERE task_id = ?", (task['task_id'],))
            deleted_count += 1
        
        conn.commit()
        conn.close()
        
        if deleted_count > 0:
            print(f"[清理] 清理了 {deleted_count} 个过期任务")
        
        return deleted_count
