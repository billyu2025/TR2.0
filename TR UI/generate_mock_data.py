#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成前端测试数据
从materials_com表提取真实数据，生成JavaScript对象用于前端测试
"""

import sqlite3
import json

def generate_mock_data(limit=20):
    """从materials_com表提取数据并生成JavaScript对象"""
    
    db_path = '../TR database/data_3years.db'
    conn = sqlite3.connect(db_path)
    
    try:
        cursor = conn.cursor()
        
        # 查询materials_com表，获取前limit条记录
        query = """
        SELECT 
            Dia, 
            Len, 
            Product, 
            Pattern, 
            Mill_Cert, 
            Test_Cert2, 
            Test_Cert1, 
            Stockist_Cert, 
            PO_No, 
            Tag_No, 
            DN_No
        FROM materials_com
        WHERE Tag_No IS NOT NULL
        LIMIT ?
        """
        
        cursor.execute(query, (limit,))
        results = cursor.fetchall()
        
        # 生成JavaScript对象
        js_code = "const mockData = {\n"
        
        for row in results:
            tag_no = row[9]  # Tag_No列
            
            # 处理None值
            def format_value(v):
                if v is None:
                    return "''"
                elif isinstance(v, str):
                    # 转义单引号
                    v_escaped = v.replace("'", "\\'")
                    return f"'{v_escaped}'"
                else:
                    return f"'{v}'"
            
            js_code += f"    '{tag_no}': {{\n"
            js_code += f"        Dia: {format_value(row[0])},\n"
            js_code += f"        Len: {format_value(row[1])},\n"
            js_code += f"        Product: {format_value(row[2])},\n"
            js_code += f"        Pattern: {format_value(row[3])},\n"
            js_code += f"        Mill_Cert: {format_value(row[4])},\n"
            js_code += f"        Test_Cert2: {format_value(row[5])},\n"
            js_code += f"        Test_Cert1: {format_value(row[6])},\n"
            js_code += f"        Stockist_Cert: {format_value(row[7])},\n"
            js_code += f"        PO_No: {format_value(row[8])},\n"
            js_code += f"        Tag_No: '{tag_no}',\n"
            js_code += f"        DN_No: {format_value(row[10])}\n"
            js_code += "    },\n"
        
        js_code += "};"
        
        print("Generated JavaScript data:")
        print("=" * 80)
        print(js_code)
        print("=" * 80)
        
        # 保存到文件
        output_file = 'mock_data.js'
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(js_code)
        
        print(f"\nData saved to: {output_file}")
        print(f"Total records: {len(results)}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    generate_mock_data(20)

