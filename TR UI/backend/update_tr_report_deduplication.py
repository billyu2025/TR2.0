#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新TR_Report_Deduplication表
功能：从TR_Report表按Order_No去重生成TR_Report_Deduplication表
作者：TR Report System
日期：2025-12-16
"""

import pandas as pd
import sqlite3
import logging
import os
import sys
from datetime import datetime

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

# SQLite数据库配置 - 指向data_3years.db
SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), 'TR database', 'data_3years.db')

class TRReportDeduplicationUpdater:
    """TR_Report_Deduplication表更新器"""
    
    def __init__(self):
        self.logger = setup_logging()
        self.sqlite_conn = None
        
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
    
    def create_tr_report_deduplication(self):
        """创建 TR_Report_Deduplication 表 - 从 TR_Report 表按 Order_No 去重生成"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("开始创建 TR_Report_Deduplication 表")
            self.logger.info("=" * 60)
            
            # 检查 TR_Report 表是否存在
            cursor = self.sqlite_conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='TR_Report'
            """)
            if not cursor.fetchone():
                self.logger.error("❌ TR_Report 表不存在，请先创建 TR_Report 表")
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
            # 1. 连接SQLite数据库
            if not self.create_sqlite_connection():
                raise Exception("无法连接SQLite数据库")
            
            # 2. 创建TR_Report_Deduplication表
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
            # 关闭连接
            if self.sqlite_conn:
                self.sqlite_conn.close()
            
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

