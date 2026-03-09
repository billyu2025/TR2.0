#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TR Fill In API Server
Handles data synchronization requests from the frontend TR Fill In page
"""

from flask import Flask, request, jsonify, send_file, g, after_this_request, Response
from flask_cors import CORS
import sqlite3
import os
import sys
import zipfile
import tempfile
import uuid
import binascii
import hashlib
import hmac
import subprocess
import threading
import secrets
import string
import traceback
import time
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 導入統一日誌系統
from logger_config import init_logger, get_logger, get_access_logger

# Import task managers at module level to avoid encoding issues during function-level imports
try:
    from pdf_task_manager import PDFTaskManager
except ImportError as e:
    PDFTaskManager = None
    try:
        logger.warning(f"Failed to import PDFTaskManager: {e}")
    except:
        pass

try:
    from download_task_manager import DownloadTaskManager
except ImportError as e:
    DownloadTaskManager = None
    try:
        logger.warning(f"Failed to import DownloadTaskManager: {e}")
    except:
        pass

app = Flask(__name__)
# 允许跨域请求，包括 file:// 协议
# 暴露自定义响应头，以便前端可以读取
CORS(app, resources={r"/*": {"origins": "*", "expose_headers": ["X-Date-Count"]}}, supports_credentials=True)

# 从环境变量读取配置，如果没有则使用默认值
# 数据库路径
# 获取当前文件所在目录（backend目录），然后向上两级到项目根目录（TR REPORT目录）
_current_dir = os.path.dirname(os.path.abspath(__file__))
# 从 backend 目录向上两级到 TR REPORT 目录（项目根目录）
_project_root = os.path.normpath(os.path.join(_current_dir, '..', '..'))
_default_db_path = os.path.join(_project_root, 'TR database', 'data_3years.db')
# 确保路径是绝对路径
_default_db_path = os.path.abspath(_default_db_path)
DB_PATH = os.getenv('DB_PATH', _default_db_path)
# 如果环境变量是相对路径，转换为绝对路径（相对于项目根目录）
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.abspath(os.path.join(_project_root, DB_PATH))

# 服务器配置
API_HOST = os.getenv('API_HOST', '0.0.0.0')  # 0.0.0.0 允许所有网络接口访问
API_PORT = int(os.getenv('API_PORT', '5000'))
DEBUG_MODE = os.getenv('DEBUG', 'False').lower() == 'true'

# 安全配置
SESSION_TTL_HOURS = int(os.getenv('SESSION_TTL_HOURS', '24'))
PASSWORD_ITERATIONS = int(os.getenv('PASSWORD_ITERATIONS', '120000'))
PASSWORD_EXPIRY_DAYS = 180  # 普通账户密码有效期（天）

# 初始化統一日誌系統
logger = init_logger(debug_mode=DEBUG_MODE)
access_logger = get_access_logger()

# 下载任务管理器单例：避免每个请求各自创建线程池/队列
_download_task_manager = None
_download_task_manager_lock = threading.Lock()


def get_download_task_manager():
    """Get singleton DownloadTaskManager with fixed worker queue."""
    global _download_task_manager
    if _download_task_manager is not None:
        return _download_task_manager
    with _download_task_manager_lock:
        if _download_task_manager is None:
            if DownloadTaskManager is None:
                raise RuntimeError('Download task manager not available')
            base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
            _download_task_manager = DownloadTaskManager(DB_PATH, base_folder)
    return _download_task_manager

# 初始化緩存系統
from cache_manager import init_cache, get_cache
cache = init_cache(default_ttl=300)  # 默認5分鐘

# 初始化請求限流系統
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    
    # 初始化限流器（使用內存存儲，簡單場景）
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,  # 根據 IP 地址限流
        default_limits=["200 per day", "50 per hour"],  # 全局默認限制
        storage_uri="memory://"  # 使用內存存儲
    )
    try:
        logger.info("Rate limiting system enabled")
    except (UnicodeEncodeError, UnicodeDecodeError):
        logger.info("Rate limiting system enabled")
except ImportError:
    limiter = None
    try:
        logger.warning("flask-limiter not installed, rate limiting disabled")
    except (UnicodeEncodeError, UnicodeDecodeError):
        logger.warning("flask-limiter not installed, rate limiting disabled")


# ============================================================================
# 全局錯誤處理器
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """處理 404 錯誤（資源不存在）"""
    logger.warning(f"404 Not Found: {request.path} - {request.remote_addr}")
    return jsonify({
        'success': False,
        'error': '資源不存在',
        'code': 404,
        'path': request.path
    }), 404


@app.errorhandler(400)
def bad_request(error):
    """處理 400 錯誤（請求格式錯誤）"""
    logger.warning(f"400 Bad Request: {request.path} - {request.remote_addr}")
    return jsonify({
        'success': False,
        'error': '請求格式錯誤',
        'code': 400
    }), 400


@app.errorhandler(401)
def unauthorized(error):
    """處理 401 錯誤（未授權）"""
    logger.warning(f"401 Unauthorized: {request.path} - {request.remote_addr}")
    return jsonify({
        'success': False,
        'error': '未授權，請先登入',
        'code': 401
    }), 401


@app.errorhandler(403)
def forbidden(error):
    """處理 403 錯誤（禁止訪問）"""
    logger.warning(f"403 Forbidden: {request.path} - {request.remote_addr}")
    return jsonify({
        'success': False,
        'error': '無權限訪問此資源',
        'code': 403
    }), 403


@app.errorhandler(500)
def internal_error(error):
    """處理 500 錯誤（服務器內部錯誤）"""
    logger.error(f"500 Internal Server Error: {request.path} - {request.remote_addr}", exc_info=True)
    
    # 根據調試模式決定是否返回詳細錯誤信息
    error_response = {
        'success': False,
        'error': 'Internal server error',
        'code': 500
    }
    
    # 僅在調試模式下返回詳細錯誤信息
    if DEBUG_MODE:
        error_response['detail'] = str(error)
        error_response['traceback'] = traceback.format_exc()
    
    return jsonify(error_response), 500


@app.errorhandler(Exception)
def handle_exception(e):
    """處理所有未捕獲的異常（最後防線）"""
    # 記錄詳細錯誤信息
    logger.error(
        f"Unhandled Exception: {type(e).__name__} - {str(e)} - "
        f"Path: {request.path} - Method: {request.method} - "
        f"Remote: {request.remote_addr}",
        exc_info=True
    )
    
    # 根據錯誤類型返回不同的響應
    error_response = {
        'success': False,
        'error': 'Unexpected error occurred',
        'code': 500
    }
    
    # 僅在調試模式下返回詳細錯誤信息
    import traceback
    if DEBUG_MODE:
        error_response['detail'] = str(e)
        error_response['type'] = type(e).__name__
        error_response['traceback'] = traceback.format_exc()
    else:
        # 生產環境：記錄詳細信息但不返回給用戶
        try:
            logger.error(f"Detailed error info (logged only, not returned to user): {traceback.format_exc()}")
        except (UnicodeEncodeError, UnicodeDecodeError):
            logger.error(f"Error occurred: {type(e).__name__}: {str(e)}")
    
    return jsonify(error_response), 500


# ============================================================================
# 數據庫連接函數（使用連接池）
# ============================================================================

# 導入連接池模組
from db_pool import init_pool, get_pool
import threading

# 初始化連接池（最大連接數20）
_pool_initialized = False
_pool_lock = threading.Lock()

# 線程本地存儲：用於跟蹤每個線程的連接和上下文管理器
_thread_local = threading.local()

def _ensure_pool_initialized():
    """確保連接池已初始化"""
    global _pool_initialized
    with _pool_lock:
        if not _pool_initialized:
            try:
                init_pool(DB_PATH, max_connections=20)
                _pool_initialized = True
                try:
                    logger.info(f"[Connection Pool] Database connection pool initialized: max_connections=20")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    logger.info("[Connection Pool] Database connection pool initialized: max_connections=20")
            except Exception as e:
                try:
                    logger.error(f"[Connection Pool] Failed to initialize connection pool: {e}")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    logger.error(f"[Connection Pool] Failed to initialize connection pool: {e}")
                _pool_initialized = False

# 包裝類：讓連接池的連接行為像普通連接
class PooledConnection:
    """連接池連接包裝類，保持與原有代碼的兼容性"""
    
    def __init__(self, conn, context_manager):
        """
        Args:
            conn: 實際的數據庫連接對象
            context_manager: 連接池上下文管理器（用於歸還連接）
        """
        self._conn = conn
        self._context_manager = context_manager
        self._closed = False
    
    def __getattr__(self, name):
        """代理所有屬性訪問到實際連接"""
        if self._closed:
            raise RuntimeError("連接已關閉")
        return getattr(self._conn, name)
    
    def close(self):
        """關閉連接（實際上是歸還到連接池）"""
        if not self._closed:
            try:
                # 歸還連接到池中（通過退出上下文管理器）
                # __exit__ 需要三個參數：exc_type, exc_val, exc_tb
                self._context_manager.__exit__(None, None, None)
            except Exception as e:
                try:
                    logger.warning(f"[Connection Pool] Error returning connection: {e}")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    logger.warning(f"[Connection Pool] Error returning connection: {e}")
            finally:
                self._conn = None
                self._closed = True
                # 清除線程本地存儲
                if hasattr(_thread_local, 'current_connection'):
                    delattr(_thread_local, 'current_connection')
                if hasattr(_thread_local, 'current_context'):
                    delattr(_thread_local, 'current_context')
    
    def __del__(self):
        """析構函數：確保連接被歸還"""
        if not self._closed:
            try:
                self.close()
            except:
                pass

def get_db_connection():
    """
    获取数据库连接（使用连接池）
    
    注意：為了保持兼容性，返回的連接對象在調用 close() 時會自動歸還到連接池。
    建議使用 with 語句，但手動 close() 也可以正常工作。
    """
    _ensure_pool_initialized()
    
    try:
        pool = get_pool()
        # 獲取連接池上下文管理器
        context_manager = pool.get_connection()
        # 進入上下文管理器以獲取實際連接
        conn = context_manager.__enter__()
        
        # 保存到線程本地存儲（用於錯誤處理和調試）
        _thread_local.current_connection = conn
        _thread_local.current_context = context_manager
        
        # 創建包裝對象
        wrapped_conn = PooledConnection(conn, context_manager)
        return wrapped_conn
    except Exception as e:
        try:
            logger.error(f"[Connection Pool] Failed to get connection: {e}")
            import traceback
            logger.error(f"[Connection Pool] Error details: {traceback.format_exc()}")
            logger.warning("[Connection Pool] Falling back to direct connection mode")
        except (UnicodeEncodeError, UnicodeDecodeError):
            logger.error(f"[Connection Pool] Failed to get connection: {e}")
            import traceback
            logger.error(f"[Connection Pool] Error details: {traceback.format_exc()}")
            logger.warning("[Connection Pool] Falling back to direct connection mode")
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
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


def _ensure_bbs_dd_indexes(conn, cursor):
    """
    确保 bbs_dd 表有必要的索引（性能优化）
    只在首次调用时创建，后续调用会快速跳过
    """
    try:
        # 检查索引是否已存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name LIKE 'idx_bbs_dd%'
        """)
        existing_indexes = [row[0] for row in cursor.fetchall()]
        
        # 创建缺失的索引
        indexes_to_create = [
            ("idx_bbs_dd_bbs_no", "CREATE INDEX IF NOT EXISTS idx_bbs_dd_bbs_no ON bbs_dd(bbs_no)"),
            ("idx_bbs_dd_jobsite_no", "CREATE INDEX IF NOT EXISTS idx_bbs_dd_jobsite_no ON bbs_dd(jobsite_no)"),
            ("idx_bbs_dd_dd_no", "CREATE INDEX IF NOT EXISTS idx_bbs_dd_dd_no ON bbs_dd(dd_no)"),
            ("idx_bbs_dd_delivery_date", "CREATE INDEX IF NOT EXISTS idx_bbs_dd_delivery_date ON bbs_dd(dd_delivery_date DESC)"),
            ("idx_bbs_dd_composite", "CREATE INDEX IF NOT EXISTS idx_bbs_dd_composite ON bbs_dd(dd_delivery_date DESC, bbs_no)")
        ]
        
        created_count = 0
        for index_name, create_sql in indexes_to_create:
            if index_name not in existing_indexes:
                cursor.execute(create_sql)
                created_count += 1
                print(f"[性能优化] 创建索引: {index_name}")
        
        if created_count > 0:
            conn.commit()
            print(f"[性能优化] bbs_dd 表索引创建完成，共创建 {created_count} 个索引")
            
    except Exception as e:
        # 索引创建失败不影响查询，只记录错误
        print(f"[警告] 创建 bbs_dd 索引时出错（不影响查询）: {e}")


# SESSION_TTL_HOURS 和 PASSWORD_ITERATIONS 已从环境变量读取（见上方）


def _row_to_dict(row):
    return dict(row) if row else None


def _generate_password_hash(password: str, salt_hex: str | None = None):
    if not password:
        raise ValueError("Password must not be empty")
    if salt_hex:
        salt_bytes = binascii.unhexlify(salt_hex)
    else:
        salt_bytes = os.urandom(16)
        salt_hex = binascii.hexlify(salt_bytes).decode('utf-8')
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt_bytes,
        PASSWORD_ITERATIONS
    )
    hash_hex = binascii.hexlify(hashed).decode('utf-8')
    return salt_hex, hash_hex


def _verify_password(password: str, salt_hex: str, hash_hex: str):
    if not password or not salt_hex or not hash_hex:
        return False
    try:
        salt_bytes = binascii.unhexlify(salt_hex)
        hashed = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt_bytes,
            PASSWORD_ITERATIONS
        )
        return hmac.compare_digest(binascii.hexlify(hashed).decode('utf-8'), hash_hex)
    except (binascii.Error, ValueError):
        return False


def _generate_random_password(length: int = 10) -> str:
    """
    生成随机强密码（大小写字母+数字+特殊符号）
    
    Args:
        length: 密码长度，默认10位
        
    Returns:
        生成的随机密码
    """
    # 定义字符集
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    special = '!@#$%^&*'
    
    # 确保至少包含每种类型的字符
    password_chars = [
        secrets.choice(lowercase),
        secrets.choice(uppercase),
        secrets.choice(digits),
        secrets.choice(special)
    ]
    
    # 填充剩余长度
    all_chars = lowercase + uppercase + digits + special
    for _ in range(length - 4):
        password_chars.append(secrets.choice(all_chars))
    
    # 打乱顺序
    secrets.SystemRandom().shuffle(password_chars)
    
    return ''.join(password_chars)


def _calculate_password_days_remaining(password_expires_at: str | None) -> int | None:
    """
    计算密码剩余天数
    
    Args:
        password_expires_at: 密码过期时间（ISO格式字符串）
        
    Returns:
        剩余天数，如果已过期返回负数，如果未设置返回None
    """
    if not password_expires_at:
        return None
    
    try:
        expires_date = datetime.fromisoformat(password_expires_at.replace('Z', '+00:00'))
        if expires_date.tzinfo:
            expires_date = expires_date.replace(tzinfo=None)
        now = datetime.now()
        delta = expires_date - now
        return delta.days
    except (ValueError, AttributeError):
        return None


def _normalize_job_numbers(job_nos):
    if not job_nos:
        return []
    normalized = []
    seen = set()
    for item in job_nos:
        if item is None:
            continue
        text = str(item).strip()
        if not text:
            continue
        text = text.upper()
        if text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


def _ensure_account_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 检查表是否存在
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='user_accounts'
    """)
    table_exists = cursor.fetchone() is not None
    
    if table_exists:
        # 表已存在，检查约束是否需要更新
        cursor.execute("""
            SELECT sql FROM sqlite_master 
            WHERE type='table' AND name='user_accounts'
        """)
        create_sql = cursor.fetchone()
        if create_sql and 'manager' not in create_sql[0]:
            # 约束不包含'manager'，需要重建表
            print("[INFO] Updating user_accounts table to support 'manager' role...")
            # 创建临时表
            cursor.execute("""
                CREATE TABLE user_accounts_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    password_plaintext TEXT,
                    full_name TEXT,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'manager', 'user')),
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 复制数据
            cursor.execute("""
                INSERT INTO user_accounts_new 
                (id, username, password_hash, password_salt, password_plaintext, full_name, role, is_active, created_at, updated_at)
                SELECT id, username, password_hash, password_salt, NULL, full_name, role, is_active, created_at, updated_at
                FROM user_accounts
            """)
            # 删除旧表
            cursor.execute("DROP TABLE user_accounts")
            # 重命名新表
            cursor.execute("ALTER TABLE user_accounts_new RENAME TO user_accounts")
            # 重新创建触发器
            cursor.execute("DROP TRIGGER IF EXISTS trg_user_accounts_updated")
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_user_accounts_updated
                AFTER UPDATE ON user_accounts
                FOR EACH ROW
                BEGIN
                    UPDATE user_accounts
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE id = NEW.id;
                END;
            """)
            conn.commit()
            logger.info("user_accounts table updated successfully")
    else:
        # 表不存在，创建新表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                password_plaintext TEXT,
                full_name TEXT,
                role TEXT NOT NULL CHECK(role IN ('admin', 'manager', 'user')),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                password_changed_at TEXT,
                password_expires_at TEXT
            )
            """
        )
    
    # 检查并添加密码过期相关字段（如果表已存在但字段不存在）
    cursor.execute("PRAGMA table_info(user_accounts)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'password_changed_at' not in columns:
        logger.info("Adding password_changed_at column to user_accounts table...")
        cursor.execute("ALTER TABLE user_accounts ADD COLUMN password_changed_at TEXT")
        conn.commit()
    
    if 'password_expires_at' not in columns:
        logger.info("Adding password_expires_at column to user_accounts table...")
        cursor.execute("ALTER TABLE user_accounts ADD COLUMN password_expires_at TEXT")
        conn.commit()
    
    if 'password_plaintext' not in columns:
        logger.info("Adding password_plaintext column to user_accounts table...")
        cursor.execute("ALTER TABLE user_accounts ADD COLUMN password_plaintext TEXT")
        conn.commit()
    
    # 创建其他表和触发器（无论表是否已更新）
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_job_access (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            job_no TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, job_no),
            FOREIGN KEY(user_id) REFERENCES user_accounts(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES user_accounts(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_user_accounts_updated
        AFTER UPDATE ON user_accounts
        FOR EACH ROW
        BEGIN
            UPDATE user_accounts
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = NEW.id;
        END;
        """
    )
    
    # 创建PDF_Status表（如果不存在）
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='PDF_Status'
    """)
    pdf_status_exists = cursor.fetchone() is not None
    
    if not pdf_status_exists:
        cursor.execute(
            """
            CREATE TABLE PDF_Status (
                Order_No INTEGER PRIMARY KEY,
                pdf_status TEXT NOT NULL DEFAULT 'pending',
                pdf_path TEXT,
                generated_at TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        logger.info("PDF_Status table created successfully")
    else:
        logger.info("PDF_Status table already exists, skipping creation")
    
    # 创建PDF_Status表的更新触发器（如果不存在则创建，如果存在则先删除再创建以确保最新）
    cursor.execute("DROP TRIGGER IF EXISTS trg_pdf_status_updated")
    cursor.execute(
        """
        CREATE TRIGGER trg_pdf_status_updated
        AFTER UPDATE ON PDF_Status
        FOR EACH ROW
        BEGIN
            UPDATE PDF_Status
            SET updated_at = CURRENT_TIMESTAMP
            WHERE Order_No = NEW.Order_No;
        END;
        """
    )
    
    conn.commit()

    # 确保至少存在一个可用的管理员账户
    cursor.execute("SELECT id FROM user_accounts WHERE username = ?", ('admin',))
    existing_admin = cursor.fetchone()
    new_password = 'Vschk!8866'
    salt, password_hash = _generate_password_hash(new_password)
    
    if not existing_admin:
        cursor.execute(
            """
            INSERT INTO user_accounts (username, password_hash, password_salt, full_name, role, is_active)
            VALUES (?, ?, ?, ?, 'admin', 1)
            """,
            ('admin', password_hash, salt, 'System Administrator')
        )
        cursor.execute(
            "UPDATE user_accounts SET password_plaintext = ? WHERE username = 'admin'",
            (new_password,)
        )
        conn.commit()
        logger.info(f"Created default admin account (username: admin, password: {new_password})")
    else:
        # 更新现有 admin 账户的密码
        cursor.execute(
            """
            UPDATE user_accounts 
            SET password_hash = ?, password_salt = ?, password_plaintext = ?, updated_at = CURRENT_TIMESTAMP
            WHERE username = 'admin'
            """,
            (password_hash, salt, new_password)
        )
        conn.commit()
        logger.info(f"Updated admin account password to: {new_password}")
    conn.close()


def _fetch_user(conn, *, username=None, user_id=None):
    cursor = conn.cursor()
    if username is not None:
        cursor.execute("SELECT * FROM user_accounts WHERE username = ?", (username,))
    else:
        cursor.execute("SELECT * FROM user_accounts WHERE id = ?", (user_id,))
    return _row_to_dict(cursor.fetchone())


def _fetch_user_job_nos(conn, user_id):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT job_no FROM user_job_access WHERE user_id = ? ORDER BY job_no",
        (user_id,)
    )
    return [row['job_no'] for row in cursor.fetchall()]


def _replace_user_job_nos(conn, user_id, job_nos):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_job_access WHERE user_id = ?", (user_id,))
    for job_no in _normalize_job_numbers(job_nos):
        cursor.execute(
            "INSERT OR IGNORE INTO user_job_access (user_id, job_no) VALUES (?, ?)",
            (user_id, job_no)
        )


def _create_session(user_id):
    # 使用 UTC 时间，并添加 'Z' 后缀明确标识为 UTC
    expires_at = (datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)).isoformat() + 'Z'
    token = uuid.uuid4().hex
    conn = get_db_connection()
    cursor = conn.cursor()
    # 清理该用户旧的会话
    cursor.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
    cursor.execute(
        """
        INSERT INTO user_sessions (token, user_id, expires_at)
        VALUES (?, ?, ?)
        """,
        (token, user_id, expires_at)
    )
    conn.commit()
    conn.close()
    return token, expires_at


def _delete_session(token):
    if not token:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def _get_session(token):
    if not token:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT token, user_id, expires_at FROM user_sessions WHERE token = ?",
        (token,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    expires_at = row['expires_at']
    try:
        # 处理时区：如果字符串以 'Z' 结尾，替换为 '+00:00'；如果没有时区信息，假设为 UTC
        if expires_at.endswith('Z'):
            expires_at_parsed = expires_at.replace('Z', '+00:00')
        elif '+' in expires_at or expires_at.count('-') > 2:  # 已有时区信息
            expires_at_parsed = expires_at
        else:
            # 没有时区信息，假设为 UTC
            expires_at_parsed = expires_at + '+00:00'
        
        expires = datetime.fromisoformat(expires_at_parsed)
        # 转换为 naive datetime (UTC) 以便比较
        if expires.tzinfo:
            expires = expires.replace(tzinfo=None)
    except (ValueError, AttributeError) as e:
        logger.warning(f"解析会话过期时间失败: {expires_at}, 错误: {e}")
        expires = datetime.utcnow()
    
    # 使用 UTC 时间比较
    now_utc = datetime.utcnow()
    if expires < now_utc:
        logger.info(f"会话已过期: token={token[:8]}..., expires={expires_at}, now={now_utc.isoformat()}")
        cursor.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return None
    
    session = {
        'token': row['token'],
        'user_id': row['user_id'],
        'expires_at': expires_at
    }
    conn.close()
    return session


def _resolve_token_from_request():
    auth_header = request.headers.get('Authorization')
    if isinstance(auth_header, str) and auth_header.lower().startswith('bearer '):
        return auth_header.split(' ', 1)[1].strip()
    token = request.headers.get('X-Auth-Token')
    if token:
        return token.strip()
    return request.args.get('token')


def get_current_user(optional=False):
    if hasattr(g, 'current_user') and g.current_user is not None:
        return g.current_user
    token = _resolve_token_from_request()
    if not token:
        if optional:
            return None
        return None
    session = _get_session(token)
    if not session:
        if optional:
            return None
        # 记录会话验证失败（仅在非可选模式下）
        logger.warning(f"会话验证失败: token={token[:8] if token else 'None'}..., 可能已过期或不存在")
        return None
    conn = get_db_connection()
    user = _fetch_user(conn, user_id=session['user_id'])
    conn.close()
    if not user or not user.get('is_active'):
        if optional:
            return None
        return None
    g.current_user = user
    g.current_token = token
    return user


def require_auth(role=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            token = _resolve_token_from_request()
            if not token:
                return jsonify({'success': False, 'error': 'Authentication token required'}), 401
            session = _get_session(token)
            if not session:
                return jsonify({
                    'success': False,
                    'error': 'Invalid or expired token. Your account may have signed in on another device.'
                }), 401
            conn = get_db_connection()
            user = _fetch_user(conn, user_id=session['user_id'])
            conn.close()
            if not user or not user.get('is_active'):
                return jsonify({'success': False, 'error': 'User is disabled'}), 403
            if role and user.get('role') != role:
                return jsonify({'success': False, 'error': 'Insufficient permissions'}), 403
            g.current_user = user
            g.current_token = token
            return func(*args, **kwargs)
        return wrapper
    return decorator


def _ensure_file_index_tables():
    """确保文件索引缓存表存在"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 检查 file_index_cache 表是否存在
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='file_index_cache'
    """)
    cache_table_exists = cursor.fetchone() is not None
    
    if not cache_table_exists:
        # 创建 file_index_cache 表
        cursor.execute("""
            CREATE TABLE file_index_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL UNIQUE,
                file_name TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                folder_type TEXT NOT NULL CHECK(folder_type IN ('Stockist Cert', 'Private Formal', 'Private Prelim', 'IAT Formal', 'IAT Prelim')),
                file_size INTEGER,
                modified_time REAL,
                created_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_checked TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                extracted_keywords TEXT,
                identifiers TEXT,
                file_hash TEXT,
                is_deleted INTEGER NOT NULL DEFAULT 0
            )
        """)
        
        # 创建索引
        # 唯一索引：file_path
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_file_index_cache_file_path 
            ON file_index_cache(file_path)
        """)
        
        # 复合索引：folder_type + file_name（用于按文件夹类型和文件名查询）
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_index_cache_folder_type_file_name 
            ON file_index_cache(folder_type, file_name)
        """)
        
        # 索引：last_checked（用于增量更新时快速查找需要检查的文件）
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_index_cache_last_checked 
            ON file_index_cache(last_checked)
        """)
        
        # 索引：folder_type（用于按文件夹类型过滤）
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_index_cache_folder_type 
            ON file_index_cache(folder_type)
        """)
        
        # 索引：is_deleted（用于过滤已删除的文件）
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_index_cache_is_deleted 
            ON file_index_cache(is_deleted)
        """)
        
        conn.commit()
        logger.info("file_index_cache table created successfully")
    else:
        logger.info("file_index_cache table already exists, skipping creation")
        # 检查是否存在 identifiers 列，如果不存在则添加
        cursor.execute("PRAGMA table_info(file_index_cache)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'identifiers' not in columns:
            try:
                cursor.execute("ALTER TABLE file_index_cache ADD COLUMN identifiers TEXT")
                conn.commit()
                logger.info("Added 'identifiers' column to file_index_cache table")
            except Exception as e:
                logger.warning(f"Failed to add 'identifiers' column: {e}")
        
        # 为 identifiers 列创建索引（用于快速查询）
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='idx_file_index_cache_identifiers'
        """)
        if cursor.fetchone() is None:
            try:
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_file_index_cache_identifiers 
                    ON file_index_cache(identifiers)
                """)
                conn.commit()
                logger.info("Created index on 'identifiers' column")
            except Exception as e:
                logger.warning(f"Failed to create index on 'identifiers' column: {e}")
    
    # 检查 file_index_metadata 表是否存在
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='file_index_metadata'
    """)
    metadata_table_exists = cursor.fetchone() is not None
    
    if not metadata_table_exists:
        # 创建 file_index_metadata 表
        cursor.execute("""
            CREATE TABLE file_index_metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 初始化默认元数据
        default_metadata = [
            ('last_full_scan', ''),
            ('total_files_indexed', '0'),
            ('index_version', '1.0'),
            ('scan_status', 'idle')
        ]
        
        cursor.executemany("""
            INSERT INTO file_index_metadata (key, value) 
            VALUES (?, ?)
        """, default_metadata)
        
        conn.commit()
        logger.info("file_index_metadata table created successfully")
    else:
        logger.info("file_index_metadata table already exists, skipping creation")
    
    conn.close()


def _ensure_download_tasks_table():
    """确保下载任务表存在"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 检查表是否存在
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='download_tasks'
    """)
    table_exists = cursor.fetchone() is not None
    
    if not table_exists:
        # 创建 download_tasks 表
        cursor.execute("""
            CREATE TABLE download_tasks (
                task_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                task_type TEXT NOT NULL,
                request_params TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                progress INTEGER DEFAULT 0,
                total_files INTEGER DEFAULT 0,
                processed_files INTEGER DEFAULT 0,
                zip_path TEXT,
                zip_size INTEGER,
                error_message TEXT,
                warning_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                completed_at TEXT,
                expires_at TEXT
            )
        """)
        
        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_download_tasks_user_id 
            ON download_tasks(user_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_download_tasks_status 
            ON download_tasks(status)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_download_tasks_created_at 
            ON download_tasks(created_at)
        """)
        
        conn.commit()
        logger.info("download_tasks table created successfully")
    else:
        logger.info("download_tasks table already exists, skipping creation")
        # 向后兼容：旧表增加 warning_message 字段
        cursor.execute("PRAGMA table_info(download_tasks)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        if 'warning_message' not in existing_columns:
            cursor.execute("ALTER TABLE download_tasks ADD COLUMN warning_message TEXT")
            conn.commit()
            logger.info("download_tasks table altered: added warning_message column")
    
    conn.close()


def _ensure_pdf_tasks_table():
    """确保 PDF 任务表存在"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 检查表是否存在
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='pdf_tasks'
    """)
    table_exists = cursor.fetchone() is not None
    
    if not table_exists:
        # 创建 pdf_tasks 表
        cursor.execute("""
            CREATE TABLE pdf_tasks (
                task_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                order_no INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                progress INTEGER DEFAULT 0,
                message TEXT,
                pdf_path TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                completed_at TEXT,
                expires_at TEXT
            )
        """)
        
        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pdf_tasks_user_id 
            ON pdf_tasks(user_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pdf_tasks_order_no 
            ON pdf_tasks(order_no)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pdf_tasks_status 
            ON pdf_tasks(status)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pdf_tasks_created_at 
            ON pdf_tasks(created_at)
        """)
        
        conn.commit()
        logger.info("pdf_tasks table created successfully")
    else:
        logger.info("pdf_tasks table already exists, skipping creation")
    
    conn.close()


# 初始化數據庫連接池（必須在其他初始化之前）
_ensure_pool_initialized()

# 初始化账号系统
_ensure_account_tables()

# 初始化文件索引缓存表
_ensure_file_index_tables()

# 初始化下载任务表
_ensure_download_tasks_table()

# 初始化 PDF 任务表
_ensure_pdf_tasks_table()


def check_pdf_status_table_exists(conn):
    """检查PDF_Status表是否存在"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='PDF_Status'")
        return cursor.fetchone() is not None
    except:
        return False


@app.route('/api/auth/login', methods=['POST'])
@limiter.limit("5 per minute") if limiter else (lambda f: f)
def login():
    """登录并获取会话令牌"""
    request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
    t_start = time.perf_counter()
    db_query_ms = 0
    password_verify_ms = 0
    token_issue_ms = 0

    def _log_login_attempt(status_code, result, fail_type=''):
        total_ms = int((time.perf_counter() - t_start) * 1000)
        username_masked = ''
        if username:
            username_masked = username[:2] + '***' if len(username) > 2 else username[0] + '*'

        logger.info(
            "login_attempt request_id=%s username=%s status_code=%s result=%s fail_type=%s "
            "db_query_ms=%s password_verify_ms=%s token_issue_ms=%s total_ms=%s",
            request_id,
            username_masked,
            status_code,
            result,
            fail_type,
            db_query_ms,
            password_verify_ms,
            token_issue_ms,
            total_ms
        )
        return total_ms

    def _build_response(payload, status_code, result, fail_type=''):
        total_ms = _log_login_attempt(status_code=status_code, result=result, fail_type=fail_type)
        payload['request_id'] = request_id
        payload['timing'] = {
            'db_query_ms': db_query_ms,
            'password_verify_ms': password_verify_ms,
            'token_issue_ms': token_issue_ms,
            'total_ms': total_ms
        }
        response = jsonify(payload)
        response.status_code = status_code
        response.headers['X-Request-ID'] = request_id
        return response

    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return _build_response(
            {'success': False, 'error': 'Username and password are required'},
            400,
            'fail',
            'missing_credentials'
        )

    t_db_start = time.perf_counter()
    conn = get_db_connection()
    user = _fetch_user(conn, username=username)
    db_query_ms = int((time.perf_counter() - t_db_start) * 1000)
    if not user:
        conn.close()
        return _build_response(
            {'success': False, 'error': 'Invalid username or password'},
            401,
            'fail',
            'invalid_username_or_password'
        )

    t_verify_start = time.perf_counter()
    is_password_valid = _verify_password(password, user['password_salt'], user['password_hash'])
    password_verify_ms = int((time.perf_counter() - t_verify_start) * 1000)
    if not is_password_valid:
        conn.close()
        return _build_response(
            {'success': False, 'error': 'Invalid username or password'},
            401,
            'fail',
            'invalid_username_or_password'
        )

    if not user.get('is_active'):
        conn.close()
        return _build_response(
            {'success': False, 'error': 'Account is disabled'},
            403,
            'fail',
            'account_disabled'
        )

    job_nos = _fetch_user_job_nos(conn, user['id'])
    conn.close()

    t_token_start = time.perf_counter()
    token, expires_at = _create_session(user['id'])
    token_issue_ms = int((time.perf_counter() - t_token_start) * 1000)
    response_user = {
        'username': user['username'],
        'role': user['role'],
        'name': user.get('full_name') or user['username'],
        'job_nos': job_nos,
        'active': bool(user.get('is_active'))
    }
    return _build_response(
        {
            'success': True,
            'token': token,
            'expires_at': expires_at,
            'user': response_user
        },
        200,
        'success'
    )


@app.route('/api/auth/logout', methods=['POST'])
@require_auth()
def logout():
    """注销当前会话"""
    token = getattr(g, 'current_token', None)
    _delete_session(token)
    return jsonify({'success': True})


@app.route('/api/auth/me', methods=['GET'])
@require_auth()
def get_profile():
    """获取当前用户信息"""
    user = g.current_user
    user_id = user['id']
    
    # 生成緩存鍵
    cache_key = cache.generate_key('user:profile', user_id=user_id)
    
    # 嘗試從緩存獲取
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        logger.debug(f"用戶信息緩存命中: {cache_key}")
        return jsonify(cached_result)
    
    conn = get_db_connection()
    job_nos = _fetch_user_job_nos(conn, user_id)
    conn.close()
    
    # 構建響應
    response_data = {
        'success': True,
        'user': {
            'username': user['username'],
            'role': user['role'],
            'name': user.get('full_name') or user['username'],
            'job_nos': job_nos,
            'active': bool(user.get('is_active')),
            'created_at': user.get('created_at'),
            'updated_at': user.get('updated_at')
        }
    }
    
    # 保存到緩存（30分鐘，與 Session 對應）
    cache.set(cache_key, response_data, ttl=1800)
    logger.debug(f"用戶信息緩存已保存: {cache_key}")
    
    return jsonify(response_data)


def _list_users_from_db():
    """從數據庫獲取用戶列表（內部函數）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_accounts ORDER BY role DESC, username ASC")
    rows = cursor.fetchall()
    users = []
    for row in rows:
        row_dict = dict(row)
        job_nos = _fetch_user_job_nos(conn, row_dict['id'])
        password_days_remaining = _calculate_password_days_remaining(row_dict.get('password_expires_at'))
        users.append({
            'username': row_dict['username'],
            'name': row_dict.get('full_name') or '',
            'role': row_dict['role'],
            'active': bool(row_dict.get('is_active')),
            'current_password': row_dict.get('password_plaintext') or '',
            'job_nos': job_nos,
            'created_at': row_dict.get('created_at'),
            'updated_at': row_dict.get('updated_at'),
            'password_days_remaining': password_days_remaining,
            'password_expires_at': row_dict.get('password_expires_at')
        })
    conn.close()
    return users


@app.route('/api/admin/users', methods=['GET'])
@require_auth('admin')
def list_users():
    """管理员：查看所有账户"""
    # 嘗試從緩存獲取用戶列表
    cache_key = 'admin:users:list'
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        logger.debug(f"用戶列表緩存命中: {cache_key}")
        return jsonify(cached_result)
    
    # 查詢數據庫
    users = _list_users_from_db()
    
    # 構建響應
    response_data = {'success': True, 'users': users}
    
    # 保存到緩存（5分鐘）
    cache.set(cache_key, response_data, ttl=300)
    logger.debug(f"用戶列表緩存已保存: {cache_key}")
    
    return jsonify(response_data)


@app.route('/api/admin/users', methods=['POST'])
@require_auth('admin')
@limiter.limit("10 per hour") if limiter else (lambda f: f)
def create_user():
    """管理员：新增普通账号"""
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    full_name = (data.get('name') or '').strip() or None
    job_nos = data.get('job_nos') or []
    active = data.get('active', True)

    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password are required'}), 400

    if username.lower() == 'admin':
        return jsonify({'success': False, 'error': 'Username "admin" is reserved'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM user_accounts WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': 'Username already exists'}), 409

    salt, password_hash = _generate_password_hash(password)
    # 允许创建'user'或'manager'角色
    role_raw = data.get('role', 'user')
    if not role_raw or not isinstance(role_raw, str):
        role = 'user'
    else:
        role = role_raw.strip().lower()
        if role not in ('user', 'manager'):
            role = 'user'
    
    # 设置密码过期时间（仅对普通用户和manager，admin不过期）
    now = datetime.now()
    password_changed_at = now.isoformat()
    password_expires_at = None
    if role in ('user', 'manager'):
        password_expires_at = (now + timedelta(days=PASSWORD_EXPIRY_DAYS)).isoformat()
    
    cursor.execute(
        """
        INSERT INTO user_accounts (username, password_hash, password_salt, password_plaintext, full_name, role, is_active, password_changed_at, password_expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (username, password_hash, salt, password, full_name, role, 1 if active else 0, password_changed_at, password_expires_at)
    )
    user_id = cursor.lastrowid
    # 只有user角色需要Job No，manager不需要
    if role == 'user' and job_nos:
        _replace_user_job_nos(conn, user_id, job_nos)
    conn.commit()
    new_user = _fetch_user(conn, user_id=user_id)
    assigned_jobs = _fetch_user_job_nos(conn, user_id)
    conn.close()

    password_days_remaining = _calculate_password_days_remaining(new_user.get('password_expires_at'))
    
    # 清除用戶列表緩存（已創建新用戶）
    cache.delete('admin:users:list')
    logger.info("已清除用戶列表緩存（已創建新用戶）")
    
    return jsonify({
        'success': True,
        'user': {
            'username': new_user['username'],
            'name': new_user.get('full_name') or '',
            'role': new_user['role'],
            'active': bool(new_user.get('is_active')),
            'current_password': new_user.get('password_plaintext') or '',
            'job_nos': assigned_jobs,
            'created_at': new_user.get('created_at'),
            'updated_at': new_user.get('updated_at'),
            'password_days_remaining': password_days_remaining,
            'password_expires_at': new_user.get('password_expires_at')
        }
    }), 201


@app.route('/api/admin/users/<username>', methods=['PUT'])
@require_auth('admin')
def update_user(username):
    """管理员：更新普通账号"""
    username = (username or '').strip()
    if not username:
        return jsonify({'success': False, 'error': 'Username is required'}), 400

    data = request.get_json(silent=True) or {}
    conn = get_db_connection()
    cursor = conn.cursor()
    user = _fetch_user(conn, username=username)
    if not user:
        conn.close()
        return jsonify({'success': False, 'error': 'User not found'}), 404

    updates = []
    params = []

    if 'name' in data:
        full_name = (data.get('name') or '').strip()
        updates.append("full_name = ?")
        params.append(full_name if full_name else None)

    if 'active' in data:
        desired_active = bool(data.get('active'))
        if user['username'] == 'admin' and not desired_active:
            conn.close()
            return jsonify({'success': False, 'error': 'Administrator account cannot be disabled'}), 400
        updates.append("is_active = ?")
        params.append(1 if desired_active else 0)

    password = data.get('password')
    if password:
        salt, password_hash = _generate_password_hash(password)
        updates.append("password_hash = ?")
        params.append(password_hash)
        updates.append("password_salt = ?")
        params.append(salt)
        updates.append("password_plaintext = ?")
        params.append(password)
        # 更新密码时，设置新的过期时间（仅对普通用户和manager）
        now = datetime.now()
        password_changed_at = now.isoformat()
        updates.append("password_changed_at = ?")
        params.append(password_changed_at)
        if user['role'] in ('user', 'manager'):
            password_expires_at = (now + timedelta(days=PASSWORD_EXPIRY_DAYS)).isoformat()
            updates.append("password_expires_at = ?")
            params.append(password_expires_at)
        else:
            # admin账户密码不过期
            updates.append("password_expires_at = ?")
            params.append(None)

    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(username)
        cursor.execute(
            f"UPDATE user_accounts SET {', '.join(updates)} WHERE username = ?",
            params
        )

    if 'job_nos' in data and user['role'] == 'user':
        _replace_user_job_nos(conn, user['id'], data.get('job_nos') or [])

    conn.commit()
    refreshed = _fetch_user(conn, username=username)
    job_nos = _fetch_user_job_nos(conn, refreshed['id'])
    conn.close()

    password_days_remaining = _calculate_password_days_remaining(refreshed.get('password_expires_at'))
    
    # 清除相關緩存（用戶信息已更新）
    cache.delete('admin:users:list')  # 清除用戶列表緩存
    cache.delete(cache.generate_key('user:profile', user_id=refreshed['id']))  # 清除該用戶的個人信息緩存
    logger.info(f"已清除用戶緩存（用戶 {username} 已更新）")
    
    return jsonify({
        'success': True,
        'user': {
            'username': refreshed['username'],
            'name': refreshed.get('full_name') or '',
            'role': refreshed['role'],
            'active': bool(refreshed.get('is_active')),
            'current_password': refreshed.get('password_plaintext') or '',
            'job_nos': job_nos,
            'created_at': refreshed.get('created_at'),
            'updated_at': refreshed.get('updated_at'),
            'password_days_remaining': password_days_remaining,
            'password_expires_at': refreshed.get('password_expires_at')
        }
    })


@app.route('/api/admin/users/<username>', methods=['DELETE'])
@require_auth('admin')
def delete_user(username):
    """管理员：删除普通账号"""
    username = (username or '').strip()
    if not username:
        return jsonify({'success': False, 'error': 'Username is required'}), 400

    if username.lower() == 'admin':
        return jsonify({'success': False, 'error': 'Administrator account cannot be deleted'}), 400

    current_admin = g.current_user
    if current_admin and current_admin.get('username') == username:
        return jsonify({'success': False, 'error': 'You cannot delete your own account'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, role FROM user_accounts WHERE username = ?", (username,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'error': 'User not found'}), 404

    # 允许删除'user'和'manager'角色，但不允许删除'admin'
    if row['role'] == 'admin':
        conn.close()
        return jsonify({'success': False, 'error': 'Administrator account cannot be deleted'}), 400

    cursor.execute("DELETE FROM user_accounts WHERE id = ?", (row['id'],))
    conn.commit()
    conn.close()
    
    # 清除相關緩存（用戶已刪除）
    cache.delete('admin:users:list')  # 清除用戶列表緩存
    cache.delete(f"user:profile:user_id:{row['id']}")  # 清除該用戶的個人信息緩存
    logger.info(f"已清除用戶緩存（用戶 {username} 已刪除）")
    
    return jsonify({'success': True, 'message': f'User {username} has been removed'})


@app.route('/api/admin/users/<username>/reset-password', methods=['POST'])
@require_auth('admin')
@limiter.limit("3 per hour") if limiter else (lambda f: f)
def reset_user_password(username):
    """管理员：重置用户密码（自动生成10位强密码）"""
    username = (username or '').strip()
    if not username:
        return jsonify({'success': False, 'error': 'Username is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    user = _fetch_user(conn, username=username)
    if not user:
        conn.close()
        return jsonify({'success': False, 'error': 'User not found'}), 404

    # 生成10位随机强密码
    new_password = _generate_random_password(10)
    salt, password_hash = _generate_password_hash(new_password)
    
    # 更新密码和过期时间
    now = datetime.now()
    password_changed_at = now.isoformat()
    
    # 仅对普通用户和manager设置过期时间，admin不过期
    if user['role'] in ('user', 'manager'):
        password_expires_at = (now + timedelta(days=PASSWORD_EXPIRY_DAYS)).isoformat()
    else:
        password_expires_at = None
    
    cursor.execute(
        """
        UPDATE user_accounts 
        SET password_hash = ?, password_salt = ?, password_plaintext = ?, password_changed_at = ?, password_expires_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE username = ?
        """,
        (password_hash, salt, new_password, password_changed_at, password_expires_at, username)
    )
    
    conn.commit()
    conn.close()
    
    # 返回新生成的密码（仅此一次，用于显示给管理员）
    return jsonify({
        'success': True,
        'new_password': new_password,
        'message': f'Password has been reset for user {username}. New password: {new_password}'
    })


def regenerate_orders_gen_pdf():
    """
    重新生成Orders_gen_pdf表
    当TR_Fill_in表发生变化时，调用此函数同步更新Orders_gen_pdf表
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查TR_Fill_in表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='TR_Fill_in'")
        if cursor.fetchone() is None:
            logger.warning("TR_Fill_in表不存在，跳过Orders_gen_pdf更新")
            conn.close()
            return {'success': False, 'reason': 'TR_Fill_in表不存在'}
        
        # 检查TR_Fill_in表是否有数据
        cursor.execute("SELECT COUNT(*) FROM TR_Fill_in")
        tr_fill_in_count = cursor.fetchone()[0]
        if tr_fill_in_count == 0:
            logger.warning("TR_Fill_in表为空，删除Orders_gen_pdf表（如果有）")
            cursor.execute("DROP TABLE IF EXISTS Orders_gen_pdf")
            conn.commit()
            conn.close()
            return {'success': True, 'reason': 'TR_Fill_in表为空，已清空Orders_gen_pdf表', 'count': 0}
        
        # 检查orders_com表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders_com'")
        if cursor.fetchone() is None:
            logger.warning("orders_com表不存在，跳过Orders_gen_pdf更新")
            conn.close()
            return {'success': False, 'reason': 'orders_com表不存在'}
        
        print(f"[INFO] 开始重新生成Orders_gen_pdf表，TR_Fill_in有 {tr_fill_in_count} 条记录")
        
        # 删除已存在的表
        cursor.execute("DROP TABLE IF EXISTS Orders_gen_pdf")
        
        # 创建新表
        create_table_sql = """
        CREATE TABLE Orders_gen_pdf AS
        SELECT 
            tf.Dia,
            oc.Wt as 'Wt(ton)',
            tf.Product,
            oc.Grade,
            tf.Pattern,
            tf.Mill_Cert,
            tf.Test_Cert2,
            tf.Test_Cert1,
            'VSC STEEL COMPANY LTD' as Supplier,
            tf.Stockist_Cert,
            tf.PO_No as 'PO_No(1)',
            tf.Tag_No,
            tf.DN_No,
            oc.Client,
            oc.Jobsite,
            oc.Jobsite_Type,
            oc.Job_No,
            oc.PO_No as 'PO_No(2)',
            oc.Order_No,
            oc.Del_Date,
            oc.Ref_No,
            oc.Order_Description
        FROM TR_Fill_in tf
        INNER JOIN orders_com oc ON tf.Dia = oc.Dia
        """
        
        cursor.execute(create_table_sql)
        conn.commit()
        
        # 检查生成结果
        cursor.execute("SELECT COUNT(*) FROM Orders_gen_pdf")
        count = cursor.fetchone()[0]
        
        print(f"[OK] Orders_gen_pdf表重新生成成功: {count} 行")
        conn.close()
        
        return {'success': True, 'count': count}
        
    except Exception as e:
        logger.error(f"重新生成Orders_gen_pdf表失败: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        try:
            conn.close()
        except:
            pass
        return {'success': False, 'error': str(e)}


@app.route('/api/tr-fill-in/data', methods=['GET'])
def get_all_data():
    """获取TR_Fill_in表中的所有数据"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM TR_Fill_in ORDER BY id")
        rows = cursor.fetchall()
        conn.close()
        
        # 转换为字典列表
        data = []
        for row in rows:
            data.append(dict(row))
        
        return jsonify({
            'success': True,
            'data': data,
            'count': len(data)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/tr-fill-in/save', methods=['POST'])
def save_data():
    """
    保存选择的Tag No到TR_Fill_in表
    请求体：{"tag_nos": ["410340", "403825", "362764"]}
    """
    try:
        data = request.get_json()
        tag_nos = data.get('tag_nos', [])
        
        if not tag_nos:
            return jsonify({
                'success': False,
                'error': 'No tag numbers provided'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 从materials_com查询数据
        placeholders = ','.join('?' * len(tag_nos))
        query = f"""
        SELECT Dia, Len, Product, Pattern, Mill_Cert, Test_Cert2, Test_Cert1, 
               Stockist_Cert, PO_No, Tag_No, DN_No
        FROM materials_com
        WHERE Tag_No IN ({placeholders})
        """
        
        materials_data = cursor.execute(query, tag_nos).fetchall()
        
        if not materials_data:
            return jsonify({
                'success': False,
                'error': 'No data found for the provided tag numbers'
            }), 404
        
        # 插入到TR_Fill_in表
        inserted_count = 0
        skipped_count = 0
        
        insert_sql = """
        INSERT OR IGNORE INTO TR_Fill_in 
        (Dia, Len, Product, Pattern, Tag_No, Mill_Cert, Test_Cert1, Test_Cert2, Stockist_Cert, PO_No, DN_No, Grade)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        for row in materials_data:
            try:
                # materials_com表没有Grade字段，所以设为NULL
                # Grade会在生成Orders_gen_pdf时从orders_com表获取
                cursor.execute(insert_sql, (
                    row['Dia'],
                    row['Len'],
                    row['Product'],
                    row['Pattern'],
                    row['Tag_No'],
                    row['Mill_Cert'],
                    row['Test_Cert1'],
                    row['Test_Cert2'],
                    row['Stockist_Cert'],
                    row['PO_No'],
                    row['DN_No'],
                    None  # Grade字段，从materials_com无法获取，设为NULL
                ))
                if cursor.rowcount > 0:
                    inserted_count += 1
                else:
                    skipped_count += 1
            except Exception as e:
                print(f"Error inserting tag {row['Tag_No']}: {e}")
                skipped_count += 1
        
        conn.commit()
        conn.close()
        
        # 如果成功插入新记录，触发Orders_gen_pdf表的更新
        if inserted_count > 0:
            print(f"[INFO] TR_Fill_in表已更新（新增{inserted_count}条记录），开始同步Orders_gen_pdf表...")
            regenerate_result = regenerate_orders_gen_pdf()
            if regenerate_result['success']:
                logger.info(f"Orders_gen_pdf表同步成功，当前记录数: {regenerate_result.get('count', 0)}")
            else:
                logger.warning(f"Orders_gen_pdf表同步失败: {regenerate_result.get('error', '未知错误')}")
        
        return jsonify({
            'success': True,
            'message': f'Inserted {inserted_count} new records, skipped {skipped_count} duplicates',
            'inserted': inserted_count,
            'skipped': skipped_count
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/tr-fill-in/delete', methods=['POST'])
def delete_data():
    """
    删除指定的Tag No
    请求体：{"tag_nos": ["410340"]}
    """
    try:
        data = request.get_json()
        tag_nos = data.get('tag_nos', [])
        
        if not tag_nos:
            return jsonify({
                'success': False,
                'error': 'No tag numbers provided'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(tag_nos))
        delete_sql = f"DELETE FROM TR_Fill_in WHERE Tag_No IN ({placeholders})"
        
        cursor.execute(delete_sql, tag_nos)
        conn.commit()
        deleted_count = cursor.rowcount
        conn.close()
        
        # 如果成功删除记录，触发Orders_gen_pdf表的更新
        if deleted_count > 0:
            print(f"[INFO] TR_Fill_in表已更新（删除{deleted_count}条记录），开始同步Orders_gen_pdf表...")
            regenerate_result = regenerate_orders_gen_pdf()
            if regenerate_result['success']:
                logger.info(f"Orders_gen_pdf表同步成功，当前记录数: {regenerate_result.get('count', 0)}")
            else:
                logger.warning(f"Orders_gen_pdf表同步失败: {regenerate_result.get('error', '未知错误')}")
            
            # 清除訂單列表緩存（數據已更新）
            cache.delete('orders:list:*')
            logger.info("已清除訂單列表緩存（數據已更新）")
        
        return jsonify({
            'success': True,
            'message': f'Deleted {deleted_count} records',
            'deleted': deleted_count
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/tr-fill-in/clear', methods=['POST'])
def clear_data():
    """清空TR_Fill_in表"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM TR_Fill_in")
        conn.commit()
        conn.close()
        
        # 清空TR_Fill_in表后，触发Orders_gen_pdf表的更新（会清空Orders_gen_pdf表）
        print(f"[INFO] TR_Fill_in表已清空，开始同步Orders_gen_pdf表...")
        regenerate_result = regenerate_orders_gen_pdf()
        if regenerate_result['success']:
            print(f"[OK] Orders_gen_pdf表同步成功，当前记录数: {regenerate_result.get('count', 0)}")
        else:
            print(f"[WARNING] Orders_gen_pdf表同步失败: {regenerate_result.get('error', '未知错误')}")
        
        # 清除訂單列表緩存（數據已更新）
        cache.delete('orders:list:*')
        logger.info("已清除訂單列表緩存（數據已清空）")
        
        return jsonify({
            'success': True,
            'message': 'TR_Fill_in table cleared'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/tr-fill-in/update', methods=['POST'])
def update_data():
    """
    更新指定Tag No的数据
    请求体：{"tag_no": "410340", "data": {"Dia": "Y20", "Len": "15m", ...}}
    """
    try:
        data = request.get_json()
        tag_no = data.get('tag_no')
        update_data = data.get('data', {})
        
        if not tag_no:
            return jsonify({
                'success': False,
                'error': 'No tag number provided'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 构建更新语句
        set_clauses = []
        values = []
        
        allowed_fields = ['Dia', 'Len', 'Product', 'Pattern', 'Mill_Cert', 
                         'Test_Cert1', 'Test_Cert2', 'Stockist_Cert', 'PO_No', 'DN_No', 'Grade']
        
        for field, value in update_data.items():
            if field in allowed_fields:
                set_clauses.append(f"{field} = ?")
                values.append(value)
        
        if not set_clauses:
            return jsonify({
                'success': False,
                'error': 'No valid fields to update'
            }), 400
        
        # 添加更新时间
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values.append(tag_no)
        
        update_sql = f"""
        UPDATE TR_Fill_in 
        SET {', '.join(set_clauses)}
        WHERE Tag_No = ?
        """
        
        cursor.execute(update_sql, values)
        updated_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        # 如果成功更新记录，触发Orders_gen_pdf表的更新
        if updated_count > 0:
            print(f"[INFO] TR_Fill_in表已更新（更新{updated_count}条记录），开始同步Orders_gen_pdf表...")
            regenerate_result = regenerate_orders_gen_pdf()
            if regenerate_result['success']:
                logger.info(f"Orders_gen_pdf表同步成功，当前记录数: {regenerate_result.get('count', 0)}")
            else:
                logger.warning(f"Orders_gen_pdf表同步失败: {regenerate_result.get('error', '未知错误')}")
            
            # 清除訂單列表緩存（數據已更新）
            cache.delete('orders:list:*')
            logger.info("已清除訂單列表緩存（數據已更新）")
        
        return jsonify({
            'success': True,
            'message': 'Data updated successfully',
            'updated': updated_count
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/orders-gen-pdf/regenerate', methods=['POST'])
def regenerate_orders_gen_pdf_endpoint():
    """
    手动触发Orders_gen_pdf表的重新生成
    用于手动同步或批量修改后的同步
    """
    try:
        print("[INFO] 收到手动触发Orders_gen_pdf表重新生成的请求")
        result = regenerate_orders_gen_pdf()
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'Orders_gen_pdf表重新生成成功',
                'count': result.get('count', 0),
                'reason': result.get('reason', '')
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', result.get('reason', '未知错误'))
            }), 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/materials/search/<tag_no>', methods=['GET'])
def search_material(tag_no):
    """
    搜索materials_com表中的Tag No
    从data_3years.db的materials_com表中查询
    """
    try:
        # 生成緩存鍵
        cache_key = cache.generate_key('materials:search', tag_no=tag_no)
        
        # 嘗試從緩存獲取
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"材料搜索緩存命中: {cache_key}")
            return jsonify(cached_result)
        
        # 调试：打印实际使用的数据库路径
        if DEBUG_MODE:
            print(f"[DEBUG] Using database: {DB_PATH}")
            print(f"[DEBUG] Database exists: {os.path.exists(DB_PATH)}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='materials_com'")
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            # 列出所有表以便调试
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            all_tables = [row[0] for row in cursor.fetchall()]
            error_msg = f"Table 'materials_com' does not exist in database. Available tables: {', '.join(all_tables)}"
            logger.error(error_msg)
            logger.error(f"Database path: {DB_PATH}")
            conn.close()
            return jsonify({
                'found': False,
                'error': error_msg,
                'database_path': DB_PATH,
                'available_tables': all_tables
            }), 500
        
        # 尝试将tag_no转换为整数（因为Tag_No在数据库中是INTEGER类型）
        try:
            tag_no_int = int(tag_no)
        except (ValueError, TypeError):
            tag_no_int = None
        
        # 查询materials_com表（在data_3years.db中）
        # 使用CAST确保类型匹配，同时支持字符串和整数查询
        if tag_no_int is not None:
            # 优先使用整数查询（更高效）
            query = """
            SELECT Dia, Len, Product, Pattern, Mill_Cert, Test_Cert2, Test_Cert1, 
                   Stockist_Cert, PO_No, Tag_No, DN_No
            FROM materials_com
            WHERE Tag_No = ?
            LIMIT 1
            """
            cursor.execute(query, (tag_no_int,))
        else:
            # 如果无法转换为整数，使用CAST查询
            query = """
            SELECT Dia, Len, Product, Pattern, Mill_Cert, Test_Cert2, Test_Cert1, 
                   Stockist_Cert, PO_No, Tag_No, DN_No
            FROM materials_com
            WHERE CAST(Tag_No AS TEXT) = ?
            LIMIT 1
            """
            cursor.execute(query, (tag_no,))
        
        row = cursor.fetchone()
        
        # 调试日志（仅在DEBUG模式下）
        if DEBUG_MODE:
            print(f"[DEBUG] Searching Tag_No: {tag_no} (as int: {tag_no_int})")
            print(f"[DEBUG] Query returned: {row is not None}")
        
        if row:
            # 将Row对象转换为字典
            data = {
                'Dia': row['Dia'] if row['Dia'] else '',
                'Len': row['Len'] if row['Len'] else '',
                'Product': row['Product'] if row['Product'] else '',
                'Pattern': row['Pattern'] if row['Pattern'] else '',
                'Mill_Cert': row['Mill_Cert'] if row['Mill_Cert'] else '',
                'Test_Cert2': row['Test_Cert2'] if row['Test_Cert2'] else '',
                'Test_Cert1': row['Test_Cert1'] if row['Test_Cert1'] else '',
                'Stockist_Cert': row['Stockist_Cert'] if row['Stockist_Cert'] else '',
                'PO_No': row['PO_No'] if row['PO_No'] else '',
                'Tag_No': str(row['Tag_No']) if row['Tag_No'] else '',
                'DN_No': row['DN_No'] if row['DN_No'] else ''
            }
            conn.close()
            
            # 構建響應
            result = {
                'found': True,
                'data': data
            }
            
            # 保存到緩存（1小時，材料數據非常穩定）
            cache.set(cache_key, result, ttl=3600)
            logger.debug(f"材料搜索緩存已保存: {cache_key}")
            
            return jsonify(result)
        else:
            conn.close()
            
            # 構建響應（未找到也緩存，避免重複查詢）
            result = {
                'found': False,
                'data': None,
                'message': f'Tag No {tag_no} not found in materials_com'
            }
            
            # 保存到緩存（30分鐘，避免重複查詢不存在的數據）
            cache.set(cache_key, result, ttl=1800)
            logger.debug(f"材料搜索緩存已保存（未找到）: {cache_key}")
            
            return jsonify(result)
            
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        return jsonify({
            'found': False,
            'error': error_msg
        }), 500


def get_bbs_dd_list(page, per_page_param, order_no, job_no, dn_no, start_date, end_date, conn, cursor):
    """
    从 bbs_dd 表获取订单列表（用于 Stocklist&Test Report 标签页）
    性能优化版本：减少 CAST 操作，优化查询条件
    """
    try:
        # 确保索引存在（首次调用时创建）
        _ensure_bbs_dd_indexes(conn, cursor)
        
        # 检查PDF_Status表是否存在
        pdf_status_exists = check_pdf_status_table_exists(conn)
        
        # 构建WHERE子句（优化：减少 CAST 操作）
        where_conditions = []
        params = []
        
        if order_no:
            # 优化：尝试使用数值比较，避免 CAST
            try:
                order_no_int = int(order_no)
                where_conditions.append("b.bbs_no = ?")
                params.append(order_no_int)
            except (ValueError, TypeError):
                # 如果不是纯数字，使用 LIKE（但避免通配符开头以使用索引）
                where_conditions.append("CAST(b.bbs_no AS TEXT) LIKE ?")
                params.append(f"{order_no}%")  # 改为 value% 而不是 %value%
        
        if job_no:
            # 优化：尝试使用数值比较
            try:
                job_no_int = int(job_no)
                where_conditions.append("b.jobsite_no = ?")
                params.append(job_no_int)
            except (ValueError, TypeError):
                where_conditions.append("CAST(b.jobsite_no AS TEXT) LIKE ?")
                params.append(f"{job_no}%")  # 改为 value% 而不是 %value%
        
        if dn_no:
            # 优化：尝试使用数值比较
            try:
                dn_no_int = int(dn_no)
                where_conditions.append("b.dd_no = ?")
                params.append(dn_no_int)
            except (ValueError, TypeError):
                where_conditions.append("CAST(b.dd_no AS TEXT) LIKE ?")
                params.append(f"{dn_no}%")  # 改为 value% 而不是 %value%
        
        if start_date:
            where_conditions.append("b.dd_delivery_date >= ?")
            params.append(start_date)
        
        if end_date:
            where_conditions.append("b.dd_delivery_date <= ?")
            params.append(end_date)
        
        # 普通账号只能看到授权范围内的Job No
        # 优化：使用数值比较而不是 CAST
        current_user = get_current_user(optional=True)
        if current_user and current_user.get('role') == 'user':
            scoped_jobs = _fetch_user_job_nos(conn, current_user['id'])
            if scoped_jobs:
                placeholders = ','.join('?' * len(scoped_jobs))
                where_conditions.append(f"b.jobsite_no IN ({placeholders})")
                params.extend(scoped_jobs)  # 直接使用数值，不需要转换为字符串
            else:
                where_conditions.append("1 = 0")
        
        # 构建WHERE子句
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # 根据PDF_Status表是否存在构建不同的查询
        # 优化：COUNT 查询不需要 JOIN，可以更快
        if pdf_status_exists:
            # COUNT 查询：不需要 JOIN，提升性能
            count_query = f"""
                SELECT COUNT(*) 
                FROM bbs_dd b
                {where_clause}
            """
            # 主查询：需要 JOIN 获取 PDF 状态
            # 优化：PDF_Status.Order_No 是 INTEGER，bbs_dd.bbs_no 也应该是数值类型
            # 直接使用数值比较，避免 CAST
            query = f"""
            SELECT 
                b.bbs_no AS Order_No,
                b.jobsite_no AS Job_No,
                b.order_desc AS Order_Description,
                b.jobsite_type AS Jobsite_Type,
                b.dd_no AS rm_dn_no,
                b.dd_delivery_date AS Del_Date,
                COALESCE(p.pdf_status, 'pending') as pdf_status,
                p.pdf_path,
                p.generated_at
            FROM bbs_dd b
            LEFT JOIN PDF_Status p ON b.bbs_no = p.Order_No
            {where_clause}
            ORDER BY b.dd_delivery_date DESC
            LIMIT ? OFFSET ?
            """
        else:
            count_query = f"""
                SELECT COUNT(*) 
                FROM bbs_dd b
                {where_clause}
            """
            query = f"""
            SELECT 
                b.bbs_no AS Order_No,
                b.jobsite_no AS Job_No,
                b.order_desc AS Order_Description,
                b.jobsite_type AS Jobsite_Type,
                b.dd_no AS rm_dn_no,
                b.dd_delivery_date AS Del_Date,
                'pending' as pdf_status,
                NULL as pdf_path,
                NULL as generated_at
            FROM bbs_dd b
            {where_clause}
            ORDER BY b.dd_delivery_date DESC
            LIMIT ? OFFSET ?
            """
        
        # 添加调试信息
        try:
            print("[DEBUG] /api/orders/list (bbs_dd) - Executing count query")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()[0]
        
        try:
            print(f"[DEBUG] /api/orders/list (bbs_dd) - Total records: {total_records}")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        
        # 处理 per_page 参数
        try:
            if per_page_param == 'all':
                per_page = total_records or 1
            else:
                per_page = int(per_page_param)
                if per_page <= 0:
                    per_page = 1
        except (ValueError, TypeError):
            per_page = 100
        
        # 计算分页
        offset = (page - 1) * per_page
        total_pages = max((total_records + per_page - 1) // per_page, 1)
        
        # 执行查询
        query_params = params + [per_page, offset]
        try:
            print(f"[DEBUG] /api/orders/list (bbs_dd) - Executing query with limit={per_page}, offset={offset}")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        
        import time
        start_time = time.time()
        cursor.execute(query, query_params)
        execution_time = time.time() - start_time
        try:
            print(f"[DEBUG] /api/orders/list (bbs_dd) - Query executed in {execution_time:.2f} seconds")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        
        rows = cursor.fetchall()
        try:
            print(f"[DEBUG] /api/orders/list (bbs_dd) - Fetched {len(rows)} rows")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        
        # 转换为字典列表
        data = []
        for row in rows:
            # 从 bbs_dd 表获取的 dd_no 直接使用，不做任何过滤
            dd_no_value = row['rm_dn_no'] or ''
            data.append({
                'Order_No': row['Order_No'],
                'Job_No': row['Job_No'],
                'Order_Description': row['Order_Description'] or '',
                'Jobsite_Type': row['Jobsite_Type'] or '',
                'rm_dn_no': dd_no_value,
                'Del_Date': row['Del_Date'] or '',
                'pdf_status': row['pdf_status'] or 'pending',
                'pdf_path': row['pdf_path'],
                'generated_at': row['generated_at']
            })
        
        # 注意：不要在这里关闭连接，连接是在调用函数之前创建的
        # conn.close()  # 移除这行
        
        return jsonify({
            'success': True,
            'data': data,
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total_records': total_records,
                'total_pages': total_pages
            },
            'count': len(data)
        })
        
    except Exception as e:
        if conn:
            conn.close()
        import traceback
        error_trace = traceback.format_exc()
        try:
            print(f"Error getting bbs_dd list: {error_trace}")
        except (UnicodeEncodeError, UnicodeDecodeError):
            logger.error(f"Error getting bbs_dd list: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/orders/list', methods=['GET'])
def get_orders_list():
    """
    获取订单列表
    支持分页：?page=1&per_page=100
    支持搜索：
      - order_no: 搜索Order No
      - job_no: 搜索Job No  
      - start_date: 开始日期
      - end_date: 结束日期
      - tab: 标签页类型 ('records' 使用 TR_Report_Deduplication, 'stocklist-test' 使用 bbs_dd)
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page_param = request.args.get('per_page', 100)
        
        # 获取标签页类型
        tab = request.args.get('tab', 'records').strip()
        
        # 获取搜索参数
        order_no = request.args.get('order_no', '').strip()
        job_no = request.args.get('job_no', '').strip()
        dn_no = request.args.get('dn_no', '').strip()
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()
        
        # 獲取當前用戶（用於緩存鍵）
        current_user = get_current_user(optional=True)
        user_id = current_user.get('id') if current_user else 'anonymous'
        user_role = current_user.get('role') if current_user else 'anonymous'
        
        # 生成緩存鍵
        cache_key = cache.generate_key(
            'orders:list',
            page=page,
            per_page=per_page_param,
            tab=tab,
            order_no=order_no,
            job_no=job_no,
            dn_no=dn_no,
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            user_role=user_role
        )
        
        # 嘗試從緩存獲取
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            try:
                logger.debug(f"Orders list cache hit: {cache_key}")
            except (UnicodeEncodeError, UnicodeDecodeError):
                logger.debug(f"Orders list cache hit: {cache_key}")
            return jsonify(cached_result)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 如果是 stocklist-test 标签页，使用 bbs_dd 表
        if tab == 'stocklist-test':
            return get_bbs_dd_list(
                page,
                per_page_param,
                order_no,
                job_no,
                dn_no,
                start_date,
                end_date,
                conn,
                cursor
            )
        
        # 检查PDF_Status表是否存在
        pdf_status_exists = check_pdf_status_table_exists(conn)
        
        # 构建WHERE子句
        where_conditions = []
        params = []
        
        if order_no:
            where_conditions.append("CAST(o.Order_No AS TEXT) LIKE ?")
            params.append(f"%{order_no}%")
        
        if job_no:
            where_conditions.append("o.Job_No LIKE ?")
            params.append(f"%{job_no}%")
        
        if dn_no:
            where_conditions.append("CAST(o.rm_dn_no AS TEXT) LIKE ?")
            params.append(f"%{dn_no}%")
        
        if start_date:
            where_conditions.append("o.Del_Date >= ?")
            params.append(start_date)
        
        if end_date:
            where_conditions.append("o.Del_Date <= ?")
            params.append(end_date)

        # 普通账号只能看到授权范围内的Job No
        # manager和admin可以看到所有记录
        if current_user and current_user.get('role') == 'user':
            scoped_jobs = _fetch_user_job_nos(conn, current_user['id'])
            if scoped_jobs:
                placeholders = ','.join('?' * len(scoped_jobs))
                where_conditions.append(f"o.Job_No IN ({placeholders})")
                params.extend(scoped_jobs)
            else:
                where_conditions.append("1 = 0")
        
        # 构建WHERE子句
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # 根据PDF_Status表是否存在构建不同的查询
        # DD_No和Del_Date优先从bbs_dd表获取，如果不存在则使用TR_Report_Deduplication表的值
        if pdf_status_exists:
            # PDF_Status表存在：使用LEFT JOIN
            count_query = f"""
                SELECT COUNT(*) 
                FROM TR_Report_Deduplication o
                LEFT JOIN PDF_Status p ON o.Order_No = p.Order_No
                {where_clause}
            """
            # 简化查询：先不使用 bbs_dd JOIN，确保查询快速返回
            query = f"""
            SELECT 
                o.Order_No, 
                o.Client, 
                o.Jobsite,
                o.Jobsite_Type,
                o.Job_No, 
                o.PO_No, 
                o.Del_Date, 
                o.Ref_No, 
                o.Order_Description, 
                o.Grade, 
                o.Wt,
                o.rm_dn_no,
                COALESCE(p.pdf_status, 'pending') as pdf_status,
                p.pdf_path,
                p.generated_at
            FROM TR_Report_Deduplication o
            LEFT JOIN PDF_Status p ON o.Order_No = p.Order_No
            {where_clause}
            ORDER BY o.Del_Date DESC, o.Order_No DESC
            LIMIT ? OFFSET ?
            """
        else:
            # PDF_Status表不存在：不JOIN任何表，直接查询
            count_query = f"""
                SELECT COUNT(*) 
                FROM TR_Report_Deduplication o
                {where_clause}
            """
            # 简化查询：暂时不 JOIN bbs_dd，直接使用 TR_Report_Deduplication 表的数据
            # 这样可以确保查询快速返回
            query = f"""
            SELECT 
                o.Order_No, 
                o.Client, 
                o.Jobsite,
                o.Jobsite_Type,
                o.Job_No, 
                o.PO_No, 
                o.Del_Date, 
                o.Ref_No, 
                o.Order_Description, 
                o.Grade, 
                o.Wt,
                o.rm_dn_no,
                'pending' as pdf_status,
                NULL as pdf_path,
                NULL as generated_at
            FROM TR_Report_Deduplication o
            {where_clause}
            ORDER BY o.Del_Date DESC, o.Order_No DESC
            LIMIT ? OFFSET ?
            """
        
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()[0]
        
        # 调试信息：打印总记录数和用户信息
        print(f"[DEBUG] /api/orders/list - User: {user_role}, Total records: {total_records}, Params: {params}")
        
        # 处理 per_page 参数
        try:
            if per_page_param == 'all':
                per_page = total_records or 1
            else:
                per_page = int(per_page_param)
                if per_page <= 0:
                    per_page = 1
        except (ValueError, TypeError):
            per_page = 100
        
        # 计算总页数
        if total_records == 0:
            total_pages = 1
            page = 1
            offset = 0
        else:
            total_pages = max((total_records + per_page - 1) // per_page, 1)
            if page < 1:
                page = 1
            if page > total_pages:
                page = total_pages
            offset = (page - 1) * per_page
        
        # 添加LIMIT和OFFSET的参数
        query_params = params + [per_page, offset]
        
        # 调试信息：打印查询参数
        print(f"[DEBUG] /api/orders/list - Executing query with params: limit={per_page}, offset={offset}, param_count={len(params)}")
        print(f"[DEBUG] /api/orders/list - Query preview (first 200 chars): {query[:200]}")
        
        try:
            # 设置查询超时（SQLite的busy_timeout已经在连接时设置了，但这里添加额外的超时检查）
            import time
            start_time = time.time()
            print(f"[DEBUG] /api/orders/list - Starting query execution at {start_time}")
            
            cursor.execute(query, query_params)
            
            execution_time = time.time() - start_time
            print(f"[DEBUG] /api/orders/list - Query executed in {execution_time:.2f} seconds")
            
            rows = cursor.fetchall()
            fetch_time = time.time() - start_time - execution_time
            print(f"[DEBUG] /api/orders/list - Fetched {len(rows)} rows (fetch took {fetch_time:.2f}s, total {time.time() - start_time:.2f}s)")
            
            # 如果查询返回空结果，打印警告
            if len(rows) == 0:
                logger.warning(f"/api/orders/list - Query returned 0 rows, but total_records={total_records}")
        except Exception as query_error:
            logger.error(f"/api/orders/list - Query execution failed: {query_error}")
            logger.error(f"Query: {query[:500]}...")  # 打印前500个字符
            logger.error(f"Params: {query_params}")
            import traceback
            traceback.print_exc()
            conn.close()
            raise
        
        # 转换为字典列表
        data = []
        for row in rows:
            row_dict = dict(row)
            # 调试：打印第一条记录的Client字段
            if len(data) == 0:
                print(f"[DEBUG] /api/orders/list - First record: Order_No={row_dict.get('Order_No')}, Client={row_dict.get('Client')}, Jobsite={row_dict.get('Jobsite')}")
            data.append(row_dict)
        
        conn.close()
        
        # 调试信息：打印分页信息
        print(f"[DEBUG] /api/orders/list - Returning pagination: total_records={total_records}, total_pages={total_pages}, current_page={page}, per_page={per_page}, data_count={len(data)}")
        
        # 检查Client字段
        if len(data) > 0:
            sample_client = data[0].get('Client')
            print(f"[DEBUG] /api/orders/list - Sample Client value: '{sample_client}' (type: {type(sample_client)})")
        
        # 構建響應
        response_data = {
            'success': True,
            'data': data,
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total_records': total_records,
                'total_pages': total_pages
            },
            'search_params': {
                'order_no': order_no,
                'job_no': job_no,
                'start_date': start_date,
                'end_date': end_date
            },
            'count': len(data)
        }
        
        # 保存到緩存（5分鐘）
        cache.set(cache_key, response_data, ttl=300)
        logger.debug(f"訂單列表緩存已保存: {cache_key}")
        
        return jsonify(response_data)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"/api/orders/list - Exception occurred: {str(e)}")
        logger.error(f"Traceback:\n{error_trace}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/orders/group-by-job-no', methods=['GET'])
def group_by_job_no():
    """
    按Job_No分组统计订单
    支持搜索参数：
      - order_no: 搜索Order No
      - job_no: 搜索Job No
      - start_date: 开始日期
      - end_date: 结束日期
    """
    try:
        # 获取搜索参数
        order_no = request.args.get('order_no', '').strip()
        job_no = request.args.get('job_no', '').strip()
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 构建WHERE子句
        where_conditions = []
        params = []
        
        if order_no:
            where_conditions.append("Order_No LIKE ?")
            params.append(f"%{order_no}%")
        
        if job_no:
            where_conditions.append("Job_No LIKE ?")
            params.append(f"%{job_no}%")
        
        if start_date:
            where_conditions.append("Del_Date >= ?")
            params.append(start_date)
        
        if end_date:
            where_conditions.append("Del_Date <= ?")
            params.append(end_date)

        # manager和admin可以看到所有记录
        current_user = get_current_user(optional=True)
        if current_user and current_user.get('role') == 'user':
            scoped_jobs = _fetch_user_job_nos(conn, current_user['id'])
            if scoped_jobs:
                placeholders = ','.join('?' * len(scoped_jobs))
                where_conditions.append(f"Job_No IN ({placeholders})")
                params.extend(scoped_jobs)
            else:
                where_conditions.append("1 = 0")
        
        # 构建WHERE子句
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # 按Job_No分组统计
        query = f"""
        SELECT 
            Job_No,
            COUNT(*) as record_count,
            SUM(Wt) as total_weight,
            MIN(Del_Date) as earliest_date,
            MAX(Del_Date) as latest_date,
            GROUP_CONCAT(DISTINCT Client) as clients
        FROM TR_Report_Deduplication
        {where_clause}
        GROUP BY Job_No
        ORDER BY record_count DESC
        """
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # 转换为字典列表
        data = []
        for row in rows:
            data.append({
                'Job_No': row[0],
                'record_count': row[1],
                'total_weight': row[2],
                'earliest_date': row[3],
                'latest_date': row[4],
                'clients': row[5] if row[5] else ''
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'data': data,
            'count': len(data),
            'search_params': {
                'order_no': order_no,
                'job_no': job_no,
                'start_date': start_date,
                'end_date': end_date
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/pdf/generate', methods=['POST'])
@require_auth()
def generate_pdf():
    """
    创建 PDF 生成任务（异步模式）
    
    请求体：
    {
        "order_no": 123456
    }
    
    返回：
    {
        "success": true,
        "task_id": "550e8400-e29b-41d4-a716-446655440000",
        "order_no": 123456,
        "message": "PDF 生成任务已创建，正在后台处理"
    }
    """
    try:
        if PDFTaskManager is None:
            return jsonify({
                'success': False,
                'error': 'PDF task manager not available'
            }), 500
        
        current_user = g.current_user
        # 安全地获取 JSON 数据，避免编码问题
        try:
            data = request.get_json(silent=True) or {}
        except Exception as json_error:
            # 如果 JSON 解析失败，记录错误但不使用中文
            try:
                logger.error(f"Failed to parse JSON request: {json_error}")
            except:
                pass
            return jsonify({
                'success': False,
                'error': 'Invalid JSON request'
            }), 400
        order_no = data.get('order_no')
        
        if not order_no:
            return jsonify({
                'success': False,
                'error': 'Order No is required'
            }), 400
        
        user_id = current_user['id']
        
        # 创建任务管理器
        task_manager = PDFTaskManager(DB_PATH)
        
        # 创建任务
        task_id = task_manager.create_task(user_id, int(order_no))
        
        # 在后台线程中处理任务
        def process_task_async():
            try:
                task_manager.process_task(task_id, int(order_no))
            except Exception as e:
                try:
                    print(f"[PDF Task] Background processing failed: {e}")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
                import traceback
                traceback.print_exc()
        
        thread = threading.Thread(target=process_task_async, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'order_no': order_no,
            'message': 'PDF generation task created, processing in background'
        }), 202  # 202 Accepted
        
    except Exception as e:
        import traceback
        try:
            print(f"[Error] Failed to create PDF task: {e}")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/pdf/task-status/<task_id>', methods=['GET'])
@require_auth()
def get_pdf_task_status(task_id):
    """
    查询 PDF 生成任务状态
    
    返回：
    {
        "success": true,
        "task_id": "...",
        "order_no": 123456,
        "status": "processing",  // pending, processing, completed, failed
        "progress": 45,
        "message": "正在生成 PDF...",
        "pdf_path": "...",  // 仅当completed时
        "error_message": "..."  // 仅当failed时
    }
    """
    try:
        from pdf_task_manager import PDFTaskManager
        
        current_user = g.current_user
        user_id = current_user['id']
        
        task_manager = PDFTaskManager(DB_PATH)
        task_status = task_manager.get_task_status(task_id, user_id)
        
        if not task_status:
            return jsonify({
                'success': False,
                'error': '任务不存在或无权访问'
            }), 404
        
        result = {
            'success': True,
            'task_id': task_status['task_id'],
            'order_no': task_status['order_no'],
            'status': task_status['status'],
            'progress': task_status['progress'] or 0,
            'message': task_status.get('message', '')
        }
        
        # 根据状态添加额外信息
        if task_status['status'] == 'completed':
            result['pdf_path'] = task_status['pdf_path']
            result['pdf_status'] = 'generated'
            if not result['message']:
                result['message'] = 'PDF generated successfully'
            warning_markers = ['存在空数据', '空數據', 'warning', 'empty data']
            message_lower = str(result['message']).lower()
            if any(marker in result['message'] for marker in warning_markers[:2]) or any(marker in message_lower for marker in warning_markers[2:]):
                result['has_warning'] = True
                result['warning_message'] = result['message']
        elif task_status['status'] == 'failed':
            result['error_message'] = task_status.get('error_message', '')
            result['pdf_status'] = 'failed'
            if not result['message']:
                result['message'] = f'PDF generation failed: {result["error_message"]}'
        elif task_status['status'] == 'processing':
            if not result['message']:
                result['message'] = 'Processing...'
        else:
            if not result['message']:
                result['message'] = 'Waiting...'
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        try:
            print(f"[Error] Failed to query PDF task status: {e}")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/pdf/download/<int:order_no>', methods=['GET'])
@require_auth()
def download_pdf(order_no):
    """下载单个PDF文件"""
    try:
        # 查询PDF路径和状态
        conn = get_db_connection()
        cursor = conn.cursor()
        current_user = g.current_user
        job_scope = set()
        # manager和admin可以看到所有记录，不需要Job No过滤
        if current_user.get('role') == 'user':
            job_scope = set(_fetch_user_job_nos(conn, current_user['id']))
            if not job_scope:
                conn.close()
                return jsonify({
                    'success': False,
                    'error': 'No authorized Job No assigned to this account'
                }), 403

        cursor.execute("""
            SELECT 
                s.pdf_path, 
                s.pdf_status,
                d.Job_No,
                d.Del_Date
            FROM PDF_Status s
            LEFT JOIN TR_Report_Deduplication d ON d.Order_No = s.Order_No
            WHERE s.Order_No = ?
        """, (order_no,))
        result = cursor.fetchone()
        
        pdf_status = None
        pdf_path = None
        del_date = None
        
        if result:
            pdf_status = dict(result)
            pdf_path = pdf_status.get('pdf_path')
            del_date = pdf_status.get('Del_Date')
        
        # 如果PDF_Status表中没有记录，或者文件不存在，尝试查找文件
        backend_dir = os.path.dirname(__file__)
        abs_pdf_path = None
        
        if pdf_path:
            if not os.path.isabs(pdf_path):
                abs_pdf_path = os.path.normpath(os.path.join(backend_dir, pdf_path))
            else:
                abs_pdf_path = os.path.normpath(os.path.abspath(pdf_path))
        
        # 如果文件不存在，尝试根据Del_Date查找文件
        if not abs_pdf_path or not os.path.exists(abs_pdf_path):
            if not del_date:
                # 如果没有Del_Date，从TR_Report_Deduplication获取
                cursor.execute("""
                    SELECT Del_Date FROM TR_Report_Deduplication WHERE Order_No = ? LIMIT 1
                """, (order_no,))
                del_date_result = cursor.fetchone()
                if del_date_result:
                    del_date = dict(del_date_result).get('Del_Date')
            
            if del_date:
                # 清理日期字符串
                def sanitize_subdir_name(value):
                    if not value:
                        return 'Unknown_Date'
                    text = str(value).strip()
                    if not text:
                        return 'Unknown_Date'
                    safe = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '-' for ch in text)
                    safe = safe.strip('-_')
                    return safe or 'Unknown_Date'
                
                sanitized_date = sanitize_subdir_name(del_date)
                possible_paths = [
                    os.path.join(backend_dir, 'Generated_PDFs', sanitized_date, f'TR_{order_no}.pdf'),
                    os.path.join(backend_dir, 'Generated_PDFs', sanitized_date, f'Order_{order_no}.pdf'),
                ]
                
                found_path = None
                for possible_path in possible_paths:
                    if os.path.exists(possible_path):
                        found_path = possible_path
                        rel_path = os.path.relpath(possible_path, backend_dir)
                        # 更新或插入PDF_Status记录
                        cursor.execute("""
                            INSERT OR REPLACE INTO PDF_Status 
                            (Order_No, pdf_status, pdf_path, generated_at, updated_at)
                            VALUES (?, 'generated', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """, (order_no, rel_path))
                        conn.commit()
                        pdf_path = rel_path
                        abs_pdf_path = found_path
                        pdf_status = {'pdf_status': 'generated', 'pdf_path': rel_path, 'Job_No': pdf_status.get('Job_No') if pdf_status else None}
                        break
        
        if not pdf_status:
            conn.close()
            return jsonify({
                'success': False,
                'error': 'PDF not found for this order'
            }), 404
        
        # manager和admin可以下载所有PDF
        if current_user.get('role') == 'user':
            raw_job = pdf_status.get('Job_No')
            normalized_job = str(raw_job).strip().upper() if raw_job is not None else ''
            if not normalized_job or normalized_job not in job_scope:
                conn.close()
                return jsonify({
                    'success': False,
                    'error': 'You are not allowed to download this order'
                }), 403
        
        # 如果文件存在但状态不是generated，更新状态
        if abs_pdf_path and os.path.exists(abs_pdf_path) and pdf_status.get('pdf_status') != 'generated':
            try:
                cursor.execute("""
                    UPDATE PDF_Status 
                    SET pdf_status = 'generated', updated_at = CURRENT_TIMESTAMP
                    WHERE Order_No = ?
                """, (order_no,))
                conn.commit()
                pdf_status['pdf_status'] = 'generated'
            except Exception as update_error:
                logger.error(f"Failed to update PDF_Status for order {order_no}: {update_error}")
        
        # 检查状态
        if pdf_status.get('pdf_status') != 'generated':
            conn.close()
            return jsonify({
                'success': False,
                'error': f'PDF status is {pdf_status.get("pdf_status", "unknown")}, not generated yet'
            }), 400
        
        if not abs_pdf_path or not os.path.exists(abs_pdf_path):
            conn.close()
            print(f"[DEBUG] PDF path from DB: {pdf_path}")
            print(f"[DEBUG] Converted absolute path: {abs_pdf_path}")
            print(f"[DEBUG] File exists: {os.path.exists(abs_pdf_path) if abs_pdf_path else False}")
            return jsonify({
                'success': False,
                'error': 'PDF file not found on server. The file may have been moved or deleted. Please regenerate the PDF.',
                'pdf_path': pdf_path,
                'absolute_path': abs_pdf_path
            }), 404
        
        # 验证路径安全性（防止目录遍历攻击）
        # 确保路径在允许的目录内（TR UI/backend/Generated_PDFs）
        backend_dir = os.path.dirname(__file__)  # TR UI/backend
        allowed_dir = os.path.join(backend_dir, 'Generated_PDFs')
        abs_allowed_dir = os.path.normpath(os.path.abspath(allowed_dir))
        
        # 验证路径在允许目录内
        if not abs_pdf_path.startswith(abs_allowed_dir):
            conn.close()
            print(f"[DEBUG] Path validation failed:")
            print(f"[DEBUG] PDF path: {abs_pdf_path}")
            print(f"[DEBUG] Allowed dir: {abs_allowed_dir}")
            return jsonify({
                'success': False,
                'error': 'Invalid file path'
            }), 403
        
        # 使用转换后的绝对路径
        pdf_path = abs_pdf_path
        conn.close()
        
        # 返回PDF文件
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f'TR_{order_no}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error downloading PDF: {error_trace}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/pdf/batch-download', methods=['POST'])
@require_auth()
def batch_download_pdf():
    """批量下载PDF文件（打包为ZIP）"""
    try:
        data = request.json
        order_nos = data.get('order_nos', [])
        
        if not order_nos:
            return jsonify({
                'success': False,
                'error': 'No order numbers provided'
            }), 400
        
        # 限制批量下载数量
        if len(order_nos) > 200:
            return jsonify({
                'success': False,
                'error': 'Too many orders. Maximum 200 orders per batch download'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()

        current_user = g.current_user
        user_job_scope = set()
        # manager和admin可以批量下载所有PDF
        if current_user.get('role') == 'user':
            user_job_nos = _fetch_user_job_nos(conn, current_user['id'])
            # 统一转换为大写字符串进行比较
            user_job_scope = {str(job).strip().upper() for job in user_job_nos if job}
            if not user_job_scope:
                conn.close()
                return jsonify({
                    'success': False,
                    'error': 'No authorized Job No assigned to this account'
                }), 403
        
        # 查询所有订单的PDF路径
        # 统一转换为字符串，确保类型一致
        order_nos_str = [str(ono) for ono in order_nos]
        placeholders = ','.join('?' * len(order_nos_str))
        query = f"""
            SELECT 
                s.Order_No,
                s.pdf_path,
                s.pdf_status,
                d.Del_Date,
                d.Job_No
            FROM PDF_Status s
            LEFT JOIN TR_Report_Deduplication d ON CAST(d.Order_No AS TEXT) = CAST(s.Order_No AS TEXT)
            WHERE CAST(s.Order_No AS TEXT) IN ({placeholders})
        """
        
        try:
            cursor.execute(query, order_nos_str)
            results = cursor.fetchall()
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"批量下载查询失败: {error_trace}")
            logger.error(f"订单号列表: {order_nos_str}")
            conn.close()
            return jsonify({
                'success': False,
                'error': f'Database query failed: {str(e)}'
            }), 500
        
        if not results:
            conn.close()
            return jsonify({
                'success': False,
                'error': 'No PDF files found for the provided orders'
            }), 404
        
        # 收集有效的PDF文件
        pdf_files = []
        missing_files = []
        not_generated = []
        unauthorized_orders = []
        
        allowed_dir = os.path.join(os.path.dirname(DB_PATH), 'Generated_PDFs')
        abs_allowed_dir = os.path.normpath(os.path.abspath(allowed_dir))
        
        def sanitize_subdir_name(value):
            if not value:
                return 'Unknown_Date'
            text = str(value).strip()
            if not text:
                return 'Unknown_Date'
            safe = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '-' for ch in text)
            safe = safe.strip('-_')
            return safe or 'Unknown_Date'

        for row in results:
            pdf_info = dict(row)
            order_no = pdf_info['Order_No']
            pdf_status = pdf_info['pdf_status']
            pdf_path = pdf_info['pdf_path']
            del_date = pdf_info.get('Del_Date')
            raw_job = pdf_info.get('Job_No')
            job_no_value = str(raw_job).strip().upper() if raw_job is not None else ''
            
            # manager和admin可以下载所有订单
            if current_user.get('role') == 'user':
                if not job_no_value or job_no_value not in user_job_scope:
                    unauthorized_orders.append(order_no)
                    continue
            
            # 如果路径是相对路径，转换为基于backend目录的绝对路径
            # PDF实际保存在 TR UI/backend/Generated_PDFs
            if not pdf_path:
                # 如果没有路径，尝试根据Del_Date构建路径
                if del_date:
                    backend_dir = os.path.dirname(__file__)  # TR UI/backend
                    # 尝试构建可能的PDF路径
                    sanitized_date = sanitize_subdir_name(del_date)
                    possible_paths = [
                        os.path.join(backend_dir, 'Generated_PDFs', sanitized_date, f'TR_{order_no}.pdf'),
                        os.path.join(backend_dir, 'Generated_PDFs', sanitized_date, f'Order_{order_no}.pdf'),
                    ]
                    pdf_path = None
                    for possible_path in possible_paths:
                        if os.path.exists(possible_path):
                            pdf_path = os.path.relpath(possible_path, backend_dir)
                            # 更新数据库中的路径和状态
                            try:
                                cursor.execute("""
                                    UPDATE PDF_Status 
                                    SET pdf_path = ?, pdf_status = 'generated', updated_at = CURRENT_TIMESTAMP
                                    WHERE Order_No = ?
                                """, (pdf_path, order_no))
                                conn.commit()
                                pdf_status = 'generated'
                            except Exception as update_error:
                                logger.error(f"Failed to update PDF_Status for order {order_no}: {update_error}")
                            break
                
                if not pdf_path:
                    missing_files.append(order_no)
                    continue
            
            if not os.path.isabs(pdf_path):
                # 相对路径，基于backend目录（API服务器运行目录）
                backend_dir = os.path.dirname(__file__)  # TR UI/backend
                abs_pdf_path = os.path.normpath(os.path.join(backend_dir, pdf_path))
            else:
                # 已经是绝对路径
                abs_pdf_path = os.path.normpath(os.path.abspath(pdf_path))
            
            # 检查文件存在
            if not os.path.exists(abs_pdf_path):
                # 文件不存在，但如果状态是generated，可能是路径问题，尝试查找文件
                if pdf_status == 'generated':
                    # 尝试根据Del_Date查找文件
                    if del_date:
                        backend_dir = os.path.dirname(__file__)
                        sanitized_date = sanitize_subdir_name(del_date)
                        possible_paths = [
                            os.path.join(backend_dir, 'Generated_PDFs', sanitized_date, f'TR_{order_no}.pdf'),
                            os.path.join(backend_dir, 'Generated_PDFs', sanitized_date, f'Order_{order_no}.pdf'),
                        ]
                        found_path = None
                        for possible_path in possible_paths:
                            if os.path.exists(possible_path):
                                found_path = possible_path
                                # 更新数据库中的路径
                                try:
                                    rel_path = os.path.relpath(possible_path, backend_dir)
                                    cursor.execute("""
                                        UPDATE PDF_Status 
                                        SET pdf_path = ?, updated_at = CURRENT_TIMESTAMP
                                        WHERE Order_No = ?
                                    """, (rel_path, order_no))
                                    conn.commit()
                                    abs_pdf_path = found_path
                                except Exception as update_error:
                                    logger.error(f"Failed to update PDF_Status path for order {order_no}: {update_error}")
                                break
                        
                        if not found_path:
                            missing_files.append(order_no)
                            continue
                    else:
                        missing_files.append(order_no)
                        continue
                else:
                    missing_files.append(order_no)
                    continue
            
            # 检查状态 - 如果文件存在但状态不是generated，更新状态
            if pdf_status != 'generated' and os.path.exists(abs_pdf_path):
                # 文件存在但状态不对，更新状态
                try:
                    cursor.execute("""
                        UPDATE PDF_Status 
                        SET pdf_status = 'generated', updated_at = CURRENT_TIMESTAMP
                        WHERE Order_No = ?
                    """, (order_no,))
                    conn.commit()
                    pdf_status = 'generated'
                except Exception as update_error:
                    logger.error(f"Failed to update PDF_Status for order {order_no}: {update_error}")
            
            # 验证路径安全性（确保在backend/Generated_PDFs目录内）
            backend_dir = os.path.dirname(__file__)  # TR UI/backend
            abs_allowed_dir = os.path.normpath(os.path.join(backend_dir, 'Generated_PDFs'))
            if not abs_pdf_path.startswith(abs_allowed_dir):
                missing_files.append(order_no)
                continue
            
            pdf_files.append({
                'order_no': order_no,
                'path': abs_pdf_path,  # 使用绝对路径
                'del_date': sanitize_subdir_name(del_date),
                'job_no': sanitize_subdir_name(job_no_value) if job_no_value else 'Unknown_Job'
            })

        # manager和admin不会有无权访问的订单
        if current_user.get('role') == 'user' and unauthorized_orders:
            conn.close()
            return jsonify({
                'success': False,
                'error': 'You are not allowed to download some of the requested orders',
                'unauthorized': unauthorized_orders
            }), 403
        
        if not pdf_files:
            conn.close()
            error_msg = 'No valid PDF files to download'
            if not_generated:
                error_msg += f'. {len(not_generated)} orders not generated'
            if missing_files:
                error_msg += f'. {len(missing_files)} files missing'
            return jsonify({
                'success': False,
                'error': error_msg,
                'not_generated': not_generated,
                'missing': missing_files
            }), 400
        
        # 按日期、Job No、订单号排序
        pdf_files.sort(key=lambda item: (
            item.get('del_date') or '', 
            item.get('job_no') or '', 
            str(item['order_no'])
        ))
        conn.close()

        print(f"[批量下载] 准备打包 {len(pdf_files)} 个PDF文件")
        for pdf_file in pdf_files:
            print(f"[批量下载] - Order {pdf_file['order_no']}: {pdf_file['path']} (Date: {pdf_file.get('del_date')}, Job: {pdf_file.get('job_no')})")

        # 创建临时ZIP文件
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_zip_path = temp_zip.name
        temp_zip.close()
        
        try:
            # 创建ZIP文件
            print(f"[批量下载] 创建ZIP文件: {temp_zip_path}")
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for pdf_file in pdf_files:
                    order_no = pdf_file['order_no']
                    pdf_path = pdf_file['path']
                    # 在ZIP中使用有意义的文件名：日期/Job_No/TR_订单号.pdf
                    del_date_folder = pdf_file.get('del_date') or 'Unknown_Date'
                    job_no_folder = pdf_file.get('job_no') or 'Unknown_Job'
                    # 清理文件夹名称，移除不安全的字符
                    date_folder = del_date_folder.replace('\\', '-').replace('/', '-')
                    job_folder = f"Job_No_{job_no_folder}".replace('\\', '-').replace('/', '-')
                    arcname = f"{date_folder}/{job_folder}/TR_{order_no}.pdf"
                    if not os.path.exists(pdf_path):
                        print(f"[批量下载] 警告: PDF文件不存在: {pdf_path}")
                        continue
                    zipf.write(pdf_path, arcname)
                    print(f"[批量下载] 已添加: {arcname}")
            
            # 检查ZIP文件是否存在且不为空
            if not os.path.exists(temp_zip_path):
                raise FileNotFoundError(f"ZIP file was not created: {temp_zip_path}")
            
            zip_size = os.path.getsize(temp_zip_path)
            if zip_size == 0:
                raise ValueError(f"ZIP file is empty: {temp_zip_path}")
            
            print(f"[批量下载] ZIP文件已创建: {temp_zip_path}, 大小: {zip_size} bytes")
            
            # 返回ZIP文件
            # Flask的send_file会在文件发送完成后自动清理临时文件
            zip_filename = f'Orders_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
            
            print(f"[批量下载] 返回ZIP文件: {zip_filename}, 路径: {temp_zip_path}")
            
            return send_file(
                temp_zip_path,
                as_attachment=True,
                download_name=zip_filename,
                mimetype='application/zip'
            )
        except Exception as zip_error:
            # 如果ZIP创建失败，清理临时文件
            try:
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
            except:
                pass
            raise zip_error
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error batch downloading PDFs: {error_trace}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查（增強版）"""
    try:
        from health_check import health_check_endpoint
        return health_check_endpoint()
    except ImportError:
        # 如果健康檢查模組未導入，返回簡單響應
        return jsonify({
            'status': 'ok',
            'timestamp': datetime.now().isoformat()
        })


@app.route('/api/system/update-all-tables', methods=['POST'])
@require_auth(role='admin')
def update_all_tables():
    """
    执行数据更新（调用批处理文件）
    仅管理员可以执行
    """
    try:
        # 批处理文件路径
        batch_file = r'C:\TR-master\TR database\auto_update_all_tables.bat'
        # 可由环境变量覆盖的计划任务名称（任务需预先配置为“使用最高权限运行”）
        scheduled_task_name = os.getenv('UPDATE_ALL_TABLES_TASK_NAME', 'TR-Auto-Update-All-Tables')
        
        # 检查文件是否存在
        if not os.path.exists(batch_file):
            return jsonify({
                'success': False,
                'error': f'批处理文件不存在: {batch_file}'
            }), 404
        
        # 优先使用计划任务触发（可实现管理员权限运行）
        # 注意：Web 后端进程无法直接无交互弹出 UAC 并提权，推荐通过“最高权限”计划任务执行。
        try:
            task_cmd = ['schtasks', '/Run', '/TN', scheduled_task_name]
            task_proc = subprocess.run(
                task_cmd,
                capture_output=True,
                text=True,
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            if task_proc.returncode == 0:
                return jsonify({
                    'success': True,
                    'message': f'数据更新已通过计划任务启动: {scheduled_task_name}',
                    'status': 'running',
                    'runner': 'scheduled_task'
                })
            else:
                logger.warning(
                    f"Scheduled task start failed ({scheduled_task_name}): "
                    f"code={task_proc.returncode}, stderr={task_proc.stderr.strip()}"
                )
        except Exception as task_error:
            logger.warning(f"Scheduled task start exception ({scheduled_task_name}): {task_error}")

        # 计划任务不可用时，回退到旧逻辑：在后台线程中执行批处理文件（可能受权限限制）
        def run_batch():
            try:
                # 切换到批处理文件所在目录
                batch_dir = os.path.dirname(batch_file)
                # 执行批处理文件
                process = subprocess.Popen(
                    batch_file,
                    cwd=batch_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                # 等待执行完成（不阻塞主线程）
                stdout, stderr = process.communicate()
                return process.returncode == 0, stdout.decode('utf-8', errors='ignore'), stderr.decode('utf-8', errors='ignore')
            except Exception as e:
                return False, '', str(e)
        
        # 启动后台线程执行
        result_container = {'success': None, 'stdout': '', 'stderr': '', 'error': None}
        
        def execute():
            try:
                success, stdout, stderr = run_batch()
                result_container['success'] = success
                result_container['stdout'] = stdout
                result_container['stderr'] = stderr
            except Exception as e:
                result_container['error'] = str(e)
        
        thread = threading.Thread(target=execute, daemon=True)
        thread.start()
        
        # 立即返回，告诉前端已开始执行
        return jsonify({
            'success': True,
            'message': '数据更新已启动，正在后台执行',
            'status': 'running'
        })
        
    except Exception as e:
        import traceback
        print(f"[错误] 启动数据更新失败: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/system/check-update-status', methods=['GET'])
@require_auth(role='admin')
def check_update_status():
    """
    检查更新状态（通过检查最近的日志文件）
    """
    try:
        import glob
        import time
        
        log_dir = r'C:\TR-master\TR database\logs'
        if not os.path.exists(log_dir):
            return jsonify({
                'success': True,
                'status': 'unknown',
                'message': '日志目录不存在'
            })
        
        # 查找最新的日志文件
        log_files = glob.glob(os.path.join(log_dir, 'auto_update_all_*.log'))
        if not log_files:
            return jsonify({
                'success': True,
                'status': 'unknown',
                'message': '未找到更新日志'
            })
        
        # 获取最新的日志文件
        latest_log = max(log_files, key=os.path.getmtime)
        
        # 检查文件修改时间
        mtime = os.path.getmtime(latest_log)
        time_diff = time.time() - mtime
        
        # 如果文件在最近5分钟内被修改，说明正在运行
        if time_diff < 300:  # 5分钟
            # 读取最后几行日志判断状态
            try:
                with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    last_lines = ''.join(lines[-10:]) if len(lines) > 10 else ''.join(lines)
                    
                    if '自动更新流程结束' in last_lines or '更新流程结束' in last_lines:
                        if '成功' in last_lines or '🎉' in last_lines:
                            status = 'completed'
                            message = '更新已完成'
                        else:
                            status = 'failed'
                            message = '更新可能失败，请查看日志'
                    else:
                        status = 'running'
                        message = '更新正在进行中'
            except:
                status = 'running'
                message = '更新可能正在进行中'
        else:
            # 读取日志判断最终状态
            try:
                with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if '自动更新流程结束' in content or '更新流程结束' in content:
                        if '成功' in content or '🎉' in content:
                            status = 'completed'
                            message = '更新已完成'
                        else:
                            status = 'failed'
                            message = '更新可能失败'
                    else:
                        status = 'unknown'
                        message = '无法确定状态'
            except:
                status = 'unknown'
                message = '无法读取日志'
        
        return jsonify({
            'success': True,
            'status': status,
            'message': message,
            'log_file': latest_log,
            'last_modified': datetime.fromtimestamp(mtime).isoformat()
        })
        
    except Exception as e:
        import traceback
        print(f"[错误] 检查更新状态失败: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/file-index/status', methods=['GET'])
@require_auth()
def get_file_index_status():
    """
    获取文件索引缓存状态
    
    返回：
    {
        "success": true,
        "total_files": 12345,
        "last_full_scan": "2024-01-15T02:00:00",
        "last_incremental_update": "2024-01-15T14:30:00",
        "index_size_mb": 12.5,
        "status": "healthy"
    }
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取总文件数
        cursor.execute("SELECT COUNT(*) as cnt FROM file_index_cache WHERE is_deleted = 0")
        total_files = cursor.fetchone()['cnt']
        
        # 获取元数据
        cursor.execute("SELECT key, value FROM file_index_metadata")
        metadata = {row['key']: row['value'] for row in cursor.fetchall()}
        
        # 计算索引表大小（近似值）
        cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
        size_result = cursor.fetchone()
        index_size_bytes = size_result['size'] if size_result else 0
        index_size_mb = round(index_size_bytes / (1024 * 1024), 2)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'total_files': total_files,
            'last_full_scan': metadata.get('last_full_scan', ''),
            'total_files_indexed': int(metadata.get('total_files_indexed', 0)),
            'index_version': metadata.get('index_version', '1.0'),
            'scan_status': metadata.get('scan_status', 'idle'),
            'index_size_mb': index_size_mb,
            'status': 'healthy' if metadata.get('scan_status') == 'idle' else 'scanning'
        })
    except Exception as e:
        import traceback
        print(f"[错误] 获取文件索引状态失败: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/file-index/rebuild', methods=['POST'])
@require_auth(role='admin')
def rebuild_file_index():
    """
    手动触发全量索引重建（仅管理员）
    
    请求体（可选）：
    {
        "clear_existing": true  // 是否清空现有索引
    }
    
    返回：
    {
        "success": true,
        "message": "索引重建已启动",
        "estimated_time_minutes": 30
    }
    """
    try:
        from file_index_builder import FileIndexBuilder
        
        data = request.get_json() or {}
        clear_existing = data.get('clear_existing', False)
        
        # 获取基础文件夹路径
        base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
        
        # 创建索引建立器
        builder = FileIndexBuilder(DB_PATH, base_folder)
        
        # 在后台线程中执行索引建立（避免阻塞）
        import threading
        
        def build_index_async():
            try:
                result = builder.build_index(clear_existing=clear_existing)
                print(f"[索引建立] 完成: {result}")
            except Exception as e:
                print(f"[索引建立] 失败: {e}")
                import traceback
                traceback.print_exc()
        
        thread = threading.Thread(target=build_index_async, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': '索引重建已启动，将在后台执行',
            'clear_existing': clear_existing
        })
    except Exception as e:
        import traceback
        print(f"[错误] 启动索引重建失败: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/file-index/update', methods=['POST'])
@require_auth(role='admin')
def update_file_index():
    """
    手动触发增量索引更新（仅管理员）
    
    请求体（可选）：
    {
        "folder_type": "Stockist Cert"  // 指定要更新的文件夹类型，如果为空则更新所有
    }
    
    返回：
    {
        "success": true,
        "files_added": 10,
        "files_updated": 5,
        "files_deleted": 2,
        "files_checked": 1000,
        "elapsed_time": 5.2
    }
    """
    try:
        from file_index_updater import FileIndexUpdater
        
        data = request.get_json() or {}
        folder_type = data.get('folder_type')  # 可选，如果为None则更新所有
        
        # 获取基础文件夹路径
        base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
        
        # 创建更新器
        updater = FileIndexUpdater(DB_PATH, base_folder)
        
        # 在后台线程中执行更新（避免阻塞）
        import threading
        
        result_container = {'result': None, 'error': None}
        
        def update_index_async():
            try:
                result = updater.update_index(folder_type=folder_type)
                result_container['result'] = result
            except Exception as e:
                result_container['error'] = str(e)
                print(f"[索引更新] 失败: {e}")
                import traceback
                traceback.print_exc()
        
        thread = threading.Thread(target=update_index_async, daemon=True)
        thread.start()
        
        # 等待一下，看是否能快速完成
        thread.join(timeout=2)
        
        if result_container['result']:
            # 已经完成
            return jsonify({
                'success': True,
                **result_container['result']
            })
        elif result_container['error']:
            return jsonify({
                'success': False,
                'error': result_container['error']
            }), 500
        else:
            # 还在执行中
            return jsonify({
                'success': True,
                'message': '增量更新已启动，正在后台执行',
                'folder_type': folder_type
            })
    except Exception as e:
        import traceback
        print(f"[错误] 启动增量更新失败: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/file-index/cleanup', methods=['POST'])
@require_auth(role='admin')
def cleanup_file_index():
    """
    清理无效记录（仅管理员）
    
    返回：
    {
        "success": true,
        "records_deleted": 15
    }
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查找所有索引记录
        cursor.execute("SELECT file_path FROM file_index_cache WHERE is_deleted = 0")
        records = cursor.fetchall()
        
        deleted_count = 0
        for record in records:
            file_path = record['file_path']
            if not os.path.exists(file_path):
                # 文件不存在，标记为已删除
                cursor.execute("""
                    UPDATE file_index_cache 
                    SET is_deleted = 1 
                    WHERE file_path = ?
                """, (file_path,))
                deleted_count += 1
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'records_deleted': deleted_count
        })
    except Exception as e:
        import traceback
        print(f"[错误] 清理索引失败: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stockist-test/download-by-order/<int:order_no>', methods=['GET'])
@require_auth()
def download_stockist_test_by_order(order_no):
    """
    按 Order 下载 Stockist&Test Report PDF 文件（异步任务）
    
    逻辑：
    1. 创建异步下载任务
    2. 立即返回任务 ID
    3. 后台线程处理文件查找和打包
    """
    try:
        if DownloadTaskManager is None:
            return jsonify({
                'success': False,
                'error': 'Download task manager not available'
            }), 500
        
        # 获取当前用户
        current_user = g.current_user
        user_id = current_user['id']
        
        # 创建任务管理器（单例，固定 worker 队列）
        task_manager = get_download_task_manager()
        
        # 创建任务
        task_id = task_manager.create_task(
            user_id, 
            'order', 
            {'order_nos': [order_no]}
        )
        
        # 仅入队，快速返回 task_id
        task_manager.enqueue_task(task_id, 'order', {'order_nos': [order_no]})
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '下载任务已创建，正在后台处理'
        })
        
    except RuntimeError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 503
    except Exception as e:
        import traceback
        logger.error(f"创建下载任务失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stockist-test/download-by-dd-no/<dd_no>', methods=['GET'])
@require_auth()
def download_stockist_test_by_dd_no(dd_no):
    """
    按 DD_No 下载 Stockist&Test Report PDF 文件
    
    逻辑：
    1. 从 bbs_dd 表获取 dd_no 对应的所有 order_no
    2. 为每个 order_no 下载对应的 Stockist 和 Test Report 文件
    3. 去重处理，合并所有文件
    4. 按 Order_No 和 stockist_cert 组织文件
    """
    try:
        from stockist_test_download import StockistTestDownloader
        
        # 获取基础文件夹路径
        base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
        
        # 创建下载器
        downloader = StockistTestDownloader(DB_PATH, base_folder)
        
        # 执行下载
        zip_path, file_count = downloader.download_by_dd_no(dd_no)
        
        # 返回 ZIP 文件
        zip_filename = f'DD_No_{dd_no}_Stockist_Test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[错误] 按 Order 下载失败: {error_trace}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stockist-test/download-by-order-nos-grouped-by-dd-no', methods=['POST'])
@require_auth()
def download_stockist_test_by_order_nos_grouped_by_dd_no():
    """
    批量按多个 Order No 下载，按 DD_No 分组
    
    请求体：
    {
        "order_nos": [126091, 126193, 127009, ...]
    }
    
    逻辑：
    1. 从每个 order_no 获取对应的 DD_No
    2. 对 DD_No 去重
    3. 为每个 DD_No 下载文件（与单个 DD_No 下载逻辑一致）
    4. ZIP 结构：DD_No/Stockist_No/文件
    """
    try:
        from stockist_test_download import StockistTestDownloader
        
        # 获取请求体中的 order_nos
        data = request.get_json()
        if not data or 'order_nos' not in data:
            return jsonify({
                'success': False,
                'error': '请求体中缺少 order_nos 字段'
            }), 400
        
        order_nos = data.get('order_nos', [])
        if not isinstance(order_nos, list) or len(order_nos) == 0:
            return jsonify({
                'success': False,
                'error': 'order_nos 必须是非空列表'
            }), 400
        
        # 确保所有 order_no 都是整数
        try:
            order_nos = [int(no) for no in order_nos]
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'order_nos 中的元素必须是整数'
            }), 400
        
        # 限制订单数量
        if len(order_nos) > 500:
            return jsonify({
                'success': False,
                'error': '订单数量过多，最多支持500个订单'
            }), 400
        
        # 获取当前用户
        current_user = g.current_user
        user_id = current_user['id']
        
        # 创建任务管理器（单例，固定 worker 队列）
        task_manager = get_download_task_manager()
        
        # 创建任务
        task_id = task_manager.create_task(
            user_id, 
            'dd_no', 
            {'order_nos': order_nos}
        )
        
        # 仅入队，快速返回 task_id
        task_manager.enqueue_task(task_id, 'dd_no', {'order_nos': order_nos})
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '下载任务已创建，正在后台处理'
        })
    except RuntimeError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 503
    except Exception as e:
        import traceback
        logger.error(f"创建下载任务失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stockist-test/get-date-count', methods=['POST'])
@require_auth()
def get_date_count():
    """
    获取订单对应的日期数量（用于前端进度显示）
    
    请求体：
    {
        "order_nos": [126091, 126193, 127009, ...]
    }
    
    返回：
    {
        "success": True,
        "date_count": 3
    }
    """
    try:
        from stockist_test_download import StockistTestDownloader
        
        # 获取请求体中的 order_nos
        data = request.get_json()
        if not data or 'order_nos' not in data:
            return jsonify({
                'success': False,
                'error': '请求体中缺少 order_nos 字段'
            }), 400
        
        order_nos = data.get('order_nos', [])
        if not isinstance(order_nos, list) or len(order_nos) == 0:
            return jsonify({
                'success': False,
                'error': 'order_nos 必须是非空列表'
            }), 400
        
        # 确保所有 order_no 都是整数
        try:
            order_nos = [int(no) for no in order_nos]
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'order_nos 中的元素必须是整数'
            }), 400
        
        # 获取基础文件夹路径
        base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
        
        # 创建下载器
        downloader = StockistTestDownloader(DB_PATH, base_folder)
        
        # 获取日期数量（使用批量查询优化性能）
        # 使用批量查询一次性获取所有订单的日期，而不是逐个查询
        unique_dates = set()
        print(f"[API] 开始批量查询 {len(order_nos)} 个订单的日期...")
        
        try:
            # 直接使用数据库连接进行批量查询
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 构建批量查询，一次性获取所有订单的日期
            placeholders = ','.join('?' * len(order_nos))
            query = f"""
                SELECT DISTINCT order_no, del_date
                FROM TR_Report
                WHERE order_no IN ({placeholders}) AND del_date IS NOT NULL
            """
            
            cursor.execute(query, order_nos)
            rows = cursor.fetchall()
            conn.close()
            
            # 处理查询结果
            for row in rows:
                del_date = row[1]  # del_date 是第二列
                if not del_date:
                    continue
                
                # 格式化日期（确保格式一致，与 download_by_order_nos_grouped_by_date 保持一致）
                date_str = str(del_date).strip()
                # 如果日期包含时间部分，只取日期部分
                if ' ' in date_str:
                    date_str = date_str.split(' ')[0]
                # 标准化日期格式为 YYYY-MM-DD
                try:
                    from datetime import datetime
                    # 尝试解析日期
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    date_str = date_obj.strftime('%Y-%m-%d')
                except:
                    # 如果解析失败，尝试其他格式
                    try:
                        date_obj = datetime.strptime(date_str, '%Y/%m/%d')
                        date_str = date_obj.strftime('%Y-%m-%d')
                    except:
                        # 如果都失败，使用原始字符串
                        pass
                
                unique_dates.add(date_str)
            
            print(f"[API] 批量查询完成，找到 {len(unique_dates)} 个唯一日期")
        except Exception as e:
            print(f"[API] 批量查询失败，回退到逐个查询: {e}")
            # 如果批量查询失败，回退到逐个查询
            for order_no in order_nos:
                try:
                    order_info = downloader.get_order_info(order_no)
                    if not order_info:
                        continue
                    
                    del_date = order_info.get('del_date')
                    if not del_date:
                        continue
                    
                    # 格式化日期
                    date_str = str(del_date).strip()
                    if ' ' in date_str:
                        date_str = date_str.split(' ')[0]
                    try:
                        from datetime import datetime
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        date_str = date_obj.strftime('%Y-%m-%d')
                    except:
                        try:
                            date_obj = datetime.strptime(date_str, '%Y/%m/%d')
                            date_str = date_obj.strftime('%Y-%m-%d')
                        except:
                            pass
                    
                    unique_dates.add(date_str)
                except Exception as e2:
                    print(f"[API] 处理 Order {order_no} 时出错: {e2}")
                    continue
        
        date_count = len(unique_dates)
        if date_count == 0:
            date_count = 1  # 至少为1，避免前端显示 0/1
            print(f"[API] 警告: 没有找到任何日期，使用默认值 1")
        print(f"[API] 找到 {date_count} 个唯一的日期: {sorted(unique_dates) if unique_dates else '无'}")
        
        return jsonify({
            'success': True,
            'date_count': date_count,
            'dates': sorted(list(unique_dates)) if unique_dates else []
        })
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[错误] 获取日期数量失败: {error_trace}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stockist-test/download-by-order-nos-grouped-by-date', methods=['POST'])
@require_auth()
def download_stockist_test_by_order_nos_grouped_by_date():
    """
    批量按多个 Order No 下载，按日期分组
    
    请求体：
    {
        "order_nos": [126091, 126193, 127009, ...]
    }
    
    逻辑：
    1. 从每个 order_no 获取对应的 del_date
    2. 对日期去重（同一天的订单合并）
    3. 为每个日期收集文件，同一天的所有stockist放到同一个文件夹并去重
    4. ZIP 结构：日期/Stockist_No/文件
    """
    try:
        from stockist_test_download import StockistTestDownloader
        
        # 获取请求体中的 order_nos
        data = request.get_json()
        if not data or 'order_nos' not in data:
            return jsonify({
                'success': False,
                'error': '请求体中缺少 order_nos 字段'
            }), 400
        
        order_nos = data.get('order_nos', [])
        if not isinstance(order_nos, list) or len(order_nos) == 0:
            return jsonify({
                'success': False,
                'error': 'order_nos 必须是非空列表'
            }), 400
        
        # 确保所有 order_no 都是整数
        try:
            order_nos = [int(no) for no in order_nos]
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'order_nos 中的元素必须是整数'
            }), 400
        
        # 限制订单数量
        if len(order_nos) > 500:
            return jsonify({
                'success': False,
                'error': '订单数量过多，最多支持500个订单'
            }), 400
        
        # 获取当前用户
        current_user = g.current_user
        user_id = current_user['id']
        
        # 创建任务管理器（单例，固定 worker 队列）
        task_manager = get_download_task_manager()
        
        # 创建任务
        task_id = task_manager.create_task(
            user_id, 
            'date', 
            {'order_nos': order_nos}
        )
        
        # 仅入队，快速返回 task_id
        task_manager.enqueue_task(task_id, 'date', {'order_nos': order_nos})
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '下载任务已创建，正在后台处理'
        })
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404
    except RuntimeError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 503
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[错误] 批量按日期下载失败: {error_trace}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/download/create-task', methods=['POST'])
@require_auth()
def create_download_task():
    """
    创建下载任务（异步模式）
    
    请求体：
    {
        "type": "order",  // 或 "dd_no", "date"
        "params": {
            "order_nos": [126091, 126193, ...]
        }
    }
    
    返回：
    {
        "success": true,
        "task_id": "550e8400-e29b-41d4-a716-446655440000",
        "message": "下载任务已创建，正在后台处理"
    }
    """
    try:
        if DownloadTaskManager is None:
            return jsonify({
                'success': False,
                'error': 'Download task manager not available'
            }), 500
        
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '请求体不能为空'
            }), 400
        
        task_type = data.get('type')
        request_params = data.get('params', {})
        
        if task_type not in ['order', 'dd_no', 'date']:
            return jsonify({
                'success': False,
                'error': f'无效的任务类型: {task_type}'
            }), 400
        
        if 'order_nos' not in request_params:
            return jsonify({
                'success': False,
                'error': '请求参数中缺少 order_nos'
            }), 400
        
        order_nos = request_params.get('order_nos', [])
        if not isinstance(order_nos, list) or len(order_nos) == 0:
            return jsonify({
                'success': False,
                'error': 'order_nos 必须是非空列表'
            }), 400
        
        # 限制订单数量
        if len(order_nos) > 500:
            return jsonify({
                'success': False,
                'error': '订单数量过多，最多支持500个订单'
            }), 400
        
        # 获取当前用户
        current_user = g.current_user
        user_id = current_user['id']
        
        # 获取基础文件夹路径
        base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
        
        # 创建任务管理器
        task_manager = DownloadTaskManager(DB_PATH, base_folder)
        
        # 创建任务
        task_id = task_manager.create_task(user_id, task_type, request_params)
        
        # 仅入队，快速返回 task_id
        task_manager.enqueue_task(task_id, task_type, request_params)
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '下载任务已创建，正在后台处理'
        })
        
    except RuntimeError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 503
    except Exception as e:
        import traceback
        print(f"[错误] 创建下载任务失败: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/download/task-status/<task_id>', methods=['GET'])
@require_auth()
def get_download_task_status(task_id):
    """
    查询下载任务状态
    
    返回：
    {
        "success": true,
        "task_id": "...",
        "status": "processing",  // pending, processing, completed, failed
        "progress": 45,
        "total_files": 300,
        "processed_files": 135,
        "zip_path": "...",  // 仅当completed时
        "zip_size": 52428800,  // 仅当completed时
        "download_url": "...",  // 仅当completed时
        "has_warning": false,  // 仅当completed时
        "warning_message": "...",  // 仅当completed且有缺失告警时
        "error_message": "..."  // 仅当failed时
    }
    """
    try:
        if DownloadTaskManager is None:
            return jsonify({
                'success': False,
                'error': 'Download task manager not available'
            }), 500
        
        current_user = g.current_user
        user_id = current_user['id']
        
        task_manager = get_download_task_manager()
        
        task_status = task_manager.get_task_status(task_id, user_id)
        
        if not task_status:
            return jsonify({
                'success': False,
                'error': '任务不存在或无权访问'
            }), 404
        
        result = {
            'success': True,
            'task_id': task_status['task_id'],
            'status': task_status['status'],
            'progress': task_status['progress'] or 0,
            'total_files': task_status['total_files'] or 0,
            'processed_files': task_status['processed_files'] or 0
        }
        
        # 根据状态添加额外信息
        if task_status['status'] == 'completed':
            result['zip_path'] = task_status['zip_path']
            result['zip_size'] = task_status['zip_size']
            result['download_url'] = f'/api/download/download/{task_id}'
            warning_message = task_status.get('warning_message')
            result['has_warning'] = bool(warning_message)
            if warning_message:
                result['warning_message'] = warning_message
            result['message'] = '下载已完成'
        elif task_status['status'] == 'failed':
            result['error_message'] = task_status['error_message']
            result['message'] = f'下载失败: {task_status["error_message"]}'
        elif task_status['status'] == 'processing':
            result['message'] = '正在处理中...'
        else:
            result['message'] = '等待处理...'
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        print(f"[错误] 查询任务状态失败: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500




@app.route('/api/download/download/<task_id>', methods=['GET'])
@require_auth()
def download_task_file(task_id):
    """
    下载任务生成的ZIP文件
    
    仅当任务状态为completed时才能下载
    """
    try:
        if DownloadTaskManager is None:
            return jsonify({
                'success': False,
                'error': 'Download task manager not available'
            }), 500
        
        current_user = g.current_user
        user_id = current_user['id']
        
        task_manager = get_download_task_manager()
        
        task_status = task_manager.get_task_status(task_id, user_id)
        
        if not task_status:
            return jsonify({
                'success': False,
                'error': '任务不存在或无权访问'
            }), 404
        
        if task_status['status'] != 'completed':
            return jsonify({
                'success': False,
                'error': f'任务尚未完成，当前状态: {task_status["status"]}'
            }), 400
        
        zip_path = task_status['zip_path']
        if not zip_path or not os.path.exists(zip_path):
            logger.error(f"[下载] ZIP文件不存在: {zip_path}, 任务状态: {task_status}")
            return jsonify({
                'success': False,
                'error': f'ZIP文件不存在: {zip_path}'
            }), 404
        
        # 构建下载文件名
        import json
        task_type = task_status['task_type']
        request_params_str = task_status.get('request_params', '{}')
        try:
            request_params = json.loads(request_params_str) if isinstance(request_params_str, str) else request_params_str
        except:
            request_params = {}
        
        order_nos = request_params.get('order_nos', [])
        
        if task_type == 'order':
            if len(order_nos) == 1:
                zip_filename = f'Order_{order_nos[0]}_Stockist_Test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
            elif len(order_nos) <= 3:
                order_nos_str = '_'.join(str(no) for no in order_nos)
                zip_filename = f'{order_nos_str}_Stockist_Test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
            else:
                order_nos_str = '_'.join(str(no) for no in order_nos[:3]) + '_...'
                zip_filename = f'{order_nos_str}_Stockist_Test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        elif task_type == 'dd_no':
            if len(order_nos) <= 3:
                order_nos_str = '_'.join(str(no) for no in order_nos)
            else:
                order_nos_str = '_'.join(str(no) for no in order_nos[:3]) + '_...'
            zip_filename = f'{order_nos_str}_DD_No_Stockist_Test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        elif task_type == 'date':
            if len(order_nos) <= 3:
                order_nos_str = '_'.join(str(no) for no in order_nos)
            else:
                order_nos_str = '_'.join(str(no) for no in order_nos[:3]) + '_...'
            zip_filename = f'{order_nos_str}_Date_Stockist_Test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            zip_filename = f'Download_{task_type}_{timestamp}.zip'
        
        zip_size = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
        logger.info(f"[下载] 返回ZIP文件: {zip_path}, 文件名: {zip_filename}, 大小: {zip_size} bytes")
        
        # 使用流式传输，在传输完成后删除文件
        def generate():
            try:
                with open(zip_path, 'rb') as f:
                    while True:
                        chunk = f.read(8192)  # 8KB chunks
                        if not chunk:
                            break
                        yield chunk
            finally:
                # 文件传输完成后，延迟删除（确保文件句柄已关闭）
                import threading
                def delete_file_delayed():
                    import time
                    time.sleep(1)  # 等待1秒确保文件句柄已关闭
                    try:
                        if os.path.exists(zip_path):
                            os.remove(zip_path)
                            logger.info(f"[下载] 已删除临时文件: {zip_path}")
                    except Exception as e:
                        logger.error(f"[下载] 删除临时文件失败: {zip_path}, 错误: {e}")
                
                thread = threading.Thread(target=delete_file_delayed, daemon=True)
                thread.start()
        
        response = Response(
            generate(),
            mimetype='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename="{zip_filename}"',
                'Content-Length': str(zip_size)
            }
        )
        return response
        
    except Exception as e:
        import traceback
        print(f"[错误] 下载文件失败: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stockist-test/download-by-order-nos', methods=['POST'])
@require_auth()
def download_stockist_test_by_order_nos():
    """
    批量按多个 Order No 下载 Stockist&Test Report PDF 文件
    
    请求体：
    {
        "order_nos": [126193, 127009, 128001, ...]
    }
    
    逻辑：
    1. 为每个 order_no 下载对应的 Stockist 和 Test Report 文件
    2. 去重处理，合并所有文件
    3. 按 Order_No/Stockist_No 组织文件
    4. ZIP 文件命名：前三个 Order No + ... + Stockist + Test
    """
    try:
        from stockist_test_download import StockistTestDownloader
        
        # 获取请求体中的 order_nos
        data = request.get_json()
        if not data or 'order_nos' not in data:
            return jsonify({
                'success': False,
                'error': '请求体中缺少 order_nos 字段'
            }), 400
        
        order_nos = data.get('order_nos', [])
        if not isinstance(order_nos, list) or len(order_nos) == 0:
            return jsonify({
                'success': False,
                'error': 'order_nos 必须是非空列表'
            }), 400
        
        # 确保所有 order_no 都是整数
        try:
            order_nos = [int(no) for no in order_nos]
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'order_nos 中的元素必须是整数'
            }), 400
        
        # 限制订单数量
        if len(order_nos) > 500:
            return jsonify({
                'success': False,
                'error': '订单数量过多，最多支持500个订单'
            }), 400
        
        # 获取当前用户
        current_user = g.current_user
        user_id = current_user['id']
        
        # 创建任务管理器（单例，固定 worker 队列）
        task_manager = get_download_task_manager()
        
        # 创建任务
        task_id = task_manager.create_task(
            user_id, 
            'order', 
            {'order_nos': order_nos}
        )
        
        # 仅入队，快速返回 task_id
        task_manager.enqueue_task(task_id, 'order', {'order_nos': order_nos})
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '下载任务已创建，正在后台处理'
        })
    except RuntimeError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 503
    except Exception as e:
        import traceback
        logger.error(f"创建下载任务失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stockist-test/download-all-stockist-nos', methods=['POST'])
@require_auth()
def download_stockist_test_all_stockist_nos():
    """
    批量按多个 Order No 下载并按 Stockist No 扁平组织（不按 Item 分类）

    请求体：
    {
        "order_nos": [126193, 127009, 128001, ...]
    }

    ZIP 结构：
    - Stockist_No_1/file1.pdf
    - Stockist_No_2/file2.pdf
    """
    try:
        data = request.get_json()
        if not data or 'order_nos' not in data:
            return jsonify({
                'success': False,
                'error': '请求体中缺少 order_nos 字段'
            }), 400

        order_nos = data.get('order_nos', [])
        if not isinstance(order_nos, list) or len(order_nos) == 0:
            return jsonify({
                'success': False,
                'error': 'order_nos 必须是非空列表'
            }), 400

        try:
            order_nos = [int(no) for no in order_nos]
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'order_nos 中的元素必须是整数'
            }), 400

        if len(order_nos) > 500:
            return jsonify({
                'success': False,
                'error': '订单数量过多，最多支持500个订单'
            }), 400

        current_user = g.current_user
        user_id = current_user['id']

        task_manager = get_download_task_manager()

        task_id = task_manager.create_task(
            user_id,
            'order_stockist_flat',
            {'order_nos': order_nos}
        )

        # 仅入队，快速返回 task_id
        task_manager.enqueue_task(task_id, 'order_stockist_flat', {'order_nos': order_nos})

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '下载任务已创建，正在后台处理'
        })
    except RuntimeError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 503
    except Exception as e:
        logger.error(f"创建扁平Stockist下载任务失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/orders-gen-pdf/<int:order_no>', methods=['GET'])
def get_orders_gen_pdf(order_no: int):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        header_query = """
            SELECT 
                o.Order_No,
                o.Client,
                o.Jobsite,
                o.Job_No,
                o."PO_No(2)" as PO_No_2,
                o.Del_Date,
                o.Ref_No,
                o.Order_Description,
                o.Supplier
            FROM Orders_gen_pdf o
            WHERE o.Order_No = ?
            LIMIT 1
        """
        cursor.execute(header_query, (order_no,))
        header_row = cursor.fetchone()
        if not header_row:
            conn.close()
            return jsonify({'success': False, 'error': f'Order {order_no} not found'}), 404
        header = dict(header_row)
        lines_query = """
            SELECT 
                rowid as id,
                Dia,
                "Wt(ton)" as Wt,
                Product,
                Grade,
                Pattern,
                Mill_Cert,
                Test_Cert2,
                Test_Cert1,
                Supplier,
                Stockist_Cert,
                "PO_No(1)" as PO_No_1,
                Tag_No,
                DN_No
            FROM Orders_gen_pdf
            WHERE Order_No = ?
            ORDER BY Dia
        """
        cursor.execute(lines_query, (order_no,))
        line_rows = cursor.fetchall()
        lines = [dict(r) for r in line_rows]
        conn.close()
        return jsonify({'success': True, 'data': {'header': header, 'lines': lines}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/orders-gen-pdf/<int:order_no>/edit', methods=['POST'])
def edit_orders_gen_pdf(order_no: int):
    try:
        payload = request.get_json(force=True) or {}
        header_updates = payload.get('header_updates', {}) or {}
        line_updates = payload.get('line_updates', []) or []
        conn = get_db_connection()
        cursor = conn.cursor()
        before = conn.total_changes
        # Header updates
        header_allowed = {
            'Client': 'Client',
            'Jobsite': 'Jobsite',
            'Job_No': 'Job_No',
            'PO_No_2': '"PO_No(2)"',
            'Del_Date': 'Del_Date',
            'Ref_No': 'Ref_No',
            'Order_Description': 'Order_Description',
            'Supplier': 'Supplier',
            'Order_No': 'Order_No'
        }
        if header_updates:
            set_parts = []
            values = []
            for k, v in header_updates.items():
                col = header_allowed.get(k)
                if col:
                    set_parts.append(f"{col} = ?")
                    values.append(v)
            if set_parts:
                values.append(order_no)
                cursor.execute(f"UPDATE Orders_gen_pdf SET {', '.join(set_parts)} WHERE Order_No = ?", values)
        # Line updates (by rowid)
        line_allowed = {
            'Dia': 'Dia',
            'Wt': '"Wt(ton)"',
            'Product': 'Product',
            'Grade': 'Grade',
            'Pattern': 'Pattern',
            'Mill_Cert': 'Mill_Cert',
            'Test_Cert2': 'Test_Cert2',
            'Test_Cert1': 'Test_Cert1',
            'Supplier': 'Supplier',
            'Stockist_Cert': 'Stockist_Cert',
            'PO_No_1': '"PO_No(1)"',
            'Tag_No': 'Tag_No',
            'DN_No': 'DN_No'
        }
        for item in line_updates:
            rowid = item.get('id')
            if not rowid:
                continue
            set_parts = []
            values = []
            for k, v in item.items():
                if k == 'id':
                    continue
                col = line_allowed.get(k)
                if col:
                    set_parts.append(f"{col} = ?")
                    values.append(v)
            if set_parts:
                values.extend([order_no, rowid])
                cursor.execute(f"UPDATE Orders_gen_pdf SET {', '.join(set_parts)} WHERE Order_No = ? AND rowid = ?", values)
        changed = conn.total_changes - before
        if changed > 0:
            try:
                cursor.execute(
                    """
                    INSERT INTO PDF_Status (Order_No, pdf_status, updated_at)
                    VALUES (?, 'pending', CURRENT_TIMESTAMP)
                    ON CONFLICT(Order_No) DO UPDATE SET pdf_status='pending', updated_at=CURRENT_TIMESTAMP
                    """,
                    (order_no,)
                )
            except Exception:
                pass
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'changed': max(changed, 0)})
    except Exception as e:
        import traceback
        # 生产环境不应返回详细的错误堆栈给前端
        if DEBUG_MODE:
            return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()}), 500
        else:
            return jsonify({'success': False, 'error': '操作失败，请稍后重试或联系管理员'}), 500

if __name__ == '__main__':
    # 检查数据库是否存在
    if not os.path.exists(DB_PATH):
        logger.error(f"Database not found: {DB_PATH}")
        logger.error("Please ensure data_3years.db exists in the TR database directory.")
        exit(1)
    
    # 初始化數據庫連接池（在應用啟動時）
    _ensure_pool_initialized()
    
    # 可选：启动文件索引定时任务
    # 从环境变量读取是否启用定时任务
    enable_scheduler = os.getenv('ENABLE_FILE_INDEX_SCHEDULER', 'False').lower() == 'true'
    if enable_scheduler:
        try:
            from file_index_scheduler import start_file_index_scheduler
            base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
            update_interval = int(os.getenv('FILE_INDEX_UPDATE_INTERVAL_HOURS', '1'))
            start_file_index_scheduler(DB_PATH, base_folder, update_interval)
            print(f"[调度器] 文件索引定时任务已启动，更新间隔: {update_interval} 小时")
        except Exception as e:
            print(f"[警告] 启动文件索引定时任务失败: {e}")
    
    logger.info("=" * 50)
    logger.info("TR Fill In API Server")
    logger.info(f"Database: {DB_PATH}")
    logger.info("=" * 50)
    logger.info("\nAvailable endpoints:")
    logger.info("  POST /api/auth/login - User login")
    logger.info("  POST /api/auth/logout - User logout")
    logger.info("  GET  /api/auth/me - Get current user profile")
    logger.info("  GET  /api/admin/users - List managed accounts (admin)")
    logger.info("  POST /api/admin/users - Create ordinary account (admin)")
    logger.info("  PUT  /api/admin/users/<username> - Update account (admin)")
    logger.info("  DELETE /api/admin/users/<username> - Delete account (admin)")
    logger.info("  GET  /api/tr-fill-in/data - Get all data")
    logger.info("  POST /api/tr-fill-in/save - Save tag numbers (自动同步Orders_gen_pdf)")
    logger.info("  POST /api/tr-fill-in/delete - Delete tag numbers (自动同步Orders_gen_pdf)")
    logger.info("  POST /api/tr-fill-in/clear - Clear all data (自动同步Orders_gen_pdf)")
    logger.info("  POST /api/tr-fill-in/update - Update record (自动同步Orders_gen_pdf)")
    logger.info("  POST /api/orders-gen-pdf/regenerate - 手动触发Orders_gen_pdf表重新生成")
    logger.info("  GET  /api/materials/search/<tag_no> - Search materials by Tag No")
    logger.info("  GET  /api/orders/list - Get orders list (paginated)")
    logger.info("  POST /api/pdf/generate - Create PDF generation task (async)")
    logger.info("  GET  /api/pdf/task-status/<task_id> - Get PDF generation task status")
    logger.info("  GET  /api/pdf/download/<order_no> - Download single PDF")
    logger.info("  POST /api/pdf/batch-download - Batch download PDFs as ZIP")
    logger.info("  GET  /api/orders-gen-pdf/<order_no> - Get editable data")
    logger.info("  POST /api/orders-gen-pdf/<order_no>/edit - Edit order and lines")
    logger.info("  POST /api/download/create-task - Create async download task")
    logger.info("  GET  /api/download/task-status/<task_id> - Get download task status")
    logger.info("  GET  /api/download/download/<task_id> - Download completed file")
    logger.info("  GET  /health - Health check")
    logger.info("  GET  /ready - Readiness check")
    logger.info("  GET  /live - Liveness check")
    logger.info("=" * 50)
    logger.info(f"\nStarting server on http://{API_HOST}:{API_PORT}")
    logger.info(f"Debug mode: {DEBUG_MODE}")
    logger.info(f"Database: {DB_PATH}")
    
    # 添加額外的健康檢查端點（/health 已在上面定義）
    try:
        from health_check import readiness_check_endpoint, liveness_check_endpoint
        app.add_url_rule('/ready', 'readiness_check', readiness_check_endpoint, methods=['GET'])
        app.add_url_rule('/live', 'liveness_check', liveness_check_endpoint, methods=['GET'])
        logger.info("健康檢查端點已啟用（/health, /ready, /live）")
    except ImportError:
        logger.warning("健康檢查模組未找到，使用默認健康檢查端點")
    
    app.run(debug=DEBUG_MODE, host=API_HOST, port=API_PORT, threaded=True)

