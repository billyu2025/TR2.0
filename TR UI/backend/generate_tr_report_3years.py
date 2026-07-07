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
import logging
import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import pyodbc
import warnings
from db_adapter import DB_PATH, POSTGRES_DSN, is_postgres, sqlalchemy_postgres_dsn, coerce_dataframe_date_columns
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

class TRReportGenerator3Years:
    """3年TR_Report表生成器"""
    
    def __init__(self):
        self.logger = setup_logging()
        self.engine = None
        self.target_engine = None
        self.target_table_ref = '"TR_Report"' if is_postgres() else 'TR_Report'

    def _target_table_exists(self) -> bool:
        if not self.target_engine:
            return False
        with self.target_engine.connect() as conn:
            if is_postgres():
                row = conn.execute(
                    text("""
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = 'public' AND table_name = 'TR_Report'
                        ) AS exists
                    """)
                ).mappings().first()
            else:
                row = conn.execute(
                    text("""
                        SELECT EXISTS (
                            SELECT 1 FROM sqlite_master
                            WHERE type='table' AND name='TR_Report'
                        ) AS exists
                    """)
                ).mappings().first()
            return bool(row['exists']) if row else False
        
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
    
    def create_target_connection(self):
        """创建目标数据库连接"""
        try:
            if is_postgres():
                if not POSTGRES_DSN:
                    raise RuntimeError("POSTGRES_DSN 未配置")
                self.target_engine = create_engine(sqlalchemy_postgres_dsn(), echo=False)
                with self.target_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                self.logger.info("✅ PostgreSQL目标数据库连接成功")
            else:
                db_dir = os.path.dirname(DB_PATH)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir)
                self.target_engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
                with self.target_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                self.logger.info(f"✅ SQLite目标数据库连接成功: {DB_PATH}")
            return True
        except Exception as e:
            self.logger.error(f"❌ 目标数据库连接失败: {e}")
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
                self.logger.info(f"找到 {count:,} 条近3年的记录")
                
                if count == 0:
                    self.logger.warning("⚠️ 近3年没有数据，表将为空")
                
                # 查询数据
                self.logger.info("从 SQL Server 获取数据...")
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
                
                df = pd.read_sql(query_sql, conn)
                self.logger.info(f"获取了 {len(df):,} 条记录")
                
                if len(df) == 0:
                    self.logger.warning("⚠️ 没有获取到数据")
                    return False
                
                if not self.target_engine:
                    self.create_target_connection()

                if is_postgres():
                    df = coerce_dataframe_date_columns(df)

                with self.target_engine.begin() as target_conn:
                    if self._target_table_exists():
                        target_conn.execute(text(f"DELETE FROM {self.target_table_ref}"))
                        self.logger.info("已清空旧的 TR_Report 表数据，保留现有结构和索引")
                    else:
                        self.logger.info("TR_Report 表不存在，将按 DataFrame 结构创建")

                    self.logger.info(f"写入数据到 {'PostgreSQL' if is_postgres() else 'SQLite'}...")
                    df.to_sql(
                        'TR_Report',
                        target_conn,
                        if_exists='append',
                        index=False,
                        method='multi',
                        chunksize=1000,
                    )

                verify_count = pd.read_sql(f"SELECT COUNT(*) as cnt FROM {self.target_table_ref}", self.target_engine).iloc[0]['cnt']
                self.logger.info(f"✅ TR_Report 表创建成功: {verify_count:,} 条记录")
                
                # 统计信息（使用正确的表名和列名引用）
                if is_postgres():
                    stats_query = f"""
                        SELECT 
                            MIN("del_date") as earliest_date,
                            MAX("del_date") as latest_date,
                            COUNT(DISTINCT "order_no") as unique_orders,
                            COUNT(DISTINCT "Job_No") as unique_jobsites
                        FROM {self.target_table_ref}
                    """
                else:
                    stats_query = """
                    SELECT 
                        MIN(del_date) as earliest_date,
                        MAX(del_date) as latest_date,
                        COUNT(DISTINCT order_no) as unique_orders,
                        COUNT(DISTINCT Job_No) as unique_jobsites
                    FROM TR_Report
                    """
                stats = pd.read_sql(stats_query, self.target_engine).iloc[0]
                
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
            
            # 2. 连接目标数据库
            if not self.create_target_connection():
                raise Exception("无法连接目标数据库")
            
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
            if self.target_engine:
                self.target_engine.dispose()
            
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

