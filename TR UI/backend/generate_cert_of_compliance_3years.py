#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sync cert_of_compliance from SQL Server (last 3 years) to PostgreSQL/SQLite.
Source: TVSC.dbo.cert_of_compliance, filtered by del_date >= DATEADD(MONTH, -36, GETDATE())
"""

import logging
import os
import sys
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text

from db_adapter import DB_PATH, POSTGRES_DSN, is_postgres, sqlalchemy_postgres_dsn, coerce_dataframe_date_columns

warnings_import = __import__('warnings')
warnings_import.filterwarnings('ignore')


def setup_logging():
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_filename = os.path.join(
        log_dir, f'cert_of_compliance_3years_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    )
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger(__name__)


DB_CONFIG = {
    'server': os.getenv('SQL_SERVER', '192.168.80.242'),
    'database': os.getenv('SQL_DATABASE', 'TVSC'),
    'username': os.getenv('SQL_USERNAME', 'reportuser'),
    'password': os.getenv('SQL_PASSWORD', 'HKSHA123'),
    'driver': 'SQL Server',
}


class CertOfComplianceGenerator3Years:
    def __init__(self):
        self.logger = setup_logging()
        self.engine = None
        self.target_engine = None
        self.target_table_ref = 'cert_of_compliance'

    def _target_table_exists(self) -> bool:
        if not self.target_engine:
            return False
        with self.target_engine.connect() as conn:
            if is_postgres():
                row = conn.execute(
                    text("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema = 'public' AND table_name = 'cert_of_compliance'
                        ) AS exists
                    """)
                ).mappings().first()
            else:
                row = conn.execute(
                    text("""
                        SELECT EXISTS (
                            SELECT 1 FROM sqlite_master
                            WHERE type='table' AND name='cert_of_compliance'
                        ) AS exists
                    """)
                ).mappings().first()
            return bool(row['exists']) if row else False

    def create_database_connection(self):
        try:
            cs = (
                f"mssql+pyodbc://{DB_CONFIG['username']}:{DB_CONFIG['password']}"
                f"@{DB_CONFIG['server']}/{DB_CONFIG['database']}?driver={DB_CONFIG['driver']}"
            )
            self.engine = create_engine(cs, echo=False)
            with self.engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            self.logger.info('Source database connection OK')
            return True
        except Exception as e:
            self.logger.error(f'Source database connection failed: {e}')
            return False

    def _ensure_target_table(self):
        ddl = text("""
            CREATE TABLE IF NOT EXISTS cert_of_compliance (
                shipping_no BIGINT NOT NULL PRIMARY KEY,
                del_date DATE NOT NULL,
                jobsite_no BIGINT NOT NULL,
                jobsite_name TEXT,
                del_address TEXT,
                asd_contract_no1 TEXT,
                asd_contract_no2 TEXT,
                work_order_no TEXT,
                client_name TEXT,
                main_contractor TEXT,
                bbs_no_list TEXT
            )
        """)
        idx1 = text(
            'CREATE INDEX IF NOT EXISTS idx_cert_of_compliance_del_date '
            'ON cert_of_compliance(del_date DESC)'
        )
        idx2 = text(
            'CREATE INDEX IF NOT EXISTS idx_cert_of_compliance_jobsite_no '
            'ON cert_of_compliance(jobsite_no)'
        )
        with self.target_engine.begin() as conn:
            conn.execute(ddl)
            conn.execute(idx1)
            conn.execute(idx2)

    def create_target_connection(self):
        try:
            if is_postgres():
                if not POSTGRES_DSN:
                    raise RuntimeError('POSTGRES_DSN is not configured')
                self.target_engine = create_engine(sqlalchemy_postgres_dsn(), echo=False)
                with self.target_engine.connect() as conn:
                    conn.execute(text('SELECT 1'))
                self._ensure_target_table()
                self.logger.info('PostgreSQL target connection OK')
            else:
                db_dir = os.path.dirname(DB_PATH)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir)
                self.target_engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
                with self.target_engine.connect() as conn:
                    conn.execute(text('SELECT 1'))
                self._ensure_target_table()
                self.logger.info(f'SQLite target connection OK: {DB_PATH}')
            return True
        except Exception as e:
            self.logger.error(f'Target database connection failed: {e}')
            return False

    def sync_cert_of_compliance_table(self):
        try:
            self.logger.info('=' * 60)
            self.logger.info('Sync cert_of_compliance (last 3 years)')
            self.logger.info('=' * 60)

            count_sql = text("""
                SELECT COUNT(*) AS record_count
                FROM dbo.cert_of_compliance
                WHERE del_date >= DATEADD(MONTH, -36, GETDATE())
            """)
            query_sql = text("""
                SELECT
                    shipping_no,
                    del_date,
                    jobsite_no,
                    jobsite_name,
                    del_address,
                    asd_contract_no1,
                    asd_contract_no2,
                    work_order_no,
                    client_name,
                    main_contractor,
                    bbs_no_list
                FROM dbo.cert_of_compliance
                WHERE del_date >= DATEADD(MONTH, -36, GETDATE())
            """)

            with self.engine.connect() as conn:
                count = conn.execute(count_sql).scalar()
                self.logger.info(f'Rows to sync from SQL Server: {count:,}')
                if count == 0:
                    self.logger.warning('No rows in last 36 months')
                    return False
                df = pd.read_sql(query_sql, conn)
                self.logger.info(f'Fetched {len(df):,} rows')

            if df.empty:
                return False

            if not self.target_engine:
                self.create_target_connection()

            if is_postgres():
                df = coerce_dataframe_date_columns(df)

            with self.target_engine.begin() as target_conn:
                target_conn.execute(text(f'DELETE FROM {self.target_table_ref}'))
                self.logger.info('Cleared existing cert_of_compliance rows')
                df.to_sql(
                    self.target_table_ref,
                    target_conn,
                    if_exists='append',
                    index=False,
                    method='multi',
                    chunksize=1000,
                )

            verify_count = pd.read_sql(
                f'SELECT COUNT(*) AS cnt FROM {self.target_table_ref}',
                self.target_engine,
            ).iloc[0]['cnt']
            self.logger.info(f'cert_of_compliance sync OK: {verify_count:,} rows')

            stats = pd.read_sql(
                f"""
                SELECT MIN(del_date) AS earliest_date, MAX(del_date) AS latest_date
                FROM {self.target_table_ref}
                """,
                self.target_engine,
            ).iloc[0]
            self.logger.info(f"  Date range: {stats['earliest_date']} .. {stats['latest_date']}")
            return True

        except Exception as e:
            self.logger.error(f'cert_of_compliance sync failed: {e}')
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    def run_generation(self):
        start_time = datetime.now()
        self.logger.info('=' * 60)
        self.logger.info('cert_of_compliance sync started')
        self.logger.info(f'Start: {start_time.strftime("%Y-%m-%d %H:%M:%S")}')
        self.logger.info('=' * 60)
        try:
            if not self.create_database_connection():
                raise RuntimeError('Cannot connect to source database')
            if not self.create_target_connection():
                raise RuntimeError('Cannot connect to target database')
            if not self.sync_cert_of_compliance_table():
                raise RuntimeError('cert_of_compliance sync failed')
            self.logger.info(f'Duration: {datetime.now() - start_time}')
        except Exception as e:
            self.logger.error(f'Sync flow failed: {e}')
            import traceback
            self.logger.error(traceback.format_exc())
            raise
        finally:
            if self.engine:
                self.engine.dispose()
            if self.target_engine:
                self.target_engine.dispose()
            self.logger.info('cert_of_compliance sync ended')


def main():
    CertOfComplianceGenerator3Years().run_generation()


if __name__ == '__main__':
    main()
