#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件索引缓存查询器
功能：使用数据库索引快速查询文件
"""

import os
import json
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from db_adapter import get_connection as get_db_connection, is_postgres

# 导入 logger
try:
    from logger_config import get_logger
    logger = get_logger('file_index_query')
except ImportError:
    import logging
    logger = logging.getLogger('file_index_query')


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
        return get_db_connection()

    def _sql(self, sql_text: str) -> str:
        if is_postgres():
            return sql_text.replace('?', '%s')
        return sql_text

    def _execute(self, cursor, sql_text: str, params=()):
        return cursor.execute(self._sql(sql_text), params)

    def _table_exists(self, cursor, table_name: str) -> bool:
        try:
            if is_postgres():
                self._execute(
                    cursor,
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = %s
                    ) AS exists
                    """,
                    (table_name.lower(),)
                )
            else:
                # SQLite: 使用简单的查询检查表是否存在
                self._execute(
                    cursor,
                    """
                    SELECT COUNT(*) as cnt
                    FROM sqlite_master
                    WHERE type='table' AND name=?
                    """,
                    (table_name,)
                )
                row = cursor.fetchone()
                if row:
                    count = row.get('cnt', 0) if hasattr(row, 'get') else (row['cnt'] if 'cnt' in row else row[0])
                    return bool(count > 0)
                return False
            
            row = cursor.fetchone()
            if not row:
                return False
            if isinstance(row, dict):
                return bool(row.get('exists', False))
            if hasattr(row, 'keys'):
                return bool(row.get('exists', False))
            return bool(row[0])
        except Exception as e:
            # 如果查询失败，尝试直接查询表
            try:
                if is_postgres():
                    self._execute(cursor, f'SELECT 1 FROM "{table_name}" LIMIT 1')
                else:
                    self._execute(cursor, f'SELECT 1 FROM {table_name} LIMIT 1')
                cursor.fetchone()
                return True
            except Exception:
                return False

    def _placeholders(self, count: int) -> str:
        return ','.join(['%s' if is_postgres() else '?'] * count)
    
    def _bool_value(self, value: bool) -> str:
        """返回布尔值的 SQL 表示（PostgreSQL 使用 TRUE/FALSE，SQLite 使用 1/0）"""
        # 每次调用时重新检查，确保获取最新的数据库类型
        from db_adapter import is_postgres as check_postgres
        is_pg = check_postgres()
        if is_pg:
            result = 'TRUE' if value else 'FALSE'
        else:
            result = '1' if value else '0'
        # 添加调试日志（仅在出错时使用）
        try:
            if is_pg and (result == '0' or result == '1'):
                logger.error("[INDEX QUERY] ERROR: PostgreSQL detected but _bool_value returned '" + result + "' instead of 'TRUE'/'FALSE'")
            elif not is_pg and (result == 'TRUE' or result == 'FALSE'):
                logger.error("[INDEX QUERY] ERROR: SQLite detected but _bool_value returned '" + result + "' instead of '1'/'0'")
        except Exception:
            pass
        return result
    
    def is_index_available(self) -> bool:
        """
        检查索引是否可用
        
        Returns:
            索引是否可用
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            exists = self._table_exists(cursor, 'file_index_cache')
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
            self._execute(cursor, f"SELECT COUNT(*) as cnt FROM file_index_cache WHERE is_deleted = {self._bool_value(False)}")
            total_files = cursor.fetchone()['cnt']
            
            # 按文件夹类型统计
            self._execute(cursor, f"""
                SELECT folder_type, COUNT(*) as cnt 
                FROM file_index_cache 
                WHERE is_deleted = {self._bool_value(False)} 
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
            try:
                logger.warning("[WARNING] File index not available, will use filesystem traversal")
            except Exception:
                pass
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
            conditions = [f"is_deleted = {self._bool_value(False)}"]
            params = []
            
            # 文件夹类型过滤
            if folder_types:
                placeholders = self._placeholders(len(folder_types))
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
            
            # 方式3：identifiers 字段匹配（用于匹配 stockist_cert 和 rm_dn_no）
            for keyword in normalized_keywords:
                keyword_conditions.append("identifiers LIKE ?")
                params.append(f'%{keyword}%')
            
            # 方式4：folder_path 匹配（用于匹配子文件夹名称，如 IAT Formal/HL2322）
            for keyword in normalized_keywords:
                keyword_conditions.append("folder_path LIKE ?")
                params.append(f'%{keyword}%')
            
            if keyword_conditions:
                keyword_sql = "(" + " OR ".join(keyword_conditions) + ")"
                conditions.append(keyword_sql)
            else:
                # 如果没有关键词条件，返回空结果
                conn.close()
                try:
                    logger.debug("[INDEX QUERY] No keyword conditions generated, returning empty result")
                except Exception:
                    pass
                return []
            
            # 构建完整查询
            where_clause = ' AND '.join(conditions)
            query = f"""
                SELECT DISTINCT file_path, file_name, identifiers
                FROM file_index_cache
                WHERE {where_clause}
            """
            
            # 添加调试日志（使用安全的字符串拼接，避免编码错误）
            try:
                logger.info("[INDEX QUERY] Executing query with " + str(len(normalized_keywords)) + " keywords")
                if folder_types:
                    logger.info("[INDEX QUERY] Folder types: " + str(folder_types))
                if normalized_keywords:
                    sample_keywords = normalized_keywords[:5]
                    logger.info("[INDEX QUERY] Sample keywords: " + str(sample_keywords))
                # 添加 SQL 查询调试信息（显示转换后的 SQL）
                converted_sql = self._sql(query)
                logger.info("[INDEX QUERY] SQL WHERE clause: " + where_clause)
                logger.info("[INDEX QUERY] is_postgres: " + str(is_postgres()))
                logger.info("[INDEX QUERY] _bool_value(False): " + str(self._bool_value(False)))
                logger.info("[INDEX QUERY] Converted SQL (first 200 chars): " + converted_sql[:200])
            except (UnicodeEncodeError, UnicodeDecodeError, Exception) as e:
                try:
                    logger.error("[INDEX QUERY] Error logging query info: " + str(e))
                except Exception:
                    pass
            
            try:
                self._execute(cursor, query, params)
            except Exception as query_error:
                # 记录查询错误详情
                try:
                    error_msg = str(query_error)
                    logger.error("[INDEX QUERY] Query execution failed: " + error_msg)
                    logger.error("[INDEX QUERY] Query: " + query[:500])
                    logger.error("[INDEX QUERY] Params count: " + str(len(params)))
                except Exception:
                    pass
                raise
            rows = cursor.fetchall()
            
            # 添加调试日志（使用安全的字符串拼接，避免编码错误）
            try:
                logger.info("[INDEX QUERY] Query returned " + str(len(rows)) + " rows")
                if len(rows) == 0:
                    logger.warning("[INDEX QUERY] No files found in index. Keywords: " + str(normalized_keywords[:5]))
                    logger.warning("[INDEX QUERY] Folder types: " + str(folder_types))
                    # 检查索引中是否有该文件夹类型的任何文件
                    check_query = f"SELECT COUNT(*) FROM file_index_cache WHERE folder_type IN ({self._placeholders(len(folder_types))}) AND is_deleted = {self._bool_value(False)}"
                    cursor.execute(self._sql(check_query), folder_types)
                    total_count = cursor.fetchone()[0]
                    logger.warning("[INDEX QUERY] Total files in folder_type(s) " + str(folder_types) + ": " + str(total_count))
                if rows:
                    try:
                        sample_files = []
                        for row in rows[:5]:
                            try:
                                file_name = row.get('file_name', '') if hasattr(row, 'get') else (row['file_name'] if 'file_name' in row else '')
                                if file_name:
                                    # 安全地转换为字符串，避免编码错误
                                    file_name_str = str(file_name).encode('ascii', 'ignore').decode('ascii')
                                    if file_name_str:
                                        sample_files.append(file_name_str)
                            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                                pass
                        if sample_files:
                            logger.info("[INDEX QUERY] Sample files: " + str(sample_files))
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception) as e:
                        try:
                            logger.warning("[INDEX QUERY] Error processing sample files: " + str(e))
                        except Exception:
                            pass
            except (UnicodeEncodeError, UnicodeDecodeError, Exception) as e:
                try:
                    logger.error("[INDEX QUERY] Error logging query results: " + str(e))
                except Exception:
                    pass
            
            # 提取文件路径（安全访问，避免编码错误）
            file_paths = []
            for i, row in enumerate(rows):
                try:
                    # 尝试多种方式访问 file_path
                    file_path = None
                    if hasattr(row, 'get'):
                        # dict-like 对象（PostgreSQL dict_row）
                        # PostgreSQL 可能返回小写字段名，尝试多种可能
                        file_path = row.get('file_path') or row.get('FILE_PATH') or row.get('File_Path', '')
                    elif isinstance(row, dict):
                        file_path = row.get('file_path') or row.get('FILE_PATH') or row.get('File_Path', '')
                    elif isinstance(row, (list, tuple)):
                        # tuple/list（SQLite）
                        file_path = row[0] if len(row) > 0 else ''
                    else:
                        # 尝试直接访问（多种可能的字段名）
                        try:
                            file_path = row.get('file_path', '') if hasattr(row, 'get') else row['file_path']
                        except (KeyError, TypeError):
                            # 尝试小写
                            try:
                                file_path = row.get('file_path', '') if hasattr(row, 'get') else ''
                            except:
                                file_path = None
                    
                    if file_path:
                        file_paths.append(str(file_path))
                    else:
                        # 调试：记录无法提取 file_path 的行，并尝试打印所有可用的键
                        try:
                            row_type_str = str(type(row))
                            if hasattr(row, 'keys'):
                                row_keys = list(row.keys())
                                row_keys_str = str(row_keys)
                                # 尝试使用第一个键作为 file_path（如果是 tuple/list）
                                if isinstance(row, (list, tuple)) and len(row) > 0:
                                    file_path = str(row[0])
                                    if file_path:
                                        file_paths.append(file_path)
                                        logger.info("[INDEX QUERY] Row " + str(i) + ": Extracted file_path from tuple index 0")
                                else:
                                    logger.warning("[INDEX QUERY] Row " + str(i) + ": Cannot extract file_path, row type: " + row_type_str + ", row keys: " + row_keys_str)
                                    # 尝试使用第一个键的值
                                    if row_keys:
                                        first_key = row_keys[0]
                                        try:
                                            potential_path = row.get(first_key, '') if hasattr(row, 'get') else ''
                                            if potential_path and ('/' in str(potential_path) or '\\' in str(potential_path)):
                                                file_paths.append(str(potential_path))
                                                logger.info("[INDEX QUERY] Row " + str(i) + ": Using first key as file_path")
                                        except Exception:
                                            pass
                            else:
                                logger.warning("[INDEX QUERY] Row " + str(i) + ": Cannot extract file_path, row type: " + row_type_str + ", no keys() method")
                        except Exception as debug_e:
                            try:
                                logger.warning("[INDEX QUERY] Row " + str(i) + ": Error in debug logging: " + str(debug_e))
                            except:
                                pass
                except (UnicodeEncodeError, UnicodeDecodeError, Exception) as e:
                    # 如果访问 file_path 时出错，尝试其他方式
                    try:
                        if isinstance(row, dict) or hasattr(row, 'get'):
                            file_path = row.get('file_path', '') if hasattr(row, 'get') else row.get('file_path', '')
                        elif isinstance(row, (list, tuple)):
                            file_path = row[0] if len(row) > 0 else ''
                        else:
                            file_path = None
                        
                        if file_path:
                            file_paths.append(str(file_path))
                        else:
                            try:
                                error_str = str(e)
                                row_type_str = str(type(row))
                                logger.warning("[INDEX QUERY] Row " + str(i) + ": Error extracting file_path: " + error_str + ", row type: " + row_type_str)
                            except Exception:
                                pass
                    except Exception as e2:
                        try:
                            error_str2 = str(e2)
                            logger.warning("[INDEX QUERY] Row " + str(i) + ": Failed to extract file_path after error: " + error_str2)
                        except Exception:
                            pass
            
            # 记录提取结果
            try:
                logger.info("[INDEX QUERY] Extracted " + str(len(file_paths)) + " file paths from " + str(len(rows)) + " rows")
            except Exception:
                pass
            
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
                            self._execute(cursor, f"""
                                UPDATE file_index_cache 
                                SET is_deleted = {self._bool_value(True)} 
                                WHERE file_path = ?
                            """, (file_path,))
                        except Exception:
                            pass
                
                if invalid_count > 0:
                    conn.commit()
                    try:
                        logger.info("[INDEX QUERY] Found " + str(invalid_count) + " files that do not exist, marked as deleted")
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                
                file_paths = valid_files
            
            conn.close()
            
            return file_paths
            
        except Exception as e:
            try:
                error_msg = str(e)
                logger.error("[ERROR] Index query failed: " + error_msg)
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                try:
                    logger.error("[ERROR] Index query failed")
                except Exception:
                    pass
            import traceback
            try:
                traceback.print_exc()
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
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
            
            query = f"""
                SELECT DISTINCT file_path
                FROM file_index_cache
                WHERE folder_type = ? AND is_deleted = {self._bool_value(False)}
            """
            
            self._execute(cursor, query, (folder_type,))
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
            try:
                error_msg = str(e)
                logger.error("[ERROR] Query folder type failed: " + error_msg)
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                try:
                    logger.error("[ERROR] Query folder type failed")
                except Exception:
                    pass
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
                    try:
                        try:
                            logger.warning("[INDEX QUERY] Folder does not exist: " + str(folder_path_normalized))
                        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                            pass
                    except Exception:
                        pass
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
                    try:
                        try:
                            folder_name = os.path.basename(folder_path_normalized)
                            logger.debug("[INDEX QUERY] Folder " + str(folder_name) + ": found " + str(len(found_files)) + " PDF files")
                        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                            pass
                    except Exception:
                        pass
                    return found_files
                else:
                    # 如果是文件，直接返回
                    if folder_path_normalized.lower().endswith('.pdf'):
                        return [folder_path_normalized]
                    return []
            except Exception as e:
                try:
                    error_msg = str(e)
                    try:
                        logger.error("[INDEX QUERY] Failed to query all files in folder: " + str(folder_path) + ", error: " + error_msg)
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        logger.error("[INDEX QUERY] Failed to query all files in folder")
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    try:
                        logger.error("[INDEX QUERY] Failed to query all files in folder")
                    except Exception:
                        pass
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
                  AND is_deleted = {self._bool_value(False)}
                  AND ({' OR '.join(keyword_conditions)})
            """
            
            self._execute(cursor, query, params)
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
            try:
                error_msg = str(e)
                logger.error("[ERROR] Subfolder query failed: " + error_msg)
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                try:
                    logger.error("[ERROR] Subfolder query failed")
                except Exception:
                    pass
            import traceback
            try:
                traceback.print_exc()
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
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
                try:
                    try:
                        logger.debug("[CHECK] Cannot extract identifier from filename: " + str(source_filename))
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                except Exception:
                    pass
                return None
            
            # 使用找到的标识符进行匹配（去重）
            # 优先使用较长的标识符（更准确）
            identifiers = sorted(list(set(matches)), key=len, reverse=True)
            try:
                try:
                    logger.debug("[CHECK] Extracted identifiers from filename: " + str(source_filename) + ", identifiers: " + str(identifiers))
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            
            if not identifiers:
                try:
                    logger.warning("[CHECK] Warning: Failed to extract identifier")
                except Exception:
                    pass
                return None
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 构建查询：检查 identifiers 字段中是否包含该标识符
            # 只要索引的 identifiers 字段中包含该标识符，就认为文件已存在
            # 例如：如果索引中有文件的 identifiers 包含 "SS70913"，就无需复制 "Physical, chemical & geometry test report of SS70913.pdf"
            conditions = [
                "folder_type = 'IAT Prelim'",
                f"is_deleted = {self._bool_value(False)}"
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
            
            try:
                try:
                    logger.debug("[CHECK] Executing query, identifiers: " + str(identifiers) + ", searching in identifiers field")
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            self._execute(cursor, query, params)
            rows = cursor.fetchall()
            
            try:
                try:
                    logger.debug("[CHECK] Query result: found " + str(len(rows)) + " records")
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            if len(rows) > 0:
                row0 = rows[0]
                identifiers = row0['identifiers'] if not isinstance(row0, dict) else row0.get('identifiers', '')
                try:
                    try:
                        file_name = row0.get('file_name', '') if hasattr(row0, 'get') else (row0['file_name'] if 'file_name' in row0 else '')
                        logger.debug("[CHECK] Index identifiers contain identifier, file exists: " + str(file_name) + " (identifiers: " + str(identifiers) + ")")
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
                # 返回第一个匹配的文件路径（用于日志显示）
                file_path = rows[0]['file_path']
                if os.path.exists(file_path):
                    conn.close()
                    return file_path
                else:
                    # 即使文件不存在，只要索引中有记录，也认为文件已存在
                    try:
                        logger.warning("[CHECK] File path does not exist, but index has record, considering file exists")
                    except Exception:
                        pass
                    conn.close()
                    return file_path  # 仍然返回路径，让调用者知道找到了
            
            conn.close()
            return None
            
        except Exception as e:
            try:
                error_msg = str(e)
                logger.error("[ERROR] Failed to check IAT Prelim file: " + error_msg)
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                try:
                    logger.error("[ERROR] Failed to check IAT Prelim file")
                except Exception:
                    pass
            import traceback
            try:
                traceback.print_exc()
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
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
                f"is_deleted = {self._bool_value(False)}"
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
            
            self._execute(cursor, query, params)
            rows = cursor.fetchall()
            
            if len(rows) > 0:
                row0 = rows[0]
                identifiers = row0['identifiers'] if not isinstance(row0, dict) else row0.get('identifiers', '')
                try:
                    try:
                        file_name = row0.get('file_name', '') if hasattr(row0, 'get') else (row0['file_name'] if 'file_name' in row0 else '')
                        logger.debug("[CHECK] Index identifiers contain identifier, file exists: " + str(file_name) + " (identifiers: " + str(identifiers) + ")")
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
                file_path = rows[0]['file_path']
                conn.close()
                return file_path
            
            conn.close()
            return None
            
        except Exception as e:
            try:
                error_msg = str(e)
                logger.error("[ERROR] Failed to check Private Formal file: " + error_msg)
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                try:
                    logger.error("[ERROR] Failed to check Private Formal file")
                except Exception:
                    pass
            import traceback
            try:
                traceback.print_exc()
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
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
                f"is_deleted = {self._bool_value(False)}"
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
            
            self._execute(cursor, query, params)
            rows = cursor.fetchall()
            
            if len(rows) > 0:
                row0 = rows[0]
                identifiers = row0['identifiers'] if not isinstance(row0, dict) else row0.get('identifiers', '')
                try:
                    try:
                        file_name = row0.get('file_name', '') if hasattr(row0, 'get') else (row0['file_name'] if 'file_name' in row0 else '')
                        logger.debug("[CHECK] Index identifiers contain identifier, file exists: " + str(file_name) + " (identifiers: " + str(identifiers) + ")")
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
                file_path = rows[0]['file_path']
                conn.close()
                return file_path
            
            conn.close()
            return None
            
        except Exception as e:
            try:
                error_msg = str(e)
                logger.error("[ERROR] Failed to check Private Prelim file: " + error_msg)
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                try:
                    logger.error("[ERROR] Failed to check Private Prelim file")
                except Exception:
                    pass
            import traceback
            try:
                traceback.print_exc()
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            return None
