#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件索引缓存查询器
功能：使用数据库索引快速查询文件
"""

import os
import sqlite3
import json
from typing import List, Optional, Dict
from datetime import datetime, timedelta


class FileIndexQuery:
    """文件索引缓存查询器"""
    
    def __init__(self, db_path: str):
        """
        初始化查询器
        
        Args:
            db_path: SQLite 数据库路径
        """
        self.db_path = db_path
    
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # 启用 WAL 模式
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn
    
    def is_index_available(self) -> bool:
        """
        检查索引是否可用
        
        Returns:
            索引是否可用
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='file_index_cache'
            """)
            exists = cursor.fetchone() is not None
            conn.close()
            return exists
        except Exception:
            return False
    
    def get_index_stats(self) -> Dict:
        """
        获取索引统计信息
        
        Returns:
            统计信息字典
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 总文件数
            cursor.execute("SELECT COUNT(*) as cnt FROM file_index_cache WHERE is_deleted = 0")
            total_files = cursor.fetchone()['cnt']
            
            # 按文件夹类型统计
            cursor.execute("""
                SELECT folder_type, COUNT(*) as cnt 
                FROM file_index_cache 
                WHERE is_deleted = 0 
                GROUP BY folder_type
            """)
            folder_stats = {row['folder_type']: row['cnt'] for row in cursor.fetchall()}
            
            conn.close()
            
            return {
                'total_files': total_files,
                'folder_stats': folder_stats,
                'available': True
            }
        except Exception as e:
            return {
                'total_files': 0,
                'folder_stats': {},
                'available': False,
                'error': str(e)
            }
    
    def find_files_by_keywords(self, keywords: List[str], 
                               folder_types: Optional[List[str]] = None,
                               verify_files: bool = True) -> List[str]:
        """
        根据关键词查找文件（使用索引）
        
        Args:
            keywords: 关键词列表
            folder_types: 文件夹类型列表（可选，如 ['Stockist Cert', 'IAT Formal']）
            verify_files: 是否验证文件存在
            
        Returns:
            匹配的文件路径列表
        """
        if not keywords:
            return []
        
        if not self.is_index_available():
            print("[警告] 文件索引不可用，将使用文件系统遍历")
            return []
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 规范化关键词（转大写，去空）
            normalized_keywords = [k.upper().strip() for k in keywords if k and k.strip()]
            if not normalized_keywords:
                conn.close()
                return []
            
            # 构建查询条件
            conditions = ["is_deleted = 0"]
            params = []
            
            # 文件夹类型过滤
            if folder_types:
                placeholders = ','.join(['?'] * len(folder_types))
                conditions.append(f"folder_type IN ({placeholders})")
                params.extend(folder_types)
            
            # 关键词匹配
            # 方式1：文件名匹配（使用LIKE）
            keyword_conditions = []
            for keyword in normalized_keywords:
                keyword_conditions.append("file_name LIKE ?")
                params.append(f'%{keyword}%')
            
            # 方式2：关键词JSON匹配（如果SQLite版本支持）
            # 尝试从extracted_keywords JSON中查找
            for keyword in normalized_keywords:
                keyword_conditions.append("extracted_keywords LIKE ?")
                params.append(f'%{keyword}%')
            
            if keyword_conditions:
                keyword_sql = "(" + " OR ".join(keyword_conditions) + ")"
                conditions.append(keyword_sql)
            
            # 构建完整查询
            query = f"""
                SELECT DISTINCT file_path, file_name
                FROM file_index_cache
                WHERE {' AND '.join(conditions)}
            """
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # 提取文件路径
            file_paths = [row['file_path'] for row in rows]
            
            # 验证文件存在（可选）
            if verify_files:
                valid_files = []
                invalid_count = 0
                for file_path in file_paths:
                    if os.path.exists(file_path):
                        valid_files.append(file_path)
                    else:
                        invalid_count += 1
                        # 可选：标记为已删除
                        try:
                            cursor.execute("""
                                UPDATE file_index_cache 
                                SET is_deleted = 1 
                                WHERE file_path = ?
                            """, (file_path,))
                        except Exception:
                            pass
                
                if invalid_count > 0:
                    conn.commit()
                    print(f"[索引查询] 发现 {invalid_count} 个文件不存在，已标记为已删除")
                
                file_paths = valid_files
            
            conn.close()
            
            return file_paths
            
        except Exception as e:
            print(f"[错误] 索引查询失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def find_files_by_folder_type(self, folder_type: str, 
                                  verify_files: bool = True) -> List[str]:
        """
        根据文件夹类型查找所有文件
        
        Args:
            folder_type: 文件夹类型
            verify_files: 是否验证文件存在
            
        Returns:
            文件路径列表
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            query = """
                SELECT DISTINCT file_path
                FROM file_index_cache
                WHERE folder_type = ? AND is_deleted = 0
            """
            
            cursor.execute(query, (folder_type,))
            rows = cursor.fetchall()
            file_paths = [row['file_path'] for row in rows]
            
            # 验证文件存在
            if verify_files:
                valid_files = []
                for file_path in file_paths:
                    if os.path.exists(file_path):
                        valid_files.append(file_path)
                file_paths = valid_files
            
            conn.close()
            return file_paths
        except Exception as e:
            print(f"[错误] 查询文件夹类型失败: {e}")
            return []
    
    def find_files_in_subfolder(self, folder_path: str, 
                                keywords: List[str]) -> List[str]:
        """
        在指定文件夹的子文件夹中查找文件（用于IAT Formal等场景）
        对于 IAT Formal，返回的是匹配的子文件夹路径，需要进一步获取文件夹内的所有PDF
        
        Args:
            folder_path: 父文件夹路径或子文件夹路径
            keywords: 关键词列表（用于匹配子文件夹名）。如果为空，返回该文件夹中的所有PDF文件
            
        Returns:
            匹配的文件路径列表（对于IAT Formal，返回文件夹内所有PDF；其他返回文件路径）
        """
        # 如果 keywords 为空，返回该文件夹中的所有 PDF 文件
        if not keywords:
            # 对于 IAT Formal，索引表中存储的是文件夹路径，需要遍历文件夹获取所有 PDF
            if not self.is_index_available():
                return []
            
            try:
                # 标准化文件夹路径
                folder_path_normalized = os.path.normpath(folder_path)
                
                # 检查文件夹是否存在
                if not os.path.exists(folder_path_normalized):
                    print(f"[索引查询] 文件夹不存在: {folder_path_normalized}")
                    return []
                
                # 如果路径是文件夹，遍历获取所有 PDF 文件
                if os.path.isdir(folder_path_normalized):
                    found_files = []
                    for root, dirs, files in os.walk(folder_path_normalized):
                        for file in files:
                            if file.lower().endswith('.pdf'):
                                pdf_path = os.path.join(root, file)
                                if os.path.exists(pdf_path):
                                    found_files.append(pdf_path)
                    print(f"[索引查询] 文件夹 {os.path.basename(folder_path_normalized)}: 遍历找到 {len(found_files)} 个 PDF 文件")
                    return found_files
                else:
                    # 如果是文件，直接返回
                    if folder_path_normalized.lower().endswith('.pdf'):
                        return [folder_path_normalized]
                    return []
            except Exception as e:
                print(f"[索引查询] 查询文件夹 {folder_path} 中的所有文件失败: {e}")
                import traceback
                traceback.print_exc()
                return []
        
        if not self.is_index_available():
            return []
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 规范化关键词
            normalized_keywords = [k.upper().strip() for k in keywords if k and k.strip()]
            if not normalized_keywords:
                conn.close()
                return []
            
            # 查找文件夹路径匹配的记录
            folder_path_normalized = os.path.normpath(folder_path).replace('\\', '/')
            
            # 构建查询：查找file_name（对于IAT Formal是文件夹名）或file_path包含关键词的记录
            keyword_conditions = []
            params = [folder_path_normalized]
            
            for keyword in normalized_keywords:
                keyword_conditions.append("(file_name LIKE ? OR file_path LIKE ?)")
                params.extend([f'%{keyword}%', f'%{keyword}%'])
            
            if not keyword_conditions:
                conn.close()
                return []
            
            query = f"""
                SELECT DISTINCT file_path, folder_type
                FROM file_index_cache
                WHERE folder_path = ?
                  AND is_deleted = 0
                  AND ({' OR '.join(keyword_conditions)})
            """
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # 对于 IAT Formal，file_path 实际上是文件夹路径
            # 需要获取该文件夹内的所有PDF文件
            all_files = []
            for row in rows:
                matched_path = row['file_path']
                folder_type = row['folder_type']
                
                if folder_type == 'IAT Formal':
                    # 这是文件夹路径，需要获取文件夹内的所有PDF
                    if os.path.exists(matched_path) and os.path.isdir(matched_path):
                        # 递归获取文件夹内所有PDF
                        for root, dirs, files in os.walk(matched_path):
                            for file in files:
                                if file.lower().endswith('.pdf'):
                                    pdf_path = os.path.join(root, file)
                                    if os.path.exists(pdf_path):
                                        all_files.append(pdf_path)
                else:
                    # 这是文件路径（包括 IAT Prelim），直接添加
                    if os.path.exists(matched_path):
                        all_files.append(matched_path)
            
            conn.close()
            
            return all_files
            
        except Exception as e:
            print(f"[错误] 子文件夹查询失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def check_file_exists_in_iat_prelim(self, source_filename: str, 
                                        base_folder: str = r"D:\Stockist&Test Report") -> Optional[str]:
        """
        检查 IAT Prelim 文件夹中是否已存在对应文件
        
        例如："Physical, chemical & geometry test report of C0146" 和 "C0146_IAT_Prelim" 是同一个文件
        
        Args:
            source_filename: 源文件名（例如："Physical, chemical & geometry test report of C0146.pdf"）
            base_folder: Stockist&Test Report 基础文件夹路径
            
        Returns:
            如果找到对应文件，返回文件路径；否则返回 None
        """
        if not self.is_index_available():
            return None
        
        try:
            import re
            
            # 从源文件名中提取可能的标识符
            # 匹配模式1：多个字母+数字的组合（如 SS79825, NT0094, ZZ3274）
            # 匹配模式2：单个字母+至少3位数字的组合（如 C0146, C0274, A1234）
            # 优先匹配较长的标识符（多个字母+数字）
            identifier_pattern = r'([A-Z]{2,}\d+|[A-Z]\d{3,})'
            matches = re.findall(identifier_pattern, source_filename.upper())
            
            if not matches:
                # 如果没找到，尝试更宽泛的匹配（单个字母+至少2位数字）
                identifier_pattern_fallback = r'([A-Z]\d{2,})'
                matches = re.findall(identifier_pattern_fallback, source_filename.upper())
            
            if not matches:
                print(f"[检查] 无法从文件名中提取标识符: {source_filename}")
                return None
            
            # 使用找到的标识符进行匹配（去重）
            # 优先使用较长的标识符（更准确）
            identifiers = sorted(list(set(matches)), key=len, reverse=True)
            print(f"[检查] 从文件名 '{source_filename}' 中提取的标识符: {identifiers}")
            
            if not identifiers:
                print(f"[检查] 警告：未能提取到标识符")
                return None
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 构建查询：检查 identifiers 字段中是否包含该标识符
            # 只要索引的 identifiers 字段中包含该标识符，就认为文件已存在
            # 例如：如果索引中有文件的 identifiers 包含 "SS70913"，就无需复制 "Physical, chemical & geometry test report of SS70913.pdf"
            conditions = [
                "folder_type = 'IAT Prelim'",
                "is_deleted = 0"
            ]
            params = []
            
            # 为每个标识符构建匹配条件
            # 在 identifiers 字段中查找该标识符（逗号分隔的字符串）
            identifier_conditions = []
            for identifier in identifiers:
                # 在 identifiers 字段中查找该标识符
                # 使用 LIKE 匹配，确保匹配完整的标识符（避免部分匹配）
                # 例如：查找 "SS70913" 时，匹配 ",SS70913," 或 "SS70913," 或 ",SS70913" 或 "SS70913"
                identifier_conditions.append("(identifiers LIKE ? OR identifiers LIKE ? OR identifiers LIKE ? OR identifiers = ?)")
                params.extend([
                    f'%,{identifier},%',  # 中间
                    f'{identifier},%',   # 开头
                    f'%,{identifier}',   # 结尾
                    identifier           # 完全匹配
                ])
            
            if identifier_conditions:
                conditions.append(f"({' OR '.join(identifier_conditions)})")
            
            query = f"""
                SELECT DISTINCT file_path, file_name, identifiers
                FROM file_index_cache
                WHERE {' AND '.join(conditions)}
                LIMIT 1
            """
            
            print(f"[检查] 执行查询，标识符: {identifiers}, 在 identifiers 字段中查找")
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            print(f"[检查] 查询结果: 找到 {len(rows)} 条记录")
            if len(rows) > 0:
                print(f"[检查] 索引的 identifiers 中包含标识符，文件已存在: {rows[0]['file_name']} (identifiers: {rows[0].get('identifiers', '')})")
                # 返回第一个匹配的文件路径（用于日志显示）
                file_path = rows[0]['file_path']
                if os.path.exists(file_path):
                    conn.close()
                    return file_path
                else:
                    # 即使文件不存在，只要索引中有记录，也认为文件已存在
                    print(f"[检查] 文件路径不存在，但索引中有记录，认为文件已存在")
                    conn.close()
                    return file_path  # 仍然返回路径，让调用者知道找到了
            
            conn.close()
            return None
            
        except Exception as e:
            print(f"[错误] 检查 IAT Prelim 文件失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def check_file_exists_in_private_formal(self, source_filename: str, 
                                             base_folder: str = r"D:\Stockist&Test Report") -> Optional[str]:
        """
        检查 Private Formal 文件夹中是否已存在对应文件
        
        例如："C0146.pdf" 和 "C0146_Private_Formal.pdf" 是同一个文件
        
        Args:
            source_filename: 源文件名（例如："C0146.pdf" 或 "SS78156.pdf"）
            base_folder: Stockist&Test Report 基础文件夹路径
            
        Returns:
            如果找到对应文件，返回文件路径；否则返回 None
        """
        if not self.is_index_available():
            return None
        
        try:
            import re
            
            # 从源文件名中提取标识符（使用与 IAT Prelim 相同的逻辑）
            identifier_pattern = r'([A-Z]{2,}\d+|[A-Z]\d{3,})'
            matches = re.findall(identifier_pattern, source_filename.upper())
            
            if not matches:
                identifier_pattern_fallback = r'([A-Z]\d{2,})'
                matches = re.findall(identifier_pattern_fallback, source_filename.upper())
            
            if not matches:
                return None
            
            identifiers = sorted(list(set(matches)), key=len, reverse=True)
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 构建查询：检查 identifiers 字段中是否包含该标识符
            conditions = [
                "folder_type = 'Private Formal'",
                "is_deleted = 0"
            ]
            params = []
            
            identifier_conditions = []
            for identifier in identifiers:
                identifier_conditions.append("(identifiers LIKE ? OR identifiers LIKE ? OR identifiers LIKE ? OR identifiers = ?)")
                params.extend([
                    f'%,{identifier},%',
                    f'{identifier},%',
                    f'%,{identifier}',
                    identifier
                ])
            
            if identifier_conditions:
                conditions.append(f"({' OR '.join(identifier_conditions)})")
            
            query = f"""
                SELECT DISTINCT file_path, file_name, identifiers
                FROM file_index_cache
                WHERE {' AND '.join(conditions)}
                LIMIT 1
            """
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            if len(rows) > 0:
                print(f"[检查] 索引的 identifiers 中包含标识符，文件已存在: {rows[0]['file_name']} (identifiers: {rows[0].get('identifiers', '')})")
                file_path = rows[0]['file_path']
                conn.close()
                return file_path
            
            conn.close()
            return None
            
        except Exception as e:
            print(f"[错误] 检查 Private Formal 文件失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def check_file_exists_in_private_prelim(self, source_filename: str, 
                                             base_folder: str = r"D:\Stockist&Test Report") -> Optional[str]:
        """
        检查 Private Prelim 文件夹中是否已存在对应文件
        
        例如："Physical, chemical & geometry test report of SS77294" 和 "SS77294_Private_Prelim" 是同一个文件
        
        Args:
            source_filename: 源文件名（例如："Physical, chemical & geometry test report of SS77294.pdf"）
            base_folder: Stockist&Test Report 基础文件夹路径
            
        Returns:
            如果找到对应文件，返回文件路径；否则返回 None
        """
        if not self.is_index_available():
            return None
        
        try:
            import re
            
            # 从源文件名中提取标识符（使用与 IAT Prelim 相同的逻辑）
            identifier_pattern = r'([A-Z]{2,}\d+|[A-Z]\d{3,})'
            matches = re.findall(identifier_pattern, source_filename.upper())
            
            if not matches:
                identifier_pattern_fallback = r'([A-Z]\d{2,})'
                matches = re.findall(identifier_pattern_fallback, source_filename.upper())
            
            if not matches:
                return None
            
            identifiers = sorted(list(set(matches)), key=len, reverse=True)
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 构建查询：检查 identifiers 字段中是否包含该标识符
            conditions = [
                "folder_type = 'Private Prelim'",
                "is_deleted = 0"
            ]
            params = []
            
            identifier_conditions = []
            for identifier in identifiers:
                identifier_conditions.append("(identifiers LIKE ? OR identifiers LIKE ? OR identifiers LIKE ? OR identifiers = ?)")
                params.extend([
                    f'%,{identifier},%',
                    f'{identifier},%',
                    f'%,{identifier}',
                    identifier
                ])
            
            if identifier_conditions:
                conditions.append(f"({' OR '.join(identifier_conditions)})")
            
            query = f"""
                SELECT DISTINCT file_path, file_name, identifiers
                FROM file_index_cache
                WHERE {' AND '.join(conditions)}
                LIMIT 1
            """
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            if len(rows) > 0:
                print(f"[检查] 索引的 identifiers 中包含标识符，文件已存在: {rows[0]['file_name']} (identifiers: {rows[0].get('identifiers', '')})")
                file_path = rows[0]['file_path']
                conn.close()
                return file_path
            
            conn.close()
            return None
            
        except Exception as e:
            print(f"[错误] 检查 Private Prelim 文件失败: {e}")
            import traceback
            traceback.print_exc()
            return None
