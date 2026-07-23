#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-process mutex for TR PostgreSQL full table updates.

Uses a PostgreSQL *session-level* advisory lock held on a dedicated, long-lived
connection that is NOT taken from the application connection pool.

Why dedicated connection:
  pg_try_advisory_lock() is bound to one DB session. If the connection is
  returned to a pool or closed between sync_tr_data / generate_tr_report steps,
  the lock is released immediately and another process can start writing —
  which causes TR_Report row doubling.

Usage:
  lock = TrUpdateLock(source='scheduled')
  if not lock.try_acquire():
      sys.exit(0)  # or raise / return busy
  try:
      ... run update ...
  finally:
      lock.release()

CLI:
  python tr_update_lock.py --status
  python tr_update_lock.py --force-clear-meta
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Stable advisory lock key (bigint). Do not change once deployed.
# 872014001 = TR update namespace
DEFAULT_LOCK_KEY = int(os.getenv("TR_UPDATE_LOCK_KEY", "872014001"))
DEFAULT_MAX_AGE_SEC = int(os.getenv("TR_UPDATE_LOCK_MAX_AGE_SEC", "7200"))

_META_DIR_ENV = "TR_UPDATE_LOCK_META_DIR"


def _default_meta_path() -> str:
    override = os.getenv(_META_DIR_ENV, "").strip()
    if override:
        return os.path.join(override, "tr_update_lock_meta.json")
    # Prefer TR database/logs next to this repo layout
    here = os.path.abspath(os.path.dirname(__file__))
    # .../TR UI/backend -> .../TR database/logs
    tr_db_logs = os.path.normpath(os.path.join(here, "..", "..", "TR database", "logs"))
    return os.path.join(tr_db_logs, "tr_update_lock_meta.json")


def _postgres_dsn() -> str:
    return os.getenv(
        "POSTGRES_DSN", "postgresql://postgres:postgres@127.0.0.1:5432/tr_db"
    ).strip()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class LockBusyInfo:
    held: bool
    source: str = ""
    owner_pid: Optional[int] = None
    host: str = ""
    acquired_at: str = ""
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "held": self.held,
            "source": self.source,
            "owner_pid": self.owner_pid,
            "host": self.host,
            "acquired_at": self.acquired_at,
            "message": self.message,
        }


class TrUpdateLock:
    """
    Holds pg_try_advisory_lock on a dedicated psycopg connection for the
    entire update lifetime. Never use get_connection() / pool for this.
    """

    def __init__(
        self,
        source: str = "unknown",
        lock_key: int = DEFAULT_LOCK_KEY,
        meta_path: Optional[str] = None,
        max_age_sec: int = DEFAULT_MAX_AGE_SEC,
    ):
        self.source = source or "unknown"
        self.lock_key = int(lock_key)
        self.meta_path = meta_path or _default_meta_path()
        self.max_age_sec = int(max_age_sec)
        self._conn = None  # dedicated session
        self._acquired = False
        self._acquired_at: Optional[str] = None
        self.owner_pid = os.getpid()
        try:
            self.host = socket.gethostname()
        except Exception:
            self.host = ""

    # ---- metadata (human / API visibility; not the real mutex) ----

    def _read_meta(self) -> dict[str, Any]:
        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as exc:
            logger.warning("read lock meta failed: %s", exc)
            return {}

    def _write_meta(self, payload: dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self.meta_path) or ".", exist_ok=True)
            tmp = self.meta_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.meta_path)
        except Exception as exc:
            logger.warning("write lock meta failed: %s", exc)

    def _clear_meta(self) -> None:
        try:
            if os.path.exists(self.meta_path):
                os.remove(self.meta_path)
        except Exception as exc:
            logger.warning("clear lock meta failed: %s", exc)

    def _open_dedicated_connection(self):
        """Open a non-pooled connection; autocommit so lock ops apply immediately."""
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "psycopg is required for TrUpdateLock. pip install psycopg[binary]"
            ) from exc

        dsn = _postgres_dsn()
        if not dsn:
            raise RuntimeError("POSTGRES_DSN is empty; cannot acquire update lock")

        # IMPORTANT: do not use db_adapter.get_connection() / ConnectionPool here.
        conn = psycopg.connect(dsn, autocommit=True, connect_timeout=30)
        # Keep session alive; disable idle session quirks if any
        try:
            with conn.cursor() as cur:
                cur.execute("SET application_name = %s", (f"tr_update_lock:{self.source}",))
        except Exception:
            pass
        return conn

    def _pg_lock_granted_in_cluster(self) -> bool:
        """True if some backend currently holds our session advisory lock."""
        conn = None
        try:
            conn = self._open_dedicated_connection()
            # bigint advisory lock → classid = high 32 bits, objid = low 32 bits
            classid = (self.lock_key >> 32) & 0xFFFFFFFF
            objid = self.lock_key & 0xFFFFFFFF
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_locks
                        WHERE locktype = 'advisory'
                          AND granted
                          AND database = (
                              SELECT oid FROM pg_database WHERE datname = current_database()
                          )
                          AND classid = %s::oid
                          AND objid = %s::oid
                    )
                    """,
                    (classid, objid),
                )
                row = cur.fetchone()
                return bool(row and row[0])
        except Exception as exc:
            logger.warning("pg_locks probe failed: %s", exc)
            return False
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def is_held(lock_key: int = DEFAULT_LOCK_KEY, meta_path: Optional[str] = None) -> LockBusyInfo:
        """Probe whether the advisory lock is currently held (does not acquire)."""
        probe = TrUpdateLock(source="probe", lock_key=lock_key, meta_path=meta_path)
        meta = probe._read_meta()
        held = probe._pg_lock_granted_in_cluster()
        if held:
            msg = "已有数据更新正在执行（PostgreSQL 跨进程锁占用中）"
            if meta.get("source") or meta.get("acquired_at"):
                msg = (
                    f"已有数据更新正在执行（来源: {meta.get('source', '?')}，"
                    f"开始于 {meta.get('acquired_at', '?')}，"
                    f"pid={meta.get('owner_pid', '?')}）"
                )
            return LockBusyInfo(
                held=True,
                source=str(meta.get("source") or ""),
                owner_pid=meta.get("owner_pid"),
                host=str(meta.get("host") or ""),
                acquired_at=str(meta.get("acquired_at") or ""),
                message=msg,
            )
        return LockBusyInfo(held=False, message="无跨进程更新锁")

    def try_acquire(self) -> bool:
        """
        Acquire session advisory lock on a dedicated connection.
        Returns False if another session holds the lock.
        """
        if self._acquired and self._conn is not None:
            return True

        # If meta says held but PG lock is gone (crash), clear stale meta only.
        meta = self._read_meta()
        if meta and not self._pg_lock_granted_in_cluster():
            logger.warning(
                "lock meta present but advisory lock not held; clearing stale meta: %s",
                meta,
            )
            self._clear_meta()

        try:
            self._conn = self._open_dedicated_connection()
            with self._conn.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(%s)", (self.lock_key,))
                row = cur.fetchone()
                ok = bool(row and row[0])
            if not ok:
                logger.info(
                    "tr_update_lock BUSY key=%s source=%s (other session holds lock)",
                    self.lock_key,
                    self.source,
                )
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
                return False

            self._acquired = True
            self._acquired_at = _utc_now_iso()
            self._write_meta(
                {
                    "lock_key": self.lock_key,
                    "source": self.source,
                    "owner_pid": self.owner_pid,
                    "host": self.host,
                    "acquired_at": self._acquired_at,
                    "heartbeat_at": self._acquired_at,
                }
            )
            logger.info(
                "tr_update_lock ACQUIRED key=%s source=%s pid=%s host=%s",
                self.lock_key,
                self.source,
                self.owner_pid,
                self.host,
            )
            return True
        except Exception:
            self._acquired = False
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
            raise

    def heartbeat(self) -> None:
        if not self._acquired or self._conn is None:
            return
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
            meta = self._read_meta()
            meta["heartbeat_at"] = _utc_now_iso()
            meta["owner_pid"] = self.owner_pid
            meta["source"] = self.source
            self._write_meta(meta)
        except Exception as exc:
            logger.warning("tr_update_lock heartbeat failed: %s", exc)

    def release(self) -> None:
        """Release advisory lock and close dedicated connection."""
        conn = self._conn
        self._conn = None
        acquired = self._acquired
        self._acquired = False
        try:
            if conn is not None and acquired:
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT pg_advisory_unlock(%s)", (self.lock_key,))
                    logger.info(
                        "tr_update_lock RELEASED key=%s source=%s",
                        self.lock_key,
                        self.source,
                    )
                except Exception as exc:
                    logger.warning("pg_advisory_unlock failed (will close session): %s", exc)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            # Closing the session also drops the lock if unlock failed.
            self._clear_meta()

    def __enter__(self):
        if not self.try_acquire():
            info = self.is_held(self.lock_key, self.meta_path)
            raise RuntimeError(info.message or "update lock busy")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False


def force_clear_meta(meta_path: Optional[str] = None) -> None:
    """Admin helper: remove meta file only (cannot steal another session's lock)."""
    path = meta_path or _default_meta_path()
    try:
        if os.path.exists(path):
            os.remove(path)
            print(f"cleared meta: {path}")
        else:
            print(f"meta not found: {path}")
    except Exception as exc:
        print(f"failed: {exc}")
        raise


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="TR update cross-process lock utility")
    parser.add_argument("--status", action="store_true", help="Show whether lock is held")
    parser.add_argument(
        "--force-clear-meta",
        action="store_true",
        help="Delete lock meta JSON (does not unlock another live session)",
    )
    parser.add_argument(
        "--try-acquire-demo",
        action="store_true",
        help="Try acquire then release (smoke test)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.force_clear_meta:
        force_clear_meta()
        return 0

    if args.status:
        info = TrUpdateLock.is_held()
        print(json.dumps(info.as_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.try_acquire_demo:
        lock = TrUpdateLock(source="demo")
        if not lock.try_acquire():
            print("BUSY", TrUpdateLock.is_held().as_dict())
            return 2
        print("ACQUIRED", lock._acquired_at)
        lock.release()
        print("RELEASED")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
