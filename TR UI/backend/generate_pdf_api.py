#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF生成API
集成到tr_fill_in_api.py中
"""

import sys
import os

# 添加TR database目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../database')))

from flask import Blueprint, request, jsonify
from generate_landscape_pdf import OrderTraceabilityPDFGenerator
from datetime import datetime

pdf_bp = Blueprint('pdf', __name__)

# 数据库路径
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../TR database/data_3years.db'))

@pdf_bp.route('/api/pdf/generate', methods=['POST'])
def generate_pdf():
    """生成PDF"""
    try:
        data = request.json
        order_no = data.get('order_no')
        
        if not order_no:
            return jsonify({
                'success': False,
                'error': 'Order No is required'
            }), 400
        
        # 创建PDF生成器
        generator = OrderTraceabilityPDFGenerator(DB_PATH)
        
        # 生成PDF
        success, pdf_path = generator.generate_pdf(int(order_no))
        
        if success:
            return jsonify({
                'success': True,
                'pdf_path': pdf_path,
                'order_no': order_no,
                'message': 'PDF generated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Order {order_no} not found in database'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@pdf_bp.route('/api/pdf/download/<order_no>', methods=['GET'])
def download_pdf(order_no):
    """下载PDF"""
    try:
        from flask import send_file
        
        # 查找PDF文件
        # 从Orders_gen_pdf获取Del_Date
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT Del_Date 
            FROM Orders_gen_pdf 
            WHERE Order_No = ? 
            LIMIT 1
        """, (order_no,))
        
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return jsonify({
                'success': False,
                'error': 'Order not found'
            }), 404
        
        del_date = result[0]
        conn.close()
        
        # 构建PDF路径
        pdf_path = f"../TR database/Generated_PDFs/{del_date}/Order_{order_no}.pdf"
        
        if os.path.exists(pdf_path):
            return send_file(pdf_path, as_attachment=True, download_name=f"Order_{order_no}.pdf")
        else:
            return jsonify({
                'success': False,
                'error': 'PDF file not found'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

