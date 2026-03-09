#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix remaining Chinese characters in auto_update_all_tables_fixed.py
"""

import re
import sys

input_file = 'auto_update_all_tables_fixed.py'
output_file = 'auto_update_all_tables_fixed.py'

print(f"Reading {input_file}...")
with open(input_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Find all Chinese text patterns
chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')

def replace_chinese_in_string(match):
    """Replace Chinese text with placeholder, we'll handle specific cases"""
    chinese_text = match.group(0)
    # Common replacements
    replacements = {
        '原材料数据为空': 'Material data is empty',
        '更新Materialstable失败': 'Update Materials table failed',
        '步骤3: 生成Orders_comtable': 'Step 3: Generate Orders_com table',
        '压缩订单数据，生成Orders_comtable': 'Compress order data, generate Orders_com table',
        '原始订单数据': 'Original order data',
        '文本清理': 'Text cleaning',
        '重量单位转换': 'Weight unit conversion',
        'Orders_comtable生成成功': 'Orders_com table generated successfully',
        '压缩率': 'Compression ratio',
        '生成Orders_comtable失败': 'Generate Orders_com table failed',
        '步骤4: 生成Materials_comtable': 'Step 4: Generate Materials_com table',
        '压缩原材料数据，生成Materials_comtable': 'Compress material data, generate Materials_com table',
        '原始原材料数据': 'Original material data',
        '提取直径信息': 'Extract diameter information',
        '提取长度信息': 'Extract length information',
        '去重': 'Deduplicate',
        'Materials_comtable生成成功': 'Materials_com table generated successfully',
        '生成Materials_comtable失败': 'Generate Materials_com table failed',
        '步骤5: 生成Orders_Deduplicationtable': 'Step 5: Generate Orders_Deduplication table',
        '生成Orders_Deduplicationtable': 'Generate Orders_Deduplication table',
        '读取orders_com数据': 'Read orders_com data',
        '映射Jobsite_Type': 'Map Jobsite_Type',
        'Orders_Deduplicationtable生成成功': 'Orders_Deduplication table generated successfully',
        '生成Orders_Deduplicationtable失败': 'Generate Orders_Deduplication table failed',
        '步骤6: 生成Orders_gen_pdftable': 'Step 6: Generate Orders_gen_pdf table',
        '生成Orders_gen_pdftable': 'Generate Orders_gen_pdf table',
        '检查TR_Fill_intable是否存在': 'Check if TR_Fill_in table exists',
        'TR_Fill_intable不存在，跳过Orders_gen_pdf生成': 'TR_Fill_in table does not exist, skip Orders_gen_pdf generation',
        'TR_Fill_intable不存在': 'TR_Fill_in table does not exist',
        '检查TR_Fill_intable是否有数据': 'Check if TR_Fill_in table has data',
        'TR_Fill_intable为空，跳过Orders_gen_pdf生成': 'TR_Fill_in table is empty, skip Orders_gen_pdf generation',
        'TR_Fill_intable为空': 'TR_Fill_in table is empty',
        'TR_Fill_intable有': 'TR_Fill_in table has',
        '删除已存在的table': 'Delete existing table',
        '创建新table': 'Create new table',
        'Orders_gen_pdftable生成成功': 'Orders_gen_pdf table generated successfully',
        '生成Orders_gen_pdftable失败': 'Generate Orders_gen_pdf table failed',
        '步骤7: 检查PDF_Statustable': 'Step 7: Check PDF_Status table',
        '确保PDF_Statustable存在（如果不存在则创建）': 'Ensure PDF_Status table exists (create if not exists)',
        '检查PDF_Statustable是否存在': 'Check if PDF_Status table exists',
        'table已存在，检查记录数': 'Table already exists, check record count',
        'PDF_Statustable已存在，当前记录数': 'PDF_Status table already exists, current record count',
        'table不存在，创建它': 'Table does not exist, create it',
        'PDF_Statustable不存在，正在创建': 'PDF_Status table does not exist, creating...',
        'PDF_Statustable创建成功，当前记录数': 'PDF_Status table created successfully, current record count',
        '检查/创建PDF_Statustable失败': 'Check/create PDF_Status table failed',
        '步骤8: 检查TR_Fill_intable': 'Step 8: Check TR_Fill_in table',
        '确保TR_Fill_intable存在（如果不存在则创建）': 'Ensure TR_Fill_in table exists (create if not exists)',
        '检查TR_Fill_intable是否存在': 'Check if TR_Fill_in table exists',
        'TR_Fill_intable已存在，当前记录数': 'TR_Fill_in table already exists, current record count',
        'TR_Fill_intable不存在，正在创建': 'TR_Fill_in table does not exist, creating...',
        'TR_Fill_intable创建成功，当前记录数': 'TR_Fill_in table created successfully, current record count',
        '检查/创建TR_Fill_intable失败': 'Check/create TR_Fill_in table failed',
        '步骤1: 创建 TR_Report table': 'Step 1: Create TR_Report table',
        '创建 TR_Report table - 从 SQL Server 查询近3年的数据，直接在 SQLite 中创建': 'Create TR_Report table - Query last 3 years data from SQL Server, create directly in SQLite',
        '查询近3年的数据': 'Query last 3 years data',
        '找到': 'Found',
        '条近3年的记录': 'records in last 3 years',
        '近3年没有数据，table将为空': 'No data in last 3 years, table will be empty',
        '从 SQL Server 获取数据': 'Get data from SQL Server',
        '使用chunksize分批读取，避免内存问题（如果数据量很大）': 'Use chunksize to read in batches, avoid memory issues (if data volume is large)',
        '尝试使用chunksize分批读取': 'Try to use chunksize to read in batches',
        '每次读取5万条': 'Read 50,000 records each time',
        '每10万records输出一次进度': 'Output progress every 100,000 records',
        '合并所有chunks': 'Merge all chunks',
        '如果分批读取失败，回退到一次性读取': 'If batch read fails, fall back to one-time read',
        '连接到 SQLite': 'Connect to SQLite',
        '检查TR_Reporttable是否已存在且有数据': 'Check if TR_Report table already exists and has data',
        'TR_Reporttable已存在，当前有': 'TR_Report table already exists, currently has',
        'butTR_Reporttable中已有': 'but TR_Report table already has',
        '保留现有数据，不删除table': 'Keep existing data, do not delete table',
        '如果有新数据，使用table重命名策略（避免DROP TABLE需要独占锁）': 'If there is new data, use table renaming strategy (avoid DROP TABLE requiring exclusive lock)',
        '没有新数据，保留现有数据': 'No new data, keep existing data',
        '使用table重命名策略写入数据（避免独占锁，无需停止后端服务）': 'Use table renaming strategy to write data (avoid exclusive lock, no need to stop backend service)',
        '创建临时table': 'Create temporary table',
        '写入数据到临时table': 'Write data to temporary table',
        '删除旧table': 'Delete old table',
        '重命名临时table（原子操作，最小化锁定时间）': 'Rename temporary table (atomic operation, minimize lock time)',
        '验证': 'Verify',
        'TR_Report table创建成功': 'TR_Report table created successfully',
        '统计信息': 'Statistics',
        'table统计信息': 'Table statistics',
        '最早日期': 'Earliest date',
        '最晚日期': 'Latest date',
        '唯一订单数': 'Unique order count',
        '唯一工地数': 'Unique jobsite count',
        '创建 TR_Report table失败': 'Create TR_Report table failed',
        '步骤2: 创建 TR_Report_Deduplication table': 'Step 2: Create TR_Report_Deduplication table',
        '创建 TR_Report_Deduplication table - 从 TR_Report table按 Order_No 去重生成': 'Create TR_Report_Deduplication table - Deduplicate from TR_Report table by Order_No',
        'TR_Report table不存在，请先创建 TR_Report table': 'TR_Report table does not exist, please create TR_Report table first',
        '从 TR_Report table读取数据': 'Read data from TR_Report table',
        '从 TR_Report 读取了': 'Read from TR_Report',
        'TR_Report table为空，TR_Report_Deduplication 也将为空': 'TR_Report table is empty, TR_Report_Deduplication will also be empty',
        '按 order_no 分组并聚合': 'Group and aggregate by order_no',
        '累加重量': 'Sum weight',
        '重命名列以匹配 TR_Report_Deduplication 的命名风格': 'Rename columns to match TR_Report_Deduplication naming style',
        '已经是正确名称，不需要重命名': 'is already correct name, no need to rename',
        '聚合为': 'Aggregated to',
        '个唯一订单': 'unique orders',
        '按 Del_Date 降序排列': 'Sort by Del_Date descending',
        '使用table重命名策略更新table（避免DROP TABLE需要独占锁）': 'Use table renaming strategy to update table (avoid DROP TABLE requiring exclusive lock)',
        '关键：先创建新table并写入数据（不需要锁），然后在最短事务中完成table交换': 'Key: First create new table and write data (no lock needed), then complete table swap in shortest transaction',
        'TR_Report_Deduplication table创建成功': 'TR_Report_Deduplication table created successfully',
        '显示统计信息': 'Display statistics',
        '总重量': 'Total weight',
        '吨': 'tons',
        '工地类型数': 'Jobsite type count',
        '创建 TR_Report_Deduplication table失败': 'Create TR_Report_Deduplication table failed',
        '步骤: 更新文件索引缓存': 'Step: Update file index cache',
        '更新文件索引缓存': 'Update file index cache',
        '无法导入文件索引更新器': 'Cannot import file index updater',
        '跳过文件索引更新': 'Skip file index update',
        '模块导入失败': 'Module import failed',
        '获取数据库路径': 'Get database path',
        '获取基础文件夹路径（从环境变量或使用默认值）': 'Get base folder path (from environment variable or use default)',
        '文件夹不存在': 'Folder does not exist',
        '创建更新器并执rows更新': 'Create updater and execute update',
        '文件索引缓存update successful': 'File index cache update successful',
        '新增': 'Added',
        '更新': 'Updated',
        '删除': 'Deleted',
        '检查': 'Checked',
        '未知错误': 'Unknown error',
        '文件索引缓存更新失败': 'File index cache update failed',
        '文件索引更新异常': 'File index update exception',
        '获取bbs_ddtable的结构，用于判断日期字段': 'Get bbs_dd table structure to determine date fields',
        '查询table结构': 'Query table structure',
        'bbs_dd table结构': 'bbs_dd table structure',
        '无法获取bbs_ddtable结构': 'Cannot get bbs_dd table structure',
        '创建 bbs_dd table - 从 SQL Server 查询近3年的数据': 'Create bbs_dd table - Query last 3 years data from SQL Server',
        '开始创建 bbs_dd table': 'Start creating bbs_dd table',
        '先获取table结构，查找日期字段': 'First get table structure, find date fields',
        '构建查询SQL': 'Build query SQL',
        '如果有日期字段，添加近3年的筛选条件': 'If there are date fields, add last 3 years filter condition',
        '使用第一个日期字段作为筛选条件': 'Use first date field as filter condition',
    }
    
    if chinese_text in replacements:
        return replacements[chinese_text]
    else:
        # Generic replacement - keep the Chinese but add a comment
        return f'[{chinese_text}]'  # Placeholder, will need manual translation

# Replace all Chinese text
print("Replacing remaining Chinese text...")
lines = content.split('\n')
new_lines = []
for line in lines:
    # Only replace in strings and comments, not in code
    if '#' in line or '"' in line or "'" in line:
        # Replace Chinese in this line
        new_line = chinese_pattern.sub(replace_chinese_in_string, line)
        new_lines.append(new_line)
    else:
        new_lines.append(line)

content = '\n'.join(new_lines)

# Write the fixed file
print(f"Writing {output_file}...")
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Done! Check {output_file} for any remaining Chinese text that needs manual translation.")
