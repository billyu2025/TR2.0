#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
統一日誌系統配置模組
提供統一的日誌格式和處理
"""

import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from datetime import datetime


class _SafeRotatingFileHandler(RotatingFileHandler):
    """
    安全的 RotatingFileHandler，在 Windows 上处理文件锁定问题
    当文件被其他进程锁定时，跳过轮转而不是抛出异常
    """
    def doRollover(self):
        """
        执行日志轮转，如果失败则跳过（避免在 Windows 上因文件锁定而崩溃）
        """
        try:
            super().doRollover()
        except (PermissionError, OSError) as e:
            # 在 Windows 上，如果文件被锁定，跳过轮转
            # 这不会影响日志记录，只是不会轮转文件
            try:
                # 尝试使用安全的日志输出（如果可用）
                if hasattr(sys.stderr, 'write'):
                    sys.stderr.write(f"[WARNING] Log rotation skipped due to file lock: {e}\n")
            except Exception:
                pass  # 如果连 stderr 都不可用，静默忽略


def setup_logging(debug_mode=False, log_dir=None):
    """
    設置統一日誌系統
    
    Args:
        debug_mode: 是否為調試模式
        log_dir: 日誌目錄路徑，如果為None則使用默認路徑
    
    Returns:
        logging.Logger: 配置好的日誌器
    """
    # 確定日誌目錄
    if log_dir is None:
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    
    # 創建日誌目錄
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 日誌格式
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # 獲取根日誌器
    logger = logging.getLogger('tr_system')
    logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    
    # 清除現有的處理器（避免重複添加）
    logger.handlers.clear()
    
    # 1. 應用日誌文件處理器（所有日誌）
    app_log_file = os.path.join(log_dir, 'app.log')
    app_handler = _SafeRotatingFileHandler(
        app_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    app_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    app_handler.setFormatter(logging.Formatter(log_format, date_format))
    logger.addHandler(app_handler)
    
    # 2. 錯誤日誌文件處理器（僅錯誤）
    error_log_file = os.path.join(log_dir, 'error.log')
    error_handler = _SafeRotatingFileHandler(
        error_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,  # 錯誤日誌保留更多
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(log_format, date_format))
    logger.addHandler(error_handler)
    
    # 3. 訪問日誌文件處理器（API訪問）
    access_log_file = os.path.join(log_dir, 'access.log')
    access_handler = _SafeRotatingFileHandler(
        access_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    access_handler.setLevel(logging.INFO)
    access_handler.setFormatter(logging.Formatter(log_format, date_format))
    # 創建訪問日誌器
    access_logger = logging.getLogger('tr_system.access')
    access_logger.addHandler(access_handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False  # 不向上傳播
    
    # 4. 控制台處理器（在 Windows 服务环境中可能遇到编码问题，使用安全的编码方式）
    try:
        # 检查 sys.stdout 是否可用（在后台线程中可能已关闭）
        if sys.stdout is None or (hasattr(sys.stdout, 'closed') and sys.stdout.closed):
            # stdout 已关闭，跳过控制台处理器（只使用文件日志）
            pass
        else:
            # 尝试设置 UTF-8 编码
            import io
            if sys.platform == 'win32':
                # Windows 环境下，使用安全的编码方式
                try:
                    console_handler = logging.StreamHandler(io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace'))
                except (ValueError, AttributeError, OSError):
                    # sys.stdout.buffer 不可用，使用默认方式
                    console_handler = logging.StreamHandler(sys.stdout)
            else:
                console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.WARNING if not debug_mode else logging.DEBUG)
            console_handler.setFormatter(logging.Formatter(log_format, date_format))
            logger.addHandler(console_handler)
    except (AttributeError, UnicodeEncodeError, UnicodeDecodeError, ValueError, OSError):
        # 如果设置失败，尝试使用默认方式，但捕获所有可能的错误
        try:
            if sys.stdout is not None and not (hasattr(sys.stdout, 'closed') and sys.stdout.closed):
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setLevel(logging.WARNING if not debug_mode else logging.DEBUG)
                # 使用简单的格式，避免编码问题
                console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', date_format))
                logger.addHandler(console_handler)
        except (ValueError, OSError, AttributeError):
            # 如果仍然失败，跳过控制台处理器（只使用文件日志）
            pass
    
    # 防止日誌向上傳播到根日誌器
    logger.propagate = False
    
    return logger


def get_logger(name=None):
    """
    獲取日誌器實例
    
    Args:
        name: 日誌器名稱，如果為None則返回根日誌器
    
    Returns:
        logging.Logger: 日誌器實例
    """
    if name:
        return logging.getLogger(f'tr_system.{name}')
    return logging.getLogger('tr_system')


def get_access_logger():
    """
    獲取訪問日誌器（用於記錄API訪問）
    
    Returns:
        logging.Logger: 訪問日誌器
    """
    return logging.getLogger('tr_system.access')


# 全局日誌器實例（在模組導入時初始化）
_logger = None


def init_logger(debug_mode=False, log_dir=None):
    """
    初始化全局日誌器
    
    Args:
        debug_mode: 是否為調試模式
        log_dir: 日誌目錄路徑
    """
    global _logger
    _logger = setup_logging(debug_mode, log_dir)
    return _logger


def get_global_logger():
    """
    獲取全局日誌器實例
    
    Returns:
        logging.Logger: 全局日誌器
    """
    global _logger
    if _logger is None:
        _logger = setup_logging()
    return _logger
