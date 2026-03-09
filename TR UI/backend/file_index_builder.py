#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件索引缓存建立器
功能：扫描文件系统，建立文件索引缓存
"""

import os
import sqlite3
import json
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import time


class FileIndexBuilder:
    """文件索引缓存建立器"""
    
    # 文件夹类型映射
    FOLDER_TYPES = {
        'Stockist Cert': 'Stockist Cert',
        'Private Formal': 'Private Formal',
        'Private Prelim': 'Private Prelim',
        'IAT Formal': 'IAT Formal',
        'IAT Prelim': 'IAT Prelim'
    }
    
    def __init__(self, db_path: str, base_folder: str = None):
        """
        初始化索引建立器
        
        Args:
            db_path: SQLite 数据库路径
            base_folder: Stockist&Test Report 文件夹的基础路径
                        如果为None，从环境变量读取
        """
        self.db_path = db_path
        if base_folder is None:
            from dotenv import load_dotenv
            load_dotenv()
            base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
        self.base_folder = base_folder
        
        # 定义需要扫描的文件夹
        self.scan_folders = {
            'Stockist Cert': os.path.join(base_folder, 'Stockist Cert'),
            'Private Formal': os.path.join(base_folder, 'Private Formal'),
            'Private Prelim': os.path.join(base_folder, 'Private Prelim'),
            'IAT Formal': os.path.join(base_folder, 'IAT Formal'),
            'IAT Prelim': os.path.join(base_folder, 'IAT Prelim')
        }
        
        # 批量插入大小
        self.batch_size = 1000
        
    def extract_keywords(self, file_name: str, file_path: str = '') -> List[str]:
        """
        从文件名中提取关键词
        
        Args:
            file_name: 文件名（不含路径）
            file_path: 文件完整路径（可选，用于从路径中提取关键词）
            
        Returns:
            关键词列表（JSON字符串格式）
        """
        keywords = set()
        
        # 移除文件扩展名
        name_without_ext = os.path.splitext(file_name)[0]
        
        # 1. 提取数字序列（长度>=3）
        number_pattern = r'\d{3,}'  # 至少3位数字
        numbers = re.findall(number_pattern, name_without_ext)
        for num in numbers:
            keywords.add(num)
        
        # 2. 提取字母数字组合（如证书编号格式）
        # 匹配：字母+数字 或 数字+字母 的组合
        alphanumeric_pattern = r'[A-Za-z]+\d+|\d+[A-Za-z]+|[A-Za-z]+\d+[A-Za-z]*'
        alphanumeric = re.findall(alphanumeric_pattern, name_without_ext, re.IGNORECASE)
        for item in alphanumeric:
            # 只保留长度>=3的组合
            if len(item) >= 3:
                keywords.add(item.upper())
        
        # 3. 按分隔符分割
        # 常见分隔符：-, _, 空格, .
        separators = r'[-_\s.]+'
        parts = re.split(separators, name_without_ext)
        for part in parts:
            part = part.strip()
            # 保留长度>=2的片段
            if len(part) >= 2:
                keywords.add(part.upper())
        
        # 4. 从文件路径中提取（如果提供）
        if file_path:
            # 提取路径中的文件夹名和文件名部分
            path_parts = file_path.replace('\\', '/').split('/')
            for part in path_parts:
                if part and len(part) >= 2:
                    # 提取数字序列
                    nums = re.findall(number_pattern, part)
                    for num in nums:
                        keywords.add(num)
                    # 提取字母数字组合
                    alnums = re.findall(alphanumeric_pattern, part, re.IGNORECASE)
                    for item in alnums:
                        if len(item) >= 3:
                            keywords.add(item.upper())
        
        # 5. 去重和规范化
        # 转换为列表并排序
        keywords_list = sorted(list(keywords))
        
        # 返回JSON格式的字符串
        return json.dumps(keywords_list, ensure_ascii=False)
    
    def extract_identifiers(self, file_name: str) -> str:
        """
        从文件名中提取标识符（如 SS70913、C0146、NW00018 等）
        
        Args:
            file_name: 文件名（不含路径）
            
        Returns:
            逗号分隔的标识符字符串（如 "SS70913,C0146"），如果没有找到则返回空字符串
        """
        import re
        
        identifiers = set()
        
        # 移除文件扩展名
        name_without_ext = os.path.splitext(file_name)[0].upper()
        
        # 匹配模式1：多个字母+数字的组合（如 SS79825, NT0094, ZZ3274, NW00018）
        # 匹配模式2：单个字母+至少3位数字的组合（如 C0146, C0274, A1234）
        identifier_pattern = r'([A-Z]{2,}\d+|[A-Z]\d{3,})'
        matches = re.findall(identifier_pattern, name_without_ext)
        
        if not matches:
            # 如果没找到，尝试更宽泛的匹配（单个字母+至少2位数字）
            identifier_pattern_fallback = r'([A-Z]\d{2,})'
            matches = re.findall(identifier_pattern_fallback, name_without_ext)
        
        # 去重并排序
        for match in matches:
            identifiers.add(match)
        
        # 返回逗号分隔的字符串
        return ','.join(sorted(identifiers))
    
    def get_file_info(self, file_path: str, folder_type: str) -> Optional[Dict]:
        """
        获取文件信息
        
        Args:
            file_path: 文件完整路径
            folder_type: 文件夹类型
            
        Returns:
            文件信息字典，如果文件不存在或无法访问则返回None
        """
        try:
            if not os.path.exists(file_path):
                return None
            
            stat = os.stat(file_path)
            file_name = os.path.basename(file_path)
            folder_path = os.path.dirname(file_path)
            
            # 提取关键词
            keywords_json = self.extract_keywords(file_name, file_path)
            
            # 提取标识符（如 SS70913、C0146 等）
            identifiers_str = self.extract_identifiers(file_name)
            
            return {
                'file_path': file_path,
                'file_name': file_name,
                'folder_path': folder_path,
                'folder_type': folder_type,
                'file_size': stat.st_size,
                'modified_time': stat.st_mtime,  # Unix时间戳
                'extracted_keywords': keywords_json,
                'identifiers': identifiers_str,
                'is_deleted': 0
            }
        except (OSError, PermissionError) as e:
            print(f"[警告] 无法访问文件 {file_path}: {e}")
            return None
        except Exception as e:
            print(f"[错误] 处理文件 {file_path} 时出错: {e}")
            return None
    
    def scan_folder(self, folder_path: str, folder_type: str, 
                   callback=None) -> Tuple[int, int]:
        """
        扫描文件夹，收集文件信息
        
        Args:
            folder_path: 文件夹路径
            folder_type: 文件夹类型
            callback: 进度回调函数 (current_count, total_count, current_file)
            
        Returns:
            (扫描的文件数, 成功处理的文件数)
        """
        if not os.path.exists(folder_path):
            print(f"[警告] 文件夹不存在: {folder_path}")
            return 0, 0
        
        file_infos = []
        scanned_count = 0
        error_count = 0
        
        print(f"[扫描] 开始扫描文件夹: {folder_path}")
        
        try:
            # 使用 os.walk 递归遍历
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if not file.lower().endswith('.pdf'):
                        continue
                    
                    scanned_count += 1
                    file_path = os.path.join(root, file)
                    
                    # 获取文件信息
                    file_info = self.get_file_info(file_path, folder_type)
                    if file_info:
                        file_infos.append(file_info)
                    else:
                        error_count += 1
                    
                    # 调用进度回调
                    if callback:
                        callback(scanned_count, len(file_infos), file_path)
            
            print(f"[扫描] 完成扫描: {folder_path}")
            print(f"  - 扫描文件数: {scanned_count}")
            print(f"  - 成功处理: {len(file_infos)}")
            print(f"  - 错误/跳过: {error_count}")
            
        except Exception as e:
            print(f"[错误] 扫描文件夹失败 {folder_path}: {e}")
            import traceback
            traceback.print_exc()
        
        return scanned_count, len(file_infos)
    
    def batch_insert_files(self, file_infos: List[Dict]) -> int:
        """
        批量插入文件信息到数据库
        
        Args:
            file_infos: 文件信息列表
            
        Returns:
            成功插入的记录数
        """
        if not file_infos:
            return 0
        
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        # 启用 WAL 模式
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        
        cursor = conn.cursor()
        inserted_count = 0
        error_count = 0
        
        try:
            # 分批插入
            for i in range(0, len(file_infos), self.batch_size):
                batch = file_infos[i:i + self.batch_size]
                
                try:
                    # 使用 INSERT OR REPLACE 处理重复
                    cursor.executemany("""
                        INSERT OR REPLACE INTO file_index_cache (
                            file_path, file_name, folder_path, folder_type,
                            file_size, modified_time, extracted_keywords, identifiers,
                            is_deleted, last_checked
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, [
                        (
                            info['file_path'],
                            info['file_name'],
                            info['folder_path'],
                            info['folder_type'],
                            info['file_size'],
                            info['modified_time'],
                            info['extracted_keywords'],
                            info.get('identifiers', ''),  # 使用 get 以兼容旧数据
                            info['is_deleted']
                        )
                        for info in batch
                    ])
                    
                    conn.commit()
                    inserted_count += len(batch)
                    
                    if (i + self.batch_size) % (self.batch_size * 10) == 0:
                        print(f"[插入] 已插入 {inserted_count} 条记录...")
                
                except Exception as e:
                    error_count += len(batch)
                    print(f"[错误] 批量插入失败 (批次 {i//self.batch_size + 1}): {e}")
                    conn.rollback()
                    # 继续处理下一批
        
        finally:
            conn.close()
        
        if error_count > 0:
            print(f"[警告] 插入过程中有 {error_count} 条记录失败")
        
        return inserted_count
    
    def update_metadata(self, key: str, value: str):
        """
        更新元数据
        
        Args:
            key: 元数据键
            value: 元数据值
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO file_index_metadata (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (key, value))
            conn.commit()
        except Exception as e:
            print(f"[错误] 更新元数据失败 ({key}): {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def get_metadata(self, key: str, default: str = '') -> str:
        """
        获取元数据
        
        Args:
            key: 元数据键
            default: 默认值
            
        Returns:
            元数据值
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT value FROM file_index_metadata WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default
        except Exception as e:
            print(f"[错误] 获取元数据失败 ({key}): {e}")
            return default
        finally:
            conn.close()
    
    def build_index(self, clear_existing: bool = False, 
                   progress_callback=None) -> Dict:
        """
        建立全量索引
        
        Args:
            clear_existing: 是否清空现有索引
            progress_callback: 进度回调函数 (folder_type, current, total, message)
            
        Returns:
            建立结果统计
        """
        start_time = time.time()
        
        print("=" * 60)
        print("开始建立文件索引缓存")
        print("=" * 60)
        print(f"数据库路径: {self.db_path}")
        print(f"基础文件夹: {self.base_folder}")
        print()
        
        # 更新状态为扫描中
        self.update_metadata('scan_status', 'scanning')
        
        # 如果清空现有索引
        if clear_existing:
            print("[清理] 清空现有索引...")
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM file_index_cache")
                cursor.execute("UPDATE file_index_metadata SET value = '0' WHERE key = 'total_files_indexed'")
                conn.commit()
                print("[清理] 已清空现有索引")
            except Exception as e:
                print(f"[错误] 清空索引失败: {e}")
                conn.rollback()
            finally:
                conn.close()
        
        # 统计信息
        total_scanned = 0
        total_inserted = 0
        folder_stats = {}
        all_file_infos = []
        
        # 扫描每个文件夹并收集文件信息
        for folder_type, folder_path in self.scan_folders.items():
            if progress_callback:
                progress_callback(folder_type, 0, 0, f"开始扫描 {folder_type}...")
            
            if not os.path.exists(folder_path):
                print(f"[警告] 文件夹不存在: {folder_path}")
                folder_stats[folder_type] = {'scanned': 0, 'processed': 0}
                continue
            
            folder_file_infos = []
            scanned_count = 0
            error_count = 0
            
            print(f"[扫描] 开始扫描文件夹: {folder_path}")
            
            try:
                # IAT Formal 只扫描子文件夹名称，不递归到文件
                if folder_type == 'IAT Formal':
                    # 只扫描直接子文件夹
                    try:
                        items = os.listdir(folder_path)
                        for item in items:
                            item_path = os.path.join(folder_path, item)
                            if os.path.isdir(item_path):
                                scanned_count += 1
                                
                                # 将子文件夹作为"文件"索引（实际上存储的是文件夹路径）
                                # file_path 存储文件夹路径，file_name 存储文件夹名称
                                folder_info = {
                                    'file_path': item_path,  # 实际上是文件夹路径
                                    'file_name': item,  # 文件夹名称
                                    'folder_path': folder_path,
                                    'folder_type': folder_type,
                                    'file_size': 0,  # 文件夹没有大小
                                    'modified_time': os.path.getmtime(item_path) if os.path.exists(item_path) else 0,
                                    'extracted_keywords': self.extract_keywords(item, item_path),
                                    'is_deleted': 0
                                }
                                folder_file_infos.append(folder_info)
                                all_file_infos.append(folder_info)
                                
                                if progress_callback and scanned_count % 10 == 0:
                                    progress_callback(
                                        folder_type,
                                        scanned_count,
                                        scanned_count,
                                        f"扫描文件夹: {item}"
                                    )
                    except Exception as e:
                        print(f"[错误] 扫描子文件夹失败 {folder_path}: {e}")
                        error_count += 1
                else:
                    # 其他文件夹类型（包括 IAT Prelim）：递归扫描所有 PDF 文件
                    for root, dirs, files in os.walk(folder_path):
                        for file in files:
                            if not file.lower().endswith('.pdf'):
                                continue
                            
                            scanned_count += 1
                            file_path = os.path.join(root, file)
                            
                            # 获取文件信息
                            file_info = self.get_file_info(file_path, folder_type)
                            if file_info:
                                folder_file_infos.append(file_info)
                                all_file_infos.append(file_info)
                            else:
                                error_count += 1
                            
                            # 调用进度回调
                            if progress_callback and scanned_count % 100 == 0:
                                progress_callback(
                                    folder_type, 
                                    scanned_count, 
                                    scanned_count, 
                                    f"扫描: {os.path.basename(file)}"
                                )
                
                print(f"[扫描] 完成扫描: {folder_path}")
                if folder_type == 'IAT Formal':
                    print(f"  - 扫描子文件夹数: {scanned_count}")
                else:
                    print(f"  - 扫描文件数: {scanned_count}")
                print(f"  - 成功处理: {len(folder_file_infos)}")
                print(f"  - 错误/跳过: {error_count}")
                
                total_scanned += scanned_count
                folder_stats[folder_type] = {
                    'scanned': scanned_count,
                    'processed': len(folder_file_infos)
                }
                
                if progress_callback:
                    progress_callback(
                        folder_type, 
                        scanned_count, 
                        scanned_count, 
                        f"完成扫描 {folder_type}"
                    )
            
            except Exception as e:
                print(f"[错误] 扫描文件夹失败 {folder_path}: {e}")
                import traceback
                traceback.print_exc()
                folder_stats[folder_type] = {'scanned': 0, 'processed': 0}
        
        # 批量插入所有文件信息
        print()
        print(f"[插入] 开始批量插入 {len(all_file_infos)} 条文件信息...")
        total_inserted = self.batch_insert_files(all_file_infos)
        
        # 更新元数据
        current_time = datetime.now().isoformat()
        self.update_metadata('last_full_scan', current_time)
        self.update_metadata('total_files_indexed', str(total_inserted))
        self.update_metadata('scan_status', 'idle')
        
        # 计算耗时
        elapsed_time = time.time() - start_time
        
        # 输出统计信息
        print()
        print("=" * 60)
        print("索引建立完成")
        print("=" * 60)
        print(f"总扫描文件数: {total_scanned}")
        print(f"成功索引文件数: {total_inserted}")
        print(f"耗时: {elapsed_time:.2f} 秒")
        print()
        print("各文件夹统计:")
        for folder_type, stats in folder_stats.items():
            print(f"  {folder_type}:")
            print(f"    - 扫描: {stats['scanned']} 个文件")
            print(f"    - 处理: {stats['processed']} 个文件")
        print("=" * 60)
        
        return {
            'success': True,
            'total_scanned': total_scanned,
            'total_indexed': total_inserted,
            'elapsed_time': elapsed_time,
            'folder_stats': folder_stats,
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
    
    # 创建索引建立器
    builder = FileIndexBuilder(db_path, base_folder)
    
    # 建立索引
    result = builder.build_index(clear_existing=True)
    
    if result['success']:
        print("\n✅ 索引建立成功!")
        sys.exit(0)
    else:
        print("\n❌ 索引建立失败!")
        sys.exit(1)
