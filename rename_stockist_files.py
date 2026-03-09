#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stockist Cert 文件重命名脚本
将多种格式的文件名统一重命名为 DD_No_Stockist_No_Date 格式

支持的输入格式：
- Stockist + MIll Cert_C0483
- Stockist + MIll Cert_C0475
- SS76288_SS76288_30_MAY_2024
- Stockist cert & mill cert of SS73441

目标格式：DD_No_Stockist_No_Date
例如：SS79988_ZZ4306_06_FEB_2026
"""

import os
import re
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple, Dict
from datetime import datetime
import sys

# 获取脚本文件的绝对路径（无论从哪个目录运行脚本）
_script_file = os.path.abspath(__file__)
_script_dir = os.path.dirname(_script_file)

# 查找 TR-master 目录（项目根目录）
# 方法1: 如果脚本在 TR-master 目录或其子目录中
_project_root = None
current = _script_dir
while current and current != os.path.dirname(current):
    if os.path.basename(current) == 'TR-master':
        _project_root = current
        break
    current = os.path.dirname(current)

# 方法2: 如果找不到，尝试使用固定的绝对路径
if not _project_root:
    _fixed_path = r'C:\TR-master'
    if os.path.exists(_fixed_path) and os.path.exists(os.path.join(_fixed_path, 'TR database')):
        _project_root = _fixed_path

# 方法3: 如果还是找不到，使用脚本所在目录（假设脚本在 TR-master 目录下）
if not _project_root:
    _project_root = _script_dir

# 添加 backend 目录到路径
backend_dir = os.path.join(_project_root, 'TR UI', 'backend')
if os.path.exists(backend_dir):
    sys.path.insert(0, backend_dir)

# 数据库路径
_default_db_path = os.path.join(_project_root, 'TR database', 'data_3years.db')
DB_PATH = os.getenv('DB_PATH', _default_db_path)

# 如果环境变量是相对路径，转换为绝对路径
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.abspath(os.path.join(_project_root, DB_PATH))

# Stockist Cert 文件夹路径
STOCKIST_CERT_FOLDER = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
STOCKIST_CERT_FOLDER = os.path.join(STOCKIST_CERT_FOLDER, 'Stockist Cert')

# Stockist 与 DD_No 对应关系 XLSX 路径
_default_mapping_xlsx_path = os.path.join(_project_root, 'stockist_dn_mapping.xlsx')
MAPPING_XLSX_PATH = os.getenv('STOCKIST_DN_MAPPING_XLSX', _default_mapping_xlsx_path)

# 如果环境变量是相对路径，转换为绝对路径
if not os.path.isabs(MAPPING_XLSX_PATH):
    MAPPING_XLSX_PATH = os.path.abspath(os.path.join(_project_root, MAPPING_XLSX_PATH))


class StockistFileRenamer:
    """Stockist Cert 文件重命名器"""
    
    def __init__(self, db_path: str):
        """
        初始化重命名器
        
        Args:
            db_path: SQLite 数据库路径
        """
        self.db_path = db_path
        self.mapping_xlsx_path = MAPPING_XLSX_PATH
        self.stockist_to_dd = {}
        self.dd_to_stockist = {}
        self._load_xlsx_mapping()

    def _normalize_key(self, value: str) -> str:
        """规范化匹配键值：去首尾空格、压缩多空格、转大写"""
        if not value:
            return ""
        normalized = str(value).replace('_', ' ')
        normalized = re.sub(r'\s+', ' ', normalized.strip())
        return normalized.upper()

    def _extract_dn_candidates(self, value: str) -> list:
        """从字符串中提取可能的 DN 标识（如 SS71417、NW00018、DN112466-1）"""
        if not value:
            return []
        text = self._normalize_key(value)
        candidates = []
        # 覆盖常见 DN 形式：SSxxxxx、NWxxxxx、DNxxxxx、以及带后缀的 -1 / -A1
        for token in re.findall(r'[A-Z]{1,}\d{3,}(?:-[A-Z0-9]+)?', text):
            if token not in candidates:
                candidates.append(token)
        return candidates

    def _load_xlsx_mapping(self):
        """加载 XLSX 映射文件（Stockist -> DD_No, DD_No -> Stockist）"""
        if not self.mapping_xlsx_path or not os.path.exists(self.mapping_xlsx_path):
            return

        try:
            ns = {
                'm': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
                'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
                'pr': 'http://schemas.openxmlformats.org/package/2006/relationships',
            }

            with zipfile.ZipFile(self.mapping_xlsx_path) as zf:
                workbook_xml = ET.fromstring(zf.read('xl/workbook.xml'))
                first_sheet = workbook_xml.find('.//m:sheets/m:sheet', ns)
                if first_sheet is None:
                    return

                rel_id = first_sheet.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                if not rel_id:
                    return

                rels_xml = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
                rel_map = {}
                for rel in rels_xml.findall('.//pr:Relationship', ns):
                    rid = rel.attrib.get('Id')
                    target = rel.attrib.get('Target')
                    if rid and target:
                        rel_map[rid] = target

                sheet_target = rel_map.get(rel_id)
                if not sheet_target:
                    return
                # 兼容多种 target 形式：
                # /xl/worksheets/sheet1.xml、xl/worksheets/sheet1.xml、worksheets/sheet1.xml
                sheet_xml_path = sheet_target.lstrip('/')
                if not sheet_xml_path.startswith('xl/'):
                    sheet_xml_path = f"xl/{sheet_xml_path}"

                shared_strings = []
                if 'xl/sharedStrings.xml' in zf.namelist():
                    sst_xml = ET.fromstring(zf.read('xl/sharedStrings.xml'))
                    for si in sst_xml.findall('.//m:si', ns):
                        text = ''.join(node.text or '' for node in si.findall('.//m:t', ns))
                        shared_strings.append(text)

                sheet_xml = ET.fromstring(zf.read(sheet_xml_path))

                def _cell_value(cell):
                    cell_type = cell.attrib.get('t')
                    if cell_type == 's':
                        v = cell.find('m:v', ns)
                        if v is not None and v.text is not None:
                            idx = int(v.text)
                            if 0 <= idx < len(shared_strings):
                                return shared_strings[idx]
                        return ''
                    if cell_type == 'inlineStr':
                        tnode = cell.find('m:is/m:t', ns)
                        return tnode.text if (tnode is not None and tnode.text is not None) else ''
                    v = cell.find('m:v', ns)
                    return v.text if (v is not None and v.text is not None) else ''

                rows = []
                for row in sheet_xml.findall('.//m:sheetData/m:row', ns):
                    row_data = {}
                    for cell in row.findall('m:c', ns):
                        ref = cell.attrib.get('r', '')
                        col = ''.join(ch for ch in ref if ch.isalpha())
                        if not col:
                            continue
                        row_data[col] = str(_cell_value(cell)).strip()
                    if row_data:
                        rows.append(row_data)

                if not rows:
                    return

                # 识别表头（支持 "Stockist"、"Stockist_Cert"、"DN#"、"DN_List" 等）
                header = rows[0]
                stockist_col = None
                dn_col = None
                for col, raw_header in header.items():
                    key = self._normalize_key(raw_header)
                    if key in ('STOCKIST', 'STOCKIST CERT'):
                        stockist_col = col
                    if key in ('DN#', 'DN #', 'DN', 'DN NO', 'DN NO.', 'DN LIST'):
                        dn_col = col

                if not stockist_col or not dn_col:
                    return

                for row in rows[1:]:
                    stockist_raw = str(row.get(stockist_col, '')).strip()
                    dd_no_raw = str(row.get(dn_col, '')).strip()
                    if not stockist_raw or not dd_no_raw:
                        continue

                    stockist_key = self._normalize_key(stockist_raw)
                    dd_no_key = self._normalize_key(dd_no_raw)
                    if not stockist_key or not dd_no_key:
                        continue

                    # 保留首个映射，避免后续重复值覆盖
                    if stockist_key not in self.stockist_to_dd:
                        self.stockist_to_dd[stockist_key] = dd_no_raw
                    if dd_no_key not in self.dd_to_stockist:
                        self.dd_to_stockist[dd_no_key] = stockist_raw

                    # 同时将 DN_List 中可拆分的单个 DN 建立索引
                    for dn_candidate in self._extract_dn_candidates(dd_no_raw):
                        if dn_candidate not in self.dd_to_stockist:
                            self.dd_to_stockist[dn_candidate] = stockist_raw
        except Exception:
            # XLSX 加载失败时静默，仅保留数据库查询
            self.stockist_to_dd = {}
            self.dd_to_stockist = {}
        
    def extract_identifiers_from_filename(self, filename: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        从文件名中提取 DD_No、Stockist_No 和 Date
        
        Args:
            filename: 文件名（不含扩展名）
            
        Returns:
            (dd_no, stockist_no, date_str) 元组
        """
        filename_upper = filename.upper()
        
        # 模式1: SS76288_SS76288_30_MAY_2024 或 SS79988_ZZ4306_06_FEB_2026
        # 提取格式：DD_No_Stockist_No_Date 或 DD_No_DD_No_Date
        pattern1 = re.compile(r'^([A-Z]{2,}\d+)_([A-Z]{2,}\d+)_(\d{1,2})_([A-Z]{3})_(\d{4})$')
        match1 = pattern1.match(filename_upper)
        if match1:
            dd_no = match1.group(1)  # 第一个标识符作为 DD_No
            second_id = match1.group(2)  # 第二个标识符
            day = match1.group(3).zfill(2)  # 日期
            month = match1.group(4)
            year = match1.group(5)
            date_str = f"{day}_{month}_{year}"
            
            # 如果第二个标识符与第一个相同（如 SS76288_SS76288），需要从数据库查询 Stockist_No
            if second_id == dd_no:
                stockist_no = None  # 标记需要查询
            else:
                stockist_no = second_id  # 使用第二个标识符作为 Stockist_No
            
            return dd_no, stockist_no, date_str
        
        # 模式2: Stockist + MIll Cert_C0483 或 Stockist + MIll Cert_C0475
        # 提取 Stockist_No (C0483, C0475 等)
        pattern2 = re.compile(r'STOCKIST.*?MILL.*?CERT[_\s]+([A-Z]\d+)', re.IGNORECASE)
        match2 = pattern2.search(filename_upper)
        if match2:
            stockist_no = match2.group(1)
            # 尝试从文件名中提取 DD_No（通常是 SS 开头的格式）
            dd_no_pattern = re.compile(r'([A-Z]{2,}\d{4,})')
            dd_no_matches = dd_no_pattern.findall(filename_upper)
            # 过滤掉 Stockist_No（Stockist_No 通常是单个字母+数字，如 C0483）
            dd_no_candidates = [m for m in dd_no_matches if m != stockist_no and len(m) > len(stockist_no)]
            dd_no = dd_no_candidates[0] if dd_no_candidates else None
            return dd_no, stockist_no, None
        
        # 模式3: Stockist cert & mill cert of SS73441
        # 提取 DD_No (SS73441)
        pattern3 = re.compile(r'STOCKIST.*?CERT.*?MILL.*?CERT.*?OF\s+([A-Z]{2,}\d+)', re.IGNORECASE)
        match3 = pattern3.search(filename_upper)
        if match3:
            dd_no = match3.group(1)
            # 尝试提取 Stockist_No
            stockist_pattern = re.compile(r'([A-Z]{2,}\d+)')
            all_matches = stockist_pattern.findall(filename_upper)
            stockist_candidates = [m for m in all_matches if m != dd_no]
            stockist_no = stockist_candidates[0] if stockist_candidates else None
            return dd_no, stockist_no, None
        
        # 模式4: 尝试提取所有可能的标识符
        # 优先匹配较长的标识符（通常是 DD_No，如 SS76288）
        dd_no_pattern = re.compile(r'([A-Z]{2,}\d{4,})')
        stockist_pattern = re.compile(r'([A-Z]\d{3,})')
        
        dd_no_matches = dd_no_pattern.findall(filename_upper)
        stockist_matches = stockist_pattern.findall(filename_upper)
        
        # 过滤：DD_No 通常是较长的（如 SS76288），Stockist_No 通常是较短的（如 C0483）
        dd_no = None
        stockist_no = None
        
        if dd_no_matches:
            # 选择最长的作为 DD_No
            dd_no = max(dd_no_matches, key=len)
        
        if stockist_matches:
            # 选择与 DD_No 不同的作为 Stockist_No
            stockist_candidates = [m for m in stockist_matches if m != dd_no]
            if stockist_candidates:
                stockist_no = stockist_candidates[0]
        
        if dd_no or stockist_no:
            return dd_no, stockist_no, None
        
        return None, None, None
    
    def query_dd_no_from_stockist(self, stockist_no: str) -> Optional[str]:
        """
        从数据库查询 Stockist_No 对应的 DD_No
        
        Args:
            stockist_no: Stockist_No
            
        Returns:
            DD_No，如果未找到返回 None
        """
        if not stockist_no:
            return None

        # 1) 先查 SQLite
        if os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = """
                    SELECT DISTINCT rm_dn_no
                    FROM TR_Report
                    WHERE stockist_cert = ? AND rm_dn_no IS NOT NULL AND rm_dn_no != ''
                    LIMIT 1
                """
                cursor.execute(query, (stockist_no,))
                row = cursor.fetchone()
                
                if row and row['rm_dn_no']:
                    return str(row['rm_dn_no']).strip()
            except sqlite3.OperationalError:
                pass
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except:
                    pass

        # 2) 再查 XLSX 映射
        stockist_key = self._normalize_key(stockist_no)
        mapped_dd_no = self.stockist_to_dd.get(stockist_key)
        if mapped_dd_no:
            return str(mapped_dd_no).strip()
        
        return None
    
    def query_stockist_from_dd_no(self, dd_no: str) -> Optional[str]:
        """
        从数据库查询 DD_No 对应的 Stockist_No
        
        Args:
            dd_no: DD_No
            
        Returns:
            Stockist_No，如果未找到返回 None
        """
        if not dd_no:
            return None

        # 1) 先查 SQLite
        if os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = """
                    SELECT DISTINCT stockist_cert
                    FROM TR_Report
                    WHERE rm_dn_no = ? AND stockist_cert IS NOT NULL AND stockist_cert != ''
                    LIMIT 1
                """
                cursor.execute(query, (dd_no,))
                row = cursor.fetchone()
                
                if row and row['stockist_cert']:
                    return str(row['stockist_cert']).strip()
            except sqlite3.OperationalError:
                pass
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except:
                    pass

        # 2) 再查 XLSX 映射
        dd_no_key = self._normalize_key(dd_no)
        mapped_stockist = self.dd_to_stockist.get(dd_no_key)
        if mapped_stockist:
            return str(mapped_stockist).strip()

        # 3) 若输入包含组合值或扩展名，再尝试按 DN 片段匹配
        for candidate in self._extract_dn_candidates(dd_no):
            mapped_stockist = self.dd_to_stockist.get(candidate)
            if mapped_stockist:
                return str(mapped_stockist).strip()
        
        return None
    
    def get_file_date(self, file_path: str) -> str:
        """
        从文件修改时间获取日期字符串（格式：DD_MON_YYYY）
        
        Args:
            file_path: 文件路径
            
        Returns:
            日期字符串，格式：06_FEB_2026
        """
        try:
            mtime = os.path.getmtime(file_path)
            dt = datetime.fromtimestamp(mtime)
            day = dt.strftime('%d')
            month = dt.strftime('%b').upper()
            year = dt.strftime('%Y')
            return f"{day}_{month}_{year}"
        except Exception:
            # 如果获取失败，使用当前日期
            dt = datetime.now()
            day = dt.strftime('%d')
            month = dt.strftime('%b').upper()
            year = dt.strftime('%Y')
            return f"{day}_{month}_{year}"
    
    def generate_new_filename(self, dd_no: str, stockist_no: str, date_str: str, extension: str) -> str:
        """
        生成新的文件名
        
        Args:
            dd_no: DD_No
            stockist_no: Stockist_No
            date_str: 日期字符串（格式：DD_MON_YYYY）
            extension: 文件扩展名（含点号，如 .pdf）
            
        Returns:
            新文件名
        """
        return f"{dd_no}_{stockist_no}_{date_str}{extension}"
    
    def rename_file(self, file_path: str, dry_run: bool = True) -> Tuple[bool, str, str]:
        """
        重命名文件
        
        Args:
            file_path: 文件路径
            dry_run: 是否为试运行模式（不实际重命名）
            
        Returns:
            (success, old_name, new_name) 元组
        """
        file_path_obj = Path(file_path)
        old_filename = file_path_obj.name
        file_stem = file_path_obj.stem
        file_ext = file_path_obj.suffix
        
        # 提取信息
        dd_no, stockist_no, date_str = self.extract_identifiers_from_filename(file_stem)
        
        # 如果缺少信息，从数据库查询
        if not dd_no and stockist_no:
            dd_no = self.query_dd_no_from_stockist(stockist_no)
            if dd_no:
                print(f"  [查询] 从数据库获取 DD_No: {dd_no} (Stockist_No: {stockist_no})")
        
        if not stockist_no and dd_no:
            stockist_no = self.query_stockist_from_dd_no(dd_no)
            if stockist_no:
                print(f"  [查询] 从数据库获取 Stockist_No: {stockist_no} (DD_No: {dd_no})")
            else:
                # 若首个 DD_No 未命中，尝试从完整文件名提取多个 DD_No 逐个反查
                for candidate_dd in self._extract_dn_candidates(file_stem):
                    if not candidate_dd or candidate_dd == dd_no:
                        continue
                    candidate_stockist = self.query_stockist_from_dd_no(candidate_dd)
                    if candidate_stockist:
                        dd_no = candidate_dd
                        stockist_no = candidate_stockist
                        print(f"  [查询] 使用候选DD_No匹配成功: {dd_no} -> {stockist_no}")
                        break
        
        # 如果 DD_No 和 Stockist_No 相同（如 SS76288_SS76288），需要查询正确的 Stockist_No
        if dd_no and stockist_no and dd_no == stockist_no:
            correct_stockist = self.query_stockist_from_dd_no(dd_no)
            if correct_stockist and correct_stockist != dd_no:
                print(f"  [查询] DD_No 和 Stockist_No 相同，从数据库获取正确的 Stockist_No: {correct_stockist}")
                stockist_no = correct_stockist
        
        # 如果缺少日期，使用文件修改日期
        if not date_str:
            date_str = self.get_file_date(file_path)
            print(f"  [日期] 使用文件修改日期: {date_str}")
        
        # 检查是否所有信息都已获取
        if not dd_no:
            return False, old_filename, f"[错误] 无法提取或查询到 DD_No"
        
        if not stockist_no:
            return False, old_filename, f"[错误] 无法提取或查询到 Stockist_No"
        
        # 生成新文件名
        new_filename = self.generate_new_filename(dd_no, stockist_no, date_str, file_ext)
        
        # 如果新文件名与旧文件名相同，跳过
        if new_filename == old_filename:
            return True, old_filename, "[跳过] 文件名已符合格式"
        
        # 检查目标文件是否已存在
        new_file_path = file_path_obj.parent / new_filename
        if new_file_path.exists():
            return False, old_filename, f"[错误] 目标文件已存在: {new_filename}"
        
        # 执行重命名
        if not dry_run:
            try:
                file_path_obj.rename(new_file_path)
                return True, old_filename, new_filename
            except Exception as e:
                return False, old_filename, f"[错误] 重命名失败: {str(e)}"
        else:
            return True, old_filename, new_filename


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='重命名 Stockist Cert 文件')
    parser.add_argument('--folder', type=str, default=STOCKIST_CERT_FOLDER,
                       help='Stockist Cert 文件夹路径')
    parser.add_argument('--db', type=str, default=DB_PATH,
                       help='数据库路径')
    parser.add_argument('--dry-run', action='store_true',
                       help='试运行模式（仅预览，不实际重命名）')
    parser.add_argument('--pattern', type=str,
                       help='只处理匹配此模式的文件（正则表达式）')
    
    args = parser.parse_args()
    
    # 检查文件夹是否存在
    if not os.path.exists(args.folder):
        print(f"[错误] 文件夹不存在: {args.folder}")
        return
    
    # 检查数据库是否存在
    if not os.path.exists(args.db):
        print(f"[警告] 数据库不存在: {args.db}，将无法从数据库查询信息")
        print(f"[提示] 请确保数据库文件存在，或使用 --db 参数指定正确的数据库路径")
    else:
        print(f"[信息] 数据库文件存在: {args.db}")
    
    print("=" * 80)
    print("Stockist Cert 文件重命名脚本")
    print("=" * 80)
    print(f"文件夹: {args.folder}")
    print(f"数据库: {args.db}")
    print(f"XLSX映射: {MAPPING_XLSX_PATH}")
    print(f"模式: {'试运行模式（不会实际重命名）' if args.dry_run else '执行模式'}")
    if args.pattern:
        print(f"文件过滤: {args.pattern}")
    print("=" * 80)

    if not os.path.exists(MAPPING_XLSX_PATH):
        print(f"[警告] XLSX映射文件不存在: {MAPPING_XLSX_PATH}，仅使用数据库查询")
    else:
        print(f"[信息] XLSX映射文件存在: {MAPPING_XLSX_PATH}")
    
    # 创建重命名器
    renamer = StockistFileRenamer(args.db)
    
    # 查找所有 PDF 文件
    folder_path = Path(args.folder)
    pdf_files = list(folder_path.rglob("*.pdf"))
    
    if args.pattern:
        pattern = re.compile(args.pattern, re.IGNORECASE)
        pdf_files = [f for f in pdf_files if pattern.search(f.name)]
    
    if not pdf_files:
        print("\n[结果] 未找到匹配的 PDF 文件")
        return
    
    print(f"\n[统计] 找到 {len(pdf_files)} 个 PDF 文件\n")
    
    # 处理文件
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    for file_path in pdf_files:
        print(f"[处理] {file_path.name}")
        success, old_name, new_name = renamer.rename_file(str(file_path), dry_run=args.dry_run)
        
        if success:
            if new_name.startswith("[跳过]"):
                print(f"  {new_name}")
                skip_count += 1
            else:
                if args.dry_run:
                    print(f"  [预览] {old_name} -> {new_name}")
                else:
                    print(f"  [成功] {old_name} -> {new_name}")
                success_count += 1
        else:
            print(f"  {new_name}")
            fail_count += 1
        print()
    
    # 输出统计
    print("=" * 80)
    print("[完成] 文件处理完成")
    print(f"  成功: {success_count} 个文件")
    print(f"  跳过: {skip_count} 个文件")
    print(f"  失败: {fail_count} 个文件")
    print(f"  总计: {len(pdf_files)} 个文件")
    if args.dry_run:
        print("\n[提示] 这是试运行模式，未实际重命名文件")
        print("       默认直接执行；如需预览请使用 --dry-run")
    print("=" * 80)


if __name__ == "__main__":
    main()
