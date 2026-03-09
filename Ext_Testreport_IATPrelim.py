#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extract IAT Prelim test report files from source directory
抽取IAT Prelim测试报告文件脚本

功能：
- 从源目录中查找以DN_No命名的文件夹（如SS77820）
- 在这些文件夹下的 Test report/IAT test report 中查找对应的测试报告文件
- 复制文件到目标目录
- 如果目标文件已存在则覆盖
- 不删除源文件
"""

import os
import shutil
import re
import sys
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime

# 添加 backend 目录到路径，以便导入 file_index_query
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'TR UI', 'backend')
if os.path.exists(backend_dir):
    sys.path.insert(0, backend_dir)
    try:
        from file_index_query import FileIndexQuery
        INDEX_AVAILABLE = True
    except ImportError:
        INDEX_AVAILABLE = False
        print("[警告] 无法导入 file_index_query，将跳过文件存在性检查")
else:
    INDEX_AVAILABLE = False
    print("[警告] backend 目录不存在，将跳过文件存在性检查")


# 源目录列表
SOURCE_DIRS = [
    r"\\192.168.32.212\TVSC-Internal\Dp-Supply Chain\Inventory\04 Rebar PO DN\Rebar DN",
    r"\\192.168.32.212\TVSC-Internal\Dp-Supply Chain\Inventory\04 Rebar PO DN\Rebar DN\00 - Passed record"
]

# 目标目录
TARGET_DIR = r"D:\Stockist&Test Report\IAT Prelim"

# 数据库路径（用于文件索引查询）
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.normpath(os.path.join(_current_dir))
_default_db_path = os.path.join(_project_root, 'TR UI', 'backend', 'tr_system.db')
DB_PATH = os.getenv('DB_PATH', _default_db_path)

# 如果环境变量是相对路径，转换为绝对路径
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.abspath(os.path.join(_project_root, DB_PATH))

# 文件夹命名模式：DN_No命名
# 例如：SS77820
FOLDER_PATTERN = re.compile(
    r'^[A-Z0-9]+$',
    re.IGNORECASE
)

# Formal 格式文件模式：纯DN_No命名（如SS79852.pdf）
# 这是 Formal 格式文件，不是 Prelim 格式，需要跳过
FORMAL_FILE_PATTERN = re.compile(
    r'^[A-Z0-9]+\.pdf$',
    re.IGNORECASE
)


def is_fuzzy_prelim_file(filename: str, dn_no: str) -> bool:
    """
    使用模糊匹配判断文件是否是 Prelim 格式文件
    
    模糊匹配规则：
    1. 文件名包含 "Physical"（不区分大小写）
    2. 文件名包含 "chemical" 或 "geometry" 相关词（包括拼写错误）
    3. 文件名包含 "of {DN_No}" 或 "to {DN_No}"
    4. 满足以下条件之一：
       - 包含 "report" 或 "test report"
       - 或者格式为 "Physical, [chemical/geometry相关词] & [geometry/chemical相关词] of/to {DN_No}"
    5. 不是 Formal 格式文件（纯DN_No命名）
    
    Args:
        filename: 文件名
        dn_no: DN_No（用于检查是否包含 "of {DN_No}" 或 "to {DN_No}"）
        
    Returns:
        True if matches fuzzy pattern, False otherwise
    """
    filename_lower = filename.lower()
    
    # 排除 Formal 格式文件
    if FORMAL_FILE_PATTERN.match(filename):
        return False
    
    # 检查是否包含 "Physical"
    if 'physical' not in filename_lower:
        return False
    
    # 检查是否包含 "chemical" 或 "geometry" 相关词（包括拼写错误）
    has_chemical = any(word in filename_lower for word in ['chemical', 'chamical', 'chemcial'])
    has_geometry = any(word in filename_lower for word in ['geometry', 'gemoetry', 'geometery'])
    
    if not (has_chemical or has_geometry):
        return False
    
    # 检查是否包含 "of {DN_No}" 或 "to {DN_No}"
    has_of = f'of {dn_no}'.lower() in filename_lower
    has_to = f'to {dn_no}'.lower() in filename_lower
    
    if not (has_of or has_to):
        return False
    
    # 检查是否包含 "report" 或 "test report"，或者格式为 "Physical, [词] & [词] of/to {DN_No}"
    has_report = 'report' in filename_lower
    
    # 如果不包含 report，检查是否是 "Physical, [词] & [词] of/to {DN_No}" 格式
    if not has_report:
        # 检查格式：Physical, [chemical/geometry] & [geometry/chemical] of/to {DN_No}
        # 使用正则表达式匹配这种格式（不包含 report）
        pattern_without_report = re.compile(
            rf'^Physical,\s+.*?&\s+.*?(of|to)\s+{re.escape(dn_no)}\.',
            re.IGNORECASE
        )
        if not pattern_without_report.search(filename_lower):
            return False
    
    return True

def ensure_target_dir():
    """确保目标目录存在"""
    target_path = Path(TARGET_DIR)
    target_path.mkdir(parents=True, exist_ok=True)
    print(f"[信息] 目标目录: {TARGET_DIR}")
    return target_path


def find_test_report_files(source_dir: str) -> Tuple[List[Tuple[str, str, str]], List[str]]:
    """
    在源目录中查找测试报告文件
    
    注意：此函数对所有源目录下的 DN_No 文件夹应用相同的处理逻辑，包括：
    - \\192.168.32.212\...\Rebar DN\SS79869
    - \\192.168.32.212\...\Rebar DN\00 - Passed record\SS66594
    所有 DN_No 文件夹都使用相同的处理规则。
    
    Args:
        source_dir: 源目录路径（可以是主目录或 00 - Passed record 目录）
        
    Returns:
        Tuple of (matching_files, folders_without_files)
        matching_files: List of tuples: (file_path, file_name, dn_no)
        folders_without_files: List of folder paths without files
    """
    matching_files = []
    folders_without_files = []
    source_path = Path(source_dir)
    
    if not source_path.exists():
        print(f"[警告] 源目录不存在: {source_dir}")
        return matching_files, folders_without_files
    
    print(f"\n[搜索] 正在搜索目录: {source_dir}")
    
    # 搜索源目录下的所有直接子文件夹
    # 对所有源目录（包括主目录和 00 - Passed record 目录）下的 DN_No 文件夹应用相同的处理逻辑
    for item in source_path.iterdir():
        if item.is_dir():
            folder_name = item.name
            
            # 检查文件夹名是否匹配DN_No模式（如SS77820、SS66594、SS79869）
            # 无论在主目录还是 00 - Passed record 目录下，都使用相同的处理逻辑
            if FOLDER_PATTERN.match(folder_name):
                dn_no = folder_name
                
                # 构建测试报告文件路径
                # Test report/IAT test report/Physical, chemical & geometry test report of {DN_No}.*
                test_report_base_dir = item / "Test report"
                test_report_dir = test_report_base_dir / "IAT test report"
                
                # 检查是否存在 Test report 文件夹
                if not test_report_base_dir.exists():
                    # 没有 Test report 文件夹，说明缺少记录，跳过且不在TXT中输出
                    print(f"  [跳过] {dn_no}/ - 缺少Test report文件夹（缺少记录）")
                    continue
                
                # 检查是否存在 IAT test report 文件夹
                if not test_report_dir.exists():
                    # Test report 存在但没有 IAT test report 文件夹（可能只有 Private test report），跳过且不在TXT中输出
                    print(f"  [跳过] {dn_no}/ - Test report文件夹存在但没有IAT test report文件夹（只有Private test report）")
                    continue
                
                found_files = False
                has_formal_files = False
                has_any_pdf = False
                
                # IAT test report 文件夹存在，查找文件
                    # 查找以 "Physical, chemical & geometry test report of {DN_No}" 开头的文件
                    pattern_prefix = f"Physical, chemical & geometry test report of {dn_no}"
                # 也查找 "Physical, chemical  & geometry test report of {DN_No}" 格式（两个空格，不需要重命名）
                pattern_prefix3 = f"Physical, chemical  & geometry test report of {dn_no}"
                # 也查找 "Physical, chemical& geometry test report of {DN_No}" 格式（没有空格在chemical和&之间，不需要重命名）
                pattern_prefix4 = f"Physical, chemical& geometry test report of {dn_no}"
                # 也查找 "Chemical, physical & geometry test report of {DN_No}" 格式（以Chemical开头，不需要重命名）
                pattern_prefix5 = f"Chemical, physical & geometry test report of {dn_no}"
                # 也查找 "Physical, geometry & chemical test report of {DN_No}" 格式（不需要重命名，已包含DN_No）
                pattern_prefix2 = f"Physical, geometry & chemical test report of {dn_no}"
                # 也查找 "Physical, geometry and chemical test report of {DN_No}" 格式（使用and而不是&，不需要重命名）
                pattern_prefix9 = f"Physical, geometry and chemical test report of {dn_no}"
                # 也查找 "Physical, gemoetry & chemical test report of {DN_No}" 格式（geometry拼写错误，不需要重命名）
                pattern_prefix7 = f"Physical, gemoetry & chemical test report of {dn_no}"
                # 也查找 "Physical, chamical & geometry test report of {DN_No}" 格式（chemical拼写错误，不需要重命名）
                pattern_prefix8 = f"Physical, chamical & geometry test report of {dn_no}"
                # 也查找 "Physical & geometry test report of {DN_No}" 格式（只有Physical和geometry，不需要重命名）
                pattern_prefix6 = f"Physical & geometry test report of {dn_no}"
                # 也查找 "Physical, chemical & geometry report of {DN_No}" 格式（使用report而不是test report，不需要重命名）
                pattern_prefix10 = f"Physical, chemical & geometry report of {dn_no}"
                # 使用正则表达式匹配包含拼写错误的变体
                # 支持：Physical, [geometry/gemoetry] & [chemical/chamical] test report of/to {DN_No}
                # 或：Physical, [chemical/chamical] & [geometry/gemoetry] test report of/to {DN_No}
                flexible_pattern = re.compile(
                    rf'^Physical,\s+((geometry|gemoetry)\s*&\s*(chemical|chamical)|(chemical|chamical)\s*&\s*(geometry|gemoetry))\s+test\s+report\s+(of|to)\s+{re.escape(dn_no)}\.',
                    re.IGNORECASE
                )
                # 使用正则表达式匹配 "report" 格式（不是 "test report"）
                # 支持：Physical, [各种组合] report of/to {DN_No}
                flexible_report_pattern = re.compile(
                    rf'^Physical,\s+((chemical|chamical)\s*&\s*(geometry|gemoetry)|(geometry|gemoetry)\s*&\s*(chemical|chamical))\s+report\s+(of|to)\s+{re.escape(dn_no)}\.',
                    re.IGNORECASE
                )
                # 也查找 "Physical & Chemical & Geometry Test Report.pdf" 格式（需要重命名）
                alternative_pattern = "Physical & Chemical & Geometry Test Report.pdf"
                # 也查找 "Physical, Chemical&Geometry Test Report.pdf" 格式（需要重命名）
                alternative_pattern3 = "Physical, Chemical&Geometry Test Report.pdf"
                # 也查找 "Physical , chemical & geometry test report.pdf" 格式（需要重命名，注意逗号后有空格）
                alternative_pattern4 = "Physical , chemical & geometry test report.pdf"
                # 也查找 "Physical&Chemical&Geometry Test Report of {DN_No}" 格式（不需要重命名）
                alternative_pattern2 = f"Physical&Chemical&Geometry Test Report of {dn_no}"
                
                # 匹配 "Physical, chemical & geometry test report to SS72352&SS72408.pdf" 格式（多个DN_No，需要重命名）
                # 匹配格式：Physical, chemical & geometry test report to [DN_No组合].pdf
                pattern_to_multiple = re.compile(
                    r'^Physical,\s+chemical\s+&\s+geometry\s+test\s+report\s+to\s+[A-Z0-9]+([&~][A-Z0-9]+)+\.pdf$',
                    re.IGNORECASE
                )
                    
                    for file in test_report_dir.iterdir():
                    if file.is_file():
                        has_any_pdf = True
                        file_name = file.name
                        
                        # 检查是否是 Formal 格式文件（纯DN_No命名，如SS79852.pdf）
                        if FORMAL_FILE_PATTERN.match(file_name):
                            has_formal_files = True
                            continue  # 跳过Formal文件
                        
                        # 查找 "Physical & Chemical & Geometry Test Report.pdf" 格式文件
                        if file_name == alternative_pattern:
                            # 重命名为 "Physical & Chemical & Geometry Test Report of {DN_No}.pdf"
                            new_file_name = f"Physical & Chemical & Geometry Test Report of {dn_no}.pdf"
                            matching_files.append((str(file), new_file_name, dn_no))
                            print(f"  [找到] {dn_no}/{file_name} -> {new_file_name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical, Chemical&Geometry Test Report.pdf" 格式文件（需要重命名）
                        if file_name == alternative_pattern3:
                            # 重命名为 "Physical, Chemical&Geometry Test Report of {DN_No}.pdf"
                            new_file_name = f"Physical, Chemical&Geometry Test Report of {dn_no}.pdf"
                            matching_files.append((str(file), new_file_name, dn_no))
                            print(f"  [找到] {dn_no}/{file_name} -> {new_file_name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical , chemical & geometry test report.pdf" 格式文件（需要重命名，注意逗号后有空格）
                        if file_name == alternative_pattern4:
                            # 重命名为 "Physical , chemical & geometry test report of {DN_No}.pdf"
                            new_file_name = f"Physical , chemical & geometry test report of {dn_no}.pdf"
                            matching_files.append((str(file), new_file_name, dn_no))
                            print(f"  [找到] {dn_no}/{file_name} -> {new_file_name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical&Chemical&Geometry Test Report of {DN_No}" 格式文件（不需要重命名）
                        if file_name.startswith(alternative_pattern2):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical, chemical  & geometry test report of {DN_No}" 格式文件（两个空格，不需要重命名）
                        if file_name.startswith(pattern_prefix3):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical, chemical& geometry test report of {DN_No}" 格式文件（没有空格在chemical和&之间，不需要重命名）
                        if file_name.startswith(pattern_prefix4):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 "Chemical, physical & geometry test report of {DN_No}" 格式文件（以Chemical开头，不需要重命名）
                        if file_name.startswith(pattern_prefix5):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical, geometry & chemical test report of {DN_No}" 格式文件（不需要重命名，已包含DN_No）
                        if file_name.startswith(pattern_prefix2):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical, geometry and chemical test report of {DN_No}" 格式文件（使用and而不是&，不需要重命名）
                        if file_name.startswith(pattern_prefix9):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical, gemoetry & chemical test report of {DN_No}" 格式文件（geometry拼写错误，不需要重命名）
                        if file_name.startswith(pattern_prefix7):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical, gemoetry & chemical test report to {DN_No}" 格式文件（geometry拼写错误 + "to"格式，不需要重命名）
                        pattern_prefix7_to = f"Physical, gemoetry & chemical test report to {dn_no}"
                        if file_name.startswith(pattern_prefix7_to):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical, chamical & geometry test report of {DN_No}" 格式文件（chemical拼写错误，不需要重命名）
                        if file_name.startswith(pattern_prefix8):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical, chamical & geometry test report to {DN_No}" 格式文件（chemical拼写错误 + "to"格式，不需要重命名）
                        pattern_prefix8_to = f"Physical, chamical & geometry test report to {dn_no}"
                        if file_name.startswith(pattern_prefix8_to):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical, chemical & geometry report of {DN_No}" 格式文件（使用report而不是test report，不需要重命名）
                        if file_name.startswith(pattern_prefix10):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 使用正则表达式匹配包含拼写错误的变体（test report格式）
                        if flexible_pattern.match(file_name):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 使用正则表达式匹配 "report" 格式（不是 "test report"）
                        if flexible_report_pattern.match(file_name):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical & geometry test report of {DN_No}" 格式文件（只有Physical和geometry，不需要重命名）
                        if file_name.startswith(pattern_prefix6):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 Prelim 格式文件（"of" 格式）
                        if file_name.startswith(pattern_prefix):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical, chemical & geometry test report to {DN_No}" 格式（"to" 格式）
                        pattern_prefix_to = f"Physical, chemical & geometry test report to {dn_no}"
                        if file_name.startswith(pattern_prefix_to):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到] {dn_no}/{file.name}")
                            found_files = True
                            continue
                        
                        # 查找 "Physical, chemical & geometry test report to SS72352&SS72408.pdf" 格式（多个DN_No，需要重命名）
                        if pattern_to_multiple.match(file_name):
                            # 重命名为 "Physical, chemical & geometry test report of {DN_No}.pdf"
                            new_file_name = f"Physical, chemical & geometry test report of {dn_no}.pdf"
                            matching_files.append((str(file), new_file_name, dn_no))
                            print(f"  [找到] {dn_no}/{file_name} -> {new_file_name}")
                            found_files = True
                            continue
                        
                        # 模糊匹配作为后备（如果所有精确匹配都失败）
                        if is_fuzzy_prelim_file(file_name, dn_no):
                            matching_files.append((str(file), file.name, dn_no))
                            print(f"  [找到-模糊匹配] {dn_no}/{file.name}")
                            found_files = True
                
                # 如果没有找到Prelim文件，检查情况
                if not found_files:
                    if has_formal_files and has_any_pdf:
                        # 只有Formal文件，跳过且不在TXT中输出
                        print(f"  [跳过] {dn_no}/ - 只有Formal格式文件")
                    elif has_any_pdf:
                        # 有PDF但未命中提取规则，也不写入TXT（避免误报）
                        print(f"  [跳过] {dn_no}/ - 存在PDF（未列入未找到文件TXT）")
                else:
                        # 完全没有可用PDF时，才写入TXT
                        folder_path = str(test_report_dir)
                        folders_without_files.append(folder_path)
                        print(f"  [无文件] {folder_path}")
                # 如果找到文件（包括 Physical & Chemical & Geometry Test Report.pdf 格式），found_files = True
                # 不会进入上面的 if not found_files 分支，因此不会在TXT中输出文件夹路径
    
    return matching_files, folders_without_files


def check_file_exists_in_target(file_name: str, base_folder: str = TARGET_DIR) -> Optional[str]:
    """
    检查 IAT Prelim 文件夹中是否已存在对应文件
    
    检查逻辑：
    1. 从源文件名中提取标识符（如 SS79820、C0146、NW00018）
    2. 在 file_index_cache 表中查找 folder_type = 'IAT Prelim' 的记录
    3. 检查这些记录的 identifiers 字段中是否包含该标识符
    4. 如果存在，则无需复制对应的源文件
    
    例如：
    - 源文件："Physical, chemical & geometry test report of SS79820.pdf"
    - 提取标识符："SS79820"
    - 在索引中查找 identifiers 字段包含 "SS79820" 的记录
    - 如果找到（如 "SS79820_IAT_Prelim.pdf" 的 identifiers 包含 "SS79820"），则跳过复制
    
    Args:
        file_name: 源文件名（例如："Physical, chemical & geometry test report of SS79820.pdf"）
        base_folder: Stockist&Test Report 基础文件夹路径
        
    Returns:
        如果找到对应文件，返回文件路径；否则返回 None
    """
    if not INDEX_AVAILABLE:
        print(f"  [检查] 文件索引不可用，跳过检查: {file_name}")
        return None
    
    try:
        # 创建文件索引查询器
        index_query = FileIndexQuery(DB_PATH)
        
        # 检查 IAT Prelim 文件夹中是否已存在对应文件
        # 例如：从 "Physical, chemical & geometry test report of NW00018.pdf" 中提取 "NW00018"
        # 然后在索引中查找 "NW00018_IAT_Prelim.pdf"
        existing_file = index_query.check_file_exists_in_iat_prelim(file_name, base_folder)
        
        if existing_file:
            print(f"  [检查] 找到对应文件: {os.path.basename(existing_file)}")
        else:
            print(f"  [检查] 未找到对应文件: {file_name} (索引中可能没有对应格式的文件)")
        
        return existing_file
    except Exception as e:
        print(f"  [警告] 检查文件存在性失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def copy_file_to_target(source_file: str, target_dir: Path, file_name: str) -> Tuple[bool, str]:
    """
    复制文件到目标目录（如果已存在则覆盖）
    在复制前会先检查 IAT Prelim 文件夹中是否已存在对应文件
    
    Args:
        source_file: 源文件路径
        target_dir: 目标目录路径
        file_name: 文件名
        
    Returns:
        (success: bool, status: str)
        success: True if successful or skipped, False otherwise
        status: 'copied', 'skipped_existing', 'skipped_matched', or 'failed'
    """
    try:
        source_path = Path(source_file)
        target_file = target_dir / file_name
        
        # 先检查目标文件夹中是否已存在对应文件
        # base_folder 应该是 "D:\Stockist&Test Report"，而不是 "IAT Prelim" 子目录
        base_folder = os.path.dirname(str(target_dir))  # 获取 "D:\Stockist&Test Report"
        existing_file = check_file_exists_in_target(file_name, base_folder)
        
        if existing_file:
            existing_path = Path(existing_file)
            if existing_path.exists():
                print(f"  [跳过] {file_name} - 对应文件已存在: {existing_path.name}")
                return True, 'skipped_matched'
            else:
                print(f"  [警告] 找到对应文件但文件不存在: {existing_file}")
        
        # 如果目标文件已存在，也跳过（避免重复复制）
        if target_file.exists():
            print(f"  [跳过] {file_name} - 目标文件已存在")
            return True, 'skipped_existing'
        
        # 复制文件（如果目标文件已存在，shutil.copy2会自动覆盖）
        shutil.copy2(source_path, target_file)
        
        # 验证文件是否成功复制
        if target_file.exists():
            print(f"  [复制成功] {file_name}")
            return True, 'copied'
        else:
            print(f"  [复制失败] {file_name} - 目标文件不存在")
            return False, 'failed'
            
    except Exception as e:
        print(f"  [错误] 复制文件失败 {file_name}: {str(e)}")
        return False, 'failed'


def save_folders_without_files(folders_without_files: List[str], output_file: str):
    """
    将未找到文件的文件夹路径保存到文件
    
    Args:
        folders_without_files: 未找到文件的文件夹路径列表
        output_file: 输出文件路径
    """
    if not folders_without_files:
        return
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"未找到文件的文件夹路径列表\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总计: {len(folders_without_files)} 个文件夹\n")
            f.write("=" * 80 + "\n\n")
            
            for folder_path in folders_without_files:
                f.write(f"{folder_path}\n")
        
        print(f"\n[文件输出] 未找到文件的文件夹路径已保存到: {output_file}")
    except Exception as e:
        print(f"[错误] 保存文件失败: {str(e)}")


def main():
    """主函数"""
    print("=" * 80)
    print("IAT Prelim 测试报告文件提取脚本")
    print("=" * 80)
    
    # 确保目标目录存在
    target_dir = ensure_target_dir()
    
    # 查找所有匹配的测试报告文件（从所有源目录）
    matching_files = []
    all_folders_without_files = []
    
    for source_dir in SOURCE_DIRS:
        files, folders_without_files = find_test_report_files(source_dir)
        matching_files.extend(files)
        all_folders_without_files.extend(folders_without_files)
    
    # 复制文件（如果有找到文件）
    copied_count = 0
    skipped_matched_count = 0  # 跳过：找到对应文件
    skipped_existing_count = 0  # 跳过：目标文件已存在
    fail_count = 0
    
    if matching_files:
        print(f"\n[统计] 共找到 {len(matching_files)} 个测试报告文件")
        print(f"[目标] 将复制到: {TARGET_DIR}\n")
    
    for source_file, file_name, dn_no in matching_files:
        success, status = copy_file_to_target(source_file, target_dir, file_name)
        if success:
            if status == 'copied':
                copied_count += 1
            elif status == 'skipped_matched':
                skipped_matched_count += 1
            elif status == 'skipped_existing':
                skipped_existing_count += 1
        else:
            fail_count += 1

    if not matching_files:
        print("\n[结果] 未找到匹配的测试报告文件")
    
    # 输出结果统计
    print("\n" + "=" * 80)
    print("[完成] 文件提取完成")
    if matching_files:
    print(f"  已复制: {copied_count} 个文件")
    print(f"  跳过（找到对应文件）: {skipped_matched_count} 个文件")
    print(f"  跳过（目标文件已存在）: {skipped_existing_count} 个文件")
    print(f"  失败: {fail_count} 个文件")
    print(f"  总计: {len(matching_files)} 个文件")
    print(f"  未找到文件的文件夹: {len(all_folders_without_files)} 个")
    print("=" * 80)
    
    # 将未找到文件的文件夹路径保存到当前目录
    if all_folders_without_files:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_file = os.path.join(script_dir, "未找到文件的文件夹列表_IATPrelim.txt")
        save_folders_without_files(all_folders_without_files, output_file)


if __name__ == "__main__":
    main()

