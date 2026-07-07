#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Database adapter with SQLite/PostgreSQL switch support."""

from __future__ import annotations

import os
import sqlite3
import threading


_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# SQLite 数据库位置：C:\TR-master\TR database\data_3years.db
# 尝试两个可能的位置
_default_db_path_ui = os.path.join(_project_root, "TR database", "data_3years.db")
_default_db_path_root = os.path.join(os.path.dirname(_project_root), "TR database", "data_3years.db")
# 优先使用根目录下的路径（C:\TR-master\TR database\data_3years.db）
_default_db_path = _default_db_path_root if os.path.exists(_default_db_path_root) else _default_db_path_ui

DB_BACKEND = os.getenv("DB_BACKEND", "postgres").strip().lower()
DB_PATH = os.getenv("DB_PATH", _default_db_path)
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@127.0.0.1:5432/tr_db").strip()


def sqlalchemy_postgres_dsn(dsn: str | None = None) -> str:
    """SQLAlchemy 需 postgresql+psycopg://；psycopg(v3) 直连仍可用 postgresql://。"""
    raw = (dsn or POSTGRES_DSN).strip()
    if not raw:
        return raw
    if "+" in raw.split("://", 1)[0]:
        return raw
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw[len("postgresql://") :]
    if raw.startswith("postgres://"):
        return "postgresql+psycopg://" + raw[len("postgres://") :]
    return raw


def coerce_dataframe_date_columns(df, columns=None):
    """将 DataFrame 日期列转为 date，避免 PostgreSQL DATE 列插入 varchar 失败。"""
    import pandas as pd

    if columns is None:
        columns = [
            c
            for c in df.columns
            if c.lower().endswith("_date")
            or c.lower() in ("del_date", "delivery_date", "dd_delivery_date")
        ]
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.date
    return out


if DB_PATH and not os.path.isabs(DB_PATH):
    DB_PATH = os.path.abspath(os.path.join(_project_root, DB_PATH))

_pg_pool = None
_pg_pool_lock = threading.Lock()


def get_db_backend() -> str:
    return DB_BACKEND


def is_postgres() -> bool:
    return DB_BACKEND == "postgres"


def is_sqlite() -> bool:
    return DB_BACKEND != "postgres"


def _create_sqlite_connection():
    # Ensure the database directory exists
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Failed to create database directory: {db_dir}, error: {e}")
    
    # Create database file if it doesn't exist
    if not os.path.exists(DB_PATH):
        # Create an empty database file
        try:
            open(DB_PATH, 'a').close()
        except Exception as e:
            raise RuntimeError(f"Failed to create database file: {DB_PATH}, error: {e}")
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA optimize")
    except Exception:
        pass
    return conn


def _create_postgres_connection():
    if not POSTGRES_DSN:
        raise RuntimeError("POSTGRES_DSN is required when DB_BACKEND=postgres")

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "psycopg is not installed. Run: pip install psycopg[binary] psycopg-pool"
        ) from exc

    conn = psycopg.connect(POSTGRES_DSN, row_factory=dict_row)
    conn.autocommit = False
    # 设置事务隔离级别为 READ COMMITTED（默认值，但明确设置以确保一致性）
    # 这确保每个查询都能看到已提交的数据
    try:
        conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
    except Exception:
        pass  # 如果设置失败，使用默认值
    return conn


class _PooledPostgresConnection:
    """Wrap psycopg pooled connections so close() returns them to the pool."""

    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        self._closed = False
        # 确保连接使用 READ COMMITTED 隔离级别（能看到已提交的数据）
        # 并且回滚任何未提交的事务，确保看到最新的已提交数据
        try:
            conn.rollback()  # 回滚任何未提交的事务
            # 设置事务隔离级别为 READ COMMITTED（PostgreSQL 默认值，但明确设置以确保一致性）
            # 注意：这需要在每个事务开始时设置，但 PostgreSQL 默认就是 READ COMMITTED
            # 所以这里主要是确保回滚未提交的事务
            # 强制刷新连接状态，确保能看到最新的已提交数据
            with conn.cursor() as cur:
                cur.execute("SELECT 1")  # 执行一个简单查询，确保连接是活跃的
        except Exception:
            pass  # 如果设置失败，使用默认值

    def __getattr__(self, name):
        if self._closed:
            raise RuntimeError("Connection already closed")
        return getattr(self._conn, name)

    def close(self):
        if self._closed:
            return
        try:
            try:
                # 回滚任何未提交的事务，确保连接池中的连接是干净的
                self._conn.rollback()
            except Exception:
                pass
            self._pool.putconn(self._conn)
        finally:
            self._closed = True
            self._conn = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _get_postgres_pool():
    global _pg_pool

    if _pg_pool is not None:
        return _pg_pool

    with _pg_pool_lock:
        if _pg_pool is not None:
            return _pg_pool

        if not POSTGRES_DSN:
            raise RuntimeError("POSTGRES_DSN is required when DB_BACKEND=postgres")

        try:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise RuntimeError(
                "psycopg_pool is not installed. Run: pip install psycopg[binary] psycopg-pool"
            ) from exc

        _pg_pool = ConnectionPool(
            conninfo=POSTGRES_DSN,
            min_size=int(os.getenv("POSTGRES_POOL_MIN_SIZE", "2")),
            max_size=int(os.getenv("POSTGRES_POOL_MAX_SIZE", "20")),
            kwargs={
                "row_factory": dict_row,
                # 注意：不在连接池级别设置隔离级别，而是在每个连接获取时设置
                # PostgreSQL 默认就是 READ COMMITTED，所以这里不需要设置
            },
            open=True,
        )
        return _pg_pool


def get_connection():
    """Return a DB connection (PostgreSQL pool or SQLite)."""
    if is_postgres():
        use_pool = os.getenv("POSTGRES_USE_POOL", "1").strip().lower() not in ("0", "false")
        if use_pool:
            pool = _get_postgres_pool()
            conn = pool.getconn()
            # 确保连接能看到最新的已提交数据
            try:
                conn.rollback()  # 回滚任何未提交的事务，确保看到最新的已提交数据
            except Exception:
                pass
            return _PooledPostgresConnection(conn, pool)
        return _create_postgres_connection()
    return _create_sqlite_connection()


# Backward-compatible alias used by several backend modules.
get_db_connection = get_connection


def sql_placeholder() -> str:
    return "%s" if is_postgres() else "?"


def placeholders(count: int) -> str:
    return ",".join([sql_placeholder()] * count)


def close_all():
    global _pg_pool
    if _pg_pool is not None:
        try:
            _pg_pool.close()
        except Exception:
            pass
        _pg_pool = None
