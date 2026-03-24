#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stockist&Test Report 按 Order 下载功能
功能：根据 Order No 下载对应的 Stockist 和 Test Report PDF 文件
"""

import os
import sqlite3
import zipfile
import tempfile
import re
from typing import List, Dict, Tuple, Optional

# 尝试导入数据库适配器
try:
    from db_adapter import get_db_connection, is_postgres
    DB_ADAPTER_AVAILABLE = True
except ImportError:
    DB_ADAPTER_AVAILABLE = False
    def is_postgres():
        return False

# 尝试导入文件索引查询器
try:
    from file_index_query import FileIndexQuery
    INDEX_AVAILABLE = True
except ImportError:
    INDEX_AVAILABLE = False
    try:
        print("[警告] 文件索引查询器不可用，将使用文件系统遍历")
    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
        pass


class StockistTestDownloader:
    """Stockist&Test Report 下载器"""
    
    def __init__(self, db_path: str, base_folder: str = r"C:\Henry\TR\TR\Stockist&Test Report"):
        """
        初始化下载器
        
        Args:
            db_path: SQLite 数据库路径
            base_folder: Stockist&Test Report 文件夹的基础路径
        """
        self.db_path = db_path
        self.base_folder = base_folder
        # 可选：强制索引命中优先（不回退全盘扫描），用于高并发场景降低磁盘压力
        self.force_index_only = os.getenv('DOWNLOAD_INDEX_FORCE_HIT', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
        # 注意：实际文件夹名称是 "Stockist       Cert"（有多个空格）
        self.stockist_folder = os.path.join(base_folder, "Stockist Cert")
        # 文件夹名称：Private Formal（不是 Fomal）
        self.private_formal_folder = os.path.join(base_folder, "Private Formal")
        self.private_prelim_folder = os.path.join(base_folder, "Private Prelim")
        self.iat_formal_folder = os.path.join(base_folder, "IAT Formal")
        self.iat_prelim_folder = os.path.join(base_folder, "IAT Prelim")
        
        # 初始化文件索引查询器（如果可用）
        self.index_query = None
        if INDEX_AVAILABLE:
            try:
                self.index_query = FileIndexQuery(db_path)
                if self.index_query.is_index_available():
                    try:
                        print("[索引] 文件索引缓存可用，将使用索引查询")
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                else:
                    try:
                        print("[索引] 文件索引缓存表不存在，将使用文件系统遍历")
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                    self.index_query = None
            except Exception as e:
                try:
                    print(f"[警告] 初始化文件索引查询器失败: {e}")
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
                self.index_query = None
    
    def get_order_info(self, order_no: int) -> Optional[Dict]:
        """
        从 TR_Report 表获取订单信息
        
        Args:
            order_no: 订单号
            
        Returns:
            包含 stockist_cert, rm_dn_no, jobsite_type 的字典，如果订单不存在返回 None
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            # 查询订单的 stockist_cert, rm_dn_no, jobsite_type 和 del_date
            # 注意：TR_Report 表的字段名需要根据实际表结构调整
            # 先尝试小写字段名，如果失败再尝试其他格式
            query = """
                SELECT DISTINCT
                    stockist_cert,
                    rm_dn_no,
                    jobsite_type,
                    del_date,
                    job_no
                FROM TR_Report
                WHERE order_no = ?
                LIMIT 1
            """
            try:
                cursor.execute(query, (order_no,))
                row = cursor.fetchone()
            except sqlite3.OperationalError as e:
                # 如果字段名不对，尝试其他可能的字段名
                print(f"[警告] 查询失败，尝试其他字段名: {e}")
                # 尝试查看表结构
                cursor.execute("PRAGMA table_info(TR_Report)")
                columns = cursor.fetchall()
                print(f"[调试] TR_Report 表字段: {[col[1] for col in columns]}")
                # 重新尝试查询
                cursor.execute(query, (order_no,))
                row = cursor.fetchone()
            
            if row:
                # sqlite3.Row 对象不支持 get() 方法，直接使用键访问
                try:
                    stockist_cert = row['stockist_cert'] if row['stockist_cert'] else ''
                except (KeyError, IndexError):
                    try:
                        stockist_cert = row['Stockist_Cert'] if row['Stockist_Cert'] else ''
                    except (KeyError, IndexError):
                        stockist_cert = ''
                
                try:
                    rm_dn_no = row['rm_dn_no'] if row['rm_dn_no'] else ''
                except (KeyError, IndexError):
                    rm_dn_no = ''
                
                try:
                    jobsite_type = row['jobsite_type'] if row['jobsite_type'] else ''
                except (KeyError, IndexError):
                    try:
                        jobsite_type = row['Jobsite_Type'] if row['Jobsite_Type'] else ''
                    except (KeyError, IndexError):
                        jobsite_type = ''
                
                del_date = None
                try:
                    del_date = row['del_date'] if row['del_date'] else None
                except (KeyError, IndexError):
                    try:
                        del_date = row['Del_Date'] if row['Del_Date'] else None
                    except (KeyError, IndexError):
                        del_date = None
                
                job_no = None
                try:
                    job_no = row['job_no'] if row['job_no'] else None
                except (KeyError, IndexError):
                    try:
                        job_no = row['Job_No'] if row['Job_No'] else None
                    except (KeyError, IndexError):
                        try:
                            job_no = row['jobsite_no'] if row['jobsite_no'] else None
                        except (KeyError, IndexError):
                            try:
                                job_no = row['Jobsite_No'] if row['Jobsite_No'] else None
                            except (KeyError, IndexError):
                                job_no = None
                
                # 移除详细查询日志
                
                return {
                    'stockist_cert': str(stockist_cert) if stockist_cert else '',
                    'rm_dn_no': str(rm_dn_no) if rm_dn_no else '',
                    'jobsite_type': str(jobsite_type) if jobsite_type else '',
                    'del_date': str(del_date) if del_date else None,
                    'job_no': str(job_no) if job_no else None
                }
            else:
                # 订单未找到，静默返回None
                return None
        finally:
            conn.close()
    
    def get_orders_info_batch(self, order_nos: List[int]) -> Dict[int, Dict]:
        """
        批量获取多个订单的信息（优化版本）
        
        Args:
            order_nos: 订单号列表
            
        Returns:
            {order_no: order_info_dict} 字典
        """
        if not order_nos:
            return {}
        
        # 分批处理，每批最多500个订单
        BATCH_SIZE = 500
        all_orders_info = {}
        
        for i in range(0, len(order_nos), BATCH_SIZE):
            batch = order_nos[i:i + BATCH_SIZE]
            
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            try:
                placeholders = ','.join('?' * len(batch))
                query = f"""
                    SELECT DISTINCT
                        order_no,
                        stockist_cert,
                        rm_dn_no,
                        jobsite_type,
                        del_date,
                        job_no
                    FROM TR_Report
                    WHERE order_no IN ({placeholders})
                """
                cursor.execute(query, batch)
                rows = cursor.fetchall()
                
                for row in rows:
                    try:
                        order_no = int(row['order_no'])
                    except (KeyError, ValueError, TypeError):
                        try:
                            order_no = int(row['Order_No'])
                        except:
                            continue
                    
                    try:
                        stockist_cert = row['stockist_cert'] if row['stockist_cert'] else ''
                    except (KeyError, IndexError):
                        try:
                            stockist_cert = row['Stockist_Cert'] if row['Stockist_Cert'] else ''
                        except (KeyError, IndexError):
                            stockist_cert = ''
                    
                    try:
                        rm_dn_no = row['rm_dn_no'] if row['rm_dn_no'] else ''
                    except (KeyError, IndexError):
                        rm_dn_no = ''
                    
                    try:
                        jobsite_type = row['jobsite_type'] if row['jobsite_type'] else ''
                    except (KeyError, IndexError):
                        try:
                            jobsite_type = row['Jobsite_Type'] if row['Jobsite_Type'] else ''
                        except (KeyError, IndexError):
                            jobsite_type = ''
                    
                    try:
                        del_date = row['del_date'] if row['del_date'] else None
                    except (KeyError, IndexError):
                        try:
                            del_date = row['Del_Date'] if row['Del_Date'] else None
                        except (KeyError, IndexError):
                            del_date = None
                    
                    job_no = None
                    try:
                        job_no = row['job_no'] if row['job_no'] else None
                    except (KeyError, IndexError):
                        try:
                            job_no = row['Job_No'] if row['Job_No'] else None
                        except (KeyError, IndexError):
                            try:
                                job_no = row['jobsite_no'] if row['jobsite_no'] else None
                            except (KeyError, IndexError):
                                try:
                                    job_no = row['Jobsite_No'] if row['Jobsite_No'] else None
                                except (KeyError, IndexError):
                                    job_no = None
                    
                    all_orders_info[order_no] = {
                        'stockist_cert': str(stockist_cert) if stockist_cert else '',
                        'rm_dn_no': str(rm_dn_no) if rm_dn_no else '',
                        'jobsite_type': str(jobsite_type) if jobsite_type else '',
                        'del_date': str(del_date) if del_date else None,
                        'job_no': str(job_no) if job_no else None
                    }
            finally:
                conn.close()
        
        return all_orders_info
    
    def get_all_cert_dn_values_batch(self, order_nos: List[int]) -> Dict[int, Tuple[List[str], List[str]]]:
        """
        批量获取多个订单的所有 stockist_cert 和 rm_dn_no 值
        
        Args:
            order_nos: 订单号列表
            
        Returns:
            {order_no: (stockist_cert_list, rm_dn_no_list)} 字典
        """
        if not order_nos:
            return {}
        
        # 分批处理，每批最多500个订单
        BATCH_SIZE = 500
        all_results = {}
        
        for i in range(0, len(order_nos), BATCH_SIZE):
            batch = order_nos[i:i + BATCH_SIZE]
            
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            try:
                placeholders = ','.join('?' * len(batch))
                query = f"""
                    SELECT DISTINCT
                        order_no,
                        stockist_cert,
                        rm_dn_no
                    FROM TR_Report
                    WHERE order_no IN ({placeholders})
                """
                cursor.execute(query, batch)
                rows = cursor.fetchall()
                
                # 按 order_no 分组
                batch_results = {}
                for row in rows:
                    try:
                        order_no = int(row['order_no'])
                    except (KeyError, ValueError, TypeError):
                        try:
                            order_no = int(row['Order_No'])
                        except:
                            continue
                    
                    if order_no not in batch_results:
                        batch_results[order_no] = {'stockist_certs': set(), 'rm_dn_nos': set()}
                    
                    try:
                        stockist_cert = row['stockist_cert']
                    except (KeyError, IndexError):
                        try:
                            stockist_cert = row['Stockist_Cert']
                        except (KeyError, IndexError):
                            stockist_cert = None
                    
                    try:
                        rm_dn_no = row['rm_dn_no']
                    except (KeyError, IndexError):
                        rm_dn_no = None
                    
                    if stockist_cert:
                        stockist_cert = str(stockist_cert).strip()
                        if stockist_cert:
                            # 支持多种分隔符拆分：中文逗号、英文逗号、分号、空格
                            # 按多种分隔符拆分，并转换为大写
                            split_certs = re.split(r'[、,;\s]+', stockist_cert)
                            for cert in split_certs:
                                cert = cert.strip().upper()
                                if cert:
                                    batch_results[order_no]['stockist_certs'].add(cert)
                    
                    if rm_dn_no:
                        rm_dn_no = str(rm_dn_no).strip()
                        if rm_dn_no:
                            batch_results[order_no]['rm_dn_nos'].add(rm_dn_no)
                
                # 转换为列表格式
                for order_no, data in batch_results.items():
                    all_results[order_no] = (
                        list(data['stockist_certs']),
                        list(data['rm_dn_nos'])
                    )
            finally:
                conn.close()
        
        return all_results
    
    def get_rm_dn_to_stockist_cert_map_batch(self, order_nos: List[int]) -> Dict[int, Dict[str, str]]:
        """
        批量获取多个订单的 rm_dn_no 到 stockist_cert 映射
        
        Args:
            order_nos: 订单号列表
            
        Returns:
            {order_no: {rm_dn_no: stockist_cert}} 字典
        """
        if not order_nos:
            return {}
        
        # 分批处理，每批最多500个订单
        BATCH_SIZE = 500
        all_results = {}
        
        for i in range(0, len(order_nos), BATCH_SIZE):
            batch = order_nos[i:i + BATCH_SIZE]
            
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            try:
                placeholders = ','.join('?' * len(batch))
                query = f"""
                    SELECT DISTINCT
                        order_no,
                        rm_dn_no,
                        stockist_cert
                    FROM TR_Report
                    WHERE order_no IN ({placeholders})
                        AND rm_dn_no IS NOT NULL 
                        AND rm_dn_no != '' 
                        AND stockist_cert IS NOT NULL 
                        AND stockist_cert != ''
                """
                cursor.execute(query, batch)
                rows = cursor.fetchall()
                
                # 按 order_no 分组
                for row in rows:
                    try:
                        order_no = int(row['order_no'])
                    except (KeyError, ValueError, TypeError):
                        try:
                            order_no = int(row['Order_No'])
                        except:
                            continue
                    
                    if order_no not in all_results:
                        all_results[order_no] = {}
                    
                    try:
                        rm_dn_no = row['rm_dn_no']
                        stockist_cert = row['stockist_cert']
                    except (KeyError, IndexError):
                        try:
                            rm_dn_no = row.get('RM_DN_No', '') or row.get('rm_dn_no', '')
                            stockist_cert = row.get('Stockist_Cert', '') or row.get('stockist_cert', '')
                        except:
                            continue
                    
                    if rm_dn_no and stockist_cert:
                        rm_dn_no = str(rm_dn_no).strip()
                        stockist_cert = str(stockist_cert).strip()
                        if rm_dn_no and stockist_cert:
                            # 如果同一个 rm_dn_no 对应多个 stockist_cert，保留第一个
                            if rm_dn_no not in all_results[order_no]:
                                all_results[order_no][rm_dn_no] = stockist_cert
            finally:
                conn.close()
        
        return all_results
    
    def get_all_cert_dn_values(self, order_no: int) -> Tuple[List[str], List[str]]:
        """
        获取订单对应的所有 stockist_cert 和 rm_dn_no 值（去重）
        
        Args:
            order_no: 订单号
            
        Returns:
            (stockist_cert_list, rm_dn_no_list) 元组
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT DISTINCT
                    stockist_cert,
                    rm_dn_no
                FROM TR_Report
                WHERE order_no = ?
            """
            try:
                cursor.execute(query, (order_no,))
                rows = cursor.fetchall()
            except sqlite3.OperationalError as e:
                print(f"[警告] 查询失败: {e}")
                # 尝试查看表结构
                cursor.execute("PRAGMA table_info(TR_Report)")
                columns = cursor.fetchall()
                print(f"[调试] TR_Report 表字段: {[col[1] for col in columns]}")
                raise
            
            stockist_certs = []
            rm_dn_nos = []
            
            for row in rows:
                # sqlite3.Row 对象不支持 get() 方法，直接使用键访问
                stockist_cert = None
                try:
                    stockist_cert = row['stockist_cert']
                except (KeyError, IndexError):
                    try:
                        stockist_cert = row['Stockist_Cert']
                    except (KeyError, IndexError):
                        pass
                
                rm_dn_no = None
                try:
                    rm_dn_no = row['rm_dn_no']
                except (KeyError, IndexError):
                    pass
                
                if stockist_cert:
                    stockist_cert = str(stockist_cert).strip()
                    if stockist_cert:
                        # 支持多种分隔符拆分：中文逗号、英文逗号、分号、空格
                        # 按多种分隔符拆分，并转换为大写
                        split_certs = re.split(r'[、,;\s]+', stockist_cert)
                        for cert in split_certs:
                            cert = cert.strip().upper()
                            if cert and cert not in stockist_certs:
                                stockist_certs.append(cert)
                
                if rm_dn_no:
                    rm_dn_no = str(rm_dn_no).strip()
                    if rm_dn_no and rm_dn_no not in rm_dn_nos:
                        rm_dn_nos.append(rm_dn_no)
            
            # 移除详细查询日志
            return stockist_certs, rm_dn_nos
        finally:
            conn.close()
    
    def get_rm_dn_to_stockist_cert_map(self, order_no: int) -> Dict[str, str]:
        """
        获取订单对应的 rm_dn_no 到 stockist_cert 的映射字典
        
        Args:
            order_no: 订单号
            
        Returns:
            {rm_dn_no: stockist_cert} 字典
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT DISTINCT
                    rm_dn_no,
                    stockist_cert
                FROM TR_Report
                WHERE order_no = ? AND rm_dn_no IS NOT NULL AND rm_dn_no != '' AND stockist_cert IS NOT NULL AND stockist_cert != ''
            """
            try:
                cursor.execute(query, (order_no,))
                rows = cursor.fetchall()
            except sqlite3.OperationalError as e:
                print(f"[警告] 查询失败: {e}")
                return {}
            
            mapping = {}
            for row in rows:
                try:
                    rm_dn_no = row['rm_dn_no']
                    stockist_cert = row['stockist_cert']
                except (KeyError, IndexError):
                    try:
                        rm_dn_no = row.get('RM_DN_No', '') or row.get('rm_dn_no', '')
                        stockist_cert = row.get('Stockist_Cert', '') or row.get('stockist_cert', '')
                    except:
                        continue
                
                if rm_dn_no and stockist_cert:
                    rm_dn_no = str(rm_dn_no).strip()
                    stockist_cert = str(stockist_cert).strip()
                    if rm_dn_no and stockist_cert:
                        # 如果同一个 rm_dn_no 对应多个 stockist_cert，保留第一个
                        if rm_dn_no not in mapping:
                            mapping[rm_dn_no] = stockist_cert
            
            # 移除详细查询日志
            return mapping
        finally:
            conn.close()
    
    def find_files_by_keywords(self, folder: str, keywords: List[str], search_subfolders: bool = True) -> List[str]:
        """
        在指定文件夹中查找包含关键词的 PDF 文件
        优先使用索引查询，如果索引不可用则回退到文件系统遍历
        
        Args:
            folder: 文件夹路径
            keywords: 关键词列表（stockist_cert 或 rm_dn_no）
            search_subfolders: 是否搜索子文件夹（对于IAT Formal等，只搜索直接子文件夹）
            
        Returns:
            找到的文件路径列表
        """
        # 尝试使用索引查询
        if self.index_query and self.index_query.is_index_available():
            try:
                # 确定文件夹类型
                folder_type = None
                folder_normalized = os.path.normpath(folder).replace('\\', '/')
                base_normalized = os.path.normpath(self.base_folder).replace('\\', '/')
                
                if 'Stockist Cert' in folder_normalized:
                    folder_type = 'Stockist Cert'
                elif 'Private Formal' in folder_normalized:
                    folder_type = 'Private Formal'
                elif 'Private Prelim' in folder_normalized:
                    folder_type = 'Private Prelim'
                elif 'IAT Formal' in folder_normalized:
                    folder_type = 'IAT Formal'
                elif 'IAT Prelim' in folder_normalized:
                    folder_type = 'IAT Prelim'
                
                if folder_type:
                    # 使用索引查询
                    try:
                        print(f"[索引查询] 使用索引查询 folder_type={folder_type}, keywords={keywords[:5]}...")
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                    
                    if search_subfolders:
                        # 搜索整个文件夹类型
                        found_files = self.index_query.find_files_by_keywords(
                            keywords=keywords,
                            folder_types=[folder_type],
                            verify_files=True
                        )
                        try:
                            print(f"[索引查询] 索引查询返回 {len(found_files)} 个文件")
                            if len(found_files) == 0:
                                print(f"[索引查询] 未找到文件，可能原因：1) 索引中没有匹配的记录 2) 文件已被删除 3) 关键词不匹配")
                        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                            pass
                    else:
                        # 只搜索子文件夹（用于IAT Formal等）
                        # 对于 IAT Formal，我们需要找到包含关键词的子文件夹，然后下载该文件夹中的所有文件
                        # 先找到匹配的子文件夹
                        matching_subfolders = []
                        try:
                            items = os.listdir(folder)
                            for item in items:
                                item_path = os.path.join(folder, item)
                                if os.path.isdir(item_path):
                                    item_lower = item.lower()
                                    for keyword in keywords:
                                        keyword_lower = keyword.lower() if keyword else ''
                                        if keyword and keyword_lower in item_lower:
                                            matching_subfolders.append(item_path)
                                            try:
                                                print(f"[索引查询] 找到匹配的子文件夹: {item}")
                                            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                                                pass
                                            break
                        except Exception as e:
                            try:
                                print(f"[索引查询] 读取文件夹失败: {e}")
                            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                                pass
                        
                        # 如果找到匹配的子文件夹，使用索引查询该文件夹中的所有文件
                        if matching_subfolders:
                            found_files = []
                            for subfolder in matching_subfolders:
                                # 使用索引查询该子文件夹中的所有 PDF 文件
                                subfolder_files = self.index_query.find_files_in_subfolder(
                                    folder_path=subfolder,
                                    keywords=[]  # 不限制关键词，获取所有文件
                                )
                                found_files.extend(subfolder_files)
                                try:
                                    print(f"[索引查询] 子文件夹 {os.path.basename(subfolder)}: 找到 {len(subfolder_files)} 个 PDF 文件")
                                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                                    pass
                        else:
                            # 如果没有找到匹配的子文件夹，使用原来的逻辑
                            found_files = self.index_query.find_files_in_subfolder(
                                folder_path=folder,
                                keywords=keywords
                            )
                    
                    if found_files:
                        try:
                            print(f"[索引查询] {folder}: 找到 {len(found_files)} 个匹配的 PDF")
                        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                            pass
                    return found_files
                if self.force_index_only:
                    try:
                        print(f"[索引查询] 强制索引模式开启，未识别 folder_type，跳过全盘扫描: {folder}")
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                    return []
            except Exception as e:
                try:
                    print(f"[警告] 索引查询失败，回退到文件系统遍历: {e}")
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
                # 继续执行文件系统遍历
                if self.force_index_only:
                    try:
                        print(f"[索引查询] 强制索引模式开启，索引异常后不回退扫描: {folder}")
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                    return []
        elif self.force_index_only:
            try:
                print(f"[索引查询] 强制索引模式开启，索引不可用，跳过全盘扫描: {folder}")
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            return []
        
        # 回退到原始的文件系统遍历方法
        found_files = []
        
        if not os.path.exists(folder):
            try:
                print(f"[搜索] 文件夹不存在: {folder}")
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            return found_files
        
        # 移除详细搜索日志，只保留统计信息
        
        if search_subfolders:
            # 遍历文件夹中的所有文件（包括子文件夹）
            file_count = 0
            pdf_count = 0
            for root, dirs, files in os.walk(folder):
                for file in files:
                    file_count += 1
                    if not file.lower().endswith('.pdf'):
                        continue
                    
                    pdf_count += 1
                    file_path = os.path.join(root, file)
                    file_name_lower = file.lower()
                    
                    # 检查文件名是否包含任何关键词
                    matched_keyword = None
                    for keyword in keywords:
                        if keyword and keyword.lower() in file_name_lower:
                            found_files.append(file_path)
                            matched_keyword = keyword
                            break  # 找到就跳出，避免重复添加
                    
                    # 调试：如果前10个PDF文件都没匹配，打印一些示例
                    if pdf_count <= 10 and not matched_keyword:
                        try:
                            print(f"[搜索调试] PDF文件 {pdf_count}: {file} (不匹配关键词: {keywords[:3]}...)")
                        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                            pass
            
            # 打印统计信息
            try:
                if found_files:
                    print(f"[搜索] {folder}: 扫描 {file_count} 个文件（{pdf_count} 个PDF），找到 {len(found_files)} 个匹配的 PDF")
                else:
                    print(f"[搜索] {folder}: 扫描 {file_count} 个文件（{pdf_count} 个PDF），未找到匹配的 PDF（关键词: {keywords[:5]}...）")
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
        else:
            # 只搜索直接子文件夹（对于IAT Formal等，只需要下载对应文件夹）
            # 检查子文件夹名称是否包含关键词
            subfolders = []
            try:
                items = os.listdir(folder)
                try:
                    print(f"[搜索] {folder}: 扫描 {len(items)} 个项目")
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
                
                for item in items:
                    item_path = os.path.join(folder, item)
                    if os.path.isdir(item_path):
                        item_lower = item.lower()
                        # 检查文件夹名是否包含任何关键词
                        for keyword in keywords:
                            keyword_lower = keyword.lower() if keyword else ''
                            if keyword and keyword_lower in item_lower:
                                subfolders.append(item_path)
                                try:
                                    print(f"[搜索] 找到匹配的子文件夹: {item} (包含关键词: {keyword})")
                                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                                    pass
                                break
            except Exception as e:
                try:
                    print(f"[错误] 读取文件夹失败 {folder}: {e}")
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
                import traceback
                traceback.print_exc()
            
            # 如果找到匹配的文件夹，下载该文件夹中的所有PDF
            for subfolder in subfolders:
                pdf_count = 0
                try:
                    print(f"[搜索] 扫描子文件夹: {subfolder}")
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
                for root, dirs, files in os.walk(subfolder):
                    for file in files:
                        if file.lower().endswith('.pdf'):
                            file_path = os.path.join(root, file)
                            found_files.append(file_path)
                            pdf_count += 1
                            try:
                                print(f"[搜索]   找到 PDF: {file}")
                            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                                pass
                
                try:
                    print(f"[搜索] 子文件夹 {os.path.basename(subfolder)}: 共找到 {pdf_count} 个 PDF 文件")
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
            
            # 只打印统计信息
            if subfolders or found_files:
                try:
                    print(f"[搜索] {folder}: 找到 {len(subfolders)} 个匹配文件夹，共 {len(found_files)} 个PDF文件")
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
        
        return found_files
    
    def match_file_to_stockist_cert(self, file_name: str, file_path: str, stockist_certs: List[str], 
                                     rm_dn_nos: List[str], rm_dn_to_stockist_map: Dict[str, str]) -> Optional[str]:
        """
        匹配文件到 stockist_cert
        
        Args:
            file_name: 文件名
            file_path: 文件路径
            stockist_certs: stockist_cert 列表
            rm_dn_nos: rm_dn_no 列表
            rm_dn_to_stockist_map: rm_dn_no 到 stockist_cert 的映射字典
            
        Returns:
            匹配到的 stockist_cert，如果没有匹配到返回 None
        """
        file_path_lower = file_path.lower()
        file_name_lower = file_name.lower()
        
        # 第一步：检查文件是否包含某个 stockist_cert
        for stockist_cert in stockist_certs:
            if stockist_cert:
                stockist_cert_lower = stockist_cert.lower()
                # 检查文件名或路径中是否包含 stockist_cert
                if stockist_cert_lower in file_name_lower or stockist_cert_lower in file_path_lower:
                    return stockist_cert
        
        # 第二步：如果第一步没有匹配到，尝试通过 rm_dn_no 匹配
        for rm_dn_no in rm_dn_nos:
            if rm_dn_no:
                rm_dn_no_lower = rm_dn_no.lower()
                # 检查文件名或路径中是否包含 rm_dn_no
                if rm_dn_no_lower in file_name_lower or rm_dn_no_lower in file_path_lower:
                    # 查找该 rm_dn_no 对应的 stockist_cert
                    if rm_dn_no in rm_dn_to_stockist_map:
                        return rm_dn_to_stockist_map[rm_dn_no]
        
        return None
    
    def check_jobsite_type(self, jobsite_type) -> Tuple[bool, bool]:
        """
        判断 jobsite_type 是 IAT 还是 PRIVATE 类型
        
        Args:
            jobsite_type: jobsite_type 值（可能是字符串或数字）
            
        Returns:
            (is_iat, is_private) 元组
        """
        is_iat = False
        is_private = False
        
        if jobsite_type:
            jobsite_type_str = str(jobsite_type).lower().strip()
            
            # 先尝试字符串匹配
            is_iat = 'iat' in jobsite_type_str
            is_private = 'private' in jobsite_type_str
            
            # 如果字符串匹配失败，尝试数字映射
            # 根据数据库映射规则：
            # IAT: {1, 4, 5, 6, 8, 11}
            # PRIVATE: {2, 3, 7}
            if not is_iat and not is_private:
                try:
                    jobsite_type_num = int(float(jobsite_type_str))
                    if jobsite_type_num in {1, 4, 5, 6, 8, 11}:
                        is_iat = True
                        print(f"[类型判断] 通过数字映射识别为 IAT 类型: {jobsite_type_num}")
                    elif jobsite_type_num in {2, 3, 7}:
                        is_private = True
                        print(f"[类型判断] 通过数字映射识别为 PRIVATE 类型: {jobsite_type_num}")
                except (ValueError, TypeError):
                    # 如果无法转换为数字，忽略
                    pass
        
        return is_iat, is_private
    
    def download_by_order(self, order_no: int) -> Tuple[str, int]:
        """
        按 Order 下载所有相关 PDF 文件
        
        Args:
            order_no: 订单号
            
        Returns:
            (zip_file_path, file_count) 元组，zip_file_path 是临时 ZIP 文件路径
        """
        # 1. 获取订单信息
        order_info = self.get_order_info(order_no)
        if not order_info:
            raise ValueError(f"Order {order_no} not found in TR_Report table")
        
        # 2. 获取所有 stockist_cert 和 rm_dn_no 值
        stockist_certs, rm_dn_nos = self.get_all_cert_dn_values(order_no)
        
        # 获取 rm_dn_no 到 stockist_cert 的映射
        rm_dn_to_stockist_map = self.get_rm_dn_to_stockist_cert_map(order_no)
        
        # 合并所有关键词
        all_keywords = stockist_certs + rm_dn_nos
        all_keywords = [k for k in all_keywords if k]  # 移除空值
        
        if not all_keywords:
            raise ValueError(f"No stockist_cert or rm_dn_no found for order {order_no}")
        
        # 3. 第一步：从 Stockist 文件夹下载所有相关 PDF
        stockist_files = self.find_files_by_keywords(self.stockist_folder, all_keywords)
        
        # 4. 第二步：判断类型并查找对应文件夹
        jobsite_type = order_info['jobsite_type'] or ''
        jobsite_type_lower = jobsite_type.lower()
        
        additional_files = []
        found_formal = False
        
        # 使用辅助方法判断类型
        is_iat, is_private = self.check_jobsite_type(jobsite_type)
        
        if is_iat:
            # IAT 类型：按每个 stockist_cert 单独判断，有 Formal 就用 Formal，没有就立即查 Prelim
            certs_norm = [c.strip() for c in stockist_certs if c and str(c).strip()]
            
            for cert in certs_norm:
                # 1. 先检查该 cert 是否有对应的 IAT Formal 目录
                formal_folder = os.path.join(self.iat_formal_folder, cert)
                cert_has_formal = False
                
                if os.path.exists(formal_folder) and os.path.isdir(formal_folder):
                    # 检查目录里是否有 PDF
                    cert_formal_files = []
                    for root, _dirs, files in os.walk(formal_folder):
                        for fn in files:
                            if fn.lower().endswith('.pdf'):
                                fp = os.path.join(root, fn)
                                if os.path.exists(fp):
                                    cert_formal_files.append(fp)
                    
                    if cert_formal_files:
                        cert_has_formal = True
                        found_formal = True
                        additional_files.extend(cert_formal_files)
                        try:
                            print(f"[IAT下载] Order {order_no}: Cert {cert} 使用 IAT Formal 目录 {formal_folder}，共 {len(cert_formal_files)} 个文件")
                        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                            pass
                
                # 2. 如果该 cert 没有 Formal，立即去 IAT Prelim 搜索
                if not cert_has_formal:
                    # 为该 cert 构建关键词（cert + 对应的 rm_dn_no）
                    cert_keywords = [cert]
                    for rm_dn_no, mapped_cert in rm_dn_to_stockist_map.items():
                        if mapped_cert == cert:
                            cert_keywords.append(rm_dn_no)
                    
                    if cert_keywords:
                        cert_prelim_files = self.find_files_by_keywords(
                            self.iat_prelim_folder,
                            cert_keywords,
                            search_subfolders=True
                        )
                        
                        if cert_prelim_files:
                            # 验证这些文件确实属于这个 cert
                            valid_prelim_for_cert = []
                            for file_path in cert_prelim_files:
                                file_name = os.path.basename(file_path)
                                matched_cert = self.match_file_to_stockist_cert(
                                    file_name, file_path, [cert], rm_dn_nos, rm_dn_to_stockist_map
                                )
                                if matched_cert == cert:
                                    valid_prelim_for_cert.append(file_path)
                            
                            if valid_prelim_for_cert:
                                additional_files.extend(valid_prelim_for_cert)
                                try:
                                    print(f"[IAT下载] Order {order_no}: Cert {cert} 无 Formal，使用 {len(valid_prelim_for_cert)} 个 IAT Prelim 文件")
                                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                                    pass
        
        elif is_private:
            # Private 类型
            # 先查找 Private Formal（搜索所有文件，包括子文件夹中的文件）
            private_formal_files = self.find_files_by_keywords(self.private_formal_folder, all_keywords, search_subfolders=True)
            
            # 将 Private Formal 中找到的文件按 stockist_cert 分组
            formal_files_by_cert = {}
            for file_path in private_formal_files:
                file_name = os.path.basename(file_path)
                matched_cert = self.match_file_to_stockist_cert(
                    file_name, file_path, stockist_certs, rm_dn_nos, rm_dn_to_stockist_map
                )
                if matched_cert:
                    if matched_cert not in formal_files_by_cert:
                        formal_files_by_cert[matched_cert] = []
                    formal_files_by_cert[matched_cert].append(file_path)
            
            # 找出哪些 stockist_cert 在 Private Formal 中没有文件
            missing_certs = [cert for cert in stockist_certs if cert and cert not in formal_files_by_cert]
            
            if private_formal_files:
                found_formal = True
                additional_files.extend(private_formal_files)
                
                if missing_certs:
                    # 为缺失的 stockist_cert 构建关键词（只包含这些 cert 和对应的 rm_dn_no）
                    missing_keywords = []
                    for cert in missing_certs:
                        missing_keywords.append(cert)
                        # 查找该 cert 对应的 rm_dn_no
                        for rm_dn_no, mapped_cert in rm_dn_to_stockist_map.items():
                            if mapped_cert == cert:
                                missing_keywords.append(rm_dn_no)
                    
                    if missing_keywords:
                        # 查找 Private Prelim（搜索所有文件，包括子文件夹中的文件）
                        private_prelim_files = self.find_files_by_keywords(self.private_prelim_folder, missing_keywords, search_subfolders=True)
                        
                        if private_prelim_files:
                            # 验证这些文件确实属于缺失的 stockist_cert
                            prelim_files_by_cert = {}
                            for file_path in private_prelim_files:
                                file_name = os.path.basename(file_path)
                                matched_cert = self.match_file_to_stockist_cert(
                                    file_name, file_path, missing_certs, rm_dn_nos, rm_dn_to_stockist_map
                                )
                                if matched_cert and matched_cert in missing_certs:
                                    prelim_files_by_cert[matched_cert] = prelim_files_by_cert.get(matched_cert, []) + [file_path]
                            
                            if prelim_files_by_cert:
                                # 只添加属于缺失 stockist_cert 的文件
                                valid_prelim_files = []
                                for file_path in private_prelim_files:
                                    file_name = os.path.basename(file_path)
                                    matched_cert = self.match_file_to_stockist_cert(
                                        file_name, file_path, missing_certs, rm_dn_nos, rm_dn_to_stockist_map
                                    )
                                    if matched_cert and matched_cert in missing_certs:
                                        valid_prelim_files.append(file_path)
                                
                                additional_files.extend(valid_prelim_files)
                        else:
                            pass  # Private Prelim 中没有找到匹配的文件
                    else:
                        pass  # 无法为缺失的 stockist_cert 构建关键词，跳过 Private Prelim 搜索
                else:
                    pass  # 所有 stockist_cert 在 Private Formal 中都有文件，不需要查找 Private Prelim
            else:
                # Private Formal 中没有文件，查找 Private Prelim
                private_prelim_files = self.find_files_by_keywords(self.private_prelim_folder, all_keywords, search_subfolders=True)
                
                if private_prelim_files:
                    additional_files.extend(private_prelim_files)
        
        elif 'iat' in jobsite_type_lower:
            # IAT 类型
            # 先查找 IAT Formal（只搜索子文件夹，不需要递归搜索所有文件）
            iat_formal_files = self.find_files_by_keywords(self.iat_formal_folder, all_keywords, search_subfolders=False)
            
            if iat_formal_files:
                found_formal = True
                additional_files.extend(iat_formal_files)
                print(f"[IAT下载] 规则命中：IAT Formal 已有文件，跳过 IAT Prelim 搜索")
            else:
                print(f"[IAT下载] 规则命中：IAT Formal 无对应文件夹或文件夹为空，回退 IAT Prelim 递归搜索")
                # IAT Prelim 常见是文件名直接含 DN（不按子文件夹命名），因此需要递归按文件名搜索
                iat_prelim_files = self.find_files_by_keywords(self.iat_prelim_folder, all_keywords, search_subfolders=True)
                
                if iat_prelim_files:
                    additional_files.extend(iat_prelim_files)
        
        # 5. 合并所有文件
        all_files = stockist_files + additional_files
        
        print(f"[文件汇总] Stockist 文件: {len(stockist_files)} 个")
        print(f"[文件汇总] Additional 文件: {len(additional_files)} 个")
        print(f"[文件汇总] 总计: {len(all_files)} 个文件")
        for f in all_files:
            print(f"[文件汇总]   - {os.path.basename(f)}")
        
        if not all_files:
            raise ValueError(f"No PDF files found for order {order_no} with keywords: {all_keywords}")
        
        # 6. 按照 stockist_cert 组织文件
        # 创建一个字典，key 是 stockist_cert，value 是该 stockist_cert 对应的文件列表
        files_by_stockist_cert = {}
        
        # 为每个 stockist_cert 创建空列表
        for stockist_cert in stockist_certs:
            if stockist_cert:
                files_by_stockist_cert[stockist_cert] = []
        
        # 用于存储无法匹配到 stockist_cert 的文件（这些文件仍然需要被下载）
        unmatched_files = []
        
        # 将所有文件按照 stockist_cert 分类
        print(f"[文件匹配] 开始匹配 {len(all_files)} 个文件到 stockist_cert")
        print(f"[文件匹配] stockist_certs: {stockist_certs}")
        print(f"[文件匹配] rm_dn_nos: {rm_dn_nos}")
        
        # 对于 IAT 类型，IAT Formal/Prelim 文件夹中的文件根据文件夹名称（stockist_cert）进行分配
        iat_formal_normalized = os.path.normpath(self.iat_formal_folder)
        iat_prelim_normalized = os.path.normpath(self.iat_prelim_folder)
        
        for file_path in all_files:
            file_name = os.path.basename(file_path)
            normalized_path = os.path.normpath(file_path)
            
            # 检查是否来自 IAT Formal 或 IAT Prelim
            is_iat_formal = normalized_path.startswith(iat_formal_normalized)
            is_iat_prelim = normalized_path.startswith(iat_prelim_normalized)
            
            if is_iat and (is_iat_formal or is_iat_prelim):
                # 对于 IAT 类型，根据文件所在子文件夹的名称（stockist_cert）进行分配
                # 由于子文件夹是通过 stockist_certs 查找的，所以文件夹名称一定在 stockist_certs 列表中
                # 获取文件相对于 IAT Formal 或 IAT Prelim 的路径
                if is_iat_formal:
                    base_folder = iat_formal_normalized
                else:
                    base_folder = iat_prelim_normalized
                
                # 获取相对路径
                try:
                    rel_path = os.path.relpath(normalized_path, base_folder)
                    # 获取第一层文件夹名称（即 stockist_cert）
                    path_parts = rel_path.split(os.path.sep)
                    if path_parts:
                        folder_name = path_parts[0]  # 子文件夹名称，即 stockist_cert
                        
                        # 在 stockist_certs 列表中查找匹配的 stockist_cert（大小写不敏感）
                        matched_cert = None
                        for cert in stockist_certs:
                            if cert and cert.upper() == folder_name.upper():
                                matched_cert = cert
                                break
                        
                        if matched_cert:
                            if matched_cert not in files_by_stockist_cert:
                                files_by_stockist_cert[matched_cert] = []
                            files_by_stockist_cert[matched_cert].append(file_path)
                            print(f"[文件匹配] ✅ IAT 文件 {file_name} -> {matched_cert} (根据文件夹名称: {folder_name})")
                        else:
                            # 理论上不应该发生，因为文件夹是通过 stockist_certs 查找的
                            # 但如果发生了，记录警告并添加到未匹配列表
                            unmatched_files.append(file_path)
                            print(f"[文件匹配] ⚠️ IAT 文件 {file_name} 的文件夹名称 {folder_name} 不在 stockist_certs 中（异常情况）")
                    else:
                        # 无法获取文件夹名称（异常情况）
                        unmatched_files.append(file_path)
                        print(f"[文件匹配] ⚠️ IAT 文件 {file_name} 无法获取文件夹名称（异常情况）")
                except ValueError:
                    # 如果 relpath 失败（不同驱动器），尝试从路径中提取
                    # 路径格式：D:\Stockist&Test Report\IAT Formal\HL2310\...
                    path_parts = normalized_path.split(os.path.sep)
                    # 查找 IAT Formal 或 IAT Prelim 在路径中的位置
                    base_folder_name = os.path.basename(base_folder)
                    base_index = -1
                    for i, part in enumerate(path_parts):
                        if part == base_folder_name or base_folder_name in part:
                            base_index = i
                            break
                    
                    if base_index >= 0 and base_index + 1 < len(path_parts):
                        folder_name = path_parts[base_index + 1]  # 子文件夹名称
                        
                        # 在 stockist_certs 列表中查找匹配的 stockist_cert（大小写不敏感）
                        matched_cert = None
                        for cert in stockist_certs:
                            if cert and cert.upper() == folder_name.upper():
                                matched_cert = cert
                                break
                        
                        if matched_cert:
                            if matched_cert not in files_by_stockist_cert:
                                files_by_stockist_cert[matched_cert] = []
                            files_by_stockist_cert[matched_cert].append(file_path)
                            print(f"[文件匹配] ✅ IAT 文件 {file_name} -> {matched_cert} (根据文件夹名称: {folder_name})")
                        else:
                            # 理论上不应该发生
                            unmatched_files.append(file_path)
                            print(f"[文件匹配] ⚠️ IAT 文件 {file_name} 的文件夹名称 {folder_name} 不在 stockist_certs 中（异常情况）")
                    else:
                        # 无法提取文件夹名称（异常情况）
                        unmatched_files.append(file_path)
                        print(f"[文件匹配] ⚠️ IAT 文件 {file_name} 无法提取文件夹名称（异常情况）")
            else:
                # 对于其他文件（Stockist Cert、Private 等），使用正常匹配逻辑
                matched_stockist_cert = self.match_file_to_stockist_cert(
                    file_name, file_path, stockist_certs, rm_dn_nos, rm_dn_to_stockist_map
                )
                
                if matched_stockist_cert:
                    # 确保 matched_stockist_cert 在 files_by_stockist_cert 中
                    if matched_stockist_cert not in files_by_stockist_cert:
                        files_by_stockist_cert[matched_stockist_cert] = []
                    files_by_stockist_cert[matched_stockist_cert].append(file_path)
                    print(f"[文件匹配] ✅ {file_name} -> {matched_stockist_cert}")
                else:
                    # 如果无法匹配到 stockist_cert
                    unmatched_files.append(file_path)
                    print(f"[文件匹配] ❌ 文件无法匹配到 stockist_cert: {file_name} (路径: {file_path})")
        
        # 7. 处理无法匹配的文件：如果它们在同一个子文件夹中，分配给该文件夹中已匹配文件的 stockist_cert
        # 对于 IAT 类型，如果文件在同一个子文件夹中（如 HL2310），应该属于同一个订单
        if unmatched_files:
            print(f"[文件匹配] 发现 {len(unmatched_files)} 个无法匹配到 stockist_cert 的文件")
            for file_path in unmatched_files:
                print(f"[文件匹配] 未匹配文件: {os.path.basename(file_path)} (路径: {file_path})")
            
            if is_iat:
                # 按文件夹分组未匹配的文件
                # 对于 IAT 类型，我们需要找到文件的直接父文件夹（子文件夹，如 HL2310）
                unmatched_by_folder = {}
                for file_path in unmatched_files:
                    # 获取文件的完整路径并标准化
                    normalized_path = os.path.normpath(file_path)
                    # 获取文件的直接父文件夹
                    folder_path = os.path.dirname(normalized_path)
                    # 对于 IAT Formal，我们需要找到子文件夹（如 IAT Formal/HL2310）
                    # 检查是否在 IAT Formal 或 IAT Prelim 文件夹中
                    iat_formal_normalized = os.path.normpath(self.iat_formal_folder)
                    iat_prelim_normalized = os.path.normpath(self.iat_prelim_folder)
                    
                    # 找到子文件夹路径（相对于 IAT Formal 或 IAT Prelim 的直接子文件夹）
                    if folder_path.startswith(iat_formal_normalized):
                        # 获取相对于 IAT Formal 的路径
                        rel_path = os.path.relpath(folder_path, iat_formal_normalized)
                        # 如果是直接子文件夹，使用完整路径；否则使用子文件夹路径
                        if os.path.sep not in rel_path:
                            # 直接子文件夹（如 HL2310）
                            subfolder_path = folder_path
                        else:
                            # 在子文件夹的子目录中，找到子文件夹路径
                            parts = rel_path.split(os.path.sep)
                            subfolder_path = os.path.join(iat_formal_normalized, parts[0])
                    elif folder_path.startswith(iat_prelim_normalized):
                        rel_path = os.path.relpath(folder_path, iat_prelim_normalized)
                        if os.path.sep not in rel_path:
                            subfolder_path = folder_path
                        else:
                            parts = rel_path.split(os.path.sep)
                            subfolder_path = os.path.join(iat_prelim_normalized, parts[0])
                    else:
                        # 不在 IAT 文件夹中，使用直接父文件夹
                        subfolder_path = folder_path
                    
                    if subfolder_path not in unmatched_by_folder:
                        unmatched_by_folder[subfolder_path] = []
                    unmatched_by_folder[subfolder_path].append(file_path)
                
                print(f"[文件匹配] 按文件夹分组: {len(unmatched_by_folder)} 个文件夹")
                for folder_path, files in unmatched_by_folder.items():
                    print(f"[文件匹配] 文件夹 {os.path.basename(folder_path)}: {len(files)} 个文件")
                
                # 对于每个未匹配文件的文件夹，查找同一文件夹中已匹配的文件
                for folder_path, files in unmatched_by_folder.items():
                    # 标准化文件夹路径
                    folder_path_normalized = os.path.normpath(folder_path)
                    
                    # 查找同一文件夹中已匹配的文件
                    matched_files_in_folder = []
                    for stockist_cert, matched_files in files_by_stockist_cert.items():
                        for matched_file in matched_files:
                            matched_file_dir = os.path.normpath(os.path.dirname(matched_file))
                            # 检查是否在同一个子文件夹中
                            if matched_file_dir == folder_path_normalized:
                                matched_files_in_folder.append((stockist_cert, matched_file))
                                break
                            # 或者检查是否在同一个子文件夹的子目录中（对于 IAT，子文件夹内的所有文件都应该属于同一个订单）
                            elif (matched_file_dir.startswith(folder_path_normalized) or 
                                  folder_path_normalized.startswith(matched_file_dir)):
                                # 进一步检查：如果文件在子文件夹的子目录中，也认为是同一个文件夹
                                matched_file_rel = os.path.relpath(matched_file_dir, folder_path_normalized)
                                if not matched_file_rel.startswith('..'):
                                    matched_files_in_folder.append((stockist_cert, matched_file))
                                    break
                    
                    # 如果找到已匹配的文件，将未匹配的文件分配给同一个 stockist_cert
                    if matched_files_in_folder:
                        # 使用第一个匹配的 stockist_cert
                        target_cert = matched_files_in_folder[0][0]
                        print(f"[修复] ✅ 将文件夹 {os.path.basename(folder_path)} 中的 {len(files)} 个未匹配文件分配给 {target_cert}")
                        for file_path in files:
                            files_by_stockist_cert[target_cert].append(file_path)
                            print(f"[修复]   添加文件: {os.path.basename(file_path)} -> {target_cert}")
                    else:
                        # 如果文件夹中没有已匹配的文件，分配给第一个 stockist_cert（如果有的话）
                        if stockist_certs:
                            target_cert = stockist_certs[0]
                            print(f"[修复] ✅ 将文件夹 {os.path.basename(folder_path)} 中的 {len(files)} 个未匹配文件分配给第一个 stockist_cert: {target_cert}")
                            for file_path in files:
                                if target_cert not in files_by_stockist_cert:
                                    files_by_stockist_cert[target_cert] = []
                                files_by_stockist_cert[target_cert].append(file_path)
                                print(f"[修复]   添加文件: {os.path.basename(file_path)} -> {target_cert}")
                        else:
                            # 如果没有 stockist_cert，仍然添加到第一个（如果有的话）
                            print(f"[警告] ❌ 文件夹 {os.path.basename(folder_path)} 中的 {len(files)} 个未匹配文件无法分配，因为没有 stockist_cert")
            else:
                # 对于非 IAT 类型，也尝试分配未匹配的文件
                if stockist_certs:
                    target_cert = stockist_certs[0]
                    print(f"[修复] 将 {len(unmatched_files)} 个未匹配文件分配给第一个 stockist_cert: {target_cert}")
                    for file_path in unmatched_files:
                        if target_cert not in files_by_stockist_cert:
                            files_by_stockist_cert[target_cert] = []
                        files_by_stockist_cert[target_cert].append(file_path)
        
        # 8. 打印最终文件分配情况
        print(f"[文件分配] 最终文件分配情况:")
        total_files_in_zip = 0
        for stockist_cert, files in files_by_stockist_cert.items():
            print(f"[文件分配] {stockist_cert}: {len(files)} 个文件")
            for file_path in files:
                print(f"[文件分配]   - {os.path.basename(file_path)}")
            total_files_in_zip += len(files)
        print(f"[文件分配] 总计: {total_files_in_zip} 个文件将被添加到 ZIP")
        
        # 7. 创建 ZIP 文件
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_zip_path = temp_zip.name
        temp_zip.close()
        
        try:
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                # 为每个 stockist_cert 创建文件夹并添加对应的文件
                files_added_count = 0
                for stockist_cert, files in files_by_stockist_cert.items():
                    if not files:
                        continue
                    
                    for file_path in files:
                        abs_file_path = os.path.abspath(file_path)
                        file_name = os.path.basename(file_path)
                        
                        # 判断文件来源（Stockist Cert、Private Formal、IAT Formal 等）
                        source_folder = None
                        base_folder_path = None
                        preserve_folder_structure = False  # 是否保留文件夹结构
                        
                        if abs_file_path.startswith(os.path.abspath(self.stockist_folder)):
                            source_folder = "Stockist Cert"
                            base_folder_path = self.stockist_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        elif abs_file_path.startswith(os.path.abspath(self.private_formal_folder)):
                            source_folder = "Private Formal"
                            base_folder_path = self.private_formal_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        elif abs_file_path.startswith(os.path.abspath(self.private_prelim_folder)):
                            source_folder = "Private Prelim"
                            base_folder_path = self.private_prelim_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        elif abs_file_path.startswith(os.path.abspath(self.iat_formal_folder)):
                            source_folder = "IAT Formal"
                            base_folder_path = self.iat_formal_folder
                            preserve_folder_structure = True  # 保留文件夹结构
                        elif abs_file_path.startswith(os.path.abspath(self.iat_prelim_folder)):
                            source_folder = "IAT Prelim"
                            base_folder_path = self.iat_prelim_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        else:
                            source_folder = "Other"
                            base_folder_path = None
                            preserve_folder_structure = False
                        
                        # 构建 ZIP 中的路径
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
                                    
                                    zip_path = f"{stockist_cert}/{source_folder}/{rel_path}"
                                else:
                                    zip_path = f"{stockist_cert}/{source_folder}/{file_name}"
                            else:
                                # 其他文件夹（IAT Prelim、Private Formal、Private Prelim、Stockist Cert）：
                                # 直接放在 stockist_cert 文件夹下，只放文件名
                                zip_path = f"{stockist_cert}/{file_name}"
                            
                            zipf.write(file_path, zip_path)
                            files_added_count += 1
                            print(f"[ZIP创建] 已添加文件: {file_name} -> {zip_path}")
                        except ValueError:
                            # 如果 relpath 失败（不同驱动器），使用文件名
                            if preserve_folder_structure:
                                zip_path = f"{stockist_cert}/{source_folder}/{file_name}"
                            else:
                                # 其他文件夹直接放在 stockist_cert 文件夹下
                                zip_path = f"{stockist_cert}/{file_name}"
                            zipf.write(file_path, zip_path)
                            files_added_count += 1
                            print(f"[ZIP创建] 已添加文件: {file_name} -> {zip_path}")
                        except Exception as e:
                            print(f"[ZIP创建] 添加文件失败: {file_name}, 错误: {e}")
                            import traceback
                            traceback.print_exc()
            
            try:
                print(f"[下载] 成功创建 ZIP 文件: {temp_zip_path}")
                print(f"[下载] 实际添加到 ZIP 的文件数: {files_added_count}")
                print(f"[下载] 原始找到的文件数: {len(all_files)}")
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            return temp_zip_path, files_added_count
            
        except Exception as e:
            # 如果创建 ZIP 失败，清理临时文件
            if os.path.exists(temp_zip_path):
                try:
                    os.remove(temp_zip_path)
                except:
                    pass
            raise e
    
    def get_orders_by_dd_no(self, dd_no: str) -> List[int]:
        """
        从 bbs_dd 表获取指定 DD_No 对应的所有 Order_No（去重）
        
        Args:
            dd_no: DD_No 值
            
        Returns:
            Order_No 列表
        """
        # 使用数据库适配器以支持 PostgreSQL
        if DB_ADAPTER_AVAILABLE:
            conn = get_db_connection()
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
        
        cursor = conn.cursor()
        
        try:
            # 处理 PostgreSQL 类型转换问题
            # 如果 dd_no 字段是 INTEGER，需要将参数转换为整数，或者将字段转换为文本
            if DB_ADAPTER_AVAILABLE and is_postgres():
                # PostgreSQL: 尝试将 dd_no 转换为整数进行比较
                try:
                    dd_no_int = int(dd_no)
                    query = """
                        SELECT DISTINCT bbs_no
                        FROM bbs_dd
                        WHERE dd_no = %s
                    """
                    cursor.execute(query, (dd_no_int,))
                except (ValueError, TypeError):
                    # 如果转换失败，使用文本比较（将字段转换为文本）
                    query = """
                        SELECT DISTINCT bbs_no
                        FROM bbs_dd
                        WHERE CAST(dd_no AS TEXT) = %s
                    """
                    cursor.execute(query, (str(dd_no),))
            else:
                # SQLite: 直接使用字符串比较
                query = """
                    SELECT DISTINCT bbs_no
                    FROM bbs_dd
                    WHERE dd_no = ?
                """
                cursor.execute(query, (dd_no,))
            
            rows = cursor.fetchall()
            
            order_nos = []
            for row in rows:
                # 处理不同的行格式（SQLite Row vs PostgreSQL dict）
                if hasattr(row, 'get'):
                    order_no = row.get('bbs_no') or row.get('BBS_No')
                elif isinstance(row, dict):
                    order_no = row.get('bbs_no') or row.get('BBS_No')
                else:
                    order_no = row[0] if len(row) > 0 else None
                
                if order_no:
                    try:
                        order_no_int = int(order_no) if order_no else None
                        if order_no_int and order_no_int not in order_nos:
                            order_nos.append(order_no_int)
                    except (ValueError, TypeError):
                        continue
            
            return order_nos
        finally:
            conn.close()
    
    def download_by_dd_no(self, dd_no: str) -> Tuple[str, int]:
        """
        按 DD_No 下载所有相关 PDF 文件
        
        Args:
            dd_no: DD_No 值
            
        Returns:
            (zip_file_path, file_count) 元组，zip_file_path 是临时 ZIP 文件路径
        """
        # 1. 获取该 DD_No 对应的所有 Order_No
        order_nos = self.get_orders_by_dd_no(dd_no)
        
        if not order_nos:
            raise ValueError(f"DD_No {dd_no} 在 bbs_dd 表中未找到对应的 Order_No")
        
        # 2. 为每个 Order 下载文件，并收集所有文件（去重）
        all_files_set = set()  # 使用集合去重，存储所有文件路径
        all_stockist_certs_set = set()  # 收集所有 order 的所有 stockist_cert（去重）
        all_rm_dn_nos_set = set()  # 收集所有 order 的所有 rm_dn_no（去重）
        all_rm_dn_to_stockist_map = {}  # 合并所有订单的 rm_dn_no 到 stockist_cert 映射
        
        for order_no in order_nos:
            try:
                # 获取订单信息
                order_info = self.get_order_info(order_no)
                if not order_info:
                    continue
                
                # 获取所有 stockist_cert 和 rm_dn_no 值
                stockist_certs, rm_dn_nos = self.get_all_cert_dn_values(order_no)
                
                # 获取该订单的 rm_dn_no 到 stockist_cert 映射
                order_rm_dn_map = self.get_rm_dn_to_stockist_cert_map(order_no)
                # 合并到总映射中（如果同一个 rm_dn_no 对应不同的 stockist_cert，保留第一个）
                for rm_dn_no, stockist_cert in order_rm_dn_map.items():
                    if rm_dn_no not in all_rm_dn_to_stockist_map:
                        all_rm_dn_to_stockist_map[rm_dn_no] = stockist_cert
                
                # 收集所有 stockist_cert（去重）
                for stockist_cert in stockist_certs:
                    if stockist_cert:
                        all_stockist_certs_set.add(stockist_cert)
                
                # 收集所有 rm_dn_no（去重）
                for rm_dn_no in rm_dn_nos:
                    if rm_dn_no:
                        all_rm_dn_nos_set.add(rm_dn_no)
                
                # 合并所有关键词
                all_keywords = stockist_certs + rm_dn_nos
                all_keywords = [k for k in all_keywords if k]  # 移除空值
                
                if not all_keywords:
                        continue
                
                # 从 Stockist 文件夹下载所有相关 PDF
                stockist_files = self.find_files_by_keywords(self.stockist_folder, all_keywords)
                
                # 判断类型并查找对应文件夹
                jobsite_type = order_info['jobsite_type'] or ''
                is_iat, is_private = self.check_jobsite_type(jobsite_type)
                
                additional_files = []
                
                if is_iat:
                    # IAT 类型：按每个 stockist_cert 单独判断，有 Formal 就用 Formal，没有就立即查 Prelim
                    certs_norm = [c.strip() for c in stockist_certs if c and str(c).strip()]
                    
                    for cert in certs_norm:
                        # 1. 先检查该 cert 是否有对应的 IAT Formal 目录
                        formal_folder = os.path.join(self.iat_formal_folder, cert)
                        cert_has_formal = False
                        
                        if os.path.exists(formal_folder) and os.path.isdir(formal_folder):
                            # 检查目录里是否有 PDF
                            cert_formal_files = []
                            for root, _dirs, files in os.walk(formal_folder):
                                for fn in files:
                                    if fn.lower().endswith('.pdf'):
                                        fp = os.path.join(root, fn)
                                        if os.path.exists(fp):
                                            cert_formal_files.append(fp)
                            
                            if cert_formal_files:
                                cert_has_formal = True
                                additional_files.extend(cert_formal_files)
                                try:
                                    print(f"[IAT下载] Order {order_no}: Cert {cert} 使用 IAT Formal 目录 {formal_folder}，共 {len(cert_formal_files)} 个文件")
                                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                                    pass
                        
                        # 2. 如果该 cert 没有 Formal，立即去 IAT Prelim 搜索
                        if not cert_has_formal:
                            # 为该 cert 构建关键词（cert + 对应的 rm_dn_no）
                            cert_keywords = [cert]
                            for rm_dn_no, mapped_cert in order_rm_dn_map.items():
                                if mapped_cert == cert:
                                    cert_keywords.append(rm_dn_no)
                            
                            if cert_keywords:
                                cert_prelim_files = self.find_files_by_keywords(
                                    self.iat_prelim_folder,
                                    cert_keywords,
                                    search_subfolders=True
                                )
                                
                                if cert_prelim_files:
                                    # 验证这些文件确实属于这个 cert
                                    valid_prelim_for_cert = []
                                    for file_path in cert_prelim_files:
                                        file_name = os.path.basename(file_path)
                                        matched_cert = self.match_file_to_stockist_cert(
                                            file_name, file_path, [cert], rm_dn_nos, order_rm_dn_map
                                        )
                                        if matched_cert == cert:
                                            valid_prelim_for_cert.append(file_path)
                                    
                                    if valid_prelim_for_cert:
                                        additional_files.extend(valid_prelim_for_cert)
                                        try:
                                            print(f"[IAT下载] Order {order_no}: Cert {cert} 无 Formal，使用 {len(valid_prelim_for_cert)} 个 IAT Prelim 文件")
                                        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                                            pass
                            
                elif is_private:
                    # Private 类型
                    private_formal_files = self.find_files_by_keywords(self.private_formal_folder, all_keywords, search_subfolders=True)
                    
                    # 将 Private Formal 中找到的文件按 stockist_cert 分组
                    formal_files_by_cert = {}
                    for file_path in private_formal_files:
                        file_name = os.path.basename(file_path)
                        matched_cert = self.match_file_to_stockist_cert(
                            file_name, file_path, stockist_certs, rm_dn_nos, order_rm_dn_map
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
                            # 为缺失的 stockist_cert 构建关键词（只包含这些 cert 和对应的 rm_dn_no）
                            missing_keywords = []
                            for cert in missing_certs:
                                missing_keywords.append(cert)
                                # 查找该 cert 对应的 rm_dn_no
                                for rm_dn_no, mapped_cert in order_rm_dn_map.items():
                                    if mapped_cert == cert:
                                        missing_keywords.append(rm_dn_no)
                            
                            if missing_keywords:
                                # 查找 Private Prelim（搜索所有文件，包括子文件夹中的文件）
                                private_prelim_files = self.find_files_by_keywords(self.private_prelim_folder, missing_keywords, search_subfolders=True)
                                
                                if private_prelim_files:
                                    # 验证这些文件确实属于缺失的 stockist_cert
                                    valid_prelim_files = []
                                    for file_path in private_prelim_files:
                                        file_name = os.path.basename(file_path)
                                        matched_cert = self.match_file_to_stockist_cert(
                                            file_name, file_path, missing_certs, rm_dn_nos, order_rm_dn_map
                                        )
                                        if matched_cert and matched_cert in missing_certs:
                                            valid_prelim_files.append(file_path)
                                    
                                    if valid_prelim_files:
                                        additional_files.extend(valid_prelim_files)
                    else:
                        # Private Formal 中没有文件，查找 Private Prelim
                        private_prelim_files = self.find_files_by_keywords(self.private_prelim_folder, all_keywords, search_subfolders=True)
                        if private_prelim_files:
                            additional_files.extend(private_prelim_files)
                
                # 合并该 Order 的所有文件并添加到总集合中（去重）
                order_files = stockist_files + additional_files
                all_files_set.update(order_files)
                
            except Exception as e:
                print(f"[错误] Order {order_no} 处理失败: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        if not all_files_set:
            raise ValueError(f"DD_No {dd_no} 对应的所有 Order 都没有找到相关 PDF 文件")
        
        # 转换为列表
        all_files = list(all_files_set)
        all_stockist_certs = list(all_stockist_certs_set)
        all_rm_dn_nos = list(all_rm_dn_nos_set)
        
        # 只打印最终统计信息
        try:
            print(f"[下载] DD_No {dd_no}: 找到 {len(all_files)} 个唯一文件")
        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
            pass
        
        # 3. 按照 stockist_cert 组织文件（和 download_by_order 保持一致）
        # 创建一个字典，key 是 stockist_cert，value 是该 stockist_cert 对应的文件列表
        files_by_stockist_cert = {}
        
        # 为每个 stockist_cert 创建空列表
        for stockist_cert in all_stockist_certs:
            if stockist_cert:
                files_by_stockist_cert[stockist_cert] = []
        
        # 按照 stockist_cert 组织文件
        
        # 将所有文件按照 stockist_cert 分类
        for file_path in all_files:
            file_name = os.path.basename(file_path)
            
            # 使用通用匹配方法
            matched_stockist_cert = self.match_file_to_stockist_cert(
                file_name, file_path, all_stockist_certs, all_rm_dn_nos, all_rm_dn_to_stockist_map
            )
            
            if matched_stockist_cert:
                files_by_stockist_cert[matched_stockist_cert].append(file_path)
            else:
                # 如果文件不匹配任何 stockist_cert，不做任何处理（不添加到 ZIP）
                pass
        
        # 4. 创建 ZIP 文件（和 download_by_order 保持完全一致的结构）
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_zip_path = temp_zip.name
        temp_zip.close()
        
        try:
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                # 为每个 stockist_cert 创建文件夹并添加对应的文件
                files_added_count = 0
                for stockist_cert, files in files_by_stockist_cert.items():
                    if not files:
                        print(f"[ZIP创建] 跳过空的 stockist_cert: {stockist_cert}")
                        continue
                    
                    print(f"[ZIP创建] 处理 stockist_cert: {stockist_cert}, {len(files)} 个文件")
                    for file_path in files:
                        abs_file_path = os.path.abspath(file_path)
                        file_name = os.path.basename(file_path)
                        
                        # 判断文件来源（Stockist Cert、Private Formal、IAT Formal 等）
                        source_folder = None
                        base_folder_path = None
                        preserve_folder_structure = False  # 是否保留文件夹结构
                        
                        if abs_file_path.startswith(os.path.abspath(self.stockist_folder)):
                            source_folder = "Stockist Cert"
                            base_folder_path = self.stockist_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        elif abs_file_path.startswith(os.path.abspath(self.private_formal_folder)):
                            source_folder = "Private Formal"
                            base_folder_path = self.private_formal_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        elif abs_file_path.startswith(os.path.abspath(self.private_prelim_folder)):
                            source_folder = "Private Prelim"
                            base_folder_path = self.private_prelim_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        elif abs_file_path.startswith(os.path.abspath(self.iat_formal_folder)):
                            source_folder = "IAT Formal"
                            base_folder_path = self.iat_formal_folder
                            preserve_folder_structure = True  # 保留文件夹结构
                        elif abs_file_path.startswith(os.path.abspath(self.iat_prelim_folder)):
                            source_folder = "IAT Prelim"
                            base_folder_path = self.iat_prelim_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        else:
                            source_folder = "Other"
                            base_folder_path = None
                            preserve_folder_structure = False
                        
                        # 构建 ZIP 中的路径（和 download_by_order 完全一致）
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
                                    
                                    zip_path = f"{stockist_cert}/{source_folder}/{rel_path}"
                                else:
                                    zip_path = f"{stockist_cert}/{source_folder}/{file_name}"
                            else:
                                # 其他文件夹（IAT Prelim、Private Formal、Private Prelim、Stockist Cert）：
                                # 直接放在 stockist_cert 文件夹下，只放文件名
                                zip_path = f"{stockist_cert}/{file_name}"
                            
                            zipf.write(file_path, zip_path)
                        except ValueError:
                            # 如果 relpath 失败（不同驱动器），使用文件名
                            if preserve_folder_structure:
                                zip_path = f"{stockist_cert}/{source_folder}/{file_name}"
                            else:
                                # 其他文件夹直接放在 stockist_cert 文件夹下
                                zip_path = f"{stockist_cert}/{file_name}"
                            zipf.write(file_path, zip_path)
            
            try:
                print(f"[下载] 成功创建 ZIP 文件: {temp_zip_path}, 包含 {len(all_files)} 个文件")
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            return temp_zip_path, len(all_files)
            
        except Exception as e:
            # 如果创建 ZIP 失败，清理临时文件
            if os.path.exists(temp_zip_path):
                try:
                    os.remove(temp_zip_path)
                except:
                    pass
            raise e
    
    def download_by_order_nos(self, order_nos: List[int]) -> Tuple[str, int]:
        """
        批量按多个 Order No 下载所有相关 PDF 文件
        
        Args:
            order_nos: 订单号列表
            
        Returns:
            (zip_file_path, file_count) 元组，zip_file_path 是临时 ZIP 文件路径
            
        ZIP 结构：
        - Order_No_1/
          - Stockist_No_1/
            - file1.pdf
          - Stockist_No_2/
            - file2.pdf
        - Order_No_2/
          - Stockist_No_1/
            - file3.pdf
        """
        if not order_nos:
            raise ValueError("Order No 列表不能为空")
        
        try:
            print(f"[下载] 批量下载 {len(order_nos)} 个 Order")
        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
            pass
        
        # 1. 批量查询所有订单的信息（优化：一次性查询）
        try:
            print(f"[下载] 批量查询 {len(order_nos)} 个订单的信息...")
        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
            pass
        orders_info = self.get_orders_info_batch(order_nos)
        cert_dn_values = self.get_all_cert_dn_values_batch(order_nos)
        rm_dn_maps = self.get_rm_dn_to_stockist_cert_map_batch(order_nos)
        
        # 2. 为每个 Order 收集文件，按 Order_No 和 stockist_cert 组织
        # 结构：{(order_no, stockist_cert): [file_paths]}
        files_by_order_and_cert = {}
        # 用于统计总文件数（去重，同一个文件在不同Order中只统计一次）
        all_files_set = set()
        
        for order_no in order_nos:
            try:
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
                stockist_files = self.find_files_by_keywords(self.stockist_folder, all_keywords)
                
                # 判断类型并查找对应文件夹
                jobsite_type = order_info['jobsite_type'] or ''
                is_iat, is_private = self.check_jobsite_type(jobsite_type)
                
                additional_files = []
                
                if is_iat:
                    # IAT 类型
                    iat_formal_files = self.find_files_by_keywords(self.iat_formal_folder, all_keywords, search_subfolders=False)
                    
                    if iat_formal_files:
                        additional_files.extend(iat_formal_files)
                        print(f"[IAT下载] Order {order_no}: IAT Formal 已有文件，跳过 IAT Prelim 搜索")
                    else:
                        # IAT Formal 没有对应文件夹或文件夹为空，回退到 IAT Prelim 递归文件搜索
                        print(f"[IAT下载] Order {order_no}: IAT Formal 无对应文件夹或文件夹为空，回退 IAT Prelim 递归搜索")
                        iat_prelim_files = self.find_files_by_keywords(self.iat_prelim_folder, all_keywords, search_subfolders=True)
                        if iat_prelim_files:
                            additional_files.extend(iat_prelim_files)
                            
                elif is_private:
                    # Private 类型
                    private_formal_files = self.find_files_by_keywords(self.private_formal_folder, all_keywords, search_subfolders=True)
                    
                    # 将 Private Formal 中找到的文件按 stockist_cert 分组
                    formal_files_by_cert = {}
                    for file_path in private_formal_files:
                        file_name = os.path.basename(file_path)
                        matched_cert = self.match_file_to_stockist_cert(
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
                                private_prelim_files = self.find_files_by_keywords(self.private_prelim_folder, missing_keywords, search_subfolders=True)
                                if private_prelim_files:
                                    # 只添加属于缺失 stockist_cert 的文件
                                    valid_prelim_files = []
                                    for file_path in private_prelim_files:
                                        file_name = os.path.basename(file_path)
                                        matched_cert = self.match_file_to_stockist_cert(
                                            file_name, file_path, missing_certs, rm_dn_nos, rm_dn_to_stockist_map
                                        )
                                        if matched_cert and matched_cert in missing_certs:
                                            valid_prelim_files.append(file_path)
                                    additional_files.extend(valid_prelim_files)
                    else:
                        private_prelim_files = self.find_files_by_keywords(self.private_prelim_folder, all_keywords, search_subfolders=True)
                        if private_prelim_files:
                            additional_files.extend(private_prelim_files)
                
                # 合并该 Order 的所有文件
                order_files = stockist_files + additional_files
                
                # 按 stockist_cert 组织该 Order 的文件
                # 注意：同一个文件可以在多个Order的文件夹中都存在（不去重）
                for file_path in order_files:
                    file_name = os.path.basename(file_path)
                    
                    # 使用通用匹配方法
                    matched_stockist_cert = self.match_file_to_stockist_cert(
                        file_name, file_path, stockist_certs, rm_dn_nos, rm_dn_to_stockist_map
                    )
                    
                    if matched_stockist_cert:
                        key = (order_no, matched_stockist_cert)
                        if key not in files_by_order_and_cert:
                            files_by_order_and_cert[key] = []
                        files_by_order_and_cert[key].append(file_path)
                        all_files_set.add(file_path)  # 用于统计总文件数
                    else:
                        # 如果文件不匹配任何 stockist_cert，跳过
                        pass
                
            except Exception as e:
                try:
                    print(f"[下载] Order {order_no} 处理失败: {e}")
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
                import traceback
                traceback.print_exc()
                continue
        
        if not files_by_order_and_cert:
            raise ValueError(f"所有 Order {order_nos} 都没有找到相关 PDF 文件")
        
        # 统计每个Order的文件数量
        order_file_counts = {}
        for (order_no, stockist_cert), files in files_by_order_and_cert.items():
            if order_no not in order_file_counts:
                order_file_counts[order_no] = 0
            order_file_counts[order_no] += len(files)
        
        try:
            print(f"[下载] 批量下载总共找到 {len(all_files_set)} 个唯一文件（已去重）")
            print(f"[下载] 各Order文件统计: {order_file_counts}")
            print(f"[下载] 文件组织结构: {[(order_no, stockist_cert, len(files)) for (order_no, stockist_cert), files in files_by_order_and_cert.items()]}")
        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
            pass
        
        # 2. 创建 ZIP 文件
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
                        
                        if abs_file_path.startswith(os.path.abspath(self.stockist_folder)):
                            source_folder = "Stockist Cert"
                            base_folder_path = self.stockist_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        elif abs_file_path.startswith(os.path.abspath(self.private_formal_folder)):
                            source_folder = "Private Formal"
                            base_folder_path = self.private_formal_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        elif abs_file_path.startswith(os.path.abspath(self.private_prelim_folder)):
                            source_folder = "Private Prelim"
                            base_folder_path = self.private_prelim_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        elif abs_file_path.startswith(os.path.abspath(self.iat_formal_folder)):
                            source_folder = "IAT Formal"
                            base_folder_path = self.iat_formal_folder
                            preserve_folder_structure = True  # 保留文件夹结构
                        elif abs_file_path.startswith(os.path.abspath(self.iat_prelim_folder)):
                            source_folder = "IAT Prelim"
                            base_folder_path = self.iat_prelim_folder
                            preserve_folder_structure = False  # 只放 PDF 文件
                        else:
                            source_folder = "Other"
                            base_folder_path = None
                            preserve_folder_structure = False
                        
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
            
            try:
                print(f"[下载] 成功创建 ZIP，包含 {len(all_files_set)} 个文件")
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            return temp_zip_path, len(all_files_set)
            
        except Exception as e:
            # 如果创建 ZIP 失败，清理临时文件
            if os.path.exists(temp_zip_path):
                try:
                    os.remove(temp_zip_path)
                except:
                    pass
            raise e
    
    def get_dd_no_by_order(self, order_no: int) -> Optional[str]:
        """
        从 bbs_dd 表获取指定 Order_No 对应的 DD_No
        
        Args:
            order_no: 订单号
            
        Returns:
            DD_No 值，如果不存在返回 None
        """
        # 使用数据库适配器以支持 PostgreSQL
        if DB_ADAPTER_AVAILABLE:
            conn = get_db_connection()
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
        
        cursor = conn.cursor()
        
        try:
            if DB_ADAPTER_AVAILABLE and is_postgres():
                query = """
                    SELECT DISTINCT dd_no
                    FROM bbs_dd
                    WHERE bbs_no = %s
                    LIMIT 1
                """
                cursor.execute(query, (order_no,))
            else:
                query = """
                    SELECT DISTINCT dd_no
                    FROM bbs_dd
                    WHERE bbs_no = ?
                    LIMIT 1
                """
                cursor.execute(query, (order_no,))
            
            row = cursor.fetchone()
            
            if row:
                # 处理不同的行格式
                if hasattr(row, 'get'):
                    dd_no = row.get('dd_no') or row.get('DD_No')
                elif isinstance(row, dict):
                    dd_no = row.get('dd_no') or row.get('DD_No')
                else:
                    dd_no = row[0] if len(row) > 0 else None
                
                if dd_no:
                    dd_no = str(dd_no).strip()
                    return dd_no if dd_no else None
            
            return None
        finally:
            conn.close()
    
    def get_dd_no_by_orders_batch(self, order_nos: List[int]) -> Dict[int, str]:
        """
        批量获取多个订单对应的 DD_No（优化版本）
        
        Args:
            order_nos: 订单号列表
            
        Returns:
            {order_no: dd_no} 字典
        """
        if not order_nos:
            return {}
        
        # 分批处理，每批最多500个订单
        BATCH_SIZE = 500
        all_results = {}
        
        for i in range(0, len(order_nos), BATCH_SIZE):
            batch = order_nos[i:i + BATCH_SIZE]
            
            # 使用数据库适配器以支持 PostgreSQL
            if DB_ADAPTER_AVAILABLE:
                conn = get_db_connection()
            else:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
            
            cursor = conn.cursor()
            
            try:
                if DB_ADAPTER_AVAILABLE and is_postgres():
                    placeholders = ','.join(['%s'] * len(batch))
                    query = f"""
                        SELECT DISTINCT bbs_no, dd_no
                        FROM bbs_dd
                        WHERE bbs_no IN ({placeholders})
                    """
                    cursor.execute(query, batch)
                else:
                    placeholders = ','.join('?' * len(batch))
                    query = f"""
                        SELECT DISTINCT bbs_no, dd_no
                        FROM bbs_dd
                        WHERE bbs_no IN ({placeholders})
                    """
                    cursor.execute(query, batch)
                
                rows = cursor.fetchall()
                
                for row in rows:
                    try:
                        # 处理不同的行格式
                        if hasattr(row, 'get'):
                            order_no = int(row.get('bbs_no') or row.get('BBS_No'))
                            dd_no = row.get('dd_no') or row.get('DD_No')
                        elif isinstance(row, dict):
                            order_no = int(row.get('bbs_no') or row.get('BBS_No'))
                            dd_no = row.get('dd_no') or row.get('DD_No')
                        else:
                            order_no = int(row[0] if len(row) > 0 else 0)
                            dd_no = row[1] if len(row) > 1 else None
                        
                        if dd_no:
                            dd_no = str(dd_no).strip()
                            if dd_no:
                                all_results[order_no] = dd_no
                    except (KeyError, ValueError, TypeError):
                        continue
            finally:
                conn.close()
        
        return all_results
    
    def download_by_order_nos_grouped_by_dd_no(self, order_nos: List[int]) -> Tuple[str, int]:
        """
        批量按多个 Order No 下载，按 DD_No 分组
        
        Args:
            order_nos: 订单号列表
            
        Returns:
            (zip_file_path, file_count) 元组，zip_file_path 是临时 ZIP 文件路径
            
        ZIP 结构：
        - DD_No_1/
          - Stockist_No_1/
            - file1.pdf
          - Stockist_No_2/
            - file2.pdf
        - DD_No_2/
          - Stockist_No_1/
            - file3.pdf
        
        逻辑：
        1. 从每个 order_no 获取对应的 DD_No
        2. 对 DD_No 去重
        3. 为每个 DD_No 下载文件（与单个 DD_No 下载逻辑一致）
        """
        if not order_nos:
            raise ValueError("Order No 列表不能为空")
        
        try:
            print(f"[下载] 批量按 DD_No 下载 {len(order_nos)} 个 Order")
        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
            pass
        
        # 1. 批量获取每个 Order_No 对应的 DD_No，并去重（优化）
        try:
            print(f"[下载] 批量查询 {len(order_nos)} 个订单的 DD_No...")
        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
            pass
        order_to_dd_no = self.get_dd_no_by_orders_batch(order_nos)
        dd_no_to_orders = {}  # {dd_no: [order_nos]}
        
        for order_no, dd_no in order_to_dd_no.items():
            if dd_no not in dd_no_to_orders:
                dd_no_to_orders[dd_no] = []
            dd_no_to_orders[dd_no].append(order_no)
        
        if not dd_no_to_orders:
            raise ValueError(f"所有 Order {order_nos} 都没有找到对应的 DD_No")
        
        # 去重后的 DD_No 列表
        unique_dd_nos = list(dd_no_to_orders.keys())
        try:
            print(f"[下载] 找到 {len(unique_dd_nos)} 个唯一的 DD_No: {unique_dd_nos}")
        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
            pass
        # 2. 为每个 DD_No 收集文件
        # 结构：{dd_no: {stockist_cert: [file_paths]}}
        files_by_dd_no_and_cert = {}  # {dd_no: {stockist_cert: [file_paths]}}
        all_files_set = set()  # 用于统计总文件数（跨所有DD_No去重）
        
        for dd_no in unique_dd_nos:
            # 获取该 DD_No 对应的所有 Order_No
            order_nos_for_dd = dd_no_to_orders[dd_no]
            
            # 批量查询该 DD_No 下所有订单的信息（优化）
            orders_info_batch = self.get_orders_info_batch(order_nos_for_dd)
            cert_dn_values_batch = self.get_all_cert_dn_values_batch(order_nos_for_dd)
            rm_dn_maps_batch = self.get_rm_dn_to_stockist_cert_map_batch(order_nos_for_dd)
            
            # 为该 DD_No 收集所有文件（去重）
            dd_files_set = set()  # 该 DD_No 的所有文件（去重）
            all_stockist_certs_set = set()  # 收集所有 stockist_cert（去重）
            all_rm_dn_nos_set = set()  # 收集所有 rm_dn_no（去重）
            all_rm_dn_to_stockist_map = {}  # 合并所有订单的 rm_dn_no 到 stockist_cert 映射
            
            # 为每个 Order 收集文件
            for order_no in order_nos_for_dd:
                try:
                    # 从批量查询结果中获取订单信息
                    order_info = orders_info_batch.get(order_no)
                    if not order_info:
                        continue
                    
                    # 从批量查询结果中获取 stockist_cert 和 rm_dn_no
                    cert_dn = cert_dn_values_batch.get(order_no)
                    if not cert_dn:
                        continue
                    stockist_certs, rm_dn_nos = cert_dn
                    
                    # 从批量查询结果中获取 rm_dn_no 到 stockist_cert 映射
                    order_rm_dn_map = rm_dn_maps_batch.get(order_no, {})
                    # 合并到总映射中（如果同一个 rm_dn_no 对应不同的 stockist_cert，保留第一个）
                    for rm_dn_no, stockist_cert in order_rm_dn_map.items():
                        if rm_dn_no not in all_rm_dn_to_stockist_map:
                            all_rm_dn_to_stockist_map[rm_dn_no] = stockist_cert
                    
                    # 收集所有 stockist_cert（去重）
                    for stockist_cert in stockist_certs:
                        if stockist_cert:
                            all_stockist_certs_set.add(stockist_cert)
                    
                    # 收集所有 rm_dn_no（去重）
                    for rm_dn_no in rm_dn_nos:
                        if rm_dn_no:
                            all_rm_dn_nos_set.add(rm_dn_no)
                    
                    # 合并所有关键词
                    all_keywords = stockist_certs + rm_dn_nos
                    all_keywords = [k for k in all_keywords if k]  # 移除空值
                    
                    if not all_keywords:
                        continue
                    
                    # 从 Stockist 文件夹下载所有相关 PDF
                    stockist_files = self.find_files_by_keywords(self.stockist_folder, all_keywords)
                    
                    # 判断类型并查找对应文件夹
                    jobsite_type = order_info['jobsite_type'] or ''
                    is_iat, is_private = self.check_jobsite_type(jobsite_type)
                    
                    additional_files = []
                    
                    if is_iat:
                        # IAT 类型：按每个 stockist_cert 单独判断，有 Formal 就用 Formal，没有就立即查 Prelim
                        certs_norm = [c.strip() for c in stockist_certs if c and str(c).strip()]
                        
                        for cert in certs_norm:
                            # 1. 先检查该 cert 是否有对应的 IAT Formal 目录
                            formal_folder = os.path.join(self.iat_formal_folder, cert)
                            cert_has_formal = False
                            
                            if os.path.exists(formal_folder) and os.path.isdir(formal_folder):
                                # 检查目录里是否有 PDF
                                cert_formal_files = []
                                for root, _dirs, files in os.walk(formal_folder):
                                    for fn in files:
                                        if fn.lower().endswith('.pdf'):
                                            fp = os.path.join(root, fn)
                                            if os.path.exists(fp):
                                                cert_formal_files.append(fp)
                                
                                if cert_formal_files:
                                    cert_has_formal = True
                                    additional_files.extend(cert_formal_files)
                                    try:
                                        print(f"[IAT下载] Order {order_no}: Cert {cert} 使用 IAT Formal 目录 {formal_folder}，共 {len(cert_formal_files)} 个文件")
                                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                                        pass
                            
                            # 2. 如果该 cert 没有 Formal，立即去 IAT Prelim 搜索
                            if not cert_has_formal:
                                # 为该 cert 构建关键词（cert + 对应的 rm_dn_no）
                                cert_keywords = [cert]
                                for rm_dn_no, mapped_cert in order_rm_dn_map.items():
                                    if mapped_cert == cert:
                                        cert_keywords.append(rm_dn_no)
                                
                                if cert_keywords:
                                    cert_prelim_files = self.find_files_by_keywords(
                                        self.iat_prelim_folder,
                                        cert_keywords,
                                        search_subfolders=True
                                    )
                                    
                                    if cert_prelim_files:
                                        # 验证这些文件确实属于这个 cert
                                        valid_prelim_for_cert = []
                                        for file_path in cert_prelim_files:
                                            file_name = os.path.basename(file_path)
                                            matched_cert = self.match_file_to_stockist_cert(
                                                file_name, file_path, [cert], rm_dn_nos, order_rm_dn_map
                                            )
                                            if matched_cert == cert:
                                                valid_prelim_for_cert.append(file_path)
                                        
                                        if valid_prelim_for_cert:
                                            additional_files.extend(valid_prelim_for_cert)
                                            try:
                                                print(f"[IAT下载] Order {order_no}: Cert {cert} 无 Formal，使用 {len(valid_prelim_for_cert)} 个 IAT Prelim 文件")
                                            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                                                pass
                    elif is_private:
                        # Private 类型
                        private_formal_files = self.find_files_by_keywords(self.private_formal_folder, all_keywords, search_subfolders=True)
                        if private_formal_files:
                            additional_files.extend(private_formal_files)
                        else:
                            private_prelim_files = self.find_files_by_keywords(self.private_prelim_folder, all_keywords, search_subfolders=True)
                            if private_prelim_files:
                                additional_files.extend(private_prelim_files)
                    
                    # 合并该 Order 的所有文件并添加到该 DD_No 的集合中（去重）
                    order_files = stockist_files + additional_files
                    dd_files_set.update(order_files)
                    
                    
                except Exception as e:
                    try:
                        print(f"[下载] Order {order_no} 处理失败: {e}")
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                    import traceback
                    traceback.print_exc()
                    continue
            
            # 转换为列表（该 DD_No 的所有文件）
            all_files = list(dd_files_set)
            all_stockist_certs = list(all_stockist_certs_set)
            all_rm_dn_nos = list(all_rm_dn_nos_set)
            
            # 添加到总文件集合（用于统计）
            all_files_set.update(dd_files_set)
            
            if not all_files:
                try:
                    print(f"[下载] DD_No {dd_no} 对应的所有 Order 都没有找到相关 PDF 文件")
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
                continue
            
            # 只打印最终统计信息
            
            # 按照 stockist_cert 组织文件（和 download_by_dd_no 保持一致）
            files_by_stockist_cert = {}
            
            # 为每个 stockist_cert 创建空列表
            for stockist_cert in all_stockist_certs:
                if stockist_cert:
                    files_by_stockist_cert[stockist_cert] = []
            
            # 按照 stockist_cert 组织文件
            
            # 将所有文件按照 stockist_cert 分类
            for file_path in all_files:
                file_name = os.path.basename(file_path)
                
                # 使用通用匹配方法
                matched_stockist_cert = self.match_file_to_stockist_cert(
                    file_name, file_path, all_stockist_certs, all_rm_dn_nos, all_rm_dn_to_stockist_map
                )
                
                if matched_stockist_cert:
                    files_by_stockist_cert[matched_stockist_cert].append(file_path)
                    try:
                        print(f"[下载] 文件 {file_name} 匹配到 stockist_cert: {matched_stockist_cert}")
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                else:
                    # 如果文件不匹配任何 stockist_cert，不做任何处理（不添加到 ZIP）
                    try:
                        print(f"[下载] 文件 {file_name} 未匹配到任何 stockist_cert，跳过该文件")
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
            
            # 保存该 DD_No 的文件组织结构
            files_by_dd_no_and_cert[dd_no] = files_by_stockist_cert
        
        if not files_by_dd_no_and_cert:
            raise ValueError(f"所有 DD_No {unique_dd_nos} 都没有找到相关 PDF 文件")
        
        # 统计各DD_No的文件数
        dd_no_file_counts = {}
        for dd_no, files_by_cert in files_by_dd_no_and_cert.items():
            total_count = sum(len(files) for files in files_by_cert.values())
            dd_no_file_counts[dd_no] = total_count
        
        try:
            try:
                print(f"[下载] 批量下载总共找到 {len(all_files_set)} 个唯一文件（已去重）")
                print(f"[下载] 各DD_No文件统计: {dd_no_file_counts}")
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
            pass
        
        # 3. 创建 ZIP 文件
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_zip_path = temp_zip.name
        temp_zip.close()
        
        try:
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                # 为每个 DD_No 和 stockist_cert 组合创建文件夹并添加文件
                for dd_no, files_by_stockist_cert in files_by_dd_no_and_cert.items():
                    for stockist_cert, files in files_by_stockist_cert.items():
                        if not files or not stockist_cert:
                            continue
                        
                        for file_path in files:
                            abs_file_path = os.path.abspath(file_path)
                            file_name = os.path.basename(file_path)
                            
                            # 判断文件来源（Stockist Cert、Private Formal、IAT Formal 等）
                            source_folder = None
                            base_folder_path = None
                            preserve_folder_structure = False  # 是否保留文件夹结构
                            
                            if abs_file_path.startswith(os.path.abspath(self.stockist_folder)):
                                source_folder = "Stockist Cert"
                                base_folder_path = self.stockist_folder
                                preserve_folder_structure = False  # 只放 PDF 文件
                            elif abs_file_path.startswith(os.path.abspath(self.private_formal_folder)):
                                source_folder = "Private Formal"
                                base_folder_path = self.private_formal_folder
                                preserve_folder_structure = False  # 只放 PDF 文件
                            elif abs_file_path.startswith(os.path.abspath(self.private_prelim_folder)):
                                source_folder = "Private Prelim"
                                base_folder_path = self.private_prelim_folder
                                preserve_folder_structure = False  # 只放 PDF 文件
                            elif abs_file_path.startswith(os.path.abspath(self.iat_formal_folder)):
                                source_folder = "IAT Formal"
                                base_folder_path = self.iat_formal_folder
                                preserve_folder_structure = True  # 保留文件夹结构
                            elif abs_file_path.startswith(os.path.abspath(self.iat_prelim_folder)):
                                source_folder = "IAT Prelim"
                                base_folder_path = self.iat_prelim_folder
                                preserve_folder_structure = False  # 只放 PDF 文件
                            else:
                                source_folder = "Other"
                                base_folder_path = None
                                preserve_folder_structure = False
                            
                            # 构建 ZIP 中的路径：DD_No/stockist_cert/...
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
                                        
                                        zip_path = f"{dd_no}/{stockist_cert}/{source_folder}/{rel_path}"
                                    else:
                                        zip_path = f"{dd_no}/{stockist_cert}/{source_folder}/{file_name}"
                                else:
                                    # 其他文件夹（IAT Prelim、Private Formal、Private Prelim、Stockist Cert）：
                                    # 直接放在 DD_No/stockist_cert 文件夹下，只放文件名
                                    zip_path = f"{dd_no}/{stockist_cert}/{file_name}"
                                
                                zipf.write(file_path, zip_path)
                            except ValueError:
                                # 如果 relpath 失败（不同驱动器），使用文件名
                                if preserve_folder_structure:
                                    zip_path = f"{dd_no}/{stockist_cert}/{source_folder}/{file_name}"
                                else:
                                    # 其他文件夹直接放在 DD_No/stockist_cert 文件夹下
                                    zip_path = f"{dd_no}/{stockist_cert}/{file_name}"
                                zipf.write(file_path, zip_path)
            
            try:
                print(f"[下载] 成功创建 ZIP，包含 {len(all_files_set)} 个文件")
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            return temp_zip_path, len(all_files_set)
            
        except Exception as e:
            # 如果创建 ZIP 失败，清理临时文件
            if os.path.exists(temp_zip_path):
                try:
                    os.remove(temp_zip_path)
                except:
                    pass
            raise e
    
    def download_by_order_nos_grouped_by_date(self, order_nos: List[int]) -> Tuple[str, int]:
        """
        批量按多个 Order No 下载，按日期分组
        
        Args:
            order_nos: 订单号列表
            
        Returns:
            (zip_file_path, file_count) 元组，zip_file_path 是临时 ZIP 文件路径
            
        ZIP 结构：
        - 2024-01-15/
          - Job_No_1/
            - Stockist_No_1/
              - file1.pdf
            - Stockist_No_2/
              - file2.pdf
          - Job_No_2/
            - Stockist_No_1/
              - file3.pdf
        - 2024-01-16/
          - Job_No_1/
            - Stockist_No_1/
              - file4.pdf
        
        逻辑：
        1. 从每个 order_no 获取对应的 del_date 和 job_no
        2. 对日期去重（同一天的订单合并）
        3. 为每个日期收集文件，按 Job_No 分组，再按 stockist_cert 分组
        """
        if not order_nos:
            raise ValueError("Order No 列表不能为空")
        
        try:
            print(f"[下载] 批量按日期下载 {len(order_nos)} 个 Order")
        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
            pass
        
        # 1. 批量获取每个 Order_No 对应的日期，并去重（优化）
        try:
            print(f"[下载] 批量查询 {len(order_nos)} 个订单的日期...")
        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
            pass
        orders_info = self.get_orders_info_batch(order_nos)
        order_to_date = {}  # {order_no: date_str}
        date_to_orders = {}  # {date_str: [order_nos]}
        
        for order_no in order_nos:
            order_info = orders_info.get(order_no)
            if not order_info:
                continue
            
            del_date = order_info.get('del_date')
            if not del_date:
                continue
            
            # 格式化日期（确保格式一致）
            date_str = str(del_date).strip()
            # 如果日期包含时间部分，只取日期部分
            if ' ' in date_str:
                date_str = date_str.split(' ')[0]
            # 标准化日期格式为 YYYY-MM-DD
            try:
                from datetime import datetime
                # 尝试解析日期
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                date_str = date_obj.strftime('%Y-%m-%d')
            except:
                # 如果解析失败，尝试其他格式
                try:
                    date_obj = datetime.strptime(date_str, '%Y/%m/%d')
                    date_str = date_obj.strftime('%Y-%m-%d')
                except:
                    # 如果都失败，使用原始字符串
                    pass
            
            order_to_date[order_no] = date_str
            if date_str not in date_to_orders:
                date_to_orders[date_str] = []
            date_to_orders[date_str].append(order_no)
        
        if not date_to_orders:
            raise ValueError(f"所有 Order {order_nos} 都没有找到有效的日期")
        
        # 去重后的日期列表
        unique_dates = sorted(list(date_to_orders.keys()))  # 按日期排序
        try:
            print(f"[下载] 找到 {len(unique_dates)} 个唯一的日期")
        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
            pass
        
        # 2. 为每个日期收集文件
        # 结构：{date_str: {job_no: {stockist_cert: [file_paths]}}}
        files_by_date_job_and_cert = {}  # {date_str: {job_no: {stockist_cert: [file_paths]}}}
        all_files_set = set()  # 用于统计总文件数（跨所有日期去重）
        missing_entries = []  # 记录缺失项，用于写入 ZIP 内提示文件
        
        for date_str in unique_dates:
            # 获取该日期对应的所有 Order_No
            order_nos_for_date = date_to_orders[date_str]
            
            # 批量查询该日期下所有订单的信息（优化）
            orders_info_batch = self.get_orders_info_batch(order_nos_for_date)
            cert_dn_values_batch = self.get_all_cert_dn_values_batch(order_nos_for_date)
            rm_dn_maps_batch = self.get_rm_dn_to_stockist_cert_map_batch(order_nos_for_date)
            
            # 为该日期收集所有文件（去重）
            date_files_set = set()  # 该日期的所有文件（去重）
            all_stockist_certs_set = set()  # 收集所有 stockist_cert（去重）
            all_rm_dn_nos_set = set()  # 收集所有 rm_dn_no（去重）
            all_rm_dn_to_stockist_map = {}  # 合并所有订单的 rm_dn_no 到 stockist_cert 映射
            
            # 为每个 Order 收集文件
            for order_no in order_nos_for_date:
                try:
                    # 从批量查询结果中获取订单信息
                    order_info = orders_info_batch.get(order_no)
                    if not order_info:
                        continue
                    
                    # 从批量查询结果中获取 stockist_cert 和 rm_dn_no
                    cert_dn = cert_dn_values_batch.get(order_no)
                    if not cert_dn:
                        continue
                    stockist_certs, rm_dn_nos = cert_dn
                    
                    # 从批量查询结果中获取 rm_dn_no 到 stockist_cert 映射
                    order_rm_dn_map = rm_dn_maps_batch.get(order_no, {})
                    # 合并到总映射中（如果同一个 rm_dn_no 对应不同的 stockist_cert，保留第一个）
                    for rm_dn_no, stockist_cert in order_rm_dn_map.items():
                        if rm_dn_no not in all_rm_dn_to_stockist_map:
                            all_rm_dn_to_stockist_map[rm_dn_no] = stockist_cert
                    
                    # 收集所有 stockist_cert（去重）
                    for stockist_cert in stockist_certs:
                        if stockist_cert:
                            all_stockist_certs_set.add(stockist_cert)
                    
                    # 收集所有 rm_dn_no（去重）
                    for rm_dn_no in rm_dn_nos:
                        if rm_dn_no:
                            all_rm_dn_nos_set.add(rm_dn_no)
                    
                    # 合并所有关键词
                    all_keywords = stockist_certs + rm_dn_nos
                    all_keywords = [k for k in all_keywords if k]  # 移除空值
                    
                    if not all_keywords:
                        continue
                    
                    # 从 Stockist 文件夹下载所有相关 PDF
                    stockist_files = self.find_files_by_keywords(self.stockist_folder, all_keywords)
                    
                    # 判断类型并查找对应文件夹
                    jobsite_type = order_info['jobsite_type'] or ''
                    is_iat, is_private = self.check_jobsite_type(jobsite_type)
                    
                    additional_files = []
                    
                    if is_iat:
                        # IAT 类型：按每个 stockist_cert 单独判断，有 Formal 就用 Formal，没有就立即查 Prelim
                        certs_norm = [c.strip() for c in stockist_certs if c and str(c).strip()]
                        
                        for cert in certs_norm:
                            # 1. 先检查该 cert 是否有对应的 IAT Formal 目录
                            formal_folder = os.path.join(self.iat_formal_folder, cert)
                            cert_has_formal = False
                            
                            if os.path.exists(formal_folder) and os.path.isdir(formal_folder):
                                # 检查目录里是否有 PDF
                                cert_formal_files = []
                                for root, _dirs, files in os.walk(formal_folder):
                                    for fn in files:
                                        if fn.lower().endswith('.pdf'):
                                            fp = os.path.join(root, fn)
                                            if os.path.exists(fp):
                                                cert_formal_files.append(fp)
                                
                                if cert_formal_files:
                                    cert_has_formal = True
                                    additional_files.extend(cert_formal_files)
                                    try:
                                        print(f"[IAT下载] Order {order_no}: Cert {cert} 使用 IAT Formal 目录 {formal_folder}，共 {len(cert_formal_files)} 个文件")
                                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                                        pass
                            
                            # 2. 如果该 cert 没有 Formal，立即去 IAT Prelim 搜索
                            if not cert_has_formal:
                                # 为该 cert 构建关键词（cert + 对应的 rm_dn_no）
                                cert_keywords = [cert]
                                for rm_dn_no, mapped_cert in order_rm_dn_map.items():
                                    if mapped_cert == cert:
                                        cert_keywords.append(rm_dn_no)
                                
                                if cert_keywords:
                                    cert_prelim_files = self.find_files_by_keywords(
                                        self.iat_prelim_folder,
                                        cert_keywords,
                                        search_subfolders=True
                                    )
                                    
                                    if cert_prelim_files:
                                        # 验证这些文件确实属于这个 cert
                                        valid_prelim_for_cert = []
                                        for file_path in cert_prelim_files:
                                            file_name = os.path.basename(file_path)
                                            matched_cert = self.match_file_to_stockist_cert(
                                                file_name, file_path, [cert], rm_dn_nos, order_rm_dn_map
                                            )
                                            if matched_cert == cert:
                                                valid_prelim_for_cert.append(file_path)
                                        
                                        if valid_prelim_for_cert:
                                            additional_files.extend(valid_prelim_for_cert)
                                            try:
                                                print(f"[IAT下载] Order {order_no}: Cert {cert} 无 Formal，使用 {len(valid_prelim_for_cert)} 个 IAT Prelim 文件")
                                            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                                                pass
                    elif is_private:
                        # Private 类型
                        private_formal_files = self.find_files_by_keywords(self.private_formal_folder, all_keywords, search_subfolders=True)
                        if private_formal_files:
                            additional_files.extend(private_formal_files)
                        else:
                            private_prelim_files = self.find_files_by_keywords(self.private_prelim_folder, all_keywords, search_subfolders=True)
                            if private_prelim_files:
                                additional_files.extend(private_prelim_files)
                    
                    # 合并该 Order 的所有文件并添加到该日期的集合中（去重）
                    order_files = stockist_files + additional_files
                    date_files_set.update(order_files)
                    
                    
                except Exception as e:
                    try:
                        print(f"[下载] Order {order_no} 处理失败: {e}")
                    except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                        pass
                    import traceback
                    traceback.print_exc()
                    continue
            
            # 转换为列表（该日期的所有文件）
            all_files = list(date_files_set)
            all_stockist_certs = list(all_stockist_certs_set)
            all_rm_dn_nos = list(all_rm_dn_nos_set)
            
            # 添加到总文件集合（用于统计）
            all_files_set.update(date_files_set)
            
            if not all_files:
                try:
                    print(f"[下载] 日期 {date_str} 对应的所有 Order 都没有找到相关 PDF 文件")
                except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                    pass
                continue
            
            try:
                print(f"[下载] 日期 {date_str} 总共找到 {len(all_files)} 个唯一文件（已去重）")
                print(f"[下载] 日期 {date_str} 涉及的所有 stockist_cert: {all_stockist_certs}")
                print(f"[下载] 日期 {date_str} 涉及的所有 rm_dn_no: {all_rm_dn_nos}")
                print(f"[下载] 日期 {date_str} 的 rm_dn_no 到 stockist_cert 映射: {all_rm_dn_to_stockist_map}")
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            
            # 按照 Job_No 和 stockist_cert 组织文件
            # 首先需要记录每个文件对应的 order_no，然后根据 order_no 获取 Job_No
            # 结构：{order_no: [file_paths]}
            files_by_order = {}  # {order_no: [file_paths]}
            
            # 为每个 Order 收集文件
            for order_no in order_nos_for_date:
                files_by_order[order_no] = []
            
            # 将所有文件按照 order_no 分类（需要知道每个文件来自哪个 order）
            # 由于文件是通过关键词搜索找到的，我们需要反向匹配
            # 允许一个文件分配给多个符合条件的 order（同一天内共享文件场景）
            seen_files = set()  # 用于去重
            for file_path in all_files:
                if file_path in seen_files:
                    continue
                seen_files.add(file_path)
                
                file_name = os.path.basename(file_path)
                
                # 使用通用匹配方法找到匹配的 stockist_cert
                matched_stockist_cert = self.match_file_to_stockist_cert(
                    file_name, file_path, all_stockist_certs, all_rm_dn_nos, all_rm_dn_to_stockist_map
                )
                
                if matched_stockist_cert:
                    # 找到匹配的 stockist_cert，现在需要找到这个文件属于哪些 order
                    # 通过检查哪些 order 包含这个 stockist_cert 或相关的 rm_dn_no
                    for order_no in order_nos_for_date:
                        order_info = orders_info_batch.get(order_no)
                        if not order_info:
                            continue
                        
                        cert_dn = cert_dn_values_batch.get(order_no)
                        if not cert_dn:
                            continue
                        order_stockist_certs, order_rm_dn_nos = cert_dn
                        
                        cert_match = matched_stockist_cert in order_stockist_certs
                        dn_match = any(rm_dn_no in file_name for rm_dn_no in order_rm_dn_nos if rm_dn_no)
                        if cert_match or dn_match:
                            # 避免同一文件重复写入同一 order
                            if file_path not in files_by_order[order_no]:
                                files_by_order[order_no].append(file_path)
            
            # 按照 Job_No 和 stockist_cert 重新组织文件
            # 同时确保每个订单只包含对应类型的文件（IAT 订单只包含 IAT 文件，Private 订单只包含 Private 文件）
            files_by_job_and_cert = {}  # {job_no: {stockist_cert: [file_paths]}}
            
            for order_no, order_files in files_by_order.items():
                if not order_files:
                    continue
                
                order_info = orders_info_batch.get(order_no)
                if not order_info:
                    continue
                
                job_no = order_info.get('job_no') or 'Unknown'
                if not job_no or job_no == 'None':
                    job_no = 'Unknown'
                
                # 判断订单类型（IAT 或 Private）
                jobsite_type = order_info.get('jobsite_type') or ''
                is_iat, is_private = self.check_jobsite_type(jobsite_type)
                
                cert_dn = cert_dn_values_batch.get(order_no)
                if not cert_dn:
                    continue
                order_stockist_certs, _ = cert_dn
                
                # 为这个 Job_No 初始化结构
                if job_no not in files_by_job_and_cert:
                    files_by_job_and_cert[job_no] = {}
                
                # 将文件按 stockist_cert 分类，同时过滤掉不匹配类型的文件
                for file_path in order_files:
                    abs_file_path = os.path.abspath(file_path)
                    
                    # 根据订单类型，只保留对应类型的文件
                    if is_iat:
                        # IAT 订单：只保留 IAT Formal 和 IAT Prelim 文件，排除 Private 文件
                        if (abs_file_path.startswith(os.path.abspath(self.private_formal_folder)) or
                            abs_file_path.startswith(os.path.abspath(self.private_prelim_folder))):
                            continue  # 跳过 Private 文件
                    elif is_private:
                        # Private 订单：只保留 Private Formal 和 Private Prelim 文件，排除 IAT 文件
                        if (abs_file_path.startswith(os.path.abspath(self.iat_formal_folder)) or
                            abs_file_path.startswith(os.path.abspath(self.iat_prelim_folder))):
                            continue  # 跳过 IAT 文件
                    
                    file_name = os.path.basename(file_path)
                    matched_stockist_cert = self.match_file_to_stockist_cert(
                        file_name, file_path, order_stockist_certs, all_rm_dn_nos, all_rm_dn_to_stockist_map
                    )
                    
                    if matched_stockist_cert:
                        if matched_stockist_cert not in files_by_job_and_cert[job_no]:
                            files_by_job_and_cert[job_no][matched_stockist_cert] = []
                        # 同一 Job_No / Stockist_No 下去重，避免共享文件被重复写入
                        if file_path not in files_by_job_and_cert[job_no][matched_stockist_cert]:
                            files_by_job_and_cert[job_no][matched_stockist_cert].append(file_path)

            # 记录缺失项：该日期下，每个 order 的每个 stockist_cert 如果没有任何文件则记为缺失
            for order_no in order_nos_for_date:
                order_info = orders_info_batch.get(order_no)
                if not order_info:
                    continue

                cert_dn = cert_dn_values_batch.get(order_no)
                if not cert_dn:
                    continue

                order_job_no = order_info.get('job_no') or 'Unknown'
                if not order_job_no or order_job_no == 'None':
                    order_job_no = 'Unknown'

                order_stockist_certs, _ = cert_dn
                normalized_certs = [c.strip().upper() for c in order_stockist_certs if c and str(c).strip()]
                if not normalized_certs:
                    continue

                job_bucket = files_by_job_and_cert.get(order_job_no, {})
                for cert in normalized_certs:
                    cert_files = job_bucket.get(cert, [])
                    if not cert_files:
                        missing_entries.append({
                            'date': date_str,
                            'order_no': order_no,
                            'job_no': order_job_no,
                            'stockist_cert': cert
                        })
            
            # 保存该日期的文件组织结构
            files_by_date_job_and_cert[date_str] = files_by_job_and_cert
        
        if not files_by_date_job_and_cert:
            raise ValueError(f"所有日期 {unique_dates} 都没有找到相关 PDF 文件")
        
        # 统计各日期的文件数
        date_file_counts = {}
        for date_str, files_by_job in files_by_date_job_and_cert.items():
            total_count = 0
            for files_by_cert in files_by_job.values():
                total_count += sum(len(files) for files in files_by_cert.values())
            date_file_counts[date_str] = total_count
        
        try:
            try:
                print(f"[下载] 批量下载总共找到 {len(all_files_set)} 个唯一文件（已去重）")
                print(f"[下载] 各日期文件统计: {date_file_counts}")
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
        except (UnicodeEncodeError, UnicodeDecodeError, Exception):
            pass
        
        # 3. 创建 ZIP 文件
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_zip_path = temp_zip.name
        temp_zip.close()
        
        try:
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                # 防止重复 arcname 写入 ZIP（例如同一 Job/Stockist 下共享文件重复分配）
                written_zip_paths = set()
                # 为每个日期、Job_No 和 stockist_cert 组合创建文件夹并添加文件
                # ZIP 结构：日期/Job_No/Stockist_No/file.pdf
                for date_str, files_by_job in files_by_date_job_and_cert.items():
                    for job_no, files_by_stockist_cert in files_by_job.items():
                        for stockist_cert, files in files_by_stockist_cert.items():
                            if not files or not stockist_cert:
                                continue
                            
                            for file_path in files:
                                abs_file_path = os.path.abspath(file_path)
                                file_name = os.path.basename(file_path)
                                
                                # 判断文件来源（Stockist Cert、Private Formal、IAT Formal 等）
                                source_folder = None
                                base_folder_path = None
                                preserve_folder_structure = False  # 是否保留文件夹结构
                                
                                if abs_file_path.startswith(os.path.abspath(self.stockist_folder)):
                                    source_folder = "Stockist Cert"
                                    base_folder_path = self.stockist_folder
                                    preserve_folder_structure = False  # 只放 PDF 文件
                                elif abs_file_path.startswith(os.path.abspath(self.private_formal_folder)):
                                    source_folder = "Private Formal"
                                    base_folder_path = self.private_formal_folder
                                    preserve_folder_structure = False  # 只放 PDF 文件
                                elif abs_file_path.startswith(os.path.abspath(self.private_prelim_folder)):
                                    source_folder = "Private Prelim"
                                    base_folder_path = self.private_prelim_folder
                                    preserve_folder_structure = False  # 只放 PDF 文件
                                elif abs_file_path.startswith(os.path.abspath(self.iat_formal_folder)):
                                    source_folder = "IAT Formal"
                                    base_folder_path = self.iat_formal_folder
                                    preserve_folder_structure = True  # 保留文件夹结构
                                elif abs_file_path.startswith(os.path.abspath(self.iat_prelim_folder)):
                                    source_folder = "IAT Prelim"
                                    base_folder_path = self.iat_prelim_folder
                                    preserve_folder_structure = False  # 只放 PDF 文件
                                else:
                                    source_folder = "Other"
                                    base_folder_path = None
                                    preserve_folder_structure = False
                                
                                # 构建 ZIP 中的路径：日期/Job_No/stockist_cert/...
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
                                            
                                            zip_path = f"{date_str}/{job_no}/{stockist_cert}/{source_folder}/{rel_path}"
                                        else:
                                            zip_path = f"{date_str}/{job_no}/{stockist_cert}/{source_folder}/{file_name}"
                                    else:
                                        # 其他文件夹（IAT Prelim、Private Formal、Private Prelim、Stockist Cert）：
                                        # 直接放在 日期/Job_No/stockist_cert 文件夹下，只放文件名
                                        zip_path = f"{date_str}/{job_no}/{stockist_cert}/{file_name}"
                                    
                                    if zip_path in written_zip_paths:
                                        continue
                                    zipf.write(file_path, zip_path)
                                    written_zip_paths.add(zip_path)

                # 写入缺失提示文件，便于用户在下载包中直接看到缺失清单
                if missing_entries:
                    unique_missing = []
                    seen_missing = set()
                    for item in missing_entries:
                        key = (item['date'], str(item['order_no']), str(item['job_no']), item['stockist_cert'])
                        if key in seen_missing:
                            continue
                        seen_missing.add(key)
                        unique_missing.append(item)

                    report_lines = [
                        "Stockist & Test Report Missing Items",
                        "Generated by grouped-by-date download",
                        ""
                    ]
                    for item in unique_missing:
                        report_lines.append(
                            f"Date={item['date']} | Order={item['order_no']} | Job No={item['job_no']} | Stockist No={item['stockist_cert']} | Missing=No matched PDF"
                        )

                    zipf.writestr("MISSING_FILES_REPORT.txt", "\n".join(report_lines))
                                except ValueError:
                                    # 如果 relpath 失败（不同驱动器），使用文件名
                                    if preserve_folder_structure:
                                        zip_path = f"{date_str}/{job_no}/{stockist_cert}/{source_folder}/{file_name}"
                                    else:
                                        # 其他文件夹直接放在 日期/Job_No/stockist_cert 文件夹下
                                        zip_path = f"{date_str}/{job_no}/{stockist_cert}/{file_name}"
                                    if zip_path in written_zip_paths:
                                        continue
                                    zipf.write(file_path, zip_path)
                                    written_zip_paths.add(zip_path)
            
            try:
                print(f"[下载] 成功创建 ZIP，包含 {len(all_files_set)} 个文件")
            except (UnicodeEncodeError, UnicodeDecodeError, Exception):
                pass
            return temp_zip_path, len(all_files_set)
            
        except Exception as e:
            # 如果创建 ZIP 失败，清理临时文件
            if os.path.exists(temp_zip_path):
                try:
                    os.remove(temp_zip_path)
                except:
                    pass
            raise e

