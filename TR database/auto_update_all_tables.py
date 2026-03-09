#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TR_Report and TR_Report_Deduplication Auto Update Script
Function: Auto update TR_Report and TR_Report_Deduplication tables
Author: TR Report System
Date: 2025-11-20
"""

import sys
import os
import io

# Set UTF-8 encoding environment variable (fix Chinese and emoji display issues on Windows)
if sys.platform == 'win32':
    # Set environment variable
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # Reconfigure stdout and stderr to UTF-8
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Add backend directory to Python path (for importing file index related modules)
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

# ==================== Configuration Section ====================
# Database Configuration
DB_CONFIG = {
    'server': '192.168.80.242',
    'database': 'TVSC',
    'username': 'reportuser',
    'password': 'HKSHA123',
    'driver': 'SQL Server'
}

# SQLiteDatabase Configuration
SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), 'data_3years.db')

# Email Configuration (optional, leave empty if email notification is not needed)
EMAIL_CONFIG = {
    'smtp_server': 'corpmail1.netvigator.com',
    'smtp_port': 25,
    'username': 'tr@hkshalliance.com',  # Leave empty to disable email
    'password': '',
    'to_email': 'henry.yu@hkshalliance.com,yuyuhang1991@163.com'
}
# ==================== End of Configuration ====================

# Setup Logging
def setup_logging():
    """Setup logging configuration"""
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_filename = os.path.join(log_dir, f'auto_update_all_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    # Create custom StreamHandler to ensure UTF-8 encoding
    class UTF8StreamHandler(logging.StreamHandler):
        def __init__(self, stream=None):
            super().__init__(stream)
            
        def emit(self, record):
            try:
                msg = self.format(record) + self.terminator
                # Use errors='replace' to avoid encoding errors, even if console cannot display emoji
                try:
                    if hasattr(self.stream, 'buffer'):
                        # For streams with buffer (like redirected stdout)
                        self.stream.buffer.write(msg.encode('utf-8', errors='replace'))
                        self.stream.buffer.flush()
                    else:
                        # For normal streams
                        self.stream.write(msg)
                        self.stream.flush()
                except (UnicodeEncodeError, AttributeError):
                    # If still error, use ASCII safe version
                    safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
                    self.stream.write(safe_msg)
                    self.stream.flush()
            except Exception:
                # Silently handle errors to avoid infinite loop
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
    """Auto Updater - Only update TR_Report and TR_Report_Deduplication tables"""
    
    def __init__(self):
        self.logger = setup_logging()
        self.engine = None
        self.sqlite_conn = None
        self.update_results = {}  # Record execution results for each step
        
    def create_database_connection(self):
        """Create source database connection"""
        try:
            connection_string = f"mssql+pyodbc://{DB_CONFIG['username']}:{DB_CONFIG['password']}@{DB_CONFIG['server']}/{DB_CONFIG['database']}?driver={DB_CONFIG['driver']}"
            self.engine = create_engine(connection_string, echo=False)
            
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            self.logger.info("[OK] Source database connection successful")
            return True
            
        except Exception as e:
            self.logger.error(f"[ERROR] Source database connection failed: {e}")
            return False
    
    def create_sqlite_connection(self):
        """Create SQLite database connection"""
        try:
            # Ensure database file exists and is writable
            db_dir = os.path.dirname(SQLITE_DB_PATH)
            if not os.path.exists(db_dir):
                os.makedirs(db_dir)
            
            # Check database file permissions (check only, do not modify, avoid affecting backend service)
            if os.path.exists(SQLITE_DB_PATH):
                try:
                    import stat
                    file_stat = os.stat(SQLITE_DB_PATH)
                    if not (file_stat.st_mode & stat.S_IWRITE):
                        # Only log warning, do not modify permissions (avoid affecting backend service)
                        self.logger.warning("[WARNING] Database file may be read-only, if update fails please check file permissions")
                except Exception as perm_error:
                    self.logger.warning(f"Cannot check database file permissions: {perm_error}")
            
            # Use same connection method as backend service (standard connection, not URI mode, avoid compatibility issues)
            # Backend service uses: sqlite3.connect(DB_PATH, timeout=30.0)
            # Keep consistent here to ensure compatibility
            # Increase timeout to 60 seconds, give backend service more time to release lock
            self.sqlite_conn = sqlite3.connect(SQLITE_DB_PATH, timeout=60.0)
            
            # Enable WAL mode to improve concurrency, allow multiple readers and writers to access simultaneously
            # Use same PRAGMA settings as backend service to ensure compatibility
            self.sqlite_conn.execute("PRAGMA journal_mode=WAL")
            # Set sync mode to NORMAL (safer and better performance in WAL mode)
            self.sqlite_conn.execute("PRAGMA synchronous=NORMAL")
            # Set busy_timeout (milliseconds), wait up to 60 seconds when database is locked
            self.sqlite_conn.execute("PRAGMA busy_timeout=60000")
            
            # Test connection (test read only, not write, avoid requiring exclusive lock)
            # Handle lock issues during actual write operations, use retry mechanism
            try:
                # Execute only one read operation to test if connection is normal
                cursor = self.sqlite_conn.cursor()
                cursor.execute("PRAGMA user_version")
                # Do not execute BEGIN IMMEDIATE, as this requires exclusive lock and may fail
                # Handle lock issues during actual write operations, use retry mechanism
                self.logger.info("[OK] Database connection test successful (read mode)")
            except sqlite3.OperationalError as e:
                error_msg = str(e).lower()
                if "readonly" in error_msg or "read-only" in error_msg:
                    self.logger.error(f"[ERROR] Database connection failed: database is read-only")
                    self.logger.error(f"   Please check:")
                    self.logger.error(f"   1. Database file permissions: {SQLITE_DB_PATH}")
                    self.logger.error(f"   2. Database directory permissions: {os.path.dirname(SQLITE_DB_PATH)}")
                    self.logger.error(f"   3. Whether other processes are locking the database")
                    self.logger.error(f"   4. WAL file permissions: {SQLITE_DB_PATH}-wal, {SQLITE_DB_PATH}-shm")
                    self.logger.error(f"   5. Suggestion: If backend service is running, retry later or temporarily stop the backend service")
                    return False
                else:
                    # Also log other errors, but do not fail immediately
                    self.logger.warning(f"[WARNING] Error occurred during connection test: {e}，Will retry during actual operation")
            
            self.logger.info("[OK] SQLite database connection successful (WAL mode, writable)")
            return True
        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "readonly" in error_msg or "read-only" in error_msg:
                self.logger.error(f"[ERROR] Database connection failed: database is read-only")
                self.logger.error(f"   Please check:")
                self.logger.error(f"   1. Database file permissions: {SQLITE_DB_PATH}")
                self.logger.error(f"   2. Database directory permissions: {os.path.dirname(SQLITE_DB_PATH)}")
                self.logger.error(f"   3. Whether other processes are locking the database")
                self.logger.error(f"   4. WAL file permissions: {SQLITE_DB_PATH}-wal, {SQLITE_DB_PATH}-shm")
                self.logger.error(f"   5. Suggestion: If backend service is running, retry later or temporarily stop the backend service")
            else:
                self.logger.error(f"[ERROR] SQLite database connection failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"[ERROR] SQLite database connection failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def execute_with_retry(self, operation, max_retries=10, retry_delay=3):
        """
        Execute database operation with retry mechanism
        
        Args:
            operation: Operation to execute (function)
            max_retries: Maximum retry times (increased to 10, give backend service more time to release lock)
            retry_delay: Retry delay (seconds, increased to 3 seconds)
        """
        import time
        for attempt in range(max_retries):
            try:
                return operation()
            except sqlite3.OperationalError as e:
                error_msg = str(e).lower()
                if "readonly" in error_msg or "read-only" in error_msg:
                    if attempt < max_retries - 1:
                        # Use fixed delay instead of exponential backoff to avoid long wait times
                        wait_time = retry_delay
                        self.logger.warning(f"[WARNING] Database read-only error, waiting {wait_time} seconds before retry ({attempt + 1}/{max_retries})...")
                        self.logger.warning(f"   Tip: Backend service is using database, waiting for connection release...")
                        if attempt == 5:
                            self.logger.warning(f"   [TIP] Suggestion: If waiting time is too long, you can temporarily stop backend service to speed up update")
                        time.sleep(wait_time)
                        # Reconnect database, try to get new connection
                        if self.sqlite_conn:
                            try:
                                self.sqlite_conn.close()
                            except:
                                pass
                        # Reconnect after brief delay
                        time.sleep(1)
                        if not self.create_sqlite_connection():
                            # If reconnection fails, continue retry
                            continue
                        continue
                    else:
                        self.logger.error(f"[ERROR] Database read-only error, retried {max_retries} times but still failed")
                        self.logger.error(f"   Reason: Backend service continuously holds database connection, cannot acquire write lock")
                        self.logger.error(f"   Solution:")
                        self.logger.error(f"   1. Temporarily stop backend service: Stop-Service TR-Backend")
                        self.logger.error(f"   2. Run update script")
                        self.logger.error(f"   3. Restart backend service: Start-Service TR-Backend")
                        self.logger.error(f"   Or use batch script to handle automatically: auto_update_all_tables.bat (Requires administrator privileges)")
                        raise
                elif "locked" in error_msg or "database is locked" in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)  # exponential backoff
                        self.logger.warning(f"[WARNING] Database is locked, waiting {wait_time} seconds before retry ({attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    else:
                        self.logger.error(f"[ERROR] Database is locked, retried {max_retries} times but still failed")
                        raise
                else:
                    raise
            except Exception as e:
                raise
    
    def execute_query(self, query, params=None):
        """Execute SQL query"""
        try:
            with self.engine.connect() as conn:
                result = pd.read_sql(query, conn, params=params)
            return result
        except Exception as e:
            self.logger.error(f"[ERROR] Query execution failed: {e}")
            return None
    
    # ========== Step 1: Update Orders table ==========
    def update_orders(self):
        """Update order data (3 years)"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Step 1: Update Orders table")
            self.logger.info("=" * 60)
            
            today = datetime.now()
            start_date = today - timedelta(days=1095)  # 3years = 1095 days
            
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
                self.sqlite_conn.commit()  # Explicit commit to ensure data is written
                self.logger.info(f"[OK] Orderstableupdate successful: {len(order_data)} rows")
                self.update_results['Orders'] = {'status': 'success', 'count': len(order_data)}
                return True
            else:
                self.logger.warning("[WARNING] Order data is empty")
                self.update_results['Orders'] = {'status': 'warning', 'count': 0}
                return False
                
        except Exception as e:
            self.logger.error(f"[ERROR] Update Orders table failed: {e}")
            self.update_results['Orders'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== Step 2: Update Materials table ==========
    def update_materials(self):
        """Update material data (3 years)"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Step 2: Update Materials table")
            self.logger.info("=" * 60)
            
            today = datetime.now()
            start_date = today - timedelta(days=1095)  # 3years = 1095 days
            
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
                self.sqlite_conn.commit()  # Explicit commit to ensure data is written
                self.logger.info(f"[OK] Materialstableupdate successful: {len(material_data)} rows")
                self.update_results['Materials'] = {'status': 'success', 'count': len(material_data)}
                return True
            else:
                self.logger.warning("[WARNING] Material data is empty")
                self.update_results['Materials'] = {'status': 'warning', 'count': 0}
                return False
                
        except Exception as e:
            self.logger.error(f"[ERROR] Update Materials table failed: {e}")
            self.update_results['Materials'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== Step 3: Generate Orders_com table ==========
    def compress_orders(self):
        """Compress order data, generate Orders_com table"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Step 3: Generate Orders_com table")
            self.logger.info("=" * 60)
            
            query = """
            SELECT 
                Order_No, Client, Jobsite, Jobsite_Type, Job_No, PO_No,
                Del_Date, Ref_No, Order_Description, Dia, Grade, Length, Wt
            FROM orders
            """
            
            orders_df = pd.read_sql(query, self.sqlite_conn)
            self.logger.info(f"Original order data: {len(orders_df)} rows")
            
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
            
            # Text cleaning
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
            
            # Weight unit conversion (kg to ton)
            compressed_orders['Wt'] = compressed_orders['Wt'] / 1000
            
            final_orders = compressed_orders[[
                'Order_No', 'Client', 'Jobsite', 'Jobsite_Type', 'Job_No', 'PO_No',
                'Del_Date', 'Ref_No', 'Order_Description', 'Dia', 'Grade', 'Length', 'Wt'
            ]].copy()
            
            final_orders.to_sql('orders_com', self.sqlite_conn, if_exists='replace', index=False)
            
            self.logger.info(f"[OK] Orders_com table generated successfully: {len(final_orders)} rows")
            self.logger.info(f"Compression rate: {(1 - len(final_orders) / len(orders_df)) * 100:.2f}%")
            self.update_results['Orders_com'] = {'status': 'success', 'count': len(final_orders)}
            return True
            
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to generate Orders_com table: {e}")
            self.update_results['Orders_com'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== Step 4: Generate Materials_com table ==========
    def compress_materials(self):
        """Compress material data, generate Materials_com table"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Step 4: Generate Materials_com table")
            self.logger.info("=" * 60)
            
            query = """
            SELECT 
                Product, Pattern, Mill_Cert, Test_Cert2, Test_Cert1,
                Stockist_Cert, PO_No, Tag_No, DN_No
            FROM materials
            """
            
            materials_df = pd.read_sql(query, self.sqlite_conn)
            self.logger.info(f"Original material data: {len(materials_df)} rows")
            
            # Extract diameter information
            def extract_dia_from_product(product):
                try:
                    if pd.isna(product) or product == '':
                        return ''
                    import re
                    match = re.search(r'(\d+)mm', str(product))
                    return f"Y{match.group(1)}" if match else ''
                except:
                    return ''
            
            # Extract length information
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
            
            # Remove duplicates
            compressed_materials = materials_df.drop_duplicates(subset=[
                'Product', 'Pattern', 'Mill_Cert', 'Test_Cert2', 'Test_Cert1',
                'Stockist_Cert', 'PO_No', 'Tag_No', 'DN_No'
            ])
            
            column_order = ['Dia', 'Len', 'Product', 'Pattern', 'Mill_Cert', 'Test_Cert2', 'Test_Cert1',
                          'Stockist_Cert', 'PO_No', 'Tag_No', 'DN_No']
            compressed_materials = compressed_materials[column_order]
            
            compressed_materials.to_sql('materials_com', self.sqlite_conn, if_exists='replace', index=False)
            
            self.logger.info(f"[OK] Materials_com table generated successfully: {len(compressed_materials)} rows")
            self.logger.info(f"Compression rate: {(1 - len(compressed_materials) / len(materials_df)) * 100:.2f}%")
            self.update_results['Materials_com'] = {'status': 'success', 'count': len(compressed_materials)}
            return True
            
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to generate Materials_com table: {e}")
            self.update_results['Materials_com'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== Step 5: Generate Orders_Deduplication table ==========
    def create_orders_deduplication(self):
        """Generate Orders_Deduplication table"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Step 5: Generate Orders_Deduplication table")
            self.logger.info("=" * 60)
            
            orders_df = pd.read_sql("SELECT * FROM orders_com", self.sqlite_conn)
            self.logger.info(f"Read orders_com data: {len(orders_df)} rows")
            
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
            
            # Map Jobsite_Type
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
            
            self.logger.info(f"[OK] Orders_Deduplication table generated successfully: {len(grouped)} rows")
            self.update_results['Orders_Deduplication'] = {'status': 'success', 'count': len(grouped)}
            return True
            
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to generate Orders_Deduplication table: {e}")
            self.update_results['Orders_Deduplication'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== Step 6: Generate Orders_gen_pdf table ==========
    def create_orders_gen_pdf(self):
        """Generate Orders_gen_pdf table"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Step 6: Generate Orders_gen_pdf table")
            self.logger.info("=" * 60)
            
            # Check if TR_Fill_in table exists
            cursor = self.sqlite_conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='TR_Fill_in'")
            if cursor.fetchone() is None:
                self.logger.warning("[WARNING] TR_Fill_in table does not exist, skipping Orders_gen_pdf generation")
                self.update_results['Orders_gen_pdf'] = {'status': 'skipped', 'reason': 'TR_Fill_in table does not exist'}
                return False
            
            # Check if TR_Fill_in table has data
            cursor.execute("SELECT COUNT(*) FROM TR_Fill_in")
            tr_fill_in_count = cursor.fetchone()[0]
            if tr_fill_in_count == 0:
                self.logger.warning("[WARNING] TR_Fill_in table is empty, skipping Orders_gen_pdf generation")
                self.update_results['Orders_gen_pdf'] = {'status': 'skipped', 'reason': 'TR_Fill_in table is empty'}
                return False
            
            self.logger.info(f"TR_Fill_in table has {tr_fill_in_count} records")
            
            # Drop existing table
            cursor.execute("DROP TABLE IF EXISTS Orders_gen_pdf")
            
            # Create new table
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
            
            self.logger.info(f"[OK] Orders_gen_pdf table generated successfully: {count} rows")
            self.update_results['Orders_gen_pdf'] = {'status': 'success', 'count': count}
            return True
            
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to generate Orders_gen_pdf table: {e}")
            self.update_results['Orders_gen_pdf'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== Step 7: Ensure PDF_Status table exists ==========
    def ensure_pdf_status_table(self):
        """Ensure PDF_Status table exists (create if not exists)"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Step 7: Check PDF_Status table")
            self.logger.info("=" * 60)
            
            cursor = self.sqlite_conn.cursor()
            
            # Check if PDF_Status table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='PDF_Status'")
            if cursor.fetchone() is not None:
                # Table exists, check record count
                cursor.execute("SELECT COUNT(*) FROM PDF_Status")
                count = cursor.fetchone()[0]
                self.logger.info(f"[OK] PDF_Status table exists, current record count: {count}")
                self.update_results['PDF_Status'] = {'status': 'exists', 'count': count}
                return True
            
            # Table does not exist, create it
            self.logger.info("PDF_Status table does not exist, creating...")
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
            
            # Verify table creation
            cursor.execute("SELECT COUNT(*) FROM PDF_Status")
            count = cursor.fetchone()[0]
            
            self.logger.info(f"[OK] PDF_Status table created successfully, current record count: {count}")
            self.update_results['PDF_Status'] = {'status': 'created', 'count': count}
            return True
            
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to check/create PDF_Status table: {e}")
            self.update_results['PDF_Status'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== Step 8: Ensure TR_Fill_in table exists ==========
    def ensure_tr_fill_in_table(self):
        """Ensure TR_Fill_in table exists (create if not exists)"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Step 8: Check TR_Fill_in table")
            self.logger.info("=" * 60)
            
            cursor = self.sqlite_conn.cursor()
            
            # Check if TR_Fill_in table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='TR_Fill_in'")
            if cursor.fetchone() is not None:
                # Table exists, check record count
                cursor.execute("SELECT COUNT(*) FROM TR_Fill_in")
                count = cursor.fetchone()[0]
                self.logger.info(f"[OK] TR_Fill_in table exists, current record count: {count}")
                self.update_results['TR_Fill_in'] = {'status': 'exists', 'count': count}
                return True
            
            # Table does not exist, create it
            self.logger.info("TR_Fill_in table does not exist, creating...")
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
            
            # Verify table creation
            cursor.execute("SELECT COUNT(*) FROM TR_Fill_in")
            count = cursor.fetchone()[0]
            
            self.logger.info(f"[OK] TR_Fill_in table created successfully, current record count: {count}")
            self.update_results['TR_Fill_in'] = {'status': 'created', 'count': count}
            return True
            
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to check/create TR_Fill_in table: {e}")
            self.update_results['TR_Fill_in'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== Create TR_Report table ==========
    def create_tr_report_table(self):
        """Create TR_Report table - Query last 3 years of data from SQL Server, create directly in SQLite"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Step 1: Create TR_Report table")
            self.logger.info("=" * 60)
            
            with self.engine.connect() as conn:
                # First test query to get data count
                self.logger.info("Querying last 3 years of data...")
                count_sql = text("""
                    SELECT COUNT(*) as record_count
                    FROM tr_line_size tls
                    JOIN tr_bbs_header tbh
                        ON tbh.bbs_no = tls.bbs_no
                    LEFT JOIN tr_line_detail tld
                        ON tls.bbs_no = tld.bbs_no
                        AND tls.diameter = tld.diameter
                    LEFT JOIN pedidos_produccion pp
                        ON pp.ID_PEDIDO_PRODUCCION = tls.bbs_no
                    LEFT JOIN obras js
                        ON js.ID_OBRA = COALESCE(pp.ID_OBRA, tbh.jobsite_no)
                    WHERE COALESCE(pp.fecha_entrega_prevista, tbh.delivery_date) >= DATEADD(MONTH, -36, GETDATE())
                """)
                result = conn.execute(count_sql)
                count = result.fetchone()[0]
                self.logger.info(f"Found {count:,} records from last 3 years")
                
                if count == 0:
                    self.logger.warning("[WARNING] No data from last 3 years, table will be empty")
                
                # Query data
                self.logger.info("Fetching data from SQL Server...")
                self.logger.info(f"[WARNING]  Note: Fetching {count:,} records, this may take several minutes, please wait...")
                self.logger.info("[WARNING]  If network is slow or data volume is large, may take 5-15 minutes")
                
                query_sql = text("""
                    SELECT
                        COALESCE(pp.id_obra, tbh.jobsite_no) AS Job_No, 
                        COALESCE(js.nombre, tbh.jobsite_name) AS jobsite, 
                        COALESCE(pp.id_pedido_produccion, tbh.bbs_no) AS order_no, 
                        COALESCE(pp.descripcion, tbh.order_desc) AS order_describution,
                        COALESCE(js.arquitecto, tbh.main_contractor) AS client,
                        COALESCE(pp.fecha_entrega_prevista, tbh.delivery_date) AS del_date,
                        COALESCE(pp.referencia_1, tbh.bbs_ref_no) AS ref_no,
                        COALESCE(pp.referencia_2, tbh.bbs_po_no) AS bbs_po_no,
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
                    LEFT JOIN pedidos_produccion pp
                        ON pp.ID_PEDIDO_PRODUCCION = tls.bbs_no
                    LEFT JOIN obras js
                        ON js.ID_OBRA = COALESCE(pp.ID_OBRA, tbh.jobsite_no)
                    WHERE COALESCE(pp.fecha_entrega_prevista, tbh.delivery_date) >= DATEADD(MONTH, -36, GETDATE())
                    ORDER BY COALESCE(pp.fecha_entrega_prevista, tbh.delivery_date) DESC, COALESCE(pp.id_obra, tbh.jobsite_no), COALESCE(pp.ID_PEDIDO_PRODUCCION, tbh.bbs_no), tls.diameter, tld.pattern
                """)
                
                # Use chunksize to read in batches, avoid memory issues (if data volume is large)
                try:
                    # Try to read in chunks
                    chunk_size = 50000  # Read 50,000 records each time
                    chunks = []
                    total_read = 0
                    
                    for chunk_df in pd.read_sql(query_sql, conn, chunksize=chunk_size):
                        chunks.append(chunk_df)
                        total_read += len(chunk_df)
                        if total_read % 100000 == 0:  # Output progress every 100,000 records
                            progress = (total_read * 100 // count) if count else 100
                            self.logger.info(f"   Read: {total_read:,} / {count:,} records ({progress}%)")
                    
                    # Merge all chunks
                    df = pd.concat(chunks, ignore_index=True)
                    self.logger.info(f"[OK] Retrieved {len(df):,} records (completed)")
                except Exception as chunk_error:
                    # If batch read fails, fall back to one-time read
                    self.logger.warning(f"Batch read failed, using one-time read: {chunk_error}")
                    df = pd.read_sql(query_sql, conn)
                    self.logger.info(f"[OK] Retrieved {len(df):,} records")
                
                # Connect to SQLite
                if not self.sqlite_conn:
                    self.create_sqlite_connection()
                
                # Check if TR_Report table already exists and has data
                cursor = self.sqlite_conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='TR_Report'")
                table_exists = cursor.fetchone() is not None
                
                if table_exists:
                    cursor.execute("SELECT COUNT(*) FROM TR_Report")
                    existing_count = cursor.fetchone()[0]
                    self.logger.info(f"TR_Report table already exists, currently has {existing_count:,} records")
                    
                    if len(df) == 0:
                        self.logger.warning("[WARNING] Queried 0 new records from SQL Server")
                        self.logger.warning(f"[WARNING] but TR_Report table already has {existing_count:,} records, keeping existing data")
                        self.update_results['TR_Report'] = {'status': 'warning', 'count': existing_count, 'message': 'No new data from SQL Server, keeping existing data'}
                        return True  # Keep existing data, do not delete table
                
                # If there is new data, use table renaming strategy (avoid DROP TABLE requiring exclusive lock)
                if len(df) > 0:
                    # Strategy: Create new table -> Insert data (no lock needed) -> Delete old table and rename in shortest transaction
                    # Key: Most of the time (creating and writing new table) does not need to lock old table, only need lock during final swap
                    def replace_table():
                        cursor = self.sqlite_conn.cursor()
                        
                        # Step 1-2: Create new table and write data (no need to lock old table, can proceed concurrently)
                        temp_table_name = "TR_Report_new"
                        cursor.execute("DROP TABLE IF EXISTS " + temp_table_name)
                        self.sqlite_conn.commit()  # Commit first, release lock
                        
                        # Write data to new table (this process does not need to lock old table)
                        df.to_sql(temp_table_name, self.sqlite_conn, if_exists='replace', index=False)
                        self.sqlite_conn.commit()  # Commit, release lock
                        
                        # Step 3-4: Complete table swap in shortest transaction (lock needed here)
                        # Use BEGIN IMMEDIATE to quickly acquire lock, then immediately execute delete and rename
                        cursor.execute("BEGIN IMMEDIATE")
                        try:
                            # Delete old table (requires EXCLUSIVE lock, but time is short)
                            cursor.execute("DROP TABLE IF EXISTS TR_Report")
                            
                            # Rename new table (atomic operation, almost instant)
                            cursor.execute(f"ALTER TABLE {temp_table_name} RENAME TO TR_Report")
                            
                            self.sqlite_conn.commit()
                            return True
                        except sqlite3.OperationalError as e:
                            self.sqlite_conn.rollback()
                            # Clean up temporary table
                            try:
                                cursor.execute("DROP TABLE IF EXISTS " + temp_table_name)
                                self.sqlite_conn.commit()
                            except:
                                pass
                            raise
                    
                    try:
                        # Increase retry count and delay, as backend service may hold connection for long time
                        self.execute_with_retry(replace_table, max_retries=20, retry_delay=10)
                        self.logger.info("[OK] Updated using table renaming strategy TR_Report table (no need to stop backend service)")
                    except Exception as e:
                        self.logger.error(f"[ERROR] Cannot update table: {e}")
                        self.logger.error(f"   Reason: Backend service may be using database, cannot acquire write lock")
                        self.logger.error(f"   Solution:")
                        self.logger.error(f"   1. Temporarily stop backend service: Stop-Service TR-Backend")
                        self.logger.error(f"   2. Run update script")
                        self.logger.error(f"   3. Restart backend service: Start-Service TR-Backend")
                        raise
                else:
                    # No new data, keep existing data
                    self.logger.warning("[WARNING] No new data retrieved, keeping existing TR_Report table")
                    self.update_results['TR_Report'] = {'status': 'warning', 'count': existing_count if table_exists else 0, 'message': 'No new data, keeping existing table'}
                    return True
                
                # Use table renaming strategy to write data (avoid exclusive lock, no need to stop backend service)
                def write_table():
                    cursor = self.sqlite_conn.cursor()
                    cursor.execute("BEGIN IMMEDIATE")
                    try:
                        # 1. Create temporary table
                        temp_table_name = "TR_Report_new"
                        cursor.execute("DROP TABLE IF EXISTS " + temp_table_name)
                        
                        # 2. Write data to temporary table
                        self.logger.info("Writing data to temporary table...")
                        df.to_sql(temp_table_name, self.sqlite_conn, if_exists='replace', index=False)
                        
                        # 3. Drop old table
                        cursor.execute("DROP TABLE IF EXISTS TR_Report")
                        
                        # 4. Rename temporary table (atomic operation, minimize lock time)
                        cursor.execute(f"ALTER TABLE {temp_table_name} RENAME TO TR_Report")
                        
                        self.sqlite_conn.commit()
                        return True
                    except sqlite3.OperationalError as e:
                        self.sqlite_conn.rollback()
                        # Clean up temporary table
                        try:
                            cursor.execute("DROP TABLE IF EXISTS " + temp_table_name)
                            self.sqlite_conn.commit()
                        except:
                            pass
                        raise
                
                self.execute_with_retry(write_table)
                self.logger.info("[OK] Updated using table renaming strategy TR_Report table (no need to stop backend service)")
                
                # Verify
                verify_count = pd.read_sql("SELECT COUNT(*) as cnt FROM TR_Report", self.sqlite_conn).iloc[0]['cnt']
                self.logger.info(f"[OK] TR_Report table created successfully: {verify_count:,} records")
                
                # Statistics
                stats = pd.read_sql("""
                    SELECT 
                        MIN(del_date) as earliest_date,
                        MAX(del_date) as latest_date,
                        COUNT(DISTINCT order_no) as unique_orders,
                        COUNT(DISTINCT Job_No) as unique_jobsites
                    FROM TR_Report
                """, self.sqlite_conn).iloc[0]
                
                self.logger.info("=" * 60)
                self.logger.info("Table statistics:")
                self.logger.info(f"  Earliest date: {stats['earliest_date']}")
                self.logger.info(f"  Latest date: {stats['latest_date']}")
                self.logger.info(f"  Unique orders: {stats['unique_orders']:,}")
                self.logger.info(f"  Unique jobsites: {stats['unique_jobsites']:,}")
                self.logger.info("=" * 60)
                
                self.update_results['TR_Report'] = {'status': 'success', 'count': verify_count}
                return True
                
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to create TR_Report table: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.update_results['TR_Report'] = {'status': 'failed', 'error': str(e)}
            return False
    # ========== Create TR_Report_Deduplication table ==========
    def create_tr_report_deduplication(self):
        """Create TR_Report_Deduplication table - Deduplicate from TR_Report table by Order_No"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Step 2: Create TR_Report_Deduplication table")
            self.logger.info("=" * 60)
            
            if not self.sqlite_conn:
                self.create_sqlite_connection()
            
            # Check if TR_Report table exists
            cursor = self.sqlite_conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='TR_Report'
            """)
            if not cursor.fetchone():
                self.logger.error("[ERROR] TR_Report table does not exist, please create TR_Report table first")
                self.update_results['TR_Report_Deduplication'] = {'status': 'failed', 'error': 'TR_Report table does not exist'}
                return False
            
            # Read TR_Report table data
            self.logger.info("Reading data from TR_Report table...")
            tr_report_df = pd.read_sql("SELECT * FROM TR_Report", self.sqlite_conn)
            self.logger.info(f"Read {len(tr_report_df):,} records from TR_Report")
            
            if tr_report_df.empty:
                self.logger.warning("[WARNING] TR_Report table is empty, TR_Report_Deduplication will also be empty")
            
            # Group by order_no and deduplicate
            self.logger.info("Grouping by order_no and aggregating...")
            grouped = tr_report_df.groupby('order_no').agg({
                'Job_No': 'first',
                'jobsite': 'first',
                'order_describution': 'first',
                'client': 'first',
                'del_date': 'first',
                'ref_no': 'first',
                'bbs_po_no': 'first',
                'jobsite_type': 'first',
                'wt_ton': 'sum',  # Sum weight
                'grade': 'first',
                'rm_dn_no': 'first',
            }).reset_index()
            
            # Rename columns to match TR_Report_Deduplication naming style
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
            # Job_No is already correct name, no need to rename
            
            self.logger.info(f"Aggregated to {len(grouped):,} unique orders")
            
            # Sort by Del_Date descending
            self.logger.info("Sorting by Del_Date descending...")
            grouped = grouped.sort_values('Del_Date', ascending=False, na_position='last')
            
            # Use table renaming strategy to update table (avoid DROP TABLE requiring exclusive lock)
            # Key: Create new table and write data first (no lock needed), then complete table swap in shortest transaction
            def replace_table():
                cursor = self.sqlite_conn.cursor()
                
                # Step 1-2: Create new table and write data (no need to lock old table, can proceed concurrently)
                temp_table_name = "TR_Report_Deduplication_new"
                cursor.execute("DROP TABLE IF EXISTS " + temp_table_name)
                self.sqlite_conn.commit()  # Commit first, release lock
                
                # Write data to new table (this process does not need to lock old table)
                grouped.to_sql(temp_table_name, self.sqlite_conn, if_exists='replace', index=False)
                self.sqlite_conn.commit()  # Commit, release lock
                
                # Step 3-4: Complete table swap in shortest transaction (lock needed here)
                # Use BEGIN IMMEDIATE to quickly acquire lock, then immediately execute delete and rename
                cursor.execute("BEGIN IMMEDIATE")
                try:
                    # Delete old table (requires EXCLUSIVE lock, but time is short)
                    cursor.execute("DROP TABLE IF EXISTS TR_Report_Deduplication")
                    
                    # Rename new table (atomic operation, almost instant)
                    cursor.execute(f"ALTER TABLE {temp_table_name} RENAME TO TR_Report_Deduplication")
                    
                    self.sqlite_conn.commit()
                    return True
                except sqlite3.OperationalError as e:
                    self.sqlite_conn.rollback()
                    # Clean up temporary table
                    try:
                        cursor.execute("DROP TABLE IF EXISTS " + temp_table_name)
                        self.sqlite_conn.commit()
                    except:
                        pass
                    raise
            
            try:
                self.execute_with_retry(replace_table, max_retries=15, retry_delay=5)
                self.logger.info("[OK] Updated using table renaming strategy TR_Report_Deduplication table (no need to stop backend service)")
            except Exception as e:
                self.logger.error(f"[ERROR] Cannot update table: {e}")
                raise
            
            # Verify data
            verify_count = pd.read_sql("SELECT COUNT(*) as cnt FROM TR_Report_Deduplication", self.sqlite_conn).iloc[0]['cnt']
            self.logger.info(f"[OK] TR_Report_Deduplication table created successfully: {verify_count:,} records")
            
            # Display statistics
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
            self.logger.info("Table statistics:")
            self.logger.info(f"  Earliest date: {stats['earliest_date']}")
            self.logger.info(f"  Latest date: {stats['latest_date']}")
            self.logger.info(f"  Unique orders: {stats['unique_orders']:,}")
            self.logger.info(f"  Unique jobsites: {stats['unique_jobsites']:,}")
            self.logger.info(f"  Total weight: {stats['total_weight']:.2f} tons")
            self.logger.info(f"  Jobsite types: {stats['unique_jobsite_types']}")
            self.logger.info("=" * 60)
            
            self.update_results['TR_Report_Deduplication'] = {'status': 'success', 'count': verify_count}
            return True
            
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to create TR_Report_Deduplication table: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.update_results['TR_Report_Deduplication'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== Update file index cache ==========
    def update_file_index(self):
        """Update file index cache"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Step: Update file index cache")
            self.logger.info("=" * 60)
            
            # Try to import file index updater
            try:
                from file_index_updater import FileIndexUpdater
            except ImportError as e:
                self.logger.warning(f"[WARNING] Cannot import file index updater: {e}")
                self.logger.warning("Skipping file index update")
                self.update_results['file_index'] = {'status': 'skipped', 'reason': 'Module import failed'}
                return False
            
            # Get database path
            db_path = SQLITE_DB_PATH
            
            # Get base folder path (from environment variable or use default)
            base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
            
            # Check if folder exists
            if not os.path.exists(base_folder):
                self.logger.warning(f"[WARNING] Folder does not exist: {base_folder}")
                self.logger.warning("Skipping file index update")
                self.update_results['file_index'] = {'status': 'skipped', 'reason': f'Folder does not exist: {base_folder}'}
                return False
            
            # Create updater and execute update
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
                self.logger.info("[OK] File index cache update successful")
                self.logger.info(f"  Added: {stats['files_added']}, Updated: {stats['files_updated']}, Deleted: {stats['files_deleted']}, Checked: {stats['files_checked']}")
                return True
            else:
                error_msg = result.get('error', 'Unknown error')
                self.update_results['file_index'] = {'status': 'failed', 'error': error_msg}
                self.logger.error(f"[ERROR] File index cache update failed: {error_msg}")
                return False
            
        except Exception as e:
            self.logger.error(f"[ERROR] File index update exception: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.update_results['file_index'] = {'status': 'failed', 'error': str(e)}
            return False
    
    # ========== Create bbs_dd table ==========
    def get_bbs_dd_table_structure(self):
        """Get bbs_dd table structure to determine date fields"""
        try:
            with self.engine.connect() as conn:
                # Query table structure
                query = text("""
                    SELECT COLUMN_NAME, DATA_TYPE 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_NAME = 'bbs_dd'
                    ORDER BY ORDINAL_POSITION
                """)
                result = conn.execute(query)
                columns = result.fetchall()
                
                self.logger.info("bbs_dd table structure:")
                date_columns = []
                for col in columns:
                    col_name, col_type = col
                    self.logger.info(f"  {col_name}: {col_type}")
                    if 'date' in col_type.lower() or 'time' in col_type.lower():
                        date_columns.append(col_name)
                
                return date_columns
        except Exception as e:
            self.logger.warning(f"Cannot get bbs_dd table structure: {e}")
            return []
    
    def create_bbs_dd_table(self):
        """Create bbs_dd table - Query last 3 years of data from SQL Server"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Start creating bbs_dd table")
            self.logger.info("=" * 60)
            
            # First get table structure, find date fields
            date_columns = self.get_bbs_dd_table_structure()
            
            with self.engine.connect() as conn:
                # Build query SQL
                # If there are date fields, add last 3 years filter condition
                if date_columns:
                    # Use first date field as filter condition
                    date_column = date_columns[0]
                    self.logger.info(f"Using date field '{date_column}' for filtering")
                    
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
                    # If no date field, query all data
                    self.logger.warning("No date field found, will query all data")
                    count_sql = text("SELECT COUNT(*) as record_count FROM bbs_dd")
                    query_sql = text("SELECT * FROM bbs_dd")
                
                # First test query to get data count
                self.logger.info("Querying data...")
                result = conn.execute(count_sql)
                count = result.fetchone()[0]
                self.logger.info(f"Found {count:,} records")
                
                if count == 0:
                    self.logger.warning("[WARNING] No data, table will be empty")
                
                # Query data
                self.logger.info("Fetching data from SQL Server...")
                self.logger.info(f"[WARNING]  Note: Fetching {count:,} records, this may take several minutes, please wait...")
                self.logger.info("[WARNING]  If network is slow or data volume is large, may take 5-15 minutes")
                
                # Use chunksize to read in batches, avoid memory issues (if data volume is large)
                try:
                    # Try to read in chunks
                    chunk_size = 50000  # Read 50,000 records each time
                    chunks = []
                    total_read = 0
                    
                    for chunk_df in pd.read_sql(query_sql, conn, chunksize=chunk_size):
                        chunks.append(chunk_df)
                        total_read += len(chunk_df)
                        if total_read % 100000 == 0:  # Output progress every 100,000 records
                            self.logger.info(f"   Read: {total_read:,} / {count:,} records ({total_read*100//count}%)")
                    
                    # Merge all chunks
                    df = pd.concat(chunks, ignore_index=True)
                    self.logger.info(f"[OK] Retrieved {len(df):,} records (completed)")
                except Exception as chunk_error:
                    # If batch read fails, fall back to one-time read
                    self.logger.warning(f"Batch read failed, using one-time read: {chunk_error}")
                    df = pd.read_sql(query_sql, conn)
                    self.logger.info(f"[OK] Retrieved {len(df):,} records")
                
                if len(df) == 0:
                    self.logger.warning("[WARNING] No data retrieved")
                    self.update_results['bbs_dd'] = {'status': 'warning', 'count': 0}
                    return False
                
                # Connect to SQLite
                if not self.sqlite_conn:
                    self.create_sqlite_connection()
                
                # Use table renaming strategy to update table (avoid DROP TABLE requiring exclusive lock, no need to stop backend service)
                # Key: Create new table and write data first (no lock needed), then complete table swap in shortest transaction
                def replace_table():
                    cursor = self.sqlite_conn.cursor()
                    
                    # Step 1-2: Create new table and write data (no need to lock old table, can proceed concurrently)
                    temp_table_name = "bbs_dd_new"
                    cursor.execute("DROP TABLE IF EXISTS " + temp_table_name)
                    self.sqlite_conn.commit()  # Commit first, release lock
                    
                    # Write data to new table (this process does not need to lock old table)
                    df.to_sql(temp_table_name, self.sqlite_conn, if_exists='replace', index=False)
                    self.sqlite_conn.commit()  # Commit, release lock
                    
                    # Step 3-4: Complete table swap in shortest transaction (lock needed here)
                    # Use BEGIN IMMEDIATE to quickly acquire lock, then immediately execute delete and rename
                    cursor.execute("BEGIN IMMEDIATE")
                    try:
                        # Delete old table (requires EXCLUSIVE lock, but time is short)
                        cursor.execute("DROP TABLE IF EXISTS bbs_dd")
                        
                        # Rename new table (atomic operation, almost instant)
                        cursor.execute(f"ALTER TABLE {temp_table_name} RENAME TO bbs_dd")
                        
                        self.sqlite_conn.commit()
                        return True
                    except sqlite3.OperationalError as e:
                        self.sqlite_conn.rollback()
                        # Clean up temporary table
                        try:
                            cursor.execute("DROP TABLE IF EXISTS " + temp_table_name)
                            self.sqlite_conn.commit()
                        except:
                            pass
                        raise
                
                try:
                    self.execute_with_retry(replace_table, max_retries=15, retry_delay=5)
                    self.logger.info("[OK] Updated using table renaming strategy bbs_dd table (no need to stop backend service)")
                except Exception as e:
                    self.logger.error(f"[ERROR] Cannot update table: {e}")
                    raise
                
                # Verify
                verify_count = pd.read_sql("SELECT COUNT(*) as cnt FROM bbs_dd", self.sqlite_conn).iloc[0]['cnt']
                self.logger.info(f"[OK] bbs_dd table created successfully: {verify_count:,} records")
                
                # Display table information
                self.logger.info("=" * 60)
                self.logger.info("Table information:")
                self.logger.info(f"  Total records: {verify_count:,}")
                if date_columns:
                    stats = pd.read_sql(f"""
                        SELECT 
                            MIN({date_columns[0]}) as earliest_date,
                            MAX({date_columns[0]}) as latest_date
                        FROM bbs_dd
                    """, self.sqlite_conn).iloc[0]
                    self.logger.info(f"  Earliest date: {stats['earliest_date']}")
                    self.logger.info(f"  Latest date: {stats['latest_date']}")
                self.logger.info("=" * 60)
                
                self.update_results['bbs_dd'] = {'status': 'success', 'count': verify_count}
                return True
                
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to create bbs_dd table: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.update_results['bbs_dd'] = {'status': 'failed', 'error': str(e)}
            return False
    
    def send_notification(self, success, message):
        """Send notification email (optional)
        Supports multiple recipients: Use comma to separate multiple email addresses in to_email
        Example: 'email1@company.com,email2@company.com' or ['email1@company.com', 'email2@company.com']
        """
        if not EMAIL_CONFIG['username'] or EMAIL_CONFIG['username'] == '':
            return
        
        # Handle multiple recipients
        to_email = EMAIL_CONFIG['to_email']
        if isinstance(to_email, str):
            # If string, split by comma and strip spaces
            recipients = [email.strip() for email in to_email.split(',') if email.strip()]
        elif isinstance(to_email, list):
            # If list, use directly
            recipients = [email.strip() for email in to_email if email.strip()]
        else:
            self.logger.error("[ERROR] to_email configuration format error, should be string or list")
            return
        
        if not recipients:
            self.logger.warning("[WARNING] No valid recipient email addresses")
            return
        
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_CONFIG['username']
            # Multiple recipients separated by comma in email header
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = f"TR Database Auto Update {'Success' if success else 'Failed'}"
            
            body = f"""
TR Database Auto Update Report
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Status: {'Success' if success else 'Failed'}
Details: {message}
            
Update Results:
{chr(10).join([f"- {k}: {v}" for k, v in self.update_results.items()])}
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
            # Try to login (if server supports authentication)
            # If authentication is not supported, skip login and send directly (for internal anonymous SMTP servers)
            try:
                if EMAIL_CONFIG.get('password') and EMAIL_CONFIG['password'] != '':
                    server.login(EMAIL_CONFIG['username'], EMAIL_CONFIG['password'])
            except smtplib.SMTPAuthenticationError:
                # If authentication fails, try anonymous send (some internal servers allow)
                self.logger.warning("[WARNING] SMTP authentication failed, trying anonymous send...")
            except smtplib.SMTPException as e:
                # If server does not support authentication, skip login
                if 'not supported' in str(e).lower() or 'AUTH' in str(e):
                    self.logger.info("Server does not support SMTP authentication, using anonymous send...")
                else:
                    raise
            
            # Send to all recipients
            server.send_message(msg, to_addrs=recipients)
            server.quit()
            
            self.logger.info(f"[OK] Notification email sent successfully, sent to {len(recipients)} recipients: {', '.join(recipients)}")
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to send notification email: {e}")
    
    def check_backend_service(self):
        """Check backend service status"""
        try:
            import subprocess
            if sys.platform == 'win32':
                # Windows: Use sc query command
                result = subprocess.run(
                    ['sc', 'query', 'TR-Backend'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if 'RUNNING' in result.stdout:
                    return True, 'running'
                elif 'STOPPED' in result.stdout:
                    return False, 'stopped'
                else:
                    return None, 'unknown'
            else:
                # Linux/Mac: Use systemctl
                result = subprocess.run(
                    ['systemctl', 'is-active', 'TR-Backend'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return True, 'running'
                else:
                    return False, 'stopped'
        except Exception as e:
            self.logger.warning(f"Cannot check backend service status: {e}")
            return None, 'unknown'
    
    def run_update(self):
        """Execute update process - Update bbs_dd, TR_Report, TR_Report_Deduplication and file index"""
        start_time = datetime.now()
        self.logger.info("=" * 80)
        self.logger.info("Start bbs_dd, TR_Report, TR_Report_Deduplication and file index auto update process")
        self.logger.info(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 80)
        
        # Check backend service status
        service_running, service_status = self.check_backend_service()
        if service_running:
            self.logger.warning("=" * 80)
            self.logger.warning("[WARNING] Warning: Backend service (TR-Backend) is running")
            self.logger.warning("[WARNING]  This may cause database update to fail (read-only error)")
            self.logger.warning("[WARNING]  Suggestion:")
            self.logger.warning("[WARNING]    1. Temporarily stop backend service: Stop-Service TR-Backend")
            self.logger.warning("[WARNING]    2. Run update script")
            self.logger.warning("[WARNING]    3. Restart after update completes: Start-Service TR-Backend")
            self.logger.warning("[WARNING]  Or wait for system to automatically retry (may take a long time)")
            self.logger.warning("=" * 80)
        elif service_running is False:
            self.logger.info("[OK] Backend service (TR-Backend) is stopped, can safely update database")
        
        success_count = 0
        total_tasks = 4  # Added file index update
        
        try:
            # 1. Connect to database
            if not self.create_database_connection():
                raise Exception("Cannot connect to source database")
            
            if not self.create_sqlite_connection():
                raise Exception("Cannot connect to SQLite database")
            
            # 2. Create bbs_dd table
            if self.create_bbs_dd_table():
                success_count += 1
            
            # 3. Create TR_Report table
            if self.create_tr_report_table():
                success_count += 1
            
            # 4. Create TR_Report_Deduplication table
            if self.create_tr_report_deduplication():
                success_count += 1
            
            # 5. Update file index cache
            if self.update_file_index():
                success_count += 1
            
            # 4. Calculate execution time
            end_time = datetime.now()
            duration = end_time - start_time
            
            # 5. Record results
            if success_count == total_tasks:
                message = f"All data update successful, execution time: {duration}"
                self.logger.info("[SUCCESS] " + message)
                self.send_notification(True, message)
            else:
                message = f"Partial data update failed: {success_count}/{total_tasks}, execution time: {duration}"
                self.logger.error(f"[ERROR] {message}")
                self.logger.error("Update result details:")
                for table, result in self.update_results.items():
                    self.logger.error(f"  {table}: {result}")
                self.send_notification(False, message)
            
        except Exception as e:
            self.logger.error(f"[ERROR] Update process failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.send_notification(False, f"Update process failed: {str(e)}")
        
        finally:
            # Close connection
            if self.engine:
                self.engine.dispose()
            if self.sqlite_conn:
                self.sqlite_conn.close()
            
            self.logger.info("=" * 80)
            self.logger.info("bbs_dd、TR_Report、TR_Report_Deduplication and file index auto update process ended")
            self.logger.info(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info("=" * 80)

def main():
    """Main function"""
    error_log = None
    error_log_path = None
    try:
        # Try to create log directory (if not already created)
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except Exception as e:
                print(f"Warning: Cannot create log directory {log_dir}: {e}")
        
        # Create simple log file to capture Import error
        try:
            error_log_path = os.path.join(log_dir, f'error_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            error_log = open(error_log_path, 'w', encoding='utf-8')
            error_log.write(f"Script start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            error_log.write(f"Python version: {sys.version}\n")
            error_log.write(f"Working directory: {os.getcwd()}\n")
            error_log.write(f"Script path: {os.path.abspath(__file__)}\n")
            error_log.write("=" * 80 + "\n")
            error_log.flush()
        except Exception as e:
            print(f"Warning: Cannot create error log file: {e}")
            error_log = None
        
        try:
            updater = AutoUpdater()
            updater.run_update()
            if error_log:
                error_log.write("Script execution completed\n")
                error_log.flush()
        except Exception as e:
            error_msg = f"Error occurred during execution: {str(e)}\n"
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
        # Handle Import error (failed during import phase)
        error_msg = f"Import error: {str(e)}\n"
        error_msg += f"Please ensure all required dependencies are installed: pandas, sqlalchemy, pyodbc, numpy\n"
        error_msg += f"Install command: pip install pandas sqlalchemy pyodbc numpy\n"
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
            # If error_log does not exist, try to create a simple log file
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
        # Handle all other errors
        error_msg = f"Script execution failed: {str(e)}\n"
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
            # If error_log does not exist, try to create a simple log file
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

