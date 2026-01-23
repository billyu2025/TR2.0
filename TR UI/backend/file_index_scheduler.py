#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件索引缓存定时任务调度器
功能：定期执行增量更新
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Optional
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class FileIndexScheduler:
    """文件索引缓存定时任务调度器"""
    
    def __init__(self, db_path: str, base_folder: str = None):
        """
        初始化调度器
        
        Args:
            db_path: SQLite 数据库路径
            base_folder: Stockist&Test Report 文件夹的基础路径
        """
        self.db_path = db_path
        self.base_folder = base_folder
        self.thread = None
        self.running = False
        self.update_interval_hours = 1  # 默认每小时更新一次
        
    def start(self, update_interval_hours: int = 1):
        """
        启动定时任务
        
        Args:
            update_interval_hours: 更新间隔（小时）
        """
        if self.running:
            print("[调度器] 定时任务已在运行")
            return
        
        self.update_interval_hours = update_interval_hours
        self.running = True
        
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        
        print(f"[调度器] 已启动定时任务，更新间隔: {update_interval_hours} 小时")
    
    def stop(self):
        """停止定时任务"""
        if not self.running:
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        
        print("[调度器] 定时任务已停止")
    
    def _run_scheduler(self):
        """运行调度器主循环"""
        from file_index_updater import FileIndexUpdater
        
        updater = FileIndexUpdater(self.db_path, self.base_folder)
        
        while self.running:
            try:
                # 等待指定时间
                time.sleep(self.update_interval_hours * 3600)
                
                if not self.running:
                    break
                
                print(f"[调度器] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 开始执行增量更新")
                
                # 执行增量更新
                result = updater.update_index()
                
                if result.get('success'):
                    print(f"[调度器] 增量更新完成: 新增 {result.get('files_added', 0)}, "
                          f"更新 {result.get('files_updated', 0)}, "
                          f"删除 {result.get('files_deleted', 0)}")
                else:
                    print(f"[调度器] 增量更新失败")
                    
            except Exception as e:
                print(f"[调度器] 执行增量更新时出错: {e}")
                import traceback
                traceback.print_exc()
                # 继续运行，等待下次更新


# 全局调度器实例
_scheduler_instance: Optional[FileIndexScheduler] = None


def start_file_index_scheduler(db_path: str, base_folder: str = None, 
                               update_interval_hours: int = 1):
    """
    启动文件索引定时任务（全局函数）
    
    Args:
        db_path: 数据库路径
        base_folder: 基础文件夹路径
        update_interval_hours: 更新间隔（小时）
    """
    global _scheduler_instance
    
    if _scheduler_instance and _scheduler_instance.running:
        print("[调度器] 定时任务已在运行，跳过启动")
        return
    
    _scheduler_instance = FileIndexScheduler(db_path, base_folder)
    _scheduler_instance.start(update_interval_hours)


def stop_file_index_scheduler():
    """停止文件索引定时任务"""
    global _scheduler_instance
    
    if _scheduler_instance:
        _scheduler_instance.stop()
        _scheduler_instance = None
