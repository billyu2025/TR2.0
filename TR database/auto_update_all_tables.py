#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TR_Report 和 TR_Report_Deduplication 自动更新脚本
功能：自动更新 TR_Report 和 TR_Report_Deduplication 表
作者：TR Report System
日期：2025-11-20
"""

import sys
import os
import io

# 设置UTF-8编码环境变量（解决Windows下中文和emoji显示问题）
if sys.platform == 'win32':
    # 设置环境变量
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # 重新配置标准输出和错误输出为UTF-8
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 添加backend目录到Python路径（用于导入文件索引相关模块）
_backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'TR UI', 'backend')
if os.path.exists(_backend_path):
    sys.path.insert(0, _backend_path)

import pandas as pd
import numpy as np
import sqlite3
import logging
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy import create_engine, text
import pyodbc
import warnings
warnings.filterwarnings('ignore')

# ==================== 配置区域 ====================
# 数据库配置
DB_CONFIG = {
    'server': '192.168.80.242',
    'database': 'TVSC',
    'username': 'reportuser',
    'password': 'HKSHA123',
    'driver': 'SQL Server'
}

# SQLite数据库配置
SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), 'data_3years.db')

# 邮件配置（可选，如果不需要邮件通知可以留空）
EMAIL_CONFIG = {
    'smtp_server': 'corpmail1.netvigator.com',
    'smtp_port': 25,
    'username': 'tr@hkshalliance.com',  # 留空表示不发送邮件
    'password': '',
    'to_email': 'henry.yu@hkshalliance.com,yuyuhang1991@163.com'
}
# ==================== 配置结束 ====================

# 配置日志
def setup_logging():
    """设置日志配置"""
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_filename = os.path.join(log_dir, f'auto_update_all_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    # 创建自定义StreamHandler，确保使用UTF-8编码
    class UTF8StreamHandler(logging.StreamHandler):
        def __init__(self, stream=None):
            super().__init__(stream)
            
        def emit(self, record):
            try:
                msg = self.format(record) + self.terminator
                # 使用errors='replace'避免编码错误，即使控制台无法显示emoji也不会报错
                try:
                    if hasattr(self.stream, 'buffer'):
                        # 对于有buffer的流（如重定向后的stdout）
                        self.stream.buffer.write(msg.encode('utf-8', errors='replace'))
                        self.stream.buffer.flush()
                    else:
                        # 对于普通流
                        self.stream.write(msg)
                        self.stream.flush()
                except (UnicodeEncodeError, AttributeError):
                    # 如果还是出错，使用ASCII安全版本
                    safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
                    self.stream.write(safe_msg)
                    self.stream.flush()
            except Exception:
                # 完全静默处理错误，避免无限循环
                pass
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            UTF8StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

class AutoUpdater:
    """自动更新器 - 只更新 TR_Report 和 TR_Report_Deduplication 表"""
    
    def __init__(self):
        self.logger = setup_logging()
        self.engine = None
        self.sqlite_conn = None
        self.update_results = {}  # 记录每个步骤的执行结果
        
    def create_database_connection(self):
        """创建源数据库连接"""
        try:
            connection_string = f"mssql+pyodbc://{DB_CONFIG['username']}:{DB_CONFIG['password']}@{DB_CONFIG['server']}/{DB_CONFIG['database']}?driver={DB_CONFIG['driver']}"
            self.engine = create_engine(connection_string, echo=False)
            
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            self.logger.info("✅ 源数据库连接成功")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 源数据库连接失败: {e}")
            return False
    
    def create_sqlite_connection(self):
        """创建SQLite数据库连接"""
        try:
            # 添加超时设置（30秒）
            self.sqlite_conn = sqlite3.connect(SQLITE_DB_PATH, timeout=30.0)
            # 启用 WAL 模式以提高并发性能，允许多个读取器和写入器同时访问
            self.sqlite_conn.execute("PRAGMA journal_mode=WAL")
            # 设置同步模式为 NORMAL（在 WAL 模式下更安全且性能更好）
            self.sqlite_conn.execute("PRAGMA synchronous=NORMAL")
            # 设置 busy_timeout（毫秒），当数据库被锁定时等待最多30秒
            self.sqlite_conn.execute("PRAGMA busy_timeout=30000")
            self.logger.info("✅ SQLite数据库连接成功（WAL模式）")
            return True
        except Exception as e:
            self.logger.error(f"❌ SQLite数据库连接失败: {e}")
            return False
    
    def execute_query(self, query, params=None):
        """执行SQL查询"""
        try:
            with self.engine.connect() as conn:
                result = pd.read_sql(query, conn, params=params)
            return result
        except Exception as e:
            self.logger.error(f"❌ 查询执行失败: {e}")
            return None
    
    # ========== 步骤1: 更新Orders表 ==========
    def update_orders(self):
        """更新订单数据（3年）"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("步骤1: 更新Orders表")
            self.logger.info("=" * 60)
            
            today = datetime.now()
            start_date = today - timedelta(days=1095)  # 3年 = 1095天
            
            order_query = """
            SELECT 
                pp.ID_PEDIDO_PRODUCCION AS Order_No,
                c.NOMBRE AS Client,
                o.NOMBRE AS Jobsite,
                o.ID_TIPO_FORJADO AS Jobsite_Type,
                pp.ID_OBRA AS Job_No,
                pp.REFERENCIA_2 AS PO_No,
                pp.FECHA_ENTREGA_PREVISTA AS Del_Date,
                pp.REFERENCIA_1 AS Ref_No,
                pp.DESCRIPCION AS Order_Description,
                ppl.NOM_ELEMENTO AS Element,
                ppl.NOM_POSICION AS Mark,
                ppl.CAL_NOMBRE_FA AS Dia,
                ppl.FIGURAS_PAQUETE_FA AS Qty,
                ppl.LONGITUD_FA AS Length,
                ppl.NOM_MODELO AS Shape,
                ppl.PESO_PAQUETE_FB AS Wt,
                ppl.CAL_TIPO_ACERO_FB AS Grade,
                GETDATE() AS Update_Time
            FROM PEDIDOS_PRODUCCION pp
            LEFT JOIN PEDIDOS_PRODUCCION_LIN ppl ON pp.ID_PEDIDO_PRODUCCION = ppl.ID_PEDIDO_PRODUCCION 
            LEFT JOIN CLIENTES c ON c.ID_CLIENTE = pp.ID_CLIENTE 
            LEFT JOIN OBRAS o ON o.ID_OBRA = pp.ID_OBRA 
            WHERE pp.FECHA_ENTREGA_PREVISTA >= ? AND pp.FECHA_ENTREGA_PREVISTA <= ?
            ORDER BY pp.FECHA_ENTREGA_PREVISTA DESC, pp.ID_PEDIDO_PRODUCCION, ppl.NOM_ELEMENTO, ppl.NOM_POSICION
            """
            
            order_data = self.execute_query(order_query, params=(start_date, today))
            
            if order_data is not None and len(order_data) > 0:
                order_data.to_sql('orders', self.sqlite_conn, if_exists='replace', index=False)
                self.sqlite_conn.commit()  # 显式提交确保数据被写入
                self.logger.info(f"✅ Orders表更新成功: {len(order_data)} 行")
                self.update_results['Orders'] = {'status': 'success', 'count': len(order_data)}
                return True
            else:
                self.logger.warning("⚠️ 订单数据为空")
                self.update_results['Orders'] = {'status': 'warning', 'count': 0}
                return False
                
        except Exception as e:
            self.logger.error(f"❌ 更新Orders表失败: {e}")
            self.update_results['Orders'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== 步骤2: 更新Materials表 ==========
    def update_materials(self):
        """更新原材料数据（3年）"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("步骤2: 更新Materials表")
            self.logger.info("=" * 60)
            
            today = datetime.now()
            start_date = today - timedelta(days=1095)  # 3年 = 1095天
            
            material_query = """
            SELECT 
                ael.DESCRIPCION AS Product,
                pa.INFO_1 AS Pattern,
                ael.COLADA_FABRICANTE_2 AS Mill_Cert,
                ael.CALIDAD_NUMERO_2 AS Test_Cert2,
                ael.CERTIFICADO_NUMERO_2 AS Test_Cert1,
                ae.REFERENCIA_1 AS Stockist_Cert,
                ae.REFERENCIA_2 AS PO_No,
                pa.ID_PRODUCTO_ALMACEN AS Tag_No,
                ae.NUMERO_ALBARAN AS DN_No,
                ae.FECHA_ALBARAN AS Material_Date,
                ae.ID_ALBARAN_ENTRADA AS Albaran_ID,
                GETDATE() AS Update_Time
            FROM PRODUCTOS_ALMACEN pa
            LEFT JOIN ALBARANES_ENTRADA_LIN ael ON ael.ID_ALBARAN_ENTRADA_LIN = pa.ID_ALBARAN_ENTRADA_LIN 
            LEFT JOIN ALBARANES_ENTRADA ae ON ae.ID_ALBARAN_ENTRADA = ael.ID_ALBARAN_ENTRADA
            WHERE ae.FECHA_ALBARAN >= ? AND ae.FECHA_ALBARAN <= ? AND ae.FECHA_ALBARAN IS NOT NULL
            ORDER BY ae.FECHA_ALBARAN DESC, pa.ID_PRODUCTO_ALMACEN
            """
            
            material_data = self.execute_query(material_query, params=(start_date, today))
            
            if material_data is not None and len(material_data) > 0:
                material_data.to_sql('materials', self.sqlite_conn, if_exists='replace', index=False)
                self.sqlite_conn.commit()  # 显式提交确保数据被写入
                self.logger.info(f"✅ Materials表更新成功: {len(material_data)} 行")
                self.update_results['Materials'] = {'status': 'success', 'count': len(material_data)}
                return True
            else:
                self.logger.warning("⚠️ 原材料数据为空")
                self.update_results['Materials'] = {'status': 'warning', 'count': 0}
                return False
                
        except Exception as e:
            self.logger.error(f"❌ 更新Materials表失败: {e}")
            self.update_results['Materials'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== 步骤3: 生成Orders_com表 ==========
    def compress_orders(self):
        """压缩订单数据，生成Orders_com表"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("步骤3: 生成Orders_com表")
            self.logger.info("=" * 60)
            
            query = """
            SELECT 
                Order_No, Client, Jobsite, Jobsite_Type, Job_No, PO_No,
                Del_Date, Ref_No, Order_Description, Dia, Grade, Length, Wt
            FROM orders
            """
            
            orders_df = pd.read_sql(query, self.sqlite_conn)
            self.logger.info(f"原始订单数据: {len(orders_df)} 行")
            
            orders_df['Wt'] = pd.to_numeric(orders_df['Wt'], errors='coerce').fillna(0)
            
            compressed_orders = orders_df.groupby(['Order_No', 'Dia']).agg({
                'Client': 'first',
                'Jobsite': 'first',
                'Jobsite_Type': 'first',
                'Job_No': 'first',
                'PO_No': 'first',
                'Del_Date': 'first',
                'Ref_No': 'first',
                'Order_Description': 'first',
                'Grade': 'first',
                'Length': 'first',
                'Wt': 'sum'
            }).reset_index()
            
            # 文本清理
            def clean_text_field(series, max_length=200):
                return (
                    series.astype(str)
                    .str.replace('\n', ' ', regex=False)
                    .str.replace('\r', ' ', regex=False)
                    .str.replace('\t', ' ', regex=False)
                    .str.replace(r'\s+', ' ', regex=True)
                    .str.strip()
                    .str[:max_length]
                    .str.replace(r'[^\x20-\x7E\u4e00-\u9fff]', '', regex=True)
                    .str.strip()
                )
            
            compressed_orders['Client'] = clean_text_field(compressed_orders['Client'], 100)
            compressed_orders['Jobsite'] = clean_text_field(compressed_orders['Jobsite'], 150)
            compressed_orders['Ref_No'] = clean_text_field(compressed_orders['Ref_No'], 50)
            compressed_orders['Order_Description'] = clean_text_field(compressed_orders['Order_Description'], 200)
            
            # 重量单位转换
            compressed_orders['Wt'] = compressed_orders['Wt'] / 1000
            
            final_orders = compressed_orders[[
                'Order_No', 'Client', 'Jobsite', 'Jobsite_Type', 'Job_No', 'PO_No',
                'Del_Date', 'Ref_No', 'Order_Description', 'Dia', 'Grade', 'Length', 'Wt'
            ]].copy()
            
            final_orders.to_sql('orders_com', self.sqlite_conn, if_exists='replace', index=False)
            
            self.logger.info(f"✅ Orders_com表生成成功: {len(final_orders)} 行")
            self.logger.info(f"压缩率: {(1 - len(final_orders) / len(orders_df)) * 100:.2f}%")
            self.update_results['Orders_com'] = {'status': 'success', 'count': len(final_orders)}
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 生成Orders_com表失败: {e}")
            self.update_results['Orders_com'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== 步骤4: 生成Materials_com表 ==========
    def compress_materials(self):
        """压缩原材料数据，生成Materials_com表"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("步骤4: 生成Materials_com表")
            self.logger.info("=" * 60)
            
            query = """
            SELECT 
                Product, Pattern, Mill_Cert, Test_Cert2, Test_Cert1,
                Stockist_Cert, PO_No, Tag_No, DN_No
            FROM materials
            """
            
            materials_df = pd.read_sql(query, self.sqlite_conn)
            self.logger.info(f"原始原材料数据: {len(materials_df)} 行")
            
            # 提取直径信息
            def extract_dia_from_product(product):
                try:
                    if pd.isna(product) or product == '':
                        return ''
                    import re
                    match = re.search(r'(\d+)mm', str(product))
                    return f"Y{match.group(1)}" if match else ''
                except:
                    return ''
            
            # 提取长度信息
            def extract_len_from_product(product):
                try:
                    if pd.isna(product) or product == '':
                        return ''
                    product_str = str(product)
                    if 'Coil' in product_str or 'coil' in product_str:
                        return 'Coil'
                    import re
                    pattern = r'(\d+(?:\.\d+)?m)(?!m)'
                    match = re.search(pattern, product_str)
                    return match.group(1) if match else ''
                except:
                    return ''
            
            materials_df['Dia'] = materials_df['Product'].apply(extract_dia_from_product)
            materials_df['Len'] = materials_df['Product'].apply(extract_len_from_product)
            
            # 去重
            compressed_materials = materials_df.drop_duplicates(subset=[
                'Product', 'Pattern', 'Mill_Cert', 'Test_Cert2', 'Test_Cert1',
                'Stockist_Cert', 'PO_No', 'Tag_No', 'DN_No'
            ])
            
            column_order = ['Dia', 'Len', 'Product', 'Pattern', 'Mill_Cert', 'Test_Cert2', 'Test_Cert1',
                          'Stockist_Cert', 'PO_No', 'Tag_No', 'DN_No']
            compressed_materials = compressed_materials[column_order]
            
            compressed_materials.to_sql('materials_com', self.sqlite_conn, if_exists='replace', index=False)
            
            self.logger.info(f"✅ Materials_com表生成成功: {len(compressed_materials)} 行")
            self.logger.info(f"压缩率: {(1 - len(compressed_materials) / len(materials_df)) * 100:.2f}%")
            self.update_results['Materials_com'] = {'status': 'success', 'count': len(compressed_materials)}
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 生成Materials_com表失败: {e}")
            self.update_results['Materials_com'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== 步骤5: 生成Orders_Deduplication表 ==========
    def create_orders_deduplication(self):
        """生成Orders_Deduplication表"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("步骤5: 生成Orders_Deduplication表")
            self.logger.info("=" * 60)
            
            orders_df = pd.read_sql("SELECT * FROM orders_com", self.sqlite_conn)
            self.logger.info(f"读取orders_com数据: {len(orders_df)} 行")
            
            grouped = orders_df.groupby('Order_No').agg({
                'Client': 'first',
                'Jobsite': 'first',
                'Jobsite_Type': 'first',
                'Job_No': 'first',
                'PO_No': 'first',
                'Del_Date': 'first',
                'Ref_No': 'first',
                'Order_Description': 'first',
                'Grade': 'first',
                'Wt': 'sum'
            }).reset_index()
            
            # 映射Jobsite_Type
            def map_jobsite_type(value):
                try:
                    if value is None:
                        return 'Unknown'
                    str_val = str(value).strip()
                    if str_val == '':
                        return 'Unknown'
                    code = int(float(str_val))
                    if code in {1, 4, 5, 6, 8, 11}:
                        return 'IAT'
                    if code in {2, 3, 7}:
                        return 'PRIVATE'
                    if code in {10, 12}:
                        return 'Inner'
                    return 'Others'
                except:
                    return 'Unknown'
            
            grouped['Jobsite_Type'] = grouped['Jobsite_Type'].apply(map_jobsite_type)
            
            grouped.to_sql('Orders_Deduplication', self.sqlite_conn, if_exists='replace', index=False)
            
            self.logger.info(f"✅ Orders_Deduplication表生成成功: {len(grouped)} 行")
            self.update_results['Orders_Deduplication'] = {'status': 'success', 'count': len(grouped)}
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 生成Orders_Deduplication表失败: {e}")
            self.update_results['Orders_Deduplication'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== 步骤6: 生成Orders_gen_pdf表 ==========
    def create_orders_gen_pdf(self):
        """生成Orders_gen_pdf表"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("步骤6: 生成Orders_gen_pdf表")
            self.logger.info("=" * 60)
            
            # 检查TR_Fill_in表是否存在
            cursor = self.sqlite_conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='TR_Fill_in'")
            if cursor.fetchone() is None:
                self.logger.warning("⚠️ TR_Fill_in表不存在，跳过Orders_gen_pdf生成")
                self.update_results['Orders_gen_pdf'] = {'status': 'skipped', 'reason': 'TR_Fill_in表不存在'}
                return False
            
            # 检查TR_Fill_in表是否有数据
            cursor.execute("SELECT COUNT(*) FROM TR_Fill_in")
            tr_fill_in_count = cursor.fetchone()[0]
            if tr_fill_in_count == 0:
                self.logger.warning("⚠️ TR_Fill_in表为空，跳过Orders_gen_pdf生成")
                self.update_results['Orders_gen_pdf'] = {'status': 'skipped', 'reason': 'TR_Fill_in表为空'}
                return False
            
            self.logger.info(f"TR_Fill_in表有 {tr_fill_in_count} 条记录")
            
            # 删除已存在的表
            cursor.execute("DROP TABLE IF EXISTS Orders_gen_pdf")
            
            # 创建新表
            create_table_sql = """
            CREATE TABLE Orders_gen_pdf AS
            SELECT 
                tf.Dia,
                oc.Wt as 'Wt(ton)',
                tf.Product,
                oc.Grade,
                tf.Pattern,
                tf.Mill_Cert,
                tf.Test_Cert2,
                tf.Test_Cert1,
                'VSC STEEL COMPANY LTD' as Supplier,
                tf.Stockist_Cert,
                tf.PO_No as 'PO_No(1)',
                tf.Tag_No,
                tf.DN_No,
                oc.Client,
                oc.Jobsite,
                oc.Jobsite_Type,
                oc.Job_No,
                oc.PO_No as 'PO_No(2)',
                oc.Order_No,
                oc.Del_Date,
                oc.Ref_No,
                oc.Order_Description
            FROM TR_Fill_in tf
            INNER JOIN orders_com oc ON tf.Dia = oc.Dia
            """
            
            cursor.execute(create_table_sql)
            self.sqlite_conn.commit()
            
            cursor.execute("SELECT COUNT(*) FROM Orders_gen_pdf")
            count = cursor.fetchone()[0]
            
            self.logger.info(f"✅ Orders_gen_pdf表生成成功: {count} 行")
            self.update_results['Orders_gen_pdf'] = {'status': 'success', 'count': count}
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 生成Orders_gen_pdf表失败: {e}")
            self.update_results['Orders_gen_pdf'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== 步骤7: 确保PDF_Status表存在 ==========
    def ensure_pdf_status_table(self):
        """确保PDF_Status表存在（如果不存在则创建）"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("步骤7: 检查PDF_Status表")
            self.logger.info("=" * 60)
            
            cursor = self.sqlite_conn.cursor()
            
            # 检查PDF_Status表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='PDF_Status'")
            if cursor.fetchone() is not None:
                # 表已存在，检查记录数
                cursor.execute("SELECT COUNT(*) FROM PDF_Status")
                count = cursor.fetchone()[0]
                self.logger.info(f"✅ PDF_Status表已存在，当前记录数: {count}")
                self.update_results['PDF_Status'] = {'status': 'exists', 'count': count}
                return True
            
            # 表不存在，创建它
            self.logger.info("📋 PDF_Status表不存在，正在创建...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS PDF_Status (
                    Order_No INTEGER PRIMARY KEY,
                    pdf_status TEXT DEFAULT 'pending',
                    pdf_path TEXT,
                    generated_at TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    generated_by TEXT
                )
            """)
            
            self.sqlite_conn.commit()
            
            # 验证表创建成功
            cursor.execute("SELECT COUNT(*) FROM PDF_Status")
            count = cursor.fetchone()[0]
            
            self.logger.info(f"✅ PDF_Status表创建成功，当前记录数: {count}")
            self.update_results['PDF_Status'] = {'status': 'created', 'count': count}
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 检查/创建PDF_Status表失败: {e}")
            self.update_results['PDF_Status'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== 步骤8: 确保TR_Fill_in表存在 ==========
    def ensure_tr_fill_in_table(self):
        """确保TR_Fill_in表存在（如果不存在则创建）"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("步骤8: 检查TR_Fill_in表")
            self.logger.info("=" * 60)
            
            cursor = self.sqlite_conn.cursor()
            
            # 检查TR_Fill_in表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='TR_Fill_in'")
            if cursor.fetchone() is not None:
                # 表已存在，检查记录数
                cursor.execute("SELECT COUNT(*) FROM TR_Fill_in")
                count = cursor.fetchone()[0]
                self.logger.info(f"✅ TR_Fill_in表已存在，当前记录数: {count}")
                self.update_results['TR_Fill_in'] = {'status': 'exists', 'count': count}
                return True
            
            # 表不存在，创建它
            self.logger.info("📋 TR_Fill_in表不存在，正在创建...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS TR_Fill_in (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Dia TEXT,
                    Len TEXT,
                    Product TEXT,
                    Pattern TEXT,
                    Tag_No TEXT UNIQUE,
                    Mill_Cert TEXT,
                    Test_Cert1 TEXT,
                    Test_Cert2 TEXT,
                    Stockist_Cert TEXT,
                    PO_No TEXT,
                    DN_No TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.sqlite_conn.commit()
            
            # 验证表创建成功
            cursor.execute("SELECT COUNT(*) FROM TR_Fill_in")
            count = cursor.fetchone()[0]
            
            self.logger.info(f"✅ TR_Fill_in表创建成功，当前记录数: {count}")
            self.update_results['TR_Fill_in'] = {'status': 'created', 'count': count}
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 检查/创建TR_Fill_in表失败: {e}")
            self.update_results['TR_Fill_in'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== 创建 TR_Report 表 ==========
    def create_tr_report_table(self):
        """创建 TR_Report 表 - 从 SQL Server 查询近3年的数据，直接在 SQLite 中创建"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("步骤1: 创建 TR_Report 表")
            self.logger.info("=" * 60)
            
            with self.engine.connect() as conn:
                # 先测试查询，获取数据量
                self.logger.info("查询近3年的数据...")
                count_sql = text("""
                    SELECT COUNT(*) as record_count
                    FROM tr_line_size tls
                    LEFT JOIN tr_line_detail tld
                        ON tls.bbs_no = tld.bbs_no
                        AND tls.diameter = tld.diameter
                    JOIN pedidos_produccion pp
                        ON pp.ID_PEDIDO_PRODUCCION = tls.bbs_no
                    JOIN obras js
                        ON js.ID_OBRA = tls.jobsite_no
                    WHERE pp.fecha_entrega_prevista >= DATEADD(MONTH, -36, GETDATE())
                """)
                result = conn.execute(count_sql)
                count = result.fetchone()[0]
                self.logger.info(f"找到 {count:,} 条近3年的记录")
                
                if count == 0:
                    self.logger.warning("⚠️ 近3年没有数据，表将为空")
                
                # 查询数据
                self.logger.info("从 SQL Server 获取数据...")
                query_sql = text("""
                    SELECT
                        pp.id_obra AS Job_No, 
                        js.nombre AS jobsite, 
                        pp.id_pedido_produccion AS order_no, 
                        pp.descripcion AS order_describution,
                        js.arquitecto AS client,
                        pp.fecha_entrega_prevista AS del_date,
                        pp.referencia_1 AS ref_no,
                        pp.referencia_2 AS bbs_po_no,
                        tbh.jobsite_type,
                        tls.diameter, 
                        tls.wt_ton, 
                        tld.product, 
                        tld.grade, 
                        tld.pattern, 
                        tld.mill_cert, 
                        tld.test_cert1, 
                        tld.test_cert2, 
                        tld.supplier, 
                        tld.stockist_cert, 
                        tld.po_no,
                        tld.rm_dn_no
                    FROM tr_line_size tls
                    JOIN tr_bbs_header tbh
                        ON tbh.bbs_no = tls.bbs_no
                    LEFT JOIN tr_line_detail tld
                        ON tls.bbs_no = tld.bbs_no
                        AND tls.diameter = tld.diameter
                    JOIN pedidos_produccion pp
                        ON pp.ID_PEDIDO_PRODUCCION = tls.bbs_no
                    JOIN obras js
                        ON js.ID_OBRA = tls.jobsite_no
                    WHERE pp.fecha_entrega_prevista >= DATEADD(MONTH, -36, GETDATE())
                    ORDER BY pp.fecha_entrega_prevista DESC, pp.id_obra, pp.ID_PEDIDO_PRODUCCION, tls.diameter, tld.pattern
                """)
                
                df = pd.read_sql(query_sql, conn)
                self.logger.info(f"获取了 {len(df):,} 条记录")
                
                if len(df) == 0:
                    self.logger.warning("⚠️ 没有获取到数据")
                    self.update_results['TR_Report'] = {'status': 'warning', 'count': 0}
                    return False
                
                # 连接到 SQLite
                if not self.sqlite_conn:
                    self.create_sqlite_connection()
                
                # 如果表已存在，删除它
                cursor = self.sqlite_conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS TR_Report")
                self.sqlite_conn.commit()
                self.logger.info("已删除旧的 TR_Report 表（如果存在）")
                
                # 将数据写入 SQLite
                self.logger.info("写入数据到 SQLite...")
                df.to_sql('TR_Report', self.sqlite_conn, if_exists='replace', index=False)
                self.sqlite_conn.commit()
                
                # 验证
                verify_count = pd.read_sql("SELECT COUNT(*) as cnt FROM TR_Report", self.sqlite_conn).iloc[0]['cnt']
                self.logger.info(f"✅ TR_Report 表创建成功: {verify_count:,} 条记录")
                
                # 统计信息
                stats = pd.read_sql("""
                    SELECT 
                        MIN(del_date) as earliest_date,
                        MAX(del_date) as latest_date,
                        COUNT(DISTINCT order_no) as unique_orders,
                        COUNT(DISTINCT Job_No) as unique_jobsites
                    FROM TR_Report
                """, self.sqlite_conn).iloc[0]
                
                self.logger.info("=" * 60)
                self.logger.info("表统计信息:")
                self.logger.info(f"  最早日期: {stats['earliest_date']}")
                self.logger.info(f"  最晚日期: {stats['latest_date']}")
                self.logger.info(f"  唯一订单数: {stats['unique_orders']:,}")
                self.logger.info(f"  唯一工地数: {stats['unique_jobsites']:,}")
                self.logger.info("=" * 60)
                
                self.update_results['TR_Report'] = {'status': 'success', 'count': verify_count}
                return True
                
        except Exception as e:
            self.logger.error(f"❌ 创建 TR_Report 表失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.update_results['TR_Report'] = {'status': 'failed', 'error': str(e)}
            return False
    # ========== 创建 TR_Report_Deduplication 表 ==========
    def create_tr_report_deduplication(self):
        """创建 TR_Report_Deduplication 表 - 从 TR_Report 表按 Order_No 去重生成"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("步骤2: 创建 TR_Report_Deduplication 表")
            self.logger.info("=" * 60)
            
            if not self.sqlite_conn:
                self.create_sqlite_connection()
            
            # 检查 TR_Report 表是否存在
            cursor = self.sqlite_conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='TR_Report'
            """)
            if not cursor.fetchone():
                self.logger.error("❌ TR_Report 表不存在，请先创建 TR_Report 表")
                self.update_results['TR_Report_Deduplication'] = {'status': 'failed', 'error': 'TR_Report table does not exist'}
                return False
            
            # 读取 TR_Report 表数据
            self.logger.info("从 TR_Report 表读取数据...")
            tr_report_df = pd.read_sql("SELECT * FROM TR_Report", self.sqlite_conn)
            self.logger.info(f"从 TR_Report 读取了 {len(tr_report_df):,} 条记录")
            
            if tr_report_df.empty:
                self.logger.warning("⚠️ TR_Report 表为空，TR_Report_Deduplication 也将为空")
            
            # 按 order_no 分组去重
            self.logger.info("按 order_no 分组并聚合...")
            grouped = tr_report_df.groupby('order_no').agg({
                'Job_No': 'first',
                'jobsite': 'first',
                'order_describution': 'first',
                'client': 'first',
                'del_date': 'first',
                'ref_no': 'first',
                'bbs_po_no': 'first',
                'jobsite_type': 'first',
                'wt_ton': 'sum',  # 累加重量
                'grade': 'first',
                'rm_dn_no': 'first',
            }).reset_index()
            
            # 重命名列以匹配 TR_Report_Deduplication 的命名风格
            grouped = grouped.rename(columns={
                'order_no': 'Order_No',
                'jobsite': 'Jobsite',
                'order_describution': 'Order_Description',
                'client': 'Client',
                'del_date': 'Del_Date',
                'ref_no': 'Ref_No',
                'bbs_po_no': 'PO_No',
                'jobsite_type': 'Jobsite_Type',
                'wt_ton': 'Wt',
                'grade': 'Grade',
                'rm_dn_no': 'rm_dn_no'
            })
            # Job_No 已经是正确名称，不需要重命名
            
            self.logger.info(f"聚合为 {len(grouped):,} 个唯一订单")
            
            # 按 Del_Date 降序排列
            self.logger.info("按 Del_Date 降序排列...")
            grouped = grouped.sort_values('Del_Date', ascending=False, na_position='last')
            
            # 如果表已存在，先删除
            cursor.execute("DROP TABLE IF EXISTS TR_Report_Deduplication")
            self.sqlite_conn.commit()
            self.logger.info("已删除旧的 TR_Report_Deduplication 表（如果存在）")
            
            # 写入 SQLite 数据库
            self.logger.info("写入 TR_Report_Deduplication 表...")
            grouped.to_sql('TR_Report_Deduplication', self.sqlite_conn, if_exists='replace', index=False)
            self.sqlite_conn.commit()
            
            # 验证数据
            verify_count = pd.read_sql("SELECT COUNT(*) as cnt FROM TR_Report_Deduplication", self.sqlite_conn).iloc[0]['cnt']
            self.logger.info(f"✅ TR_Report_Deduplication 表创建成功: {verify_count:,} 条记录")
            
            # 显示统计信息
            stats = pd.read_sql("""
                SELECT 
                    MIN(Del_Date) as earliest_date,
                    MAX(Del_Date) as latest_date,
                    COUNT(DISTINCT Order_No) as unique_orders,
                    COUNT(DISTINCT Job_No) as unique_jobsites,
                    SUM(Wt) as total_weight,
                    COUNT(DISTINCT Jobsite_Type) as unique_jobsite_types
                FROM TR_Report_Deduplication
            """, self.sqlite_conn).iloc[0]
            
            self.logger.info("=" * 60)
            self.logger.info("表统计信息:")
            self.logger.info(f"  最早日期: {stats['earliest_date']}")
            self.logger.info(f"  最晚日期: {stats['latest_date']}")
            self.logger.info(f"  唯一订单数: {stats['unique_orders']:,}")
            self.logger.info(f"  唯一工地数: {stats['unique_jobsites']:,}")
            self.logger.info(f"  总重量: {stats['total_weight']:.2f} 吨")
            self.logger.info(f"  工地类型数: {stats['unique_jobsite_types']}")
            self.logger.info("=" * 60)
            
            self.update_results['TR_Report_Deduplication'] = {'status': 'success', 'count': verify_count}
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 创建 TR_Report_Deduplication 表失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.update_results['TR_Report_Deduplication'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== 更新文件索引缓存 ==========
    def update_file_index(self):
        """更新文件索引缓存"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("步骤: 更新文件索引缓存")
            self.logger.info("=" * 60)
            
            # 尝试导入文件索引更新器
            try:
                from file_index_updater import FileIndexUpdater
            except ImportError as e:
                self.logger.warning(f"⚠️ 无法导入文件索引更新器: {e}")
                self.logger.warning("跳过文件索引更新")
                self.update_results['file_index'] = {'status': 'skipped', 'reason': '模块导入失败'}
                return False
            
            # 获取数据库路径
            db_path = SQLITE_DB_PATH
            
            # 获取基础文件夹路径（从环境变量或使用默认值）
            base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
            
            # 检查文件夹是否存在
            if not os.path.exists(base_folder):
                self.logger.warning(f"⚠️ 文件夹不存在: {base_folder}")
                self.logger.warning("跳过文件索引更新")
                self.update_results['file_index'] = {'status': 'skipped', 'reason': f'文件夹不存在: {base_folder}'}
                return False
            
            # 创建更新器并执行更新
            updater = FileIndexUpdater(db_path, base_folder)
            result = updater.update_index()
            
            if result.get('success'):
                stats = {
                    'files_added': result.get('files_added', 0),
                    'files_updated': result.get('files_updated', 0),
                    'files_deleted': result.get('files_deleted', 0),
                    'files_checked': result.get('files_checked', 0)
                }
                self.update_results['file_index'] = {
                    'status': 'success',
                    'count': stats['files_checked'],
                    'stats': stats
                }
                self.logger.info("✅ 文件索引缓存更新成功")
                self.logger.info(f"  新增: {stats['files_added']}, 更新: {stats['files_updated']}, 删除: {stats['files_deleted']}, 检查: {stats['files_checked']}")
                return True
            else:
                error_msg = result.get('error', '未知错误')
                self.update_results['file_index'] = {'status': 'failed', 'error': error_msg}
                self.logger.error(f"❌ 文件索引缓存更新失败: {error_msg}")
                return False
            
        except Exception as e:
            self.logger.error(f"❌ 文件索引更新异常: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.update_results['file_index'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== 创建 bbs_dd 表 ==========
    def get_bbs_dd_table_structure(self):
        """获取bbs_dd表的结构，用于判断日期字段"""
        try:
            with self.engine.connect() as conn:
                # 查询表结构
                query = text("""
                    SELECT COLUMN_NAME, DATA_TYPE 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_NAME = 'bbs_dd'
                    ORDER BY ORDINAL_POSITION
                """)
                result = conn.execute(query)
                columns = result.fetchall()
                
                self.logger.info("bbs_dd 表结构:")
                date_columns = []
                for col in columns:
                    col_name, col_type = col
                    self.logger.info(f"  {col_name}: {col_type}")
                    if 'date' in col_type.lower() or 'time' in col_type.lower():
                        date_columns.append(col_name)
                
                return date_columns
        except Exception as e:
            self.logger.warning(f"无法获取bbs_dd表结构: {e}")
            return []
    
    def create_bbs_dd_table(self):
        """创建 bbs_dd 表 - 从 SQL Server 查询近3年的数据"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("开始创建 bbs_dd 表")
            self.logger.info("=" * 60)
            
            # 先获取表结构，查找日期字段
            date_columns = self.get_bbs_dd_table_structure()
            
            with self.engine.connect() as conn:
                # 构建查询SQL
                # 如果有日期字段，添加近3年的筛选条件
                if date_columns:
                    # 使用第一个日期字段作为筛选条件
                    date_column = date_columns[0]
                    self.logger.info(f"使用日期字段 '{date_column}' 进行筛选")
                    
                    count_sql = text(f"""
                        SELECT COUNT(*) as record_count
                        FROM bbs_dd
                        WHERE {date_column} >= DATEADD(MONTH, -36, GETDATE())
                    """)
                    
                    query_sql = text(f"""
                        SELECT *
                        FROM bbs_dd
                        WHERE {date_column} >= DATEADD(MONTH, -36, GETDATE())
                    """)
                else:
                    # 如果没有日期字段，查询所有数据
                    self.logger.warning("未找到日期字段，将查询所有数据")
                    count_sql = text("SELECT COUNT(*) as record_count FROM bbs_dd")
                    query_sql = text("SELECT * FROM bbs_dd")
                
                # 先测试查询，获取数据量
                self.logger.info("查询数据...")
                result = conn.execute(count_sql)
                count = result.fetchone()[0]
                self.logger.info(f"找到 {count:,} 条记录")
                
                if count == 0:
                    self.logger.warning("⚠️ 没有数据，表将为空")
                
                # 查询数据
                self.logger.info("从 SQL Server 获取数据...")
                df = pd.read_sql(query_sql, conn)
                self.logger.info(f"获取了 {len(df):,} 条记录")
                
                if len(df) == 0:
                    self.logger.warning("⚠️ 没有获取到数据")
                    self.update_results['bbs_dd'] = {'status': 'warning', 'count': 0}
                    return False
                
                # 连接到 SQLite
                if not self.sqlite_conn:
                    self.create_sqlite_connection()
                
                # 如果表已存在，删除它
                cursor = self.sqlite_conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS bbs_dd")
                self.sqlite_conn.commit()
                self.logger.info("已删除旧的 bbs_dd 表（如果存在）")
                
                # 将数据写入 SQLite
                self.logger.info("写入数据到 SQLite...")
                df.to_sql('bbs_dd', self.sqlite_conn, if_exists='replace', index=False)
                self.sqlite_conn.commit()
                
                # 验证
                verify_count = pd.read_sql("SELECT COUNT(*) as cnt FROM bbs_dd", self.sqlite_conn).iloc[0]['cnt']
                self.logger.info(f"✅ bbs_dd 表创建成功: {verify_count:,} 条记录")
                
                # 显示表信息
                self.logger.info("=" * 60)
                self.logger.info("表信息:")
                self.logger.info(f"  总记录数: {verify_count:,}")
                if date_columns:
                    stats = pd.read_sql(f"""
                        SELECT 
                            MIN({date_columns[0]}) as earliest_date,
                            MAX({date_columns[0]}) as latest_date
                        FROM bbs_dd
                    """, self.sqlite_conn).iloc[0]
                    self.logger.info(f"  最早日期: {stats['earliest_date']}")
                    self.logger.info(f"  最晚日期: {stats['latest_date']}")
                self.logger.info("=" * 60)
                
                self.update_results['bbs_dd'] = {'status': 'success', 'count': verify_count}
                return True
                
        except Exception as e:
            self.logger.error(f"❌ 创建 bbs_dd 表失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.update_results['bbs_dd'] = {'status': 'failed', 'error': str(e)}
            return False
    
    def send_notification(self, success, message):
        """发送通知邮件（可选）
        支持多个收件人：在to_email中使用逗号分隔多个邮箱地址
        例如：'email1@company.com,email2@company.com' 或 ['email1@company.com', 'email2@company.com']
        """
        if not EMAIL_CONFIG['username'] or EMAIL_CONFIG['username'] == '':
            return
        
        # 处理多个收件人
        to_email = EMAIL_CONFIG['to_email']
        if isinstance(to_email, str):
            # 如果是字符串，按逗号分隔并去除空格
            recipients = [email.strip() for email in to_email.split(',') if email.strip()]
        elif isinstance(to_email, list):
            # 如果是列表，直接使用
            recipients = [email.strip() for email in to_email if email.strip()]
        else:
            self.logger.error("❌ to_email配置格式错误，应为字符串或列表")
            return
        
        if not recipients:
            self.logger.warning("⚠️ 没有有效的收件人邮箱地址")
            return
        
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_CONFIG['username']
            # 多个收件人用逗号分隔显示在邮件头
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = f"TR数据库自动更新{'成功' if success else '失败'}"
            
            body = f"""
TR数据库自动更新报告
时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
状态: {'成功' if success else '失败'}
详情: {message}
            
更新结果:
{chr(10).join([f"- {k}: {v}" for k, v in self.update_results.items()])}
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
            # 尝试登录（如果服务器支持认证）
            # 如果不支持认证，会跳过登录，直接发送（适用于内网匿名SMTP服务器）
            try:
                if EMAIL_CONFIG.get('password') and EMAIL_CONFIG['password'] != '':
                    server.login(EMAIL_CONFIG['username'], EMAIL_CONFIG['password'])
            except smtplib.SMTPAuthenticationError:
                # 如果认证失败，尝试匿名发送（某些内网服务器允许）
                self.logger.warning("⚠️ SMTP认证失败，尝试匿名发送...")
            except smtplib.SMTPException as e:
                # 如果服务器不支持认证，跳过登录
                if 'not supported' in str(e).lower() or 'AUTH' in str(e):
                    self.logger.info("ℹ️ 服务器不支持SMTP认证，使用匿名发送...")
                else:
                    raise
            
            # 发送给所有收件人
            server.send_message(msg, to_addrs=recipients)
            server.quit()
            
            self.logger.info(f"✅ 通知邮件发送成功，已发送给 {len(recipients)} 个收件人: {', '.join(recipients)}")
        except Exception as e:
            self.logger.error(f"❌ 发送通知邮件失败: {e}")
    
    def run_update(self):
        """执行更新流程 - 更新 bbs_dd、TR_Report、TR_Report_Deduplication 和文件索引"""
        start_time = datetime.now()
        self.logger.info("=" * 80)
        self.logger.info("开始 bbs_dd、TR_Report、TR_Report_Deduplication 和文件索引自动更新流程")
        self.logger.info(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 80)
        
        success_count = 0
        total_tasks = 4  # 增加了文件索引更新
        
        try:
            # 1. 连接数据库
            if not self.create_database_connection():
                raise Exception("无法连接源数据库")
            
            if not self.create_sqlite_connection():
                raise Exception("无法连接SQLite数据库")
            
            # 2. 创建 bbs_dd 表
            if self.create_bbs_dd_table():
                success_count += 1
            
            # 3. 创建 TR_Report 表
            if self.create_tr_report_table():
                success_count += 1
            
            # 4. 创建 TR_Report_Deduplication 表
            if self.create_tr_report_deduplication():
                success_count += 1
            
            # 5. 更新文件索引缓存
            if self.update_file_index():
                success_count += 1
            
            # 4. 计算执行时间
            end_time = datetime.now()
            duration = end_time - start_time
            
            # 5. 记录结果
            if success_count == total_tasks:
                message = f"所有数据更新成功，执行时间: {duration}"
                self.logger.info("🎉 " + message)
                self.send_notification(True, message)
            else:
                message = f"部分数据更新失败: {success_count}/{total_tasks}，执行时间: {duration}"
                self.logger.error(f"❌ {message}")
                self.logger.error("更新结果详情:")
                for table, result in self.update_results.items():
                    self.logger.error(f"  {table}: {result}")
                self.send_notification(False, message)
            
        except Exception as e:
            self.logger.error(f"❌ 更新流程失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.send_notification(False, f"更新流程失败: {str(e)}")
        
        finally:
            # 关闭连接
            if self.engine:
                self.engine.dispose()
            if self.sqlite_conn:
                self.sqlite_conn.close()
            
            self.logger.info("=" * 80)
            self.logger.info("bbs_dd、TR_Report、TR_Report_Deduplication 和文件索引自动更新流程结束")
            self.logger.info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info("=" * 80)

def main():
    """主函数"""
    error_log = None
    error_log_path = None
    try:
        # 尝试创建日志目录（如果尚未创建）
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except Exception as e:
                print(f"警告: 无法创建日志目录 {log_dir}: {e}")
        
        # 创建简单的日志文件用于捕获导入错误
        try:
            error_log_path = os.path.join(log_dir, f'error_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            error_log = open(error_log_path, 'w', encoding='utf-8')
            error_log.write(f"脚本启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            error_log.write(f"Python版本: {sys.version}\n")
            error_log.write(f"工作目录: {os.getcwd()}\n")
            error_log.write(f"脚本路径: {os.path.abspath(__file__)}\n")
            error_log.write("=" * 80 + "\n")
            error_log.flush()
        except Exception as e:
            print(f"警告: 无法创建错误日志文件: {e}")
            error_log = None
        
        try:
            updater = AutoUpdater()
            updater.run_update()
            if error_log:
                error_log.write("脚本执行完成\n")
                error_log.flush()
        except Exception as e:
            error_msg = f"执行过程中发生错误: {str(e)}\n"
            import traceback
            traceback_str = traceback.format_exc()
            if error_log:
                error_log.write(error_msg)
                error_log.write(traceback_str)
                error_log.flush()
            print(error_msg)
            print(traceback_str)
            sys.exit(1)
            
    except ImportError as e:
        # 处理导入错误（在导入阶段就失败了）
        error_msg = f"导入错误: {str(e)}\n"
        error_msg += f"请确保已安装所有必需的依赖包: pandas, sqlalchemy, pyodbc, numpy\n"
        error_msg += f"安装命令: pip install pandas sqlalchemy pyodbc numpy\n"
        import traceback
        traceback_str = traceback.format_exc()
        
        if error_log:
            try:
                error_log.write(error_msg)
                error_log.write(traceback_str)
                error_log.flush()
                error_log.close()
            except:
                pass
        else:
            # 如果error_log不存在，尝试创建一个简单的日志文件
            try:
                log_dir = os.path.join(os.path.dirname(__file__), 'logs')
                if not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                error_log_path = os.path.join(log_dir, f'import_error_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
                with open(error_log_path, 'w', encoding='utf-8') as f:
                    f.write(error_msg)
                    f.write(traceback_str)
            except:
                pass
        
        print(error_msg)
        print(traceback_str)
        sys.exit(1)
    except Exception as e:
        # 处理其他所有错误
        error_msg = f"脚本执行失败: {str(e)}\n"
        import traceback
        traceback_str = traceback.format_exc()
        error_msg_full = error_msg + traceback_str
        
        if error_log:
            try:
                error_log.write(error_msg_full)
                error_log.flush()
            except:
                pass
        else:
            # 如果error_log不存在，尝试创建一个简单的日志文件
            try:
                log_dir = os.path.join(os.path.dirname(__file__), 'logs')
                if not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                error_log_path = os.path.join(log_dir, f'error_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
                with open(error_log_path, 'w', encoding='utf-8') as f:
                    f.write(error_msg_full)
            except:
                pass
        
        print(error_msg_full)
        sys.exit(1)
    finally:
        if error_log:
            try:
                error_log.close()
            except:
                pass

if __name__ == "__main__":
    main()

