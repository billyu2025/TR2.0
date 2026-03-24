#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Waitress 啟動腳本
用於 Windows 系統的生產環境部署
"""

from waitress import serve
from tr_fill_in_api import app, start_background_services
import os

if __name__ == '__main__':
    # 從環境變量讀取配置
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', '5000'))
    threads = int(os.getenv('WAITRESS_THREADS', '4'))
    
    # 使用安全的输出方式，避免编码错误
    try:
        print("=" * 60)
        print("TR Report System - Waitress Server")
        print("=" * 60)
        print("Listening on: http://" + str(host) + ":" + str(port))
        print("Threads: " + str(threads))
        print("Mode: Production")
        print("=" * 60)
        print("Press Ctrl+C to stop server")
        print("=" * 60)
        print()
    except (UnicodeEncodeError, UnicodeDecodeError):
        # 如果编码失败，使用最简单的输出
        print("=" * 60)
        print("TR Report System - Waitress Server")
        print("=" * 60)
        print("Server starting...")
        print("=" * 60)
        print()

    # 与直接运行 tr_fill_in_api.py 一致：连接池（SQLite）+ 文件索引调度器（若 .env 启用）
    start_background_services()

    try:
        serve(
            app,
            host=host,
            port=port,
            threads=threads,
            channel_timeout=120,
            connection_limit=1000,
            cleanup_interval=30,
            ident='TR-System'
        )
    except KeyboardInterrupt:
        try:
            print("\nServer stopped")
        except (UnicodeEncodeError, UnicodeDecodeError):
            print("\nServer stopped")
    except Exception as e:
        try:
            print(f"\nServer startup failed: {e}")
        except (UnicodeEncodeError, UnicodeDecodeError):
            print(f"\nServer startup failed: {e}")
        import traceback
        traceback.print_exc()
