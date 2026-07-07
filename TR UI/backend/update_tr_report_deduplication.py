#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新TR_Report_Deduplication表
功能：从TR_Report表按Order_No去重生成TR_Report_Deduplication表
作者：TR Report System
日期：2025-12-16
"""

import pandas as pd
import logging
import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text

from db_adapter import DB_PATH, POSTGRES_DSN, is_postgres, sqlalchemy_postgres_dsn

# 配置日志
def setup_logging():
    """设置日志配置"""
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_filename = os.path.join(log_dir, f'tr_report_deduplication_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

class TRReportDeduplicationUpdater:
    """TR_Report_Deduplication表更新器"""
    
    def __init__(self):
        self.logger = setup_logging()
        self.engine = None
        self.table_tr_report = '"TR_Report"' if is_postgres() else 'TR_Report'
        self.table_dedup = '"TR_Report_Deduplication"' if is_postgres() else 'TR_Report_Deduplication'
        
    def create_connection(self):
        """创建数据库连接"""
        try:
            if is_postgres():
                if not POSTGRES_DSN:
                    raise RuntimeError("POSTGRES_DSN 未配置")
                self.engine = create_engine(sqlalchemy_postgres_dsn())
                self.logger.info("✅ PostgreSQL 数据库连接成功")
            else:
                db_dir = os.path.dirname(DB_PATH)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir)
                self.engine = create_engine(f"sqlite:///{DB_PATH}")
                self.logger.info(f"✅ SQLite数据库连接成功: {DB_PATH}")
            return True
        except Exception as e:
            self.logger.error(f"❌ 数据库连接失败: {e}")
            return False

    def _table_exists(self, conn, table_name: str) -> bool:
        if is_postgres():
            # PostgreSQL: 使用 pg_tables 查询，正确处理带引号的表名
            result = conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_tables
                        WHERE schemaname = 'public' AND tablename = :table_name
                    ) AS exists
                """),
                {"table_name": table_name}
            ).mappings().first()
            return bool(result["exists"]) if result else False
        result = conn.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name=:table_name
                ) AS exists
            """),
            {"table_name": table_name}
        ).mappings().first()
        return bool(result["exists"]) if result else False

    def _normalize_records(self, grouped_df):
        grouped_df = grouped_df.where(pd.notna(grouped_df), None)
        records = []
        for row in grouped_df.to_dict(orient='records'):
            records.append({
                "Order_No": row.get("Order_No"),
                "Job_No": row.get("Job_No"),
                "Jobsite": row.get("Jobsite"),
                "Order_Description": row.get("Order_Description"),
                "Client": row.get("Client"),
                "Del_Date": row.get("Del_Date"),
                "Ref_No": row.get("Ref_No"),
                "PO_No": row.get("PO_No"),
                "Jobsite_Type": row.get("Jobsite_Type"),
                "Wt": row.get("Wt"),
                "Grade": row.get("Grade"),
                "rm_dn_no": row.get("rm_dn_no"),
            })
        return records
    
    def create_tr_report_deduplication(self):
        """创建 TR_Report_Deduplication 表 - 从 TR_Report 表按 Order_No 去重生成"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("开始创建 TR_Report_Deduplication 表")
            self.logger.info("=" * 60)
            
            with self.engine.begin() as conn:
                if not self._table_exists(conn, 'TR_Report'):
                    self.logger.error("❌ TR_Report 表不存在，请先创建 TR_Report 表")
                    return False
                
                self.logger.info("从 TR_Report 表读取数据...")
                tr_report_df = pd.read_sql_query(f"SELECT * FROM {self.table_tr_report}", conn)
                self.logger.info(f"从 TR_Report 读取了 {len(tr_report_df):,} 条记录")
            
                if tr_report_df.empty:
                    self.logger.warning("⚠️ TR_Report 表为空，TR_Report_Deduplication 也将为空")
            
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
                    'wt_ton': 'sum',
                    'grade': 'first',
                    'rm_dn_no': 'first',
                }).reset_index()
            
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
            
                self.logger.info(f"聚合为 {len(grouped):,} 个唯一订单")
            
                self.logger.info("按 Del_Date 降序排列...")
                grouped = grouped.sort_values('Del_Date', ascending=False, na_position='last')

                conn.execute(text(f"DROP TABLE IF EXISTS {self.table_dedup}"))
                if is_postgres():
                    conn.execute(text(f"""
                        CREATE TABLE {self.table_dedup} (
                            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                            "Order_No" BIGINT NOT NULL,
                            "Job_No" TEXT,
                            "Jobsite" TEXT,
                            "Order_Description" TEXT,
                            "Client" TEXT,
                            "Del_Date" DATE,
                            "Ref_No" TEXT,
                            "PO_No" TEXT,
                            "Jobsite_Type" TEXT,
                            "Wt" DOUBLE PRECISION,
                            "Grade" TEXT,
                            "rm_dn_no" TEXT
                        )
                    """))
                else:
                    conn.execute(text(f"""
                        CREATE TABLE {self.table_dedup} (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            "Order_No" INTEGER NOT NULL,
                            "Job_No" TEXT,
                            "Jobsite" TEXT,
                            "Order_Description" TEXT,
                            "Client" TEXT,
                            "Del_Date" TEXT,
                            "Ref_No" TEXT,
                            "PO_No" TEXT,
                            "Jobsite_Type" TEXT,
                            "Wt" REAL,
                            "Grade" TEXT,
                            "rm_dn_no" TEXT
                        )
                    """))
                self.logger.info("已删除并重建 TR_Report_Deduplication 表")

                records = self._normalize_records(grouped)
                if records:
                    conn.execute(
                        text(f"""
                            INSERT INTO {self.table_dedup} (
                                "Order_No", "Job_No", "Jobsite", "Order_Description", "Client",
                                "Del_Date", "Ref_No", "PO_No", "Jobsite_Type", "Wt", "Grade", "rm_dn_no"
                            ) VALUES (
                                :Order_No, :Job_No, :Jobsite, :Order_Description, :Client,
                                :Del_Date, :Ref_No, :PO_No, :Jobsite_Type, :Wt, :Grade, :rm_dn_no
                            )
                        """),
                        records
                    )

                verify_count = conn.execute(
                    text(f'SELECT COUNT(*) AS cnt FROM {self.table_dedup}')
                ).mappings().first()['cnt']
                self.logger.info(f"✅ TR_Report_Deduplication 表创建成功: {verify_count:,} 条记录")

                stats = conn.execute(
                    text(f"""
                        SELECT 
                            MIN("Del_Date") as earliest_date,
                            MAX("Del_Date") as latest_date,
                            COUNT(DISTINCT "Order_No") as unique_orders,
                            COUNT(DISTINCT "Job_No") as unique_jobsites,
                            SUM("Wt") as total_weight,
                            COUNT(DISTINCT "Jobsite_Type") as unique_jobsite_types
                        FROM {self.table_dedup}
                    """)
                ).mappings().first()
            
            self.logger.info("=" * 60)
            self.logger.info("表统计信息:")
            self.logger.info(f"  最早日期: {stats['earliest_date']}")
            self.logger.info(f"  最晚日期: {stats['latest_date']}")
            self.logger.info(f"  唯一订单数: {stats['unique_orders']:,}")
            self.logger.info(f"  唯一工地数: {stats['unique_jobsites']:,}")
            self.logger.info(f"  总重量: {stats['total_weight']:.2f} 吨")
            self.logger.info(f"  工地类型数: {stats['unique_jobsite_types']}")
            self.logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 创建 TR_Report_Deduplication 表失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def run_update(self):
        """执行完整更新流程"""
        start_time = datetime.now()
        self.logger.info("=" * 60)
        self.logger.info("开始 TR_Report_Deduplication 表更新流程")
        self.logger.info(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 60)
        
        try:
            if not self.create_connection():
                raise Exception("无法连接数据库")
            
            if self.create_tr_report_deduplication():
                self.logger.info("🎉 TR_Report_Deduplication 表更新成功！")
            else:
                raise Exception("TR_Report_Deduplication 表更新失败")
            
            # 3. 计算执行时间
            end_time = datetime.now()
            duration = end_time - start_time
            self.logger.info(f"执行时间: {duration}")
            
        except Exception as e:
            self.logger.error(f"❌ 更新流程失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        
        finally:
            if self.engine:
                self.engine.dispose()
            
            self.logger.info("=" * 60)
            self.logger.info("TR_Report_Deduplication 表更新流程结束")
            self.logger.info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info("=" * 60)

def main():
    """主函数"""
    updater = TRReportDeduplicationUpdater()
    updater.run_update()

if __name__ == "__main__":
    main()

