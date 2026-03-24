#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成bbs_dd表到data_3years.db
功能：从SQL Server查询近3年数据，生成bbs_dd表
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
from db_adapter import DB_PATH, POSTGRES_DSN, is_postgres
warnings.filterwarnings('ignore')

# 配置日志
def setup_logging():
    """设置日志配置"""
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_filename = os.path.join(log_dir, f'bbs_dd_3years_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
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

class BBSDDGenerator3Years:
    """3年bbs_dd表生成器"""
    
    def __init__(self):
        self.logger = setup_logging()
        self.engine = None
        self.target_engine = None
        self.target_table_ref = 'bbs_dd'

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
                            WHERE table_schema = 'public' AND table_name = 'bbs_dd'
                        ) AS exists
                    """)
                ).mappings().first()
            else:
                row = conn.execute(
                    text("""
                        SELECT EXISTS (
                            SELECT 1 FROM sqlite_master
                            WHERE type='table' AND name='bbs_dd'
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
                self.target_engine = create_engine(POSTGRES_DSN, echo=False)
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
    
    def get_table_structure(self):
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
            self.logger.warning(f"无法获取表结构: {e}")
            return []
    
    def create_bbs_dd_table(self):
        """创建 bbs_dd 表 - 从 SQL Server 查询近3年的数据"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("开始创建 bbs_dd 表")
            self.logger.info("=" * 60)
            
            # 先获取表结构，查找日期字段
            date_columns = self.get_table_structure()
            
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
                    return False
                
                if not self.target_engine:
                    self.create_target_connection()

                with self.target_engine.begin() as target_conn:
                    if self._target_table_exists():
                        target_conn.execute(text(f"DELETE FROM {self.target_table_ref}"))
                        self.logger.info("已清空旧的 bbs_dd 表数据，保留现有结构和索引")
                    else:
                        self.logger.info("bbs_dd 表不存在，将按 DataFrame 结构创建")

                self.logger.info(f"写入数据到 {'PostgreSQL' if is_postgres() else 'SQLite'}...")
                df.to_sql('bbs_dd', self.target_engine, if_exists='append', index=False, method='multi', chunksize=1000)
                
                verify_count = pd.read_sql("SELECT COUNT(*) as cnt FROM bbs_dd", self.target_engine).iloc[0]['cnt']
                self.logger.info(f"✅ bbs_dd 表创建成功: {verify_count:,} 条记录")
                
                # 显示表的前几列信息
                self.logger.info("=" * 60)
                self.logger.info("表信息:")
                self.logger.info(f"  总记录数: {verify_count:,}")
                if date_columns:
                    stats = pd.read_sql(f"""
                        SELECT 
                            MIN({date_columns[0]}) as earliest_date,
                            MAX({date_columns[0]}) as latest_date
                        FROM bbs_dd
                    """, self.target_engine).iloc[0]
                    self.logger.info(f"  最早日期: {stats['earliest_date']}")
                    self.logger.info(f"  最晚日期: {stats['latest_date']}")
                self.logger.info("=" * 60)
                
                return True
                
        except Exception as e:
            self.logger.error(f"❌ 创建 bbs_dd 表失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def run_generation(self):
        """执行完整生成流程"""
        start_time = datetime.now()
        self.logger.info("=" * 60)
        self.logger.info("开始 bbs_dd 表生成流程（3年数据）")
        self.logger.info(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M%S')}")
        self.logger.info("=" * 60)
        
        try:
            # 1. 连接源数据库
            if not self.create_database_connection():
                raise Exception("无法连接源数据库")
            
            # 2. 连接目标数据库
            if not self.create_target_connection():
                raise Exception("无法连接目标数据库")
            
            # 3. 创建bbs_dd表
            if self.create_bbs_dd_table():
                self.logger.info("🎉 bbs_dd 表生成成功！")
            else:
                raise Exception("bbs_dd 表生成失败")
            
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
            self.logger.info("bbs_dd 表生成流程结束")
            self.logger.info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M%S')}")
            self.logger.info("=" * 60)

def main():
    """主函数"""
    generator = BBSDDGenerator3Years()
    generator.run_generation()

if __name__ == "__main__":
    main()

