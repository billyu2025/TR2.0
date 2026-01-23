#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本用于重命名 Private Prelim 文件夹中的文件
格式：{DN_No}_Private_Prelim.pdf
DN No 可能是 C0146, C0152, SS79059, NW00001, SF00001 等格式
"""

import os
import re
from pathlib import Path

def extract_dn_no(filename):
    """
    从文件名中提取 DN No
    支持格式：C0146, C0152, SS79059, NW00001, SF00001 等
    格式：1-2个字母（大写）+ 数字（至少3位）
    """
    # 移除文件扩展名
    name_without_ext = os.path.splitext(filename)[0]
    
    # 匹配通用格式：1-2个字母 + 至少3位数字
    # 例如：C0146, C0152, SS79059, NW00001, SF00001
    pattern = r'\b([A-Z]{1,2}\d{3,})\b'
    match = re.search(pattern, name_without_ext, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    
    # 如果没有匹配到，返回 None
    return None

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
            new_name = f"{dn_no}_Private_Prelim.pdf"
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
    private_prelim_folder = script_dir / "Private Prelim"
    
    print("=" * 60)
    print("Private Prelim 文件重命名脚本")
    print("=" * 60)
    print(f"目标文件夹：{private_prelim_folder}\n")
    
    # 询问用户确认
    response = input("是否继续重命名文件？(y/n): ").strip().lower()
    if response == 'y' or response == 'yes':
        rename_files(private_prelim_folder)
    else:
        print("操作已取消")

