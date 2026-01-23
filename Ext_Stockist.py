#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stockist Cert 文件提取脚本
功能：从源目录中提取特定格式的PDF文件到目标目录
"""

import os
import shutil
import re
from typing import List, Tuple


class StockistExtractor:
    """Stockist Cert 文件提取器"""
    
    def __init__(self):
        """初始化提取器"""
        # 源目录列表
        self.source_dirs = [
            r"\\192.168.32.212\TVSC-Internal\Dp-Supply Chain\Inventory\07 Stockist and Mill cert Packages to Customer\01 - With IAT Report",
            r"\\192.168.32.212\TVSC-Internal\Dp-Supply Chain\Inventory\07 Stockist and Mill cert Packages to Customer\02 - With Private Report"
        ]
        
        # 目标目录
        self.target_dir = r"D:\Stockist&Test Report\Stockist Cert"
        
        # 确保目标目录存在
        os.makedirs(self.target_dir, exist_ok=True)
    
    def match_pattern1(self, filename: str) -> bool:
        """
        匹配第一类文件：DN_NO_Stockist_No_Date 或 DN_NO_Stockist_No_Date_UPDATE
        例如：SS78156_ZZ2731_18_APR_2025 或 SS79397_ZZ3826_10_NOV_2025_UPDATE
        格式：字母数字_字母数字_日期_月份_年份 或 字母数字_字母数字_日期_月份_年份_UPDATE
        """
        # 移除文件扩展名
        name_without_ext = os.path.splitext(filename)[0]
        
        # 匹配模式：支持两种格式
        # 1. DN_NO_Stockist_No_Date（如：SS78156_ZZ2731_18_APR_2025）
        # 2. DN_NO_Stockist_No_Date_UPDATE（如：SS79397_ZZ3826_10_NOV_2025_UPDATE）
        pattern = r'^[A-Z0-9]+_[A-Z0-9]+_\d{1,2}_[A-Z]{3}_\d{4}(_UPDATE)?$'
        
        return bool(re.match(pattern, name_without_ext, re.IGNORECASE))
    
    def match_pattern2(self, filename: str) -> bool:
        """
        匹配第二类文件：Stockist + MIll Cert_Stockist_No
        例如：Stockist + MIll Cert_C0473
        """
        # 移除文件扩展名
        name_without_ext = os.path.splitext(filename)[0]
        
        # 匹配模式：以 "Stockist + MIll Cert_" 或 "Stockist + Mill Cert_" 开头
        # 注意：原文件名可能有拼写错误 "MIll"，我们也匹配 "Mill"
        # 允许空格和加号周围有空格变化
        pattern = r'^Stockist\s*\+\s*M[Ii]ll\s+Cert_[A-Z0-9]+$'
        
        return bool(re.match(pattern, name_without_ext, re.IGNORECASE))
    
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
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                if file.lower().endswith('.pdf'):
                    file_path = os.path.join(root, file)
                    
                    # 检查是否匹配任一模式
                    if self.match_pattern1(file) or self.match_pattern2(file):
                        matched_files.append((file_path, file))
                        print(f"[匹配] 找到文件: {file}")
        
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

