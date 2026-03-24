#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Connection Pool Module
Provides database connection pool management for improved concurrency and stability
"""

import threading
from queue import Queue, Empty
from contextlib import contextmanager

from db_adapter import get_connection as adapter_get_connection, is_postgres


class ConnectionPool:
    """SQLite connection pool."""
    
    def __init__(self, db_path, max_connections=10, timeout=30.0):
        """
        Initialize connection pool
        
        Args:
            db_path: Database file path
            max_connections: Maximum number of connections
            timeout: Connection timeout (seconds)
        """
        self.db_path = db_path
        self.max_connections = max_connections
        self.timeout = timeout
        self.pool = Queue(maxsize=max_connections)
        self.lock = threading.Lock()
        self.created_connections = 0
        self.active_connections = 0
        
        # 預先創建連接
        for _ in range(max_connections):
            conn = self._create_connection()
            if conn:
                self.pool.put(conn)
                self.created_connections += 1
    
    def _create_connection(self):
        """Create new database connection"""
        try:
            if is_postgres():
                raise RuntimeError("ConnectionPool is SQLite-only and should not be used with PostgreSQL")
            return adapter_get_connection()
        except Exception as e:
            try:
                print(f"[ERROR] Failed to create database connection: {e}")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            return None
    
    def _is_connection_valid(self, conn):
        """Check if connection is valid"""
        try:
            conn.execute("SELECT 1")
            return True
        except:
            return False
    
    @contextmanager
    def get_connection(self):
        """
        Get database connection (context manager)
        
        Usage:
            with pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM ...")
        """
        conn = None
        try:
            # Try to get connection from pool (wait up to 5 seconds)
            try:
                conn = self.pool.get(timeout=5)
            except Empty:
                # No available connection in pool, create new one (if not at limit)
                with self.lock:
                    if self.created_connections < self.max_connections:
                        conn = self._create_connection()
                        if conn:
                            self.created_connections += 1
                    else:
                        # At limit, wait for connection from pool
                        conn = self.pool.get(timeout=10)
            
            # Check if connection is valid
            if not self._is_connection_valid(conn):
                # Connection is corrupted, create new one
                try:
                    conn.close()
                except:
                    pass
                conn = self._create_connection()
            
            self.active_connections += 1
            yield conn
            
        except Exception as e:
            # Error occurred, close connection
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            raise e
        finally:
            # Return connection
            if conn:
                self.active_connections -= 1
                # Check if connection is still valid
                if self._is_connection_valid(conn):
                    try:
                        # Reset connection state
                        conn.rollback()
                        self.pool.put(conn)
                    except:
                        # Connection is corrupted, don't return
                        try:
                            conn.close()
                        except:
                            pass
                        with self.lock:
                            self.created_connections -= 1
                else:
                    # Connection is corrupted, don't return
                    try:
                        conn.close()
                    except:
                        pass
                    with self.lock:
                        self.created_connections -= 1
    
    def get_stats(self):
        """Get connection pool statistics"""
        return {
            'max_connections': self.max_connections,
            'created_connections': self.created_connections,
            'active_connections': self.active_connections,
            'available_connections': self.pool.qsize()
        }
    
    def close_all(self):
        """Close all connections"""
        while not self.pool.empty():
            try:
                conn = self.pool.get_nowait()
                conn.close()
            except:
                pass
        self.created_connections = 0
        self.active_connections = 0


# Global connection pool instance
_pool = None


def init_pool(db_path, max_connections=10):
    """Initialize global connection pool"""
    global _pool
    if is_postgres():
        raise RuntimeError("db_pool.init_pool() should not be used when DB_BACKEND=postgres")
    if _pool is None:
        _pool = ConnectionPool(db_path, max_connections)
        try:
            print(f"[INFO] Database connection pool initialized: max_connections={max_connections}")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return _pool


def get_pool():
    """Get global connection pool instance"""
    if _pool is None:
        raise RuntimeError("Connection pool not initialized, please call init_pool() first")
    return _pool
