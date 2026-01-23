#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成TR_Report表到data_3years.db
功能：从SQL Server查询近3年数据，生成TR_Report表
作者：TR Report System
日期：2025-12-16
"""

import pandas as pd
import numpy as np
import sqlite3
import logging
import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import pyodbc
import warnings
warnings.filterwarnings('ignore')

# 配置日志
def setup_logging():
    """设置日志配置"""
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_filename = os.path.join(log_dir, f'tr_report_3years_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

# 数据库配置
DB_CONFIG = {
    'server': '192.168.80.242',
    'database': 'TVSC',
    'username': 'reportuser',
    'password': 'HKSHA123',
    'driver': 'SQL Server'
}

# SQLite数据库配置 - 指向data_3years.db
SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), 'TR database', 'data_3years.db')

class TRReportGenerator3Years:
    """3年TR_Report表生成器"""
    
    def __init__(self):
        self.logger = setup_logging()
        self.engine = None
        self.sqlite_conn = None
        
    def create_database_connection(self):
        """创建源数据库连接"""
        try:
            connection_string = f"mssql+pyodbc://{DB_CONFIG['username']}:{DB_CONFIG['password']}@{DB_CONFIG['server']}/{DB_CONFIG['database']}?driver={DB_CONFIG['driver']}"
            self.engine = create_engine(connection_string, echo=False)
            
            # 测试连接
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
            # 确保目录存在
            db_dir = os.path.dirname(SQLITE_DB_PATH)
            if not os.path.exists(db_dir):
                os.makedirs(db_dir)
            
            self.sqlite_conn = sqlite3.connect(SQLITE_DB_PATH, timeout=30.0)
            # 启用 WAL 模式以提高并发性能
            self.sqlite_conn.execute("PRAGMA journal_mode=WAL")
            self.sqlite_conn.execute("PRAGMA synchronous=NORMAL")
            self.sqlite_conn.execute("PRAGMA busy_timeout=30000")
            self.logger.info(f"✅ SQLite数据库连接成功（WAL模式）: {SQLITE_DB_PATH}")
            return True
        except Exception as e:
            self.logger.error(f"❌ SQLite数据库连接失败: {e}")
            return False
    
    def create_tr_report_table(self):
        """创建 TR_Report 表 - 从 SQL Server 查询近3年的数据"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("开始创建 TR_Report 表")
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
                
                return True
                
        except Exception as e:
            self.logger.error(f"❌ 创建 TR_Report 表失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def run_generation(self):
        """执行完整生成流程"""
        start_time = datetime.now()
        self.logger.info("=" * 60)
        self.logger.info("开始 TR_Report 表生成流程（3年数据）")
        self.logger.info(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 60)
        
        try:
            # 1. 连接源数据库
            if not self.create_database_connection():
                raise Exception("无法连接源数据库")
            
            # 2. 连接SQLite数据库
            if not self.create_sqlite_connection():
                raise Exception("无法连接SQLite数据库")
            
            # 3. 创建TR_Report表
            if self.create_tr_report_table():
                self.logger.info("🎉 TR_Report 表生成成功！")
            else:
                raise Exception("TR_Report 表生成失败")
            
            # 4. 计算执行时间
            end_time = datetime.now()
            duration = end_time - start_time
            self.logger.info(f"执行时间: {duration}")
            
        except Exception as e:
            self.logger.error(f"❌ 生成流程失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        
        finally:
            # 关闭连接
            if self.engine:
                self.engine.dispose()
            if self.sqlite_conn:
                self.sqlite_conn.close()
            
            self.logger.info("=" * 60)
            self.logger.info("TR_Report 表生成流程结束")
            self.logger.info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info("=" * 60)

def main():
    """主函数"""
    generator = TRReportGenerator3Years()
    generator.run_generation()

if __name__ == "__main__":
    main()

