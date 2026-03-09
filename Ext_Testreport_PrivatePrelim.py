#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extract Private Prelim test report files from source directory
抽取Private Prelim测试报告文件脚本

功能：
- 从源目录中查找以DN_No命名的文件夹（如SS77820）
- 在这些文件夹下的 Test report/Private test report 中查找对应的测试报告文件
- 复制文件到目标目录
- 如果目标文件已存在则覆盖
- 不删除源文件
"""

import os
import shutil
import re
import sys
import builtins
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime


def _safe_print(*args, **kwargs):
    """
    在非 UTF-8 控制台下容错打印，避免 UnicodeEncodeError 使流程中断。
    """
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        sep = kwargs.get('sep', ' ')
        end = kwargs.get('end', '\n')
        text = sep.join(str(a) for a in args)
        enc = getattr(sys.stdout, 'encoding', None) or 'utf-8'
        fallback = text.encode(enc, errors='replace').decode(enc, errors='replace')
        builtins.print(fallback, end=end)


# 覆盖模块内 print，统一使用容错输出
print = _safe_print

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
TARGET_DIR = r"D:\Stockist&Test Report\Private Prelim"

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

# Formal 格式文件模式：纯DN_No命名（如SS79782.pdf）
# 这是 Formal 格式文件，不是 Private Prelim 格式，需要跳过且不记录到 TXT
FORMAL_FILE_PATTERN = re.compile(
    r'^[A-Z0-9]+\.pdf$',
    re.IGNORECASE
)

DN_TOKEN_PATTERN = re.compile(r'[A-Z]{1,2}\d{3,}', re.IGNORECASE)


def extract_dn_tokens(text: str) -> List[str]:
    """从文本中提取一个或多个 DN（去重并保持顺序）。"""
    tokens = DN_TOKEN_PATTERN.findall(text or "")
    ordered_unique = []
    seen = set()
    for token in tokens:
        upper = token.upper()
        if upper not in seen:
            seen.add(upper)
            ordered_unique.append(upper)
    return ordered_unique


def _normalize_dir_name(name: str) -> str:
    """目录名归一化：小写 + 压缩空白。"""
    return re.sub(r'\s+', ' ', name.strip().lower())


def _is_test_report_name(name: str) -> bool:
    """
    判断目录名是否是 Test report 的变体（包含常见拼写错误）。
    支持：test report / test reoport / test reprt
    """
    n = _normalize_dir_name(name)
    return bool(re.fullmatch(r'test\s*(report|reoport|reprt)', n))


def _is_private_report_name(name: str) -> bool:
    """
    判断目录名是否是 Private test report 系列目录（包含常见拼写错误）。
    支持：
    - private test report / private test / private report / private test report only
    - private test reoport / private test reprt
    - praive test report（private 常见拼写错误）
    """
    n = _normalize_dir_name(name)
    return bool(re.fullmatch(r'(private|praive)(\s+test)?(\s+(report|reoport|reprt))?(\s+only)?', n))


def _discover_candidate_dirs(dn_folder: Path) -> List[Path]:
    """
    在单个 DN 文件夹下递归发现可能存放 Private Prelim 文件的目录。
    规则：
    1) Test report（含拼写变体）目录本身；
    2) 任意层级中，目录名匹配 Private test report 系列（含拼写变体）的目录；
       （包含直接位于 DN 根目录下的 "Private test report"）
    """
    candidates: List[Path] = []
    seen = set()

    for root, dirs, _ in os.walk(dn_folder):
        root_path = Path(root)
        root_name = root_path.name

        # 0) 直接命中 Private* 目录（不要求一定在 Test report 下）
        if _is_private_report_name(root_name):
            key = str(root_path).lower()
            if key not in seen:
                seen.add(key)
                candidates.append(root_path)

        for d in dirs:
            d_path = root_path / d
            if _is_private_report_name(d):
                d_key = str(d_path).lower()
                if d_key not in seen:
                    seen.add(d_key)
                    candidates.append(d_path)

        # 1) Test report（含拼写变体）目录本身
        if _is_test_report_name(root_name):
            key = str(root_path).lower()
            if key not in seen:
                seen.add(key)
                candidates.append(root_path)

            # 2) 递归加入 Test report 下命中的 Private* 子目录
            for sub_root, sub_dirs, _ in os.walk(root_path):
                sub_root_path = Path(sub_root)
                if _is_private_report_name(sub_root_path.name):
                    sub_key = str(sub_root_path).lower()
                    if sub_key not in seen:
                        seen.add(sub_key)
                        candidates.append(sub_root_path)

                for d in sub_dirs:
                    d_path = sub_root_path / d
                    if _is_private_report_name(d):
                        sub_key = str(d_path).lower()
                        if sub_key not in seen:
                            seen.add(sub_key)
                            candidates.append(d_path)

    return candidates


def is_fuzzy_private_prelim_file(filename: str, dn_no: str) -> bool:
    """
    Private Prelim 文件模糊匹配（作为精准匹配失败后的后备）。
    支持空格/标点变化与常见拼写错误。
    """
    if FORMAL_FILE_PATTERN.match(filename):
        return False

    filename_lower = filename.lower()
    dn_lower = dn_no.lower()

    # 必备关键要素
    if 'physical' not in filename_lower:
        return False
    # 支持：
    # 1) test report / test reprt
    # 2) test of / test to（无 report 的简写）
    if not (
        ('test' in filename_lower and ('report' in filename_lower or 'reprt' in filename_lower))
        or 'test of' in filename_lower
        or 'test to' in filename_lower
    ):
        return False

    # 支持 "of" / "to" 连接词，且允许多 DN（如 SS71088&SS71060）
    if not re.search(r'\b(of|to)\b', filename_lower):
        return False
    dn_tokens = extract_dn_tokens(filename)
    if dn_no.upper() not in dn_tokens:
        return False

    # 常见变体：Physical, chemical & geometry test report of {DN}
    pattern_forward = re.compile(
        r'^physical\s*,?\s*(chemical|chamical|chemcial)\s*(&|and)\s*(geometry|gemoetry|geometery)\s*test\s*((report|reprt)\s*)?(of|to)\s*[a-z0-9&\s]+(?:\.pdf)?$',
        re.IGNORECASE
    )
    # 反向变体：Physical, geometry & chemical test report of {DN}
    pattern_reverse = re.compile(
        r'^physical\s*,?\s*(geometry|gemoetry|geometery)\s*(&|and)\s*(chemical|chamical|chemcial)\s*test\s*((report|reprt)\s*)?(of|to)\s*[a-z0-9&\s]+(?:\.pdf)?$',
        re.IGNORECASE
    )

    return bool(pattern_forward.match(filename) or pattern_reverse.match(filename))


def get_private_prelim_output_name(filename: str, dn_no: str) -> Optional[str]:
    """
    返回 Private Prelim 文件命中的输出文件名。
    - 返回 None: 不匹配
    - 返回原文件名: 匹配且无需重命名
    - 返回新文件名: 匹配且需要重命名
    """
    if FORMAL_FILE_PATTERN.match(filename):
        return None

    filename_lower = filename.lower()
    file_path = Path(filename)
    stem_lower = file_path.stem.lower()
    suffix = file_path.suffix if file_path.suffix else '.pdf'
    dn_tokens = extract_dn_tokens(filename)
    has_current_dn = dn_no.upper() in dn_tokens

    # 0) 精准匹配：允许多 DN，只要包含当前文件夹 DN 即命中并保留原文件名
    multi_dn_precise_patterns = [
        re.compile(
            r'^physical\s*,?\s*chemical\s*&\s*geometry\s*test\s*(report\s*)?(of|to)\s*[a-z0-9&\s]+(?:\.pdf)?$',
            re.IGNORECASE
        ),
        re.compile(
            r'^physical\s*,?\s*geometry\s*&\s*chemical\s*test\s*(report\s*)?(of|to)\s*[a-z0-9&\s]+(?:\.pdf)?$',
            re.IGNORECASE
        ),
    ]
    if has_current_dn and any(p.match(filename) for p in multi_dn_precise_patterns):
        return filename

    # 1) 精准匹配优先（组合格式，保留原文件名）
    precise_prefixes = [
        f"physical, chemical & geometry test report of {dn_no}".lower(),
        f"physical, chemical & geometry test report to {dn_no}".lower(),
        f"physical , chemical & geometry test report of {dn_no}".lower(),
        f"physical,chemical & geometry test report of {dn_no}".lower(),
        f"physical, chemical& geometry test report of {dn_no}".lower(),
        f"physical, chemical  & geometry test report of {dn_no}".lower(),
        f"physical, geometry & chemical test report of {dn_no}".lower(),
        f"physical, geometry & chemical test report to {dn_no}".lower(),
        f"physical & geometry test report of {dn_no}".lower(),
        f"chemical test report of {dn_no}".lower(),
        f"{dn_no} chemical test report".lower(),
        f"{dn_no} physical & geometry test report".lower(),
    ]
    if any(filename_lower.startswith(prefix) for prefix in precise_prefixes):
        return filename

    # 1.1) 精准匹配：无 "of {DN}" 的固定命名，命中后按 DN 重命名
    # 例如：
    # - Physical & geometry test report.pdf -> Physical & geometry test report of SS68074.pdf
    # - Chemical Test Report.pdf -> Chemical Test Report of SS68074.pdf
    if stem_lower == 'physical & geometry test report':
        return f"Physical & geometry test report of {dn_no}{suffix}"
    if stem_lower == 'chemical test report':
        return f"Chemical Test Report of {dn_no}{suffix}"
    if stem_lower == 'physical , chemical & geometry test report':
        return f"Physical , Chemical & Geometry test report of {dn_no}{suffix}"

    # 2) Preliminary 单项报告重命名
    # 例如：
    # - Preliminary - Physical test report
    # - Preliminary - Physical test report of SS65994
    preliminary_patterns = {
        'physical': re.compile(
            r'^preliminary\s*-\s*physical\s*test\s*report(\s*of\s*[a-z0-9]+)?$',
            re.IGNORECASE
        ),
        'geometry': re.compile(
            r'^preliminary\s*-\s*geometry\s*test\s*report(\s*of\s*[a-z0-9]+)?$',
            re.IGNORECASE
        ),
        'chemical': re.compile(
            r'^preliminary\s*-\s*chemical\s*test\s*report(\s*of\s*[a-z0-9]+)?$',
            re.IGNORECASE
        ),
    }
    for report_type, pattern in preliminary_patterns.items():
        if pattern.match(stem_lower):
            return f"{report_type.capitalize()} test report of {dn_no}{suffix}"

    # 3) 模糊匹配后备（组合格式，保留原文件名）
    if is_fuzzy_private_prelim_file(filename, dn_no):
        return filename

    return None


def ensure_target_dir():
    """确保目标目录存在"""
    target_path = Path(TARGET_DIR)
    target_path.mkdir(parents=True, exist_ok=True)
    print(f"[信息] 目标目录: {TARGET_DIR}")
    return target_path


def find_test_report_files(source_dir: str) -> Tuple[List[Tuple[str, str, str]], List[str]]:
    """
    在源目录中查找测试报告文件
    
    Args:
        source_dir: 源目录路径
        
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
    for item in source_path.iterdir():
        if item.is_dir():
            folder_name = item.name
            
            # 检查文件夹名是否匹配DN_No模式（如SS77820）
            if FOLDER_PATTERN.match(folder_name):
                dn_no = folder_name
                
                # 递归发现 Test report / Private test report 目录（包含拼写变体）。
                # 可覆盖例如：
                # - Test reoport/Private test report
                # - Test report/Private test report only
                # - TEST REPORT/...（大小写变体）
                test_report_dirs = _discover_candidate_dirs(item)
                
                found_files = False
                has_formal_files = False
                has_non_formal_pdf = False

                for test_report_dir in test_report_dirs:
                    if not test_report_dir.exists():
                        continue
                    
                    for file in test_report_dir.iterdir():
                        if not file.is_file():
                            continue

                        # 遇到 Formal 格式文件（如 SS79781.pdf / SS79782.pdf）直接跳过
                        # 且该文件夹不写入 TXT（视为有记录）
                        if FORMAL_FILE_PATTERN.match(file.name):
                            has_formal_files = True
                            continue

                        # 记录存在非 Formal PDF（即使暂未命中提取规则）
                        # 这类文件夹不应被记入“未找到文件”TXT，避免误报。
                        if file.suffix.lower() == '.pdf':
                            has_non_formal_pdf = True

                        output_name = get_private_prelim_output_name(file.name, dn_no)
                        if output_name:
                            matching_files.append((str(file), output_name, dn_no))
                            if output_name == file.name:
                                print(f"  [找到] {dn_no}/{file.name}")
                            else:
                                print(f"  [找到] {dn_no}/{file.name} -> {output_name}")
                            found_files = True

                # 特殊规则：在 DN 根目录（含其子目录）存在 "Private test.pdf" 时，
                # 提取并重命名为 "{DN}_Private_Prilim.pdf"
                special_new_name = f"{dn_no}_Private_Prilim.pdf"
                for file in item.rglob("*.pdf"):
                    if not file.is_file():
                        continue
                    if file.stem.strip().lower() == "private test":
                        matching_files.append((str(file), special_new_name, dn_no))
                        print(f"  [找到-特殊] {dn_no}/{file.name} -> {special_new_name}")
                        found_files = True
                        # 命中特殊文件后即可退出该特殊扫描
                        break
                
                # 如果没有相应文件，输出文件夹路径并记录
                if not found_files:
                    if has_formal_files:
                        print(f"  [跳过] {dn_no}/ - 只有Formal格式文件")
                    elif has_non_formal_pdf:
                        print(f"  [跳过] {dn_no}/ - 存在非Formal PDF（未列入未找到文件TXT）")
                    else:
                        folder_path = str(item)
                        folders_without_files.append(folder_path)
                        print(f"  [无文件] {folder_path}")
    
    return matching_files, folders_without_files


def check_file_exists_in_target(file_name: str, base_folder: str = TARGET_DIR) -> Optional[str]:
    """
    检查 Private Prelim 文件夹中是否已存在对应文件
    
    例如："Physical, chemical & geometry test report of SS77294" 和 "SS77294_Private_Prelim" 是同一个文件
    
    Args:
        file_name: 源文件名（例如："Physical, chemical & geometry test report of SS77294.pdf"）
        base_folder: Stockist&Test Report 基础文件夹路径
        
    Returns:
        如果找到对应文件，返回文件路径；否则返回 None
    """
    if not INDEX_AVAILABLE:
        return None
    
    try:
        # 创建文件索引查询器
        index_query = FileIndexQuery(DB_PATH)
        
        # 检查 Private Prelim 文件夹中是否已存在对应文件
        existing_file = index_query.check_file_exists_in_private_prelim(file_name, base_folder)
        
        return existing_file
    except Exception as e:
        print(f"  [警告] 检查文件存在性失败: {str(e)}")
        return None


def copy_file_to_target(source_file: str, target_dir: Path, file_name: str) -> Tuple[bool, str]:
    """
    复制文件到目标目录（如果已存在则覆盖）
    在复制前会先检查 Private Prelim 文件夹中是否已存在对应文件
    
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
        # base_folder 应该是 "D:\Stockist&Test Report"，而不是 "Private Prelim" 子目录
        base_folder = os.path.dirname(str(target_dir))  # 获取 "D:\Stockist&Test Report"
        existing_file = check_file_exists_in_target(file_name, base_folder)
        
        if existing_file:
            existing_path = Path(existing_file)
            if existing_path.exists():
                print(f"  [跳过] {file_name} - 对应文件已存在: {existing_path.name}")
                return True, 'skipped_matched'
        
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
    print("Private Prelim 测试报告文件提取脚本")
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

    # 兜底过滤：只要该 DN 有匹配文件（无论后续是 copied / skipped_existing / skipped_matched），
    # 就不应出现在“未找到文件”TXT中。
    matched_dns = {str(dn_no).strip().upper() for _, _, dn_no in matching_files if dn_no}
    if matched_dns and all_folders_without_files:
        filtered_folders = []
        for folder_path in all_folders_without_files:
            folder_dn = os.path.basename(os.path.normpath(folder_path)).strip().upper()
            if folder_dn in matched_dns:
                continue
            filtered_folders.append(folder_path)
        all_folders_without_files = filtered_folders
    
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
        output_file = os.path.join(script_dir, "未找到文件的文件夹列表.txt")
        save_folders_without_files(all_folders_without_files, output_file)


if __name__ == "__main__":
    main()

