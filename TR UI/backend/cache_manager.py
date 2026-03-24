#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis Cache Management Module
Provides unified cache interface with cache operations and expiration policies
"""

import json
import hashlib
from functools import wraps
from typing import Any, Optional, Callable
import os
import sys

# 安全日志输出函数（避免在后台线程中 stdout 关闭的问题）
def _safe_print(message):
    """安全输出，如果 stdout 不可用则跳过"""
    try:
        if sys.stdout is not None and not (hasattr(sys.stdout, 'closed') and sys.stdout.closed):
            print(message)
    except (ValueError, OSError, AttributeError):
        pass  # 如果输出失败，静默忽略

# 嘗試導入 Redis，如果未安裝則使用內存緩存
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    # 使用簡單的內存緩存作為降級方案
    _memory_cache = {}
    import threading
    _cache_lock = threading.Lock()


class CacheManager:
    """Cache Manager"""
    
    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0, 
                 redis_password=None, default_ttl=300, enabled=True):
        """
        Initialize cache manager
        
        Args:
            redis_host: Redis host address
            redis_port: Redis port
            redis_db: Redis database number
            redis_password: Redis password (optional)
            default_ttl: Default cache time (seconds)
            enabled: Whether to enable cache
        """
        self.enabled = enabled and os.getenv('REDIS_ENABLED', 'True').lower() == 'true'
        self.default_ttl = default_ttl
        self.redis_client = None
        self.use_redis = False
        
        if self.enabled and REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    password=redis_password,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2
                )
                # 測試連接
                self.redis_client.ping()
                self.use_redis = True
                _safe_print("[INFO] Redis cache enabled")
            except Exception as e:
                _safe_print(f"[WARNING] Redis connection failed, using memory cache: {e}")
                self.use_redis = False
        elif self.enabled and not REDIS_AVAILABLE:
            _safe_print("[WARNING] Redis not installed, using memory cache")
            self.use_redis = False
    
    def _get_memory_cache(self):
        """Get memory cache (fallback)"""
        if not REDIS_AVAILABLE:
            return _memory_cache
        return {}
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get cache value
        
        Args:
            key: Cache key
        
        Returns:
            Cache value, or None if not found
        """
        if not self.enabled:
            return None
        
        try:
            if self.use_redis and self.redis_client:
                value = self.redis_client.get(key)
                if value:
                    return json.loads(value)
            else:
                # Use memory cache
                with _cache_lock:
                    cache = self._get_memory_cache()
                    if key in cache:
                        entry = cache[key]
                        # Check if expired
                        import time
                        if entry['expires_at'] > time.time():
                            return entry['value']
                        else:
                            del cache[key]
        except Exception as e:
            _safe_print(f"[ERROR] Cache read failed: {e}")
        
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set cache value
        
        Args:
            key: Cache key
            value: Cache value
            ttl: Cache time (seconds), if None use default
        
        Returns:
            Whether setting was successful
        """
        if not self.enabled:
            return False
        
        try:
            ttl = ttl or self.default_ttl
            
            if self.use_redis and self.redis_client:
                self.redis_client.setex(
                    key,
                    ttl,
                    json.dumps(value, ensure_ascii=False)
                )
            else:
                # Use memory cache
                import time
                with _cache_lock:
                    cache = self._get_memory_cache()
                    cache[key] = {
                        'value': value,
                        'expires_at': time.time() + ttl
                    }
            return True
        except Exception as e:
            _safe_print(f"[ERROR] Cache write failed: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Delete cache
        
        Args:
            key: Cache key (supports wildcards, e.g., "orders:list:*")
        
        Returns:
            Whether deletion was successful
        """
        if not self.enabled:
            return False
        
        try:
            if self.use_redis and self.redis_client:
                if '*' in key:
                    # 支持通配符刪除 - Redis使用KEYS命令
                    pattern = key.replace('*', '*')  # Redis pattern uses * directly
                    keys = self.redis_client.keys(pattern)
                    if keys:
                        deleted_count = self.redis_client.delete(*keys)
                        _safe_print(f"[INFO] Cache deleted {deleted_count} keys matching pattern: {pattern}")
                    else:
                        _safe_print(f"[INFO] No cache keys found matching pattern: {pattern}")
                else:
                    deleted = self.redis_client.delete(key)
                    if deleted:
                        _safe_print(f"[INFO] Cache deleted key: {key}")
            else:
                # Use memory cache
                with _cache_lock:
                    cache = self._get_memory_cache()
                    if '*' in key:
                        # Simple wildcard matching - match keys that start with the prefix
                        prefix = key.replace('*', '')
                        all_keys = list(cache.keys())
                        keys_to_delete = [k for k in all_keys if k.startswith(prefix)]
                        deleted_count = len(keys_to_delete)
                        for k in keys_to_delete:
                            del cache[k]
                        _safe_print(f"[INFO] Memory cache deleted {deleted_count} keys matching pattern: {key}")
                        if deleted_count > 0:
                            _safe_print(f"[INFO] Deleted keys (first 5): {keys_to_delete[:5]}")
                        else:
                            _safe_print(f"[INFO] No keys found matching pattern. All cache keys: {all_keys[:10]}")
                    else:
                        if key in cache:
                            del cache[key]
                            _safe_print(f"[INFO] Memory cache deleted key: {key}")
            return True
        except Exception as e:
            _safe_print(f"[ERROR] Cache delete failed: {e}")
            return False
    
    def clear(self) -> bool:
        """
        Clear all cache
        
        Returns:
            Whether clearing was successful
        """
        if not self.enabled:
            return False
        
        try:
            if self.use_redis and self.redis_client:
                self.redis_client.flushdb()
            else:
                # Use memory cache
                with _cache_lock:
                    cache = self._get_memory_cache()
                    cache.clear()
            return True
        except Exception as e:
            _safe_print(f"[ERROR] Cache clear failed: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """
        Check if cache exists
        
        Args:
            key: Cache key
        
        Returns:
            Whether it exists
        """
        if not self.enabled:
            return False
        
        try:
            if self.use_redis and self.redis_client:
                return self.redis_client.exists(key) > 0
            else:
                # Use memory cache
                with _cache_lock:
                    cache = self._get_memory_cache()
                    if key in cache:
                        import time
                        if cache[key]['expires_at'] > time.time():
                            return True
                        else:
                            del cache[key]
                    return False
        except Exception as e:
            _safe_print(f"[ERROR] Cache check failed: {e}")
            return False
    
    def generate_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Generate cache key
        
        Args:
            prefix: Prefix
            *args: Positional arguments
            **kwargs: Keyword arguments
        
        Returns:
            Cache key
        """
        # Combine all parameters
        parts = [prefix]
        if args:
            parts.extend(str(arg) for arg in args)
        if kwargs:
            # Sort to ensure consistency
            sorted_kwargs = sorted(kwargs.items())
            parts.extend(f"{k}:{v}" for k, v in sorted_kwargs)
        
        key_str = ":".join(parts)
        
        # If key is too long, use hash
        if len(key_str) > 200:
            key_hash = hashlib.md5(key_str.encode()).hexdigest()
            return f"{prefix}:{key_hash}"
        
        return key_str


# Global cache manager instance
_cache_manager = None


def init_cache(redis_host=None, redis_port=None, redis_db=None, 
               redis_password=None, default_ttl=300, enabled=True):
    """
    Initialize global cache manager
    
    Args:
        redis_host: Redis host address (read from environment variable or use default)
        redis_port: Redis port (read from environment variable or use default)
        redis_db: Redis database number (read from environment variable or use default)
        redis_password: Redis password (read from environment variable or use default)
        default_ttl: Default cache time (seconds)
        enabled: Whether to enable cache
    """
    global _cache_manager
    
    if redis_host is None:
        redis_host = os.getenv('REDIS_HOST', 'localhost')
    if redis_port is None:
        redis_port = int(os.getenv('REDIS_PORT', '6379'))
    if redis_db is None:
        redis_db = int(os.getenv('REDIS_DB', '0'))
    if redis_password is None:
        redis_password = os.getenv('REDIS_PASSWORD', None)
    
    _cache_manager = CacheManager(
        redis_host=redis_host,
        redis_port=redis_port,
        redis_db=redis_db,
        redis_password=redis_password,
        default_ttl=default_ttl,
        enabled=enabled
    )
    
    return _cache_manager


def get_cache() -> CacheManager:
    """
    Get global cache manager instance
    
    Returns:
        Cache manager instance
    """
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = init_cache()
    return _cache_manager


def cached(ttl: Optional[int] = None, key_prefix: Optional[str] = None):
    """
    Cache decorator
    
    Args:
        ttl: Cache time (seconds), if None use default
        key_prefix: Cache key prefix, if None use function name
    
    Usage:
        @cached(ttl=300, key_prefix='orders')
        def get_orders_list(page, per_page):
            # ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_cache()
            
            if not cache.enabled:
                return func(*args, **kwargs)
            
            # 生成緩存鍵
            prefix = key_prefix or func.__name__
            cache_key = cache.generate_key(prefix, *args, **kwargs)
            
            # 嘗試從緩存獲取
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # 執行函數
            result = func(*args, **kwargs)
            
            # 保存到緩存
            cache.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator
