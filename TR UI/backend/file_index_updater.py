#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件索引缓存增量更新器
功能：检测文件变化并更新索引
"""

import os
import sqlite3
import json
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import time

# 导入索引建立器以重用关键词提取功能
from file_index_builder import FileIndexBuilder


class FileIndexUpdater:
    """文件索引缓存增量更新器"""
    
    def __init__(self, db_path: str, base_folder: str = None):
        """
        初始化更新器
        
        Args:
            db_path: SQLite 数据库路径
            base_folder: Stockist&Test Report 文件夹的基础路径
        """
        self.db_path = db_path
        # 使用 FileIndexBuilder 来获取文件夹配置和关键词提取功能
        self.builder = FileIndexBuilder(db_path, base_folder)
        self.base_folder = self.builder.base_folder
        self.scan_folders = self.builder.scan_folders
        
        # 更新阈值（小时）
        self.update_threshold_hours = 1
        # 每次更新的最大文件数
        self.max_files_per_update = 10000
    
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn
    
    def get_files_to_check(self, folder_type: str, limit: int = None) -> List[Dict]:
        """
        获取需要检查的文件列表
        
        Args:
            folder_type: 文件夹类型
            limit: 限制数量
            
        Returns:
            需要检查的文件信息列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 计算阈值时间
            threshold_time = (datetime.now() - timedelta(hours=self.update_threshold_hours)).isoformat()
            
            query = """
                SELECT file_path, file_size, modified_time, last_checked
                FROM file_index_cache
                WHERE folder_type = ? 
                  AND is_deleted = 0
                  AND last_checked < ?
                ORDER BY last_checked ASC
            """
            
            params = [folder_type, threshold_time]
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [dict(row) for row in rows]
        finally:
            conn.close()
    
    def scan_folder_for_files(self, folder_path: str, folder_type: str = None) -> Dict[str, Dict]:
        """
        扫描文件夹，获取当前文件信息
        
        Args:
            folder_path: 文件夹路径
            folder_type: 文件夹类型（用于判断是否只扫描子文件夹）
            
        Returns:
            {file_path: {size, mtime}} 字典
        """
        files_info = {}
        
        if not os.path.exists(folder_path):
            return files_info
        
        try:
            # IAT Formal 只扫描子文件夹，不递归到文件
            if folder_type == 'IAT Formal':
                # 只扫描直接子文件夹
                items = os.listdir(folder_path)
                for item in items:
                    item_path = os.path.join(folder_path, item)
                    if os.path.isdir(item_path):
                        try:
                            mtime = os.path.getmtime(item_path)
                            files_info[item_path] = {
                                'size': 0,  # 文件夹没有大小
                                'mtime': mtime
                            }
                        except (OSError, PermissionError):
                            # 跳过无法访问的文件夹
                            continue
            else:
                # 其他文件夹类型（包括 IAT Prelim）：递归扫描所有 PDF 文件
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        if not file.lower().endswith('.pdf'):
                            continue
                        
                        file_path = os.path.join(root, file)
                        try:
                            stat = os.stat(file_path)
                            files_info[file_path] = {
                                'size': stat.st_size,
                                'mtime': stat.st_mtime
                            }
                        except (OSError, PermissionError):
                            # 跳过无法访问的文件
                            continue
        except Exception as e:
            print(f"[错误] 扫描文件夹失败 {folder_path}: {e}")
        
        return files_info
    
    def update_index(self, folder_type: Optional[str] = None) -> Dict:
        """
        执行增量更新
        
        Args:
            folder_type: 要更新的文件夹类型（如果为None，更新所有类型）
            
        Returns:
            更新结果统计
        """
        start_time = time.time()
        
        print("=" * 60)
        print("开始增量更新文件索引")
        print("=" * 60)
        
        # 更新状态
        self.builder.update_metadata('scan_status', 'updating')
        
        stats = {
            'files_added': 0,
            'files_updated': 0,
            'files_deleted': 0,
            'files_checked': 0,
            'errors': 0
        }
        
        # 确定要更新的文件夹类型
        folder_types_to_update = [folder_type] if folder_type else list(self.scan_folders.keys())
        
        for folder_type in folder_types_to_update:
            folder_path = self.scan_folders.get(folder_type)
            if not folder_path or not os.path.exists(folder_path):
                continue
            
            print(f"\n[更新] 处理文件夹类型: {folder_type}")
            
            # 1. 获取文件系统中的当前文件
            print(f"  [1/3] 扫描文件系统: {folder_path}")
            fs_files = self.scan_folder_for_files(folder_path, folder_type)
            if folder_type == 'IAT Formal':
                print(f"  [1/3] 找到 {len(fs_files)} 个子文件夹")
            else:
                print(f"  [1/3] 找到 {len(fs_files)} 个文件")
            
            # 2. 获取数据库中的文件记录
            print(f"  [2/3] 查询数据库记录...")
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT file_path, file_size, modified_time
                FROM file_index_cache
                WHERE folder_type = ? AND is_deleted = 0
            """, (folder_type,))
            
            db_files = {row['file_path']: {
                'size': row['file_size'],
                'mtime': row['modified_time']
            } for row in cursor.fetchall()}
            
            print(f"  [2/3] 数据库中有 {len(db_files)} 条记录")
            
            # 3. 对比差异
            print(f"  [3/3] 对比差异...")
            
            # 新增文件：文件系统中存在，数据库中不存在
            new_files = set(fs_files.keys()) - set(db_files.keys())
            # 删除文件：数据库中存在，文件系统中不存在
            deleted_files = set(db_files.keys()) - set(fs_files.keys())
            # 修改文件：都存在但大小或修改时间不同
            modified_files = []
            for file_path in set(fs_files.keys()) & set(db_files.keys()):
                fs_info = fs_files[file_path]
                db_info = db_files[file_path]
                if (fs_info['size'] != db_info['size'] or 
                    abs(fs_info['mtime'] - db_info['mtime']) > 1):  # 允许1秒误差
                    modified_files.append(file_path)
            
            print(f"  [差异] 新增: {len(new_files)}, 删除: {len(deleted_files)}, 修改: {len(modified_files)}")
            
            # 4. 更新数据库
            # 处理新增文件
            if new_files:
                print(f"  [插入] 插入 {len(new_files)} 个新文件...")
                new_file_infos = []
                for file_path in new_files:
                    file_info = self.builder.get_file_info(file_path, folder_type)
                    if file_info:
                        new_file_infos.append(file_info)
                
                if new_file_infos:
                    inserted = self.builder.batch_insert_files(new_file_infos)
                    stats['files_added'] += inserted
            
            # 处理修改文件
            if modified_files:
                print(f"  [更新] 更新 {len(modified_files)} 个文件...")
                updated_count = 0
                for file_path in modified_files:
                    try:
                        file_info = self.builder.get_file_info(file_path, folder_type)
                        if file_info:
                            cursor.execute("""
                                UPDATE file_index_cache
                                SET file_size = ?,
                                    modified_time = ?,
                                    extracted_keywords = ?,
                                    last_checked = CURRENT_TIMESTAMP
                                WHERE file_path = ?
                            """, (
                                file_info['file_size'],
                                file_info['modified_time'],
                                file_info['extracted_keywords'],
                                file_path
                            ))
                            updated_count += 1
                    except Exception as e:
                        print(f"  [错误] 更新文件失败 {file_path}: {e}")
                        stats['errors'] += 1
                
                conn.commit()
                stats['files_updated'] += updated_count
            
            # 处理删除文件（标记为已删除）
            if deleted_files:
                print(f"  [删除] 标记 {len(deleted_files)} 个文件为已删除...")
                placeholders = ','.join(['?'] * len(deleted_files))
                cursor.execute(f"""
                    UPDATE file_index_cache
                    SET is_deleted = 1,
                        last_checked = CURRENT_TIMESTAMP
                    WHERE file_path IN ({placeholders})
                """, list(deleted_files))
                conn.commit()
                stats['files_deleted'] += len(deleted_files)
            
            # 更新所有文件的 last_checked（即使未变化）
            cursor.execute("""
                UPDATE file_index_cache
                SET last_checked = CURRENT_TIMESTAMP
                WHERE folder_type = ? AND is_deleted = 0
            """, (folder_type,))
            conn.commit()
            
            stats['files_checked'] += len(fs_files)
            
            conn.close()
        
        # 更新元数据
        current_time = datetime.now().isoformat()
        self.builder.update_metadata('last_incremental_update', current_time)
        self.builder.update_metadata('scan_status', 'idle')
        
        # 计算耗时
        elapsed_time = time.time() - start_time
        
        # 输出统计信息
        print()
        print("=" * 60)
        print("增量更新完成")
        print("=" * 60)
        print(f"新增文件: {stats['files_added']}")
        print(f"更新文件: {stats['files_updated']}")
        print(f"删除文件: {stats['files_deleted']}")
        print(f"检查文件: {stats['files_checked']}")
        print(f"错误数量: {stats['errors']}")
        print(f"耗时: {elapsed_time:.2f} 秒")
        print("=" * 60)
        
        return {
            'success': True,
            **stats,
            'elapsed_time': elapsed_time,
            'timestamp': current_time
        }


if __name__ == '__main__':
    # 测试代码
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # 获取数据库路径
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.normpath(os.path.join(_current_dir, '..', '..'))
    _default_db_path = os.path.join(_project_root, 'TR database', 'data_3years.db')
    _default_db_path = os.path.abspath(_default_db_path)
    db_path = os.getenv('DB_PATH', _default_db_path)
    
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(os.path.join(_project_root, db_path))
    
    # 获取基础文件夹路径
    base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
    
    # 创建更新器
    updater = FileIndexUpdater(db_path, base_folder)
    
    # 执行增量更新
    result = updater.update_index()
    
    if result['success']:
        print("\n✅ 增量更新成功!")
        sys.exit(0)
    else:
        print("\n❌ 增量更新失败!")
        sys.exit(1)
