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
    app_handler = RotatingFileHandler(
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
    error_handler = RotatingFileHandler(
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
    access_handler = RotatingFileHandler(
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
        # 尝试设置 UTF-8 编码
        import io
        if sys.platform == 'win32':
            # Windows 环境下，使用安全的编码方式
            console_handler = logging.StreamHandler(io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace'))
        else:
            console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING if not debug_mode else logging.DEBUG)
        console_handler.setFormatter(logging.Formatter(log_format, date_format))
        logger.addHandler(console_handler)
    except (AttributeError, UnicodeEncodeError, UnicodeDecodeError):
        # 如果设置失败，使用默认方式，但捕获编码错误
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING if not debug_mode else logging.DEBUG)
        # 使用简单的格式，避免编码问题
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', date_format))
        logger.addHandler(console_handler)
    
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
