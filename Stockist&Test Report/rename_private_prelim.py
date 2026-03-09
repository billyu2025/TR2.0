#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本用于重命名 Private Prelim 文件夹中的文件。

默认格式：
- {DN_No}_Private_Prelim.pdf

特殊格式：
- Chemical test report* -> {DN_No}_Private_Prelim_Chemical.pdf
- Physical & geometry test report* -> {DN_No}_Private_Prelim_Physical & geometry.pdf
- Physical test report* -> {DN_No}_Private_Prelim_Physical.pdf
- Geometry test report* -> {DN_No}_Private_Prelim_Geometry.pdf

DN No 可能是 C0146, C0152, SS79059, NW00001, SF00001 等格式。
"""

import os
import re
from pathlib import Path

def extract_dn_no(filename):
    """
    从文件名中提取 DN No
    支持格式：C0146, C0152, SS79059, NW00001, SF00001 等
    也支持多 DN 格式：SS70895&SS70897
    格式：1-2个字母（大写）+ 数字（至少3位）
    """
    # 移除文件扩展名
    name_without_ext = os.path.splitext(filename)[0]

    # 对 "ofSS70381" 这种紧贴写法先做归一，便于统一提取
    normalized = re.sub(
        r'(?i)\bof(?=[A-Z]{1,2}\d{3,}\b)',
        'of ',
        name_without_ext
    )

    # 提取所有 DN，支持单个和多个（如 SS70895&SS70897）
    matches = re.findall(r'([A-Z]{1,2}\d{3,})', normalized, re.IGNORECASE)
    if matches:
        # 去重并保持顺序
        ordered_unique = []
        seen = set()
        for m in matches:
            token = m.upper()
            if token not in seen:
                seen.add(token)
                ordered_unique.append(token)
        return "&".join(ordered_unique)

    # 如果没有匹配到，返回 None
    return None


def get_private_prelim_suffix(filename: str) -> str:
    """
    根据文件名识别 Private Prelim 类型后缀。
    返回值不包含 '.pdf'。
    """
    stem = Path(filename).stem.lower()

    def classify(text: str) -> str:
        has_test_report = 'test report' in text
        has_physical = 'physical' in text
        has_chemical = 'chemical' in text
        has_geometry = 'geometry' in text

        # 先匹配更具体的类型，避免被单独规则提前命中
        if has_test_report and has_physical and has_chemical and has_geometry:
            return "Private_Prelim_Physical, chemical & geometry"
        if has_test_report and has_physical and has_geometry and not has_chemical:
            return "Private_Prelim_Physical & geometry"
        if 'chemical test report' in text and not has_physical and not has_geometry:
            return "Private_Prelim_Chemical"
        if 'physical test report' in text and not has_chemical and not has_geometry:
            return "Private_Prelim_Physical"
        if 'geometry test report' in text and not has_physical and not has_chemical:
            return "Private_Prelim_Geometry"
        return ""

    # 优先进行模糊归一后再判定，避免拼写错误导致提前误判
    normalized = stem
    typo_map = {
        'geomeytry': 'geometry',
        'geometery': 'geometry',
        'gemoetry': 'geometry',
        'geomerty': 'geometry',
        'chemcial': 'chemical',
        'cheimcal': 'chemical',
        'physcial': 'physical',
        'phycical': 'physical',
        'phyiscal': 'physical',
        'testreport': 'test report'
    }
    for typo, fixed in typo_map.items():
        normalized = normalized.replace(typo, fixed)
    normalized = re.sub(r'[_\-]+', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    normalized_type = classify(normalized)
    if normalized_type:
        return normalized_type

    # 若归一化后仍无法识别，再退回原始文本精确判定
    exact_type = classify(stem)
    if exact_type:
        return exact_type

    return "Private_Prelim"

def rename_files(folder_path):
    """
    重命名文件夹中的所有 PDF 文件
    """
    folder = Path(folder_path)
    
    if not folder.exists():
        print(f"错误：文件夹 '{folder_path}' 不存在")
        return
    
    if not folder.is_dir():
        print(f"错误：'{folder_path}' 不是一个文件夹")
        return
    
    # 获取所有 PDF 文件
    pdf_files = list(folder.glob("*.pdf"))
    
    if not pdf_files:
        print(f"在 '{folder_path}' 中没有找到 PDF 文件")
        return
    
    print(f"找到 {len(pdf_files)} 个 PDF 文件\n")
    
    renamed_count = 0
    skipped_count = 0
    
    for pdf_file in pdf_files:
        old_name = pdf_file.name
        dn_no = extract_dn_no(old_name)
        
        if dn_no:
            suffix = get_private_prelim_suffix(old_name)
            new_name = f"{dn_no}_{suffix}.pdf"
            new_path = pdf_file.parent / new_name
            
            # 如果新文件名已存在且不是当前文件，跳过
            if new_path.exists() and new_path != pdf_file:
                print(f"跳过：{old_name} -> {new_name} (目标文件已存在)")
                skipped_count += 1
                continue
            
            try:
                pdf_file.rename(new_path)
                print(f"✓ {old_name} -> {new_name}")
                renamed_count += 1
            except Exception as e:
                print(f"✗ 重命名失败：{old_name} - {e}")
                skipped_count += 1
        else:
            print(f"✗ 无法提取 DN No：{old_name}")
            skipped_count += 1
    
    print(f"\n完成！")
    print(f"成功重命名：{renamed_count} 个文件")
    print(f"跳过/失败：{skipped_count} 个文件")

if __name__ == "__main__":
    # 获取脚本所在目录
    script_dir = Path(__file__).parent
    target_folders = [
        script_dir / "Private Prelim",
        Path(r"\\192.168.32.212\TVSC-Internal\Dp-Supply Chain\Inventory\04 Rebar PO DN\Rebar DN\00 - Passed record\SS71027\Test report\Private test report only"),
    ]

    print("=" * 60)
    print("Private Prelim 文件重命名脚本")
    print("=" * 60)
    print("目标文件夹列表：")
    for idx, folder in enumerate(target_folders, start=1):
        print(f"{idx}. {folder}")
    print("")

    # 询问用户确认
    response = input("是否继续重命名文件？(y/n): ").strip().lower()
    if response == 'y' or response == 'yes':
        for folder in target_folders:
            print("\n" + "-" * 60)
            print(f"处理文件夹：{folder}")
            print("-" * 60)
            rename_files(folder)
    else:
        print("操作已取消")

