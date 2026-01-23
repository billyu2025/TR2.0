#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建 TR_Report_Deduplication 表
从 TR_Report 表按 Order_No 去重生成
逻辑与 Orders_Deduplication 相同
"""

import os
import sys
import logging
import sqlite3
import pandas as pd
from datetime import datetime

# 配置日志
def setup_logging():
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, f'create_tr_report_deduplication_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

def create_tr_report_deduplication():
    """创建 TR_Report_Deduplication 表"""
    logger = setup_logging()
    
    try:
        logger.info("=" * 60)
        logger.info("Starting to create TR_Report_Deduplication table")
        logger.info("=" * 60)
        
        # SQLite 数据库路径
        sqlite_db_path = os.path.join(os.path.dirname(__file__), 'data_3years.db')
        
        if not os.path.exists(sqlite_db_path):
            logger.error(f"Database file not found: {sqlite_db_path}")
            return False, "Database file not found"
        
        logger.info(f"Connecting to SQLite database: {sqlite_db_path}")
        conn = sqlite3.connect(sqlite_db_path)
        
        # 检查 TR_Report 表是否存在
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='TR_Report'
        """)
        if not cursor.fetchone():
            logger.error("TR_Report table does not exist. Please create it first.")
            conn.close()
            return False, "TR_Report table does not exist"
        
        # 读取 TR_Report 表数据
        logger.info("Reading data from TR_Report table...")
        tr_report_df = pd.read_sql("SELECT * FROM TR_Report", conn)
        logger.info(f"Read {len(tr_report_df)} records from TR_Report")
        
        if tr_report_df.empty:
            logger.warning("TR_Report table is empty, TR_Report_Deduplication will also be empty")
        
        # 按 order_no 分组去重（与 Orders_Deduplication 相同的逻辑）
        logger.info("Grouping by order_no and aggregating...")
        grouped = tr_report_df.groupby('order_no').agg({
            'jobsite_no': 'first',
            'jobsite': 'first',
            'order_describution': 'first',
            'client': 'first',
            'del_date': 'first',
            'ref_no': 'first',
            'bbs_po_no': 'first',
            'jobsite_type': 'first',  # 已经是字符串（IAT/PRIVATE），不需要映射
            'wt_ton': 'sum',  # 累加重量
            'grade': 'first',
            # 材料级别的字段不需要保留在去重表中（因为这些是材料级别的数据）
        }).reset_index()
        
        # 重命名列以匹配 Orders_Deduplication 的命名风格
        grouped = grouped.rename(columns={
            'order_no': 'Order_No',
            'jobsite_no': 'Jobsite_No',
            'jobsite': 'Jobsite',
            'order_describution': 'Order_Description',
            'client': 'Client',
            'del_date': 'Del_Date',
            'ref_no': 'Ref_No',
            'bbs_po_no': 'PO_No',
            'jobsite_type': 'Jobsite_Type',
            'wt_ton': 'Wt',
            'grade': 'Grade'
        })
        
        logger.info(f"Aggregated to {len(grouped)} unique orders")
        
        # 按 Del_Date 降序排列（与 TR_Report 表保持一致）
        logger.info("Sorting by Del_Date DESC...")
        grouped = grouped.sort_values('Del_Date', ascending=False, na_position='last')
        
        # 如果表已存在，先删除
        cursor.execute("DROP TABLE IF EXISTS TR_Report_Deduplication")
        conn.commit()
        
        # 写入 SQLite 数据库
        logger.info("Writing to TR_Report_Deduplication table...")
        grouped.to_sql('TR_Report_Deduplication', conn, if_exists='replace', index=False)
        conn.commit()
        
        # 验证数据
        verify_count = pd.read_sql("SELECT COUNT(*) as cnt FROM TR_Report_Deduplication", conn).iloc[0]['cnt']
        logger.info(f"TR_Report_Deduplication table created successfully with {verify_count} records")
        
        # 显示统计信息
        stats = pd.read_sql("""
            SELECT 
                MIN(Del_Date) as earliest_date,
                MAX(Del_Date) as latest_date,
                COUNT(DISTINCT Order_No) as unique_orders,
                COUNT(DISTINCT Jobsite_No) as unique_jobsites,
                SUM(Wt) as total_weight,
                COUNT(DISTINCT Jobsite_Type) as unique_jobsite_types
            FROM TR_Report_Deduplication
        """, conn).iloc[0]
        
        logger.info("=" * 60)
        logger.info("Table Statistics:")
        logger.info(f"  Earliest date: {stats['earliest_date']}")
        logger.info(f"  Latest date: {stats['latest_date']}")
        logger.info(f"  Unique orders: {stats['unique_orders']}")
        logger.info(f"  Unique jobsites: {stats['unique_jobsites']}")
        logger.info(f"  Total weight: {stats['total_weight']:.2f} tons")
        logger.info(f"  Jobsite types: {stats['unique_jobsite_types']}")
        logger.info("=" * 60)
        
        conn.close()
        return True, verify_count
        
    except Exception as e:
        logger.error(f"Failed to create TR_Report_Deduplication table: {e}")
        import traceback
        traceback.print_exc()
        return False, str(e)

if __name__ == "__main__":
    success, result = create_tr_report_deduplication()
    if success:
        print(f"\nSuccess! TR_Report_Deduplication table created with {result} records")
        sys.exit(0)
    else:
        print(f"\nFailed! Error: {result}")
        sys.exit(1)

