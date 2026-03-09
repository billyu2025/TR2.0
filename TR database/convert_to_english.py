#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to convert auto_update_all_tables.py to English version
"""

import re
import sys
import os

# Read the original file
input_file = 'auto_update_all_tables.py'
output_file = 'auto_update_all_tables_fixed.py'

if not os.path.exists(input_file):
    print(f"Error: {input_file} not found")
    sys.exit(1)

print(f"Reading {input_file}...")
with open(input_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace Chinese text with English
replacements = {
    # Header comments
    'TR_Report 和 TR_Report_Deduplication 自动更新脚本': 'TR_Report and TR_Report_Deduplication Auto Update Script',
    '功能：自动更新 TR_Report 和 TR_Report_Deduplication 表': 'Function: Auto update TR_Report and TR_Report_Deduplication tables',
    '作者：TR Report System': 'Author: TR Report System',
    '日期：2025-11-20': 'Date: 2025-11-20',
    
    # Comments
    '设置UTF-8编码环境变量（解决Windows下中文和emoji显示问题）': 'Set UTF-8 encoding environment variable (fix Chinese and emoji display issues on Windows)',
    '设置环境变量': 'Set environment variable',
    '重新配置标准输出和错误输出为UTF-8': 'Reconfigure stdout and stderr to UTF-8',
    '添加当前目录到Python路径': 'Add current directory to Python path',
    '添加backend目录到Python路径（用于导入文件索引相关模块）': 'Add backend directory to Python path (for importing file index related modules)',
    '配置区域': 'Configuration Section',
    '数据库配置': 'Database Configuration',
    'SQLite数据库配置': 'SQLite Database Configuration',
    '邮件配置（可选，如果不需要邮件通知可以留空）': 'Email Configuration (optional, leave empty if email notification is not needed)',
    '留空表示不发送邮件': 'Leave empty to disable email',
    '配置结束': 'End of Configuration',
    '配置日志': 'Setup Logging',
    '设置日志配置': 'Setup logging configuration',
    '创建自定义StreamHandler，确保使用UTF-8编码': 'Create custom StreamHandler to ensure UTF-8 encoding',
    '使用errors=\'replace\'避免编码错误，即使控制台无法显示emoji也不会报错': 'Use errors=\'replace\' to avoid encoding errors, even if console cannot display emoji',
    '对于有buffer的流（如重定向后的stdout）': 'For streams with buffer (like redirected stdout)',
    '对于普通流': 'For normal streams',
    '如果还是出错，使用ASCII安全版本': 'If still error, use ASCII safe version',
    '完全静默处理错误，避免无限循环': 'Silently handle errors to avoid infinite loop',
    
    # Class and method comments
    '自动更新器 - 只更新 TR_Report 和 TR_Report_Deduplication 表': 'Auto Updater - Only update TR_Report and TR_Report_Deduplication tables',
    '记录每个步骤的执行结果': 'Record execution results for each step',
    '创建源数据库连接': 'Create source database connection',
    '创建SQLite数据库连接': 'Create SQLite database connection',
    '执行数据库操作，带重试机制': 'Execute database operation with retry mechanism',
    '要执行的操作（函数）': 'Operation to execute (function)',
    '最大重试次数（增加到10次，给后端服务更多时间释放锁）': 'Maximum retry times (increased to 10, give backend service more time to release lock)',
    '重试延迟（秒，增加到3秒）': 'Retry delay (seconds, increased to 3 seconds)',
    '执行SQL查询': 'Execute SQL query',
    
    # Log messages - common patterns
    '✅ ': '[OK] ',
    '❌ ': '[ERROR] ',
    '⚠️ ': '[WARNING] ',
    '🎉 ': '[SUCCESS] ',
    '💡 ': '[TIP] ',
    
    # Specific log messages
    '源数据库连接成功': 'Source database connection successful',
    '源数据库连接失败': 'Source database connection failed',
    '数据库连接测试成功（读取模式）': 'Database connection test successful (read mode)',
    'SQLite数据库连接成功（WAL模式，可写）': 'SQLite database connection successful (WAL mode, writable)',
    '数据库连接失败：数据库为只读模式': 'Database connection failed: database is read-only',
    '请检查：': 'Please check:',
    '数据库文件权限': 'Database file permissions',
    '数据库目录权限': 'Database directory permissions',
    '是否有其他进程正在锁定数据库': 'Whether other processes are locking the database',
    'WAL文件权限': 'WAL file permissions',
    '建议：如果后端服务正在运行，请稍后重试或临时停止后端服务': 'Suggestion: If backend service is running, retry later or temporarily stop the backend service',
    'SQLite数据库连接失败': 'SQLite database connection failed',
    '数据库只读错误，等待': 'Database read-only error, waiting',
    '秒后重试': 'seconds before retry',
    '提示：后端服务正在使用数据库，等待连接释放...': 'Tip: Backend service is using database, waiting for connection release...',
    '建议：如果等待时间过长，可以临时停止后端服务以提高更新速度': 'Suggestion: If waiting time is too long, you can temporarily stop backend service to speed up update',
    '数据库只读错误，已重试': 'Database read-only error, retried',
    '次仍失败': 'times but still failed',
    '原因：后端服务持续持有数据库连接，无法获取写锁': 'Reason: Backend service continuously holds database connection, cannot acquire write lock',
    '解决方案：': 'Solution:',
    '临时停止后端服务': 'Temporarily stop backend service',
    '运行更新脚本': 'Run update script',
    '重启后端服务': 'Restart backend service',
    '或者使用批处理脚本自动处理': 'Or use batch script to handle automatically',
    '需要管理员权限': 'Requires administrator privileges',
    '数据库被锁定，等待': 'Database is locked, waiting',
    '数据库被锁定，已重试': 'Database is locked, retried',
    '查询执行失败': 'Query execution failed',
    
    # More specific messages
    '步骤1: 更新Orders表': 'Step 1: Update Orders table',
    '更新订单数据（3年）': 'Update order data (3 years)',
    '年 = 1095天': 'years = 1095 days',
    
    # Code comments
    '确保数据库文件存在且可写': 'Ensure database file exists and is writable',
    '检查Database file permissions（只检查，不修改，避免影响后端服务）': 'Check database file permissions (check only, do not modify, avoid affecting backend service)',
    '只记录警告，不修改权限（避免影响后端服务）': 'Only log warning, do not modify permissions (avoid affecting backend service)',
    '无法检查Database file permissions': 'Cannot check database file permissions',
    '使用与后端服务相同的连接方式（标准连接，不使用URI模式，避免兼容性问题）': 'Use same connection method as backend service (standard connection, not URI mode, avoid compatibility issues)',
    '后端服务使用: sqlite3.connect(DB_PATH, timeout=30.0)': 'Backend service uses: sqlite3.connect(DB_PATH, timeout=30.0)',
    '这里保持一致，确保兼容性': 'Keep consistent here to ensure compatibility',
    '增加超时时间到60秒，给后端服务更多时间释放锁': 'Increase timeout to 60 seconds, give backend service more time to release lock',
    '启用 WAL 模式以提高并发性能，允许多个读取器和写入器同时访问': 'Enable WAL mode to improve concurrency, allow multiple readers and writers to access simultaneously',
    '与后端服务使用相同的 PRAGMA 设置，确保兼容': 'Use same PRAGMA settings as backend service to ensure compatibility',
    '设置同步模式为 NORMAL（在 WAL 模式下更安全且性能更好）': 'Set sync mode to NORMAL (safer and better performance in WAL mode)',
    '设置 busy_timeout（毫秒），当数据库被锁定时等待最多60秒': 'Set busy_timeout (milliseconds), wait up to 60 seconds when database is locked',
    '测试连接（只测试读取，不测试写入，避免需要独占锁）': 'Test connection (test read only, not write, avoid requiring exclusive lock)',
    '在实际写入操作时再处理锁问题，并使用重试机制': 'Handle lock issues during actual write operations, use retry mechanism',
    '只执行一个读取操作来测试连接是否正常': 'Execute only one read operation to test if connection is normal',
    '不执行 BEGIN IMMEDIATE，因为这需要独占锁，可能会失败': 'Do not execute BEGIN IMMEDIATE, as this requires exclusive lock and may fail',
    '其他错误也记录，but不立即失败': 'Also log other errors, but do not fail immediately',
    '使用固定延迟而不是指数退避，避免等待时间过长': 'Use fixed delay instead of exponential backoff to avoid long wait times',
    '重新连接数据库，尝试获取新的连接': 'Reconnect database, try to get new connection',
    '短暂延迟后重新连接': 'Reconnect after brief delay',
    '如果重新连接失败，继续重试': 'If reconnection fails, continue retry',
    '指数退避': 'exponential backoff',
    '策略：创建新表 -> 插入数据（不需要锁） -> 在最短事务中删除旧表并重命名': 'Strategy: Create new table -> Insert data (no lock needed) -> Delete old table and rename in shortest transaction',
    '关键：大部分时间（创建和写入新表）不需要锁定旧表，只有最后交换时才需要锁': 'Key: Most of the time (creating and writing new table) does not need to lock old table, only need lock during final swap',
    '步骤1-2：创建新表并写入数据（不需要锁定旧表，可以并发进行）': 'Step 1-2: Create new table and write data (no need to lock old table, can proceed concurrently)',
    '先提交，释放锁': 'Commit first, release lock',
    '将数据写入新表（这个过程不需要锁定旧表）': 'Write data to new table (this process does not need to lock old table)',
    '提交，释放锁': 'Commit, release lock',
    '步骤3-4：在最短的事务中完成表交换（这里才需要锁）': 'Step 3-4: Complete table swap in shortest transaction (lock needed here)',
    '使用 BEGIN IMMEDIATE 快速获取锁，然后立即执行删除和重命名': 'Use BEGIN IMMEDIATE to quickly acquire lock, then immediately execute delete and rename',
    '删除旧表（需要 EXCLUSIVE 锁，但时间很短）': 'Delete old table (requires EXCLUSIVE lock, but time is short)',
    '重命名新表（原子操作，几乎瞬间完成）': 'Rename new table (atomic operation, almost instant)',
    '清理临时表': 'Clean up temporary table',
    '增加重试次数和延迟，因为后端服务可能长时间持有连接': 'Increase retry count and delay, as backend service may hold connection for long time',
    
    # More code comments
    '在实际写入操作时再处理锁问题，使用重试机制': 'Handle lock issues during actual write operations, use retry mechanism',
    '其他错误也记录，but不立即失败': 'Also log other errors, but do not fail immediately',
    '显式提交确保数据被写入': 'Explicit commit to ensure data is written',
    '更新成功': 'update successful',
    '行': 'rows',
    '订单数据为空': 'Order data is empty',
    '更新Orderstable失败': 'Update Orders table failed',
    '更新原材料数据（3年）': 'Update material data (3 years)',
    '步骤2: 更新Materialstable': 'Step 2: Update Materials table',
    
    # Table operations
    '已使用表重命名策略更新': 'Updated using table renaming strategy',
    '表（无需停止后端服务）': 'table (no need to stop backend service)',
    '无法更新表': 'Cannot update table',
    '原因：后端服务可能正在使用数据库，无法获取写锁': 'Reason: Backend service may be using database, cannot acquire write lock',
    '没有获取到新数据，保留现有': 'No new data retrieved, keeping existing',
    '表': 'table',
    '写入数据到临时表...': 'Writing data to temporary table...',
    
    # Progress messages
    '注意：正在获取': 'Note: Fetching',
    '条记录，这可能需要几分钟时间，请耐心等待...': 'records, this may take several minutes, please wait...',
    '如果网络较慢或数据量很大，可能需要5-15分钟': 'If network is slow or data volume is large, may take 5-15 minutes',
    '获取了': 'Retrieved',
    '条记录（完成）': 'records (completed)',
    '条记录': 'records',
    '已读取:': 'Read:',
    '分批读取失败，使用一次性读取': 'Batch read failed, using one-time read',
    '表已存在，当前有': 'table already exists, currently has',
    '条记录': 'records',
    '从SQL Server查询到0条新数据': 'Queried 0 new records from SQL Server',
    '但': 'but',
    '表中已有': 'table already has',
    '条记录，保留现有数据': 'records, keeping existing data',
    
    # Error messages
    '无法检查数据库文件权限': 'Cannot check database file permissions',
    '数据库文件可能为只读，如果更新失败请检查文件权限': 'Database file may be read-only, if update fails please check file permissions',
    '连接测试时出现错误': 'Error occurred during connection test',
    '将在实际操作时重试': 'Will retry during actual operation',
    
    # Service check messages
    '警告：后端服务（TR-Backend）正在运行': 'Warning: Backend service (TR-Backend) is running',
    '这可能导致数据库更新失败（只读错误）': 'This may cause database update to fail (read-only error)',
    '建议：': 'Suggestion:',
    '更新完成后重启': 'Restart after update completes',
    '或者等待系统自动重试（可能需要较长时间）': 'Or wait for system to automatically retry (may take a long time)',
    '后端服务（TR-Backend）已停止，可以安全更新数据库': 'Backend service (TR-Backend) is stopped, can safely update database',
    
    # Final messages
    '所有数据更新成功，执行时间': 'All data update successful, execution time',
    '部分数据更新失败': 'Partial data update failed',
    '更新结果详情': 'Update result details',
    '更新流程失败': 'Update process failed',
    '关闭连接': 'Close connection',
    '和文件索引自动更新流程结束': 'and file index auto update process ended',
    '结束时间': 'End time',
    
    # Main function messages
    '脚本启动时间': 'Script start time',
    'Python版本': 'Python version',
    '工作目录': 'Working directory',
    '脚本路径': 'Script path',
    '脚本执行完成': 'Script execution completed',
    '执行过程中发生错误': 'Error occurred during execution',
    '导入错误': 'Import error',
    '请确保已安装所有必需的依赖包': 'Please ensure all required dependencies are installed',
    '安装命令': 'Install command',
    '脚本执行失败': 'Script execution failed',
    '警告: 无法创建日志目录': 'Warning: Cannot create log directory',
    '警告: 无法创建错误日志文件': 'Warning: Cannot create error log file',
    '无法连接源数据库': 'Cannot connect to source database',
    '无法连接SQLite数据库': 'Cannot connect to SQLite database',
}

print("Replacing Chinese text with English...")
for chinese, english in replacements.items():
    content = content.replace(chinese, english)

# Also replace emoji-only patterns
content = re.sub(r'✅\s*', '[OK] ', content)
content = re.sub(r'❌\s*', '[ERROR] ', content)
content = re.sub(r'⚠️\s*', '[WARNING] ', content)
content = re.sub(r'🎉\s*', '[SUCCESS] ', content)
content = re.sub(r'💡\s*', '[TIP] ', content)

print(f"Writing {output_file}...")
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Done! Created {output_file}")
