#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Final conversion script to replace ALL Chinese text with English
"""

import re
import sys

input_file = 'auto_update_all_tables.py'
output_file = 'auto_update_all_tables_fixed.py'

print(f"Reading {input_file}...")
with open(input_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Comprehensive replacement dictionary
replacements = {
    # Header
    'TR_Report 和 TR_Report_Deduplication 自动更新脚本': 'TR_Report and TR_Report_Deduplication Auto Update Script',
    '功能：自动更新 TR_Report 和 TR_Report_Deduplication 表': 'Function: Auto update TR_Report and TR_Report_Deduplication tables',
    '作者：TR Report System': 'Author: TR Report System',
    '日期：2025-11-20': 'Date: 2025-11-20',
    
    # Common patterns
    '步骤': 'Step',
    '生成': 'Generate',
    '更新': 'Update',
    '创建': 'Create',
    '检查': 'Check',
    '失败': 'failed',
    '成功': 'successful',
    '为空': 'is empty',
    '数据': 'data',
    '记录': 'records',
    '条': '',
    '个': '',
    '行': 'rows',
    '表': 'table',
    'table': 'table',  # Keep table as is
    '统计信息': 'Statistics',
    '最早日期': 'Earliest date',
    '最晚日期': 'Latest date',
    '唯一订单数': 'Unique order count',
    '唯一工地数': 'Unique jobsite count',
    '总重量': 'Total weight',
    '吨': 'tons',
    '工地类型数': 'Jobsite type count',
    '压缩率': 'Compression ratio',
    '原始': 'Original',
    '订单': 'order',
    '原材料': 'material',
    '文本清理': 'Text cleaning',
    '重量单位转换': 'Weight unit conversion',
    '提取直径信息': 'Extract diameter information',
    '提取长度信息': 'Extract length information',
    '去重': 'Deduplicate',
    '映射': 'Map',
    '分组': 'Group',
    '聚合': 'Aggregate',
    '累加': 'Sum',
    '重量': 'weight',
    '降序排列': 'Sort descending',
    '读取': 'Read',
    '写入': 'Write',
    '临时': 'temporary',
    '删除': 'Delete',
    '旧': 'old',
    '新': 'new',
    '重命名': 'Rename',
    '验证': 'Verify',
    '显示': 'Display',
    '跳过': 'Skip',
    '无法': 'Cannot',
    '导入': 'import',
    '模块': 'module',
    '获取': 'Get',
    '文件夹': 'folder',
    '不存在': 'does not exist',
    '已存在': 'already exists',
    '当前': 'current',
    '记录数': 'record count',
    '正在': 'is',
    '创建它': 'create it',
    '请先': 'please first',
    '也将': 'will also',
    '为空': 'is empty',
    '按': 'by',
    '匹配': 'match',
    '命名风格': 'naming style',
    '已经是正确名称': 'is already correct name',
    '不需要重命名': 'no need to rename',
    '唯一订单': 'unique orders',
    '近3年': 'last 3 years',
    '没有数据': 'no data',
    '将为空': 'will be empty',
    '从 SQL Server': 'from SQL Server',
    '获取数据': 'Get data',
    '使用chunksize分批读取': 'Use chunksize to read in batches',
    '避免内存问题': 'avoid memory issues',
    '如果数据量很大': 'if data volume is large',
    '尝试使用': 'Try to use',
    '每次读取': 'Read each time',
    '万条': '0,000 records',
    '输出一次进度': 'output progress once',
    '合并所有chunks': 'Merge all chunks',
    '如果分批读取失败': 'If batch read fails',
    '回退到一次性读取': 'fall back to one-time read',
    '连接到 SQLite': 'Connect to SQLite',
    '是否已存在且有数据': 'already exists and has data',
    '当前有': 'currently has',
    '但': 'but',
    '中已有': 'already has',
    '保留现有数据': 'Keep existing data',
    '不删除': 'do not delete',
    '如果有新数据': 'If there is new data',
    '使用表重命名策略': 'Use table renaming strategy',
    '避免DROP TABLE需要独占锁': 'avoid DROP TABLE requiring exclusive lock',
    '没有新数据': 'No new data',
    '保留现有': 'keep existing',
    '避免独占锁': 'avoid exclusive lock',
    '无需停止后端服务': 'no need to stop backend service',
    '原子操作': 'atomic operation',
    '最小化锁定时间': 'minimize lock time',
    '文件索引缓存': 'File index cache',
    '更新文件索引缓存': 'Update file index cache',
    '无法导入文件索引更新器': 'Cannot import file index updater',
    '跳过文件索引更新': 'Skip file index update',
    '模块导入失败': 'Module import failed',
    '获取数据库路径': 'Get database path',
    '获取基础文件夹路径': 'Get base folder path',
    '从环境变量或使用默认值': 'from environment variable or use default',
    '检查文件夹是否存在': 'Check if folder exists',
    '创建更新器并执行更新': 'Create updater and execute update',
    '新增': 'Added',
    '更新': 'Updated',
    '删除': 'Deleted',
    '检查': 'Checked',
    '未知错误': 'Unknown error',
    '更新失败': 'update failed',
    '更新异常': 'update exception',
    '获取bbs_dd表的结构': 'Get bbs_dd table structure',
    '用于判断日期字段': 'to determine date fields',
    '查询表结构': 'Query table structure',
    'bbs_dd表结构': 'bbs_dd table structure',
    '无法获取bbs_dd表结构': 'Cannot get bbs_dd table structure',
    '开始创建': 'Start creating',
    '先获取表结构': 'First get table structure',
    '查找日期字段': 'find date fields',
    '构建查询SQL': 'Build query SQL',
    '如果有日期字段': 'If there are date fields',
    '添加近3年的筛选条件': 'add last 3 years filter condition',
    '使用第一个日期字段作为筛选条件': 'Use first date field as filter condition',
}

# Apply replacements
print("Applying replacements...")
for chinese, english in replacements.items():
    content = content.replace(chinese, english)

# Fix common patterns
content = re.sub(r'步骤(\d+):', r'Step \1:', content)
content = re.sub(r'(\d+)条记录', r'\1 records', content)
content = re.sub(r'(\d+)个', r'\1', content)
content = re.sub(r'(\d+)行', r'\1 rows', content)

# Remove emoji and replace with text
content = content.replace('✅', '[OK]')
content = content.replace('❌', '[ERROR]')
content = content.replace('⚠️', '[WARNING]')
content = content.replace('🎉', '[SUCCESS]')
content = content.replace('💡', '[TIP]')
content = content.replace('📋', '[INFO]')

print(f"Writing {output_file}...")
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(content)

# Check remaining Chinese
remaining = re.findall(r'[\u4e00-\u9fff]+', content)
if remaining:
    print(f"\nWarning: Found {len(set(remaining))} remaining Chinese phrases")
    print("Sample:", list(set(remaining))[:10])
else:
    print("\nSuccess! All Chinese text has been replaced.")

print(f"\nDone! Created {output_file}")
