#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stockist Cert 文件提取脚本
功能：从源目录中提取特定格式的PDF文件到目标目录
"""

import os
import sys
import io
import shutil
import re
from typing import List, Tuple

# Set UTF-8 encoding for Windows console output
if sys.platform == 'win32':
    # Set environment variable
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # Reconfigure stdout and stderr to UTF-8
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


class StockistExtractor:
    """Stockist Cert 文件提取器"""
    
    def __init__(self):
        """初始化提取器"""
        # 源目录列表
        self.source_dirs = [
            r"\\192.168.32.212\TVSC-Internal\Dp-Supply Chain\Inventory\07 Stockist and Mill cert Packages to Customer\01 - With IAT Report",
            r"\\192.168.32.212\TVSC-Internal\Dp-Supply Chain\Inventory\07 Stockist and Mill cert Packages to Customer\02 - With Private Report",
            r"\\192.168.32.212\TVSC-Internal\Dp-Supply Chain\Inventory\04 Rebar PO DN\Rebar DN"
        ]
        
        # 目标目录
        self.target_dir = r"D:\Stockist&Test Report\Stockist Cert"
        
        # 确保目标目录存在
        os.makedirs(self.target_dir, exist_ok=True)
    
    def match_pattern1(self, filename: str) -> bool:
        """
        匹配第一类文件：
        格式1：DN_NO_Stockist_No_Date 或 DN_NO_Stockist_No_Date_UPDATE 或 DN_NO_Stockist_No_Date(UPDATE) 或 DN_NO_Stockist_No_Date(REVISED)
        例如：SS78156_ZZ2731_18_APR_2025 或 SS79397_ZZ3826_10_NOV_2025_UPDATE 或 SS78560_ZZ3069_19_JUN_2025(UPDATE) 或 SS76533_ZZ1339_29_JUN_2024(REVISED)
        
        格式2：DN_NO_Date（缺少中间的 Stockist_No，使用下划线分隔）
        例如：SS76397_08_JUN_2024 或 SS75218_05_DEC_2023 (UPDATE) 或 SS76233_17_MAY_2024 (REVISED)
        
        格式3：DN_NO Date（缺少中间的 Stockist_No，使用空格分隔）
        例如：SS74446_5 AUG 2023
        
        支持的格式：
        1. 字母数字_字母数字_日期_月份_年份
        2. 字母数字_字母数字_日期_月份_年份_UPDATE
        3. 字母数字_字母数字_日期_月份_年份(UPDATE)
        4. 字母数字_字母数字_日期_月份_年份(REVISED)（新增）
        5. 字母数字_字母数字_日期_月份_年份 (REVISED)（空格+括号，新增）
        6. 字母数字_日期_月份_年份（下划线分隔）
        7. 字母数字_日期_月份_年份_UPDATE（下划线分隔）
        8. 字母数字_日期_月份_年份(UPDATE)（下划线分隔）
        9. 字母数字_日期_月份_年份 (UPDATE)（空格+括号）
        10. 字母数字_日期_月份_年份(REVISED)（括号）
        11. 字母数字_日期_月份_年份 (REVISED)（空格+括号）
        12. 字母数字_日期 月份 年份（空格分隔）
        """
        # 移除文件扩展名
        name_without_ext = os.path.splitext(filename)[0]
        
        # 匹配模式1：DN_NO_Stockist_No_Date（包含 Stockist_No）
        # 1. DN_NO_Stockist_No_Date（如：SS78156_ZZ2731_18_APR_2025）
        # 2. DN_NO_Stockist_No_Date_UPDATE（如：SS79397_ZZ3826_10_NOV_2025_UPDATE）
        # 3. DN_NO_Stockist_No_Date(UPDATE)（如：SS78560_ZZ3069_19_JUN_2025(UPDATE)）
        # 4. DN_NO_Stockist_No_Date(REVISED)（如：SS76533_ZZ1339_29_JUN_2024(REVISED)）
        # 5. DN_NO_Stockist_No_Date (REVISED)（如：SS76533_ZZ1339_29_JUN_2024 (REVISED)）
        pattern1 = r'^[A-Z0-9]+_[A-Z0-9]+_\d{1,2}_[A-Z]{3}_\d{4}(_UPDATE|\(UPDATE\)|\(REVISED\)|\s+\(REVISED\))?$'
        
        # 匹配模式2：DN_NO_Date（缺少 Stockist_No，使用下划线分隔，如：SS76397_08_JUN_2024）
        # 支持多种 UPDATE 和 REVISED 格式：_UPDATE、\(UPDATE\)、 (UPDATE)、\(REVISED\)、 (REVISED)（空格+括号）
        pattern2 = r'^[A-Z0-9]+_\d{1,2}_[A-Z]{3}_\d{4}(_UPDATE|\(UPDATE\)|\s+\(UPDATE\)|\(REVISED\)|\s+\(REVISED\))?$'
        
        # 匹配模式3：DN_NO Date（缺少 Stockist_No，使用空格分隔，如：SS74446_5 AUG 2023）
        # 注意：DN_NO 和日期之间是下划线，日期、月份、年份之间是空格
        pattern3 = r'^[A-Z0-9]+_\d{1,2}\s+[A-Z]{3}\s+\d{4}(_UPDATE|\(UPDATE\))?$'
        
        return bool(re.match(pattern1, name_without_ext, re.IGNORECASE) or 
                   re.match(pattern2, name_without_ext, re.IGNORECASE) or
                   re.match(pattern3, name_without_ext, re.IGNORECASE))
    
    def match_pattern2(self, filename: str) -> bool:
        """
        匹配第二类文件：
        1. Stockist + MIll Cert_Stockist_No（例如：Stockist + MIll Cert_C0473 或 Stockist + MIll Cert_C0404）
        2. Stockist + MIll Cert_Stockist_No (revised) R2（例如：Stockist + MIll Cert_C0397 (revised) R2）
        3. Stockist + MIll Cert_Stockist_No(C12)（例如：Stockist + MIll Cert_C0386(C12) 或 C10 等）
        4. Stockist + MIll Cert_Stockist_No_AdditionalText（例如：Stockist + MIll Cert_C0381_Billy）
        5. Stockist cert & mill cert of DN_NO（例如：Stockist cert & mill cert of SS74249 或 2172-1）
        6. Stockist & Mill Cert of DN_NO（例如：Stockist & Mill Cert of S1900299）
        7. Stockist  Mill Cert & mill cert of DN_NO（例如：Stockist  Mill Cert & mill cert of ISB0378133-4）
        """
        # 移除文件扩展名
        name_without_ext = os.path.splitext(filename)[0]
        
        # 匹配模式1：以 "Stockist + MIll Cert_" 或 "Stockist + Mill Cert_" 开头
        # 注意：原文件名可能有拼写错误 "MIll"，我们也匹配 "Mill"
        # 允许空格和加号周围有空格变化
        # 支持基本格式、带 (revised) R2 后缀的格式、带 (C12) 格式，以及带额外文本的格式（如 _Billy 或  Billy）
        pattern1 = r'^Stockist\s*\+\s*M[Ii]ll\s+Cert_[A-Z0-9]+(\s*\(revised\)\s*R\d+|\(C\d+\)|[_ ]+[A-Za-z0-9_]+)?$'
        
        # 匹配模式2：以 "Stockist cert & mill cert of " 开头，后面跟着订单号
        # 允许大小写变化和空格变化
        # 订单号可以包含连字符（如 2172-1, ISB0378133-4）
        pattern2 = r'^Stockist\s+cert\s*&\s*mill\s+cert\s+of\s+[A-Z0-9\-]+$'
        
        # 匹配模式3：以 "Stockist & Mill Cert of " 开头，后面跟着订单号
        # 允许大小写变化和空格变化
        pattern3 = r'^Stockist\s*&\s*M[Ii]ll\s+Cert\s+of\s+[A-Z0-9]+$'
        
        # 匹配模式4：以 "Stockist  Mill Cert & mill cert of " 开头（注意两个空格）
        # 后面跟着订单号，订单号可以包含连字符
        pattern4 = r'^Stockist\s+M[Ii]ll\s+Cert\s*&\s*mill\s+cert\s+of\s+[A-Z0-9\-]+$'
        
        return bool(re.match(pattern1, name_without_ext, re.IGNORECASE) or 
                   re.match(pattern2, name_without_ext, re.IGNORECASE) or
                   re.match(pattern3, name_without_ext, re.IGNORECASE) or
                   re.match(pattern4, name_without_ext, re.IGNORECASE))
    
    def find_pdf_files(self, source_dir: str) -> List[Tuple[str, str]]:
        """
        在源目录中查找匹配的PDF文件
        
        Args:
            source_dir: 源目录路径
            
        Returns:
            匹配的文件列表，每个元素为 (文件路径, 文件名)
        """
        matched_files = []
        
        if not os.path.exists(source_dir):
            print(f"[警告] 源目录不存在: {source_dir}")
            return matched_files
        
        print(f"[搜索] 正在搜索目录: {source_dir}")
        
        # 递归搜索所有PDF文件
        # os.walk() 会递归搜索所有子目录，包括像 SS77508 这样的子文件夹
        for root, dirs, files in os.walk(source_dir):
            # 显示当前搜索的子目录（相对于源目录）
            relative_path = os.path.relpath(root, source_dir) if root != source_dir else "."
            if relative_path != ".":
                print(f"[搜索] 正在搜索子目录: {relative_path}")
            
            for file in files:
                if file.lower().endswith('.pdf'):
                    file_path = os.path.join(root, file)
                    
                    # 检查是否匹配任一模式
                    if self.match_pattern1(file) or self.match_pattern2(file):
                        matched_files.append((file_path, file))
                        print(f"[匹配] 找到文件: {file} (位于: {relative_path})")
        
        return matched_files
    
    def copy_file(self, source_path: str, filename: str) -> bool:
        """
        复制文件到目标目录
        
        Args:
            source_path: 源文件路径
            filename: 文件名
            
        Returns:
            是否成功复制或跳过
        """
        target_path = os.path.join(self.target_dir, filename)
        
        try:
            # 如果目标文件已存在，直接跳过
            if os.path.exists(target_path):
                print(f"[跳过] 目标文件已存在，跳过: {filename}")
                return True
            
            shutil.copy2(source_path, target_path)
            print(f"[成功] 复制文件: {filename}")
            return True
        except Exception as e:
            print(f"[错误] 复制文件失败 {filename}: {str(e)}")
            return False
    
    def extract(self):
        """执行提取操作"""
        print("=" * 60)
        print("开始提取 Stockist Cert 文件")
        print("=" * 60)
        
        all_matched_files = []
        
        # 从所有源目录中查找文件
        for source_dir in self.source_dirs:
            files = self.find_pdf_files(source_dir)
            all_matched_files.extend(files)
        
        if not all_matched_files:
            print("[信息] 未找到匹配的文件")
            return
        
        print(f"\n[统计] 共找到 {len(all_matched_files)} 个匹配的文件")
        print("=" * 60)
        
        # 复制文件
        success_count = 0
        fail_count = 0
        
        for source_path, filename in all_matched_files:
            if self.copy_file(source_path, filename):
                success_count += 1
            else:
                fail_count += 1
        
        print("=" * 60)
        print(f"提取完成！")
        print(f"成功: {success_count} 个文件")
        print(f"失败: {fail_count} 个文件")
        print(f"目标目录: {self.target_dir}")
        print("=" * 60)


def main():
    """主函数"""
    extractor = StockistExtractor()
    extractor.extract()


if __name__ == "__main__":
    main()

