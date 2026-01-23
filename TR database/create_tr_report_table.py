#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建 TR_Report 表
从 SQL Server 查询近半年的数据并创建表
"""

import os
import sys
import logging
from datetime import datetime
from sqlalchemy import create_engine, text

# 配置日志
def setup_logging():
    import io
    # 设置控制台输出编码为 UTF-8
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, f'create_tr_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

# 数据库配置
DB_CONFIG = {
    'server': os.getenv('SQL_SERVER', '192.168.80.242'),
    'database': os.getenv('SQL_DATABASE', 'TVSC'),
    'username': os.getenv('SQL_USERNAME', 'reportuser'),
    'password': os.getenv('SQL_PASSWORD', 'HKSHA123'),
    'driver': 'SQL Server'
}

def create_tr_report_table():
    """创建 TR_Report 表 - 如果 SQL Server 没有权限，则创建到 SQLite"""
    logger = setup_logging()
    
    try:
        logger.info("=" * 60)
        logger.info("Starting to create TR_Report table")
        logger.info("=" * 60)
        
        # 创建数据库连接
        connection_string = (
            f"mssql+pyodbc://{DB_CONFIG['username']}:{DB_CONFIG['password']}"
            f"@{DB_CONFIG['server']}/{DB_CONFIG['database']}"
            f"?driver={DB_CONFIG['driver']}"
        )
        
        logger.info(f"Connecting to database: {DB_CONFIG['server']}/{DB_CONFIG['database']}")
        engine = create_engine(connection_string, echo=False)
        
        with engine.connect() as conn:
            # 先测试查询，获取数据量
            logger.info("Querying data from last 6 months...")
            count_sql = """
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
            """
            result = conn.execute(text(count_sql))
            count = result.fetchone()[0]
            logger.info(f"Found {count} records from last 3 years")
            
            if count == 0:
                logger.warning("No data found for last 6 months, table will be empty")
            
            # 尝试在 SQL Server 创建表
            try:
                # 检查表是否已存在
                check_table_sql = """
                SELECT COUNT(*) as table_count
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_NAME = 'TR_Report'
                """
                result = conn.execute(text(check_table_sql))
                table_exists = result.fetchone()[0] > 0
                
                if table_exists:
                    logger.warning("TR_Report table already exists, will drop it first")
                    conn.execute(text("DROP TABLE TR_Report"))
                    conn.commit()
                    logger.info("Old table dropped")
                
                # 创建表结构
                logger.info("Creating table structure in SQL Server...")
                create_table_sql = """
                CREATE TABLE TR_Report (
                    jobsite_no INT,
                    jobsite NVARCHAR(255),
                    order_no INT,
                    order_describution NVARCHAR(MAX),
                    client NVARCHAR(255),
                    del_date DATE,
                    ref_no NVARCHAR(255),
                    bbs_po_no NVARCHAR(255),
                    jobsite_type NVARCHAR(50),
                    diameter NVARCHAR(50),
                    wt_ton DECIMAL(18, 5),
                    product NVARCHAR(MAX),
                    grade NVARCHAR(255),
                    pattern NVARCHAR(255),
                    mill_cert NVARCHAR(MAX),
                    test_cert1 NVARCHAR(MAX),
                    test_cert2 NVARCHAR(MAX),
                    supplier NVARCHAR(255),
                    stockist_cert NVARCHAR(MAX),
                    po_no NVARCHAR(255)
                )
                """
                conn.execute(text(create_table_sql))
                conn.commit()
                logger.info("Table structure created successfully in SQL Server")
                
                # 插入数据
                logger.info("Inserting data...")
                insert_sql = """
                INSERT INTO TR_Report
                SELECT
                    pp.id_obra AS jobsite_no, 
                    js.nombre AS jobsite, 
                    pp.id_pedido_produccion AS order_no, 
                    pp.descripcion AS order_describution,
                    js.arquitecto AS client,
                    pp.fecha_entrega_prevista AS del_date,
                    pp.referencia_1 AS ref_no,
                    pp.referencia_2 AS bbs_po_no,
                    tls.jobsite_type,
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
                    tld.po_no
                FROM tr_line_size tls
                LEFT JOIN tr_line_detail tld
                    ON tls.bbs_no = tld.bbs_no
                    AND tls.diameter = tld.diameter
                JOIN pedidos_produccion pp
                    ON pp.ID_PEDIDO_PRODUCCION = tls.bbs_no
                JOIN obras js
                    ON js.ID_OBRA = tls.jobsite_no
                WHERE pp.fecha_entrega_prevista >= DATEADD(MONTH, -36, GETDATE())
                """
                conn.execute(text(insert_sql))
                conn.commit()
                logger.info("Data inserted successfully")
                
                # 验证数据
                verify_sql = "SELECT COUNT(*) as record_count FROM TR_Report"
                result = conn.execute(text(verify_sql))
                final_count = result.fetchone()[0]
                logger.info(f"TR_Report table created successfully in SQL Server with {final_count} records")
                
                # 显示统计信息
                stats_sql = """
                SELECT 
                    MIN(del_date) as earliest_date,
                    MAX(del_date) as latest_date,
                    COUNT(DISTINCT order_no) as unique_orders,
                    COUNT(DISTINCT jobsite_no) as unique_jobsites
                FROM TR_Report
                """
                result = conn.execute(text(stats_sql))
                stats = result.fetchone()
                logger.info("=" * 60)
                logger.info("Table Statistics:")
                logger.info(f"  Earliest date: {stats[0]}")
                logger.info(f"  Latest date: {stats[1]}")
                logger.info(f"  Unique orders: {stats[2]}")
                logger.info(f"  Unique jobsites: {stats[3]}")
                logger.info("=" * 60)
                
                return True, final_count
                
            except Exception as create_error:
                if "permission denied" in str(create_error).lower() or "CREATE TABLE permission" in str(create_error):
                    logger.warning("No permission to create table in SQL Server, creating in SQLite instead...")
                    return create_tr_report_table_sqlite(conn, count)
                else:
                    raise
            
    except Exception as e:
        logger.error(f"Failed to create TR_Report table: {e}")
        import traceback
        traceback.print_exc()
        return False, str(e)

def create_tr_report_table_sqlite(mssql_conn, expected_count):
    """在 SQLite 中创建 TR_Report 表（当 SQL Server 没有权限时）"""
    import sqlite3
    import pandas as pd
    
    logger = logging.getLogger(__name__)
    
    try:
        # SQLite 数据库路径
        sqlite_db_path = os.path.join(os.path.dirname(__file__), 'data_3years.db')
        logger.info(f"Creating TR_Report table in SQLite: {sqlite_db_path}")
        
        # 查询数据
        query_sql = """
        SELECT
            pp.id_obra AS jobsite_no, 
            js.nombre AS jobsite, 
            pp.id_pedido_produccion AS order_no, 
            pp.descripcion AS order_describution,
            js.arquitecto AS client,
            pp.fecha_entrega_prevista AS del_date,
            pp.referencia_1 AS ref_no,
            pp.referencia_2 AS bbs_po_no,
            tls.jobsite_type,
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
            tld.po_no
        FROM tr_line_size tls
        LEFT JOIN tr_line_detail tld
            ON tls.bbs_no = tld.bbs_no
            AND tls.diameter = tld.diameter
        JOIN pedidos_produccion pp
            ON pp.ID_PEDIDO_PRODUCCION = tls.bbs_no
        JOIN obras js
            ON js.ID_OBRA = tls.jobsite_no
        WHERE pp.fecha_entrega_prevista >= DATEADD(MONTH, -6, GETDATE())
        ORDER BY pp.fecha_entrega_prevista DESC, pp.id_obra, pp.ID_PEDIDO_PRODUCCION, tls.diameter, tld.pattern
        """
        
        logger.info("Fetching data from SQL Server...")
        df = pd.read_sql(text(query_sql), mssql_conn)
        logger.info(f"Fetched {len(df)} records")
        
        # 连接到 SQLite
        sqlite_conn = sqlite3.connect(sqlite_db_path)
        
        # 如果表已存在，删除它
        cursor = sqlite_conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS TR_Report")
        sqlite_conn.commit()
        
        # 将数据写入 SQLite
        logger.info("Writing data to SQLite...")
        df.to_sql('TR_Report', sqlite_conn, if_exists='replace', index=False)
        sqlite_conn.commit()
        
        # 验证
        verify_count = pd.read_sql("SELECT COUNT(*) as cnt FROM TR_Report", sqlite_conn).iloc[0]['cnt']
        logger.info(f"TR_Report table created successfully in SQLite with {verify_count} records")
        
        # 统计信息
        stats = pd.read_sql("""
            SELECT 
                MIN(del_date) as earliest_date,
                MAX(del_date) as latest_date,
                COUNT(DISTINCT order_no) as unique_orders,
                COUNT(DISTINCT jobsite_no) as unique_jobsites
            FROM TR_Report
        """, sqlite_conn).iloc[0]
        
        logger.info("=" * 60)
        logger.info("Table Statistics:")
        logger.info(f"  Earliest date: {stats['earliest_date']}")
        logger.info(f"  Latest date: {stats['latest_date']}")
        logger.info(f"  Unique orders: {stats['unique_orders']}")
        logger.info(f"  Unique jobsites: {stats['unique_jobsites']}")
        logger.info("=" * 60)
        
        sqlite_conn.close()
        return True, verify_count
        
    except Exception as e:
        logger.error(f"Failed to create TR_Report table in SQLite: {e}")
        import traceback
        traceback.print_exc()
        return False, str(e)

if __name__ == "__main__":
    success, result = create_tr_report_table()
    if success:
        print(f"\nSuccess! TR_Report table created with {result} records")
        sys.exit(0)
    else:
        print(f"\nFailed! Error: {result}")
        sys.exit(1)

