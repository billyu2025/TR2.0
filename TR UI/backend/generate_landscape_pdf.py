import os
import sqlite3
from datetime import datetime
from html import escape

import re

import pandas as pd

try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError as e:
    WEASYPRINT_AVAILABLE = False
    IMPORT_ERROR = str(e)

try:
    from jinja2 import Environment, FileSystemLoader
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

try:
    from sqlalchemy import create_engine, text
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False

try:
    # 优先尝试 pypdf（新版本）
    from pypdf import PdfReader, PdfWriter, Transformation
    PYPDF2_AVAILABLE = True
    USE_PYPDF = True
except ImportError:
    try:
        # 回退到 PyPDF2（旧版本）
        from PyPDF2 import PdfReader, PdfWriter
        PYPDF2_AVAILABLE = True
        USE_PYPDF = False
        Transformation = None  # PyPDF2 可能没有 Transformation
    except ImportError:
        PYPDF2_AVAILABLE = False
        USE_PYPDF = False
        Transformation = None


class OrderTraceabilityPDFGenerator:
    def __init__(self, db_path: str = None, db_config: dict = None):
        if not WEASYPRINT_AVAILABLE:
            error_msg = (
                "\n" + "=" * 70 + "\n"
                "ERROR: WeasyPrint is not available!\n"
                "WeasyPrint requires GTK+ runtime on Windows.\n\n"
                "SOLUTION:\n"
                "1. Download GTK3-Runtime Win64 from:\n"
                "   https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases\n"
                "2. Install it and add to PATH: C:\\Program Files\\GTK3-Runtime Win64\\bin\n"
                "3. Restart your terminal and try again\n\n"
                "For detailed instructions, see: WEASYPRINT_WINDOWS_SETUP.md\n"
                "=" * 70 + "\n"
            )
            raise ImportError(error_msg + f"\nOriginal error: {IMPORT_ERROR}")

        if not JINJA2_AVAILABLE:
            raise ImportError("Jinja2 is not installed. Please run: pip install Jinja2")

        if not SQLALCHEMY_AVAILABLE:
            raise ImportError("SQLAlchemy is not installed. Please run: pip install sqlalchemy pyodbc")

        # 数据库配置：优先使用传入的配置，否则使用默认 SQL Server 配置
        if db_config:
            self.db_config = db_config
        else:
            # 默认 SQL Server 配置
            self.db_config = {
                'server': os.getenv('SQL_SERVER', '192.168.80.242'),
                'database': os.getenv('SQL_DATABASE', 'TVSC'),
                'username': os.getenv('SQL_USERNAME', 'reportuser'),
                'password': os.getenv('SQL_PASSWORD', 'HKSHA123'),
                'driver': 'SQL Server'
            }
        
        # 创建 SQL Server 连接字符串
        connection_string = (
            f"mssql+pyodbc://{self.db_config['username']}:{self.db_config['password']}"
            f"@{self.db_config['server']}/{self.db_config['database']}"
            f"?driver={self.db_config['driver']}"
        )
        self.engine = create_engine(connection_string, echo=False)
        
        # 保留 db_path 用于兼容性（如果将来需要）
        self.db_path = db_path
        
        # 设置SQLite数据库路径（用于查询TR_Fill_in表）
        if db_path:
            self.sqlite_db_path = db_path
        else:
            # 默认路径：从backend目录向上到项目根目录，然后到TR database
            backend_dir = os.path.dirname(__file__)
            project_root = os.path.normpath(os.path.join(backend_dir, '..'))
            self.sqlite_db_path = os.path.join(project_root, 'TR database', 'data_3years.db')
        
        templates_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.jinja_env = Environment(loader=FileSystemLoader(templates_dir))

        def format_float(value, fmt_str):
            if value is None:
                return ""
            try:
                return fmt_str % float(value)
            except (ValueError, TypeError):
                return str(value) if value else ""

        self.jinja_env.filters["format"] = format_float
        self._to_text = lambda v: "" if v is None else str(v)

    def get_order_data(self, order_no: int):
        # 使用 SQL Server 连接
        conn = self.engine.connect()
        try:
            # 查询订单基本信息（订单级别）
            # SQL Server 使用 TOP 而不是 LIMIT
            order_query = """
            SELECT DISTINCT TOP 1
                tbh.jobsite_no AS Job_No, 
                tbh.jobsite_name AS Jobsite, 
                tbh.bbs_no AS Order_No, 
                tbh.order_desc AS Order_Description,
                tbh.main_contractor AS Client,
                tbh.delivery_date AS Del_Date,
                tbh.bbs_ref_no AS Ref_No,
                tbh.bbs_po_no AS [PO_No(2)],
                tbh.jobsite_type AS Jobsite_Type
            FROM tr_line_size tls
            JOIN tr_bbs_header tbh
                ON tbh.bbs_no = tls.bbs_no
            LEFT JOIN tr_line_detail tld
                ON tls.bbs_no = tld.bbs_no
                AND tls.diameter = tld.diameter
            JOIN pedidos_produccion pp
                ON pp.ID_PEDIDO_PRODUCCION = tls.bbs_no
            JOIN obras js
                ON js.ID_OBRA = tls.jobsite_no
            WHERE tls.bbs_no = :order_no
            """

            order_info = pd.read_sql(text(order_query), conn, params={'order_no': order_no})
            if order_info.empty:
                return None, None, False

            # 获取 Jobsite_Type 并决定使用 Test_Cert1 还是 Test_Cert2
            # Jobsite_Type 可能是字符串 "IAT" 或 "PRIVATE"，也可能是数字
            # 规则：PRIVATE → Test_Cert1, IAT → Test_Cert2
            jobsite_type = order_info.iloc[0]["Jobsite_Type"]
            use_test_cert1 = False
            if pd.notna(jobsite_type):
                # 先尝试作为字符串处理
                if isinstance(jobsite_type, str):
                    jobsite_type_upper = jobsite_type.upper().strip()
                    if jobsite_type_upper == "PRIVATE":
                        use_test_cert1 = True
                    # 如果是 "IAT" 或其他值，使用 Test_Cert2（use_test_cert1 = False）
                else:
                    # 如果是数字，检查是否在指定列表中
                    try:
                        jobsite_type_int = int(jobsite_type)
                        if jobsite_type_int in [1, 4, 5, 6, 8, 11]:
                            use_test_cert1 = True
                    except (ValueError, TypeError):
                        pass

            # 查询材料详细信息（材料级别）
            # 根据 Jobsite_Type 决定使用 Test_Cert1 还是 Test_Cert2
            # 现在同时查询 test_cert1 和 test_cert2，根据逻辑选择使用哪个
            materials_query = """
            SELECT 
                tbh.jobsite_no AS Job_No,
                tls.diameter AS Dia,
                tls.wt_ton AS "Wt(ton)",
                tld.product AS Product,
                tld.grade AS Grade,
                tld.pattern AS Pattern,
                tld.mill_cert AS "Mill Cert",
                tld.test_cert1 AS "Test_Cert1",
                tld.test_cert2 AS "Test_Cert2",
                tld.supplier AS Supplier,
                tld.stockist_cert AS "Stockist Cert",
                tld.po_no AS "PO_No(1)"
            FROM tr_line_size tls
            JOIN tr_bbs_header tbh
                ON tbh.bbs_no = tls.bbs_no
            LEFT JOIN tr_line_detail tld
                ON tls.bbs_no = tld.bbs_no
                AND tls.diameter = tld.diameter
            JOIN pedidos_produccion pp
                ON pp.ID_PEDIDO_PRODUCCION = tls.bbs_no
            JOIN obras js
                ON js.ID_OBRA = tls.jobsite_no
            WHERE tls.bbs_no = :order_no
            ORDER BY pp.id_obra, pp.ID_PEDIDO_PRODUCCION, tls.diameter, tld.pattern
            """

            materials_data = pd.read_sql(text(materials_query), conn, params={'order_no': order_no})
            
            # 如果materials数据完全为空，从TR_Fill_in表获取所有数据
            if materials_data.empty:
                print(f"[INFO] Materials data is completely empty for order {order_no}, trying to fetch all data from TR_Fill_in table...")
                materials_data = self._fill_materials_from_tr_fill_in(order_no, materials_data, order_info.iloc[0])
            else:
                # 检查每个Dia是否有有效数据，如果某个Dia的数据为空或无效，从TR_Fill_in填充
                materials_data = self._fill_missing_dia_from_tr_fill_in(order_no, materials_data, order_info.iloc[0])
            
            return order_info.iloc[0], materials_data, use_test_cert1
        finally:
            conn.close()
    
    def _fill_materials_from_tr_fill_in(self, order_no: int, materials_data: pd.DataFrame, order_info: pd.Series):
        """当materials数据完全为空时，从TR_Fill_in表获取所有数据"""
        try:
            if not os.path.exists(self.sqlite_db_path):
                print(f"[WARNING] SQLite database not found: {self.sqlite_db_path}")
                return materials_data
            
            sqlite_conn = sqlite3.connect(self.sqlite_db_path, timeout=30.0)
            # 启用 WAL 模式以提高并发性能
            sqlite_conn.execute("PRAGMA journal_mode=WAL")
            sqlite_conn.execute("PRAGMA synchronous=NORMAL")
            sqlite_conn.execute("PRAGMA busy_timeout=30000")
            try:
                # 从TR_Fill_in表查询所有数据
                tr_fill_in_query = """
                SELECT 
                    Dia,
                    Product,
                    Pattern,
                    Mill_Cert,
                    Test_Cert1,
                    Test_Cert2,
                    Stockist_Cert,
                    PO_No,
                    Grade
                FROM TR_Fill_in
                ORDER BY Dia, Tag_No
                """
                
                tr_fill_in_data = pd.read_sql(tr_fill_in_query, sqlite_conn)
                
                if tr_fill_in_data.empty:
                    print(f"[INFO] TR_Fill_in table is empty, cannot fill materials data")
                    return materials_data
                
                # 将TR_Fill_in数据映射到materials数据结构
                # 需要从order_info获取Job_No，Wt(ton)设为None（因为TR_Fill_in没有重量信息）
                job_no = order_info.get('Job_No', '')
                
                mapped_data = []
                for _, row in tr_fill_in_data.iterrows():
                    mapped_row = {
                        'Job_No': job_no,
                        'Dia': str(row.get('Dia', '')).strip() if pd.notna(row.get('Dia')) else '',
                        'Wt(ton)': None,  # TR_Fill_in没有重量信息
                        'Product': str(row.get('Product', '')).strip() if pd.notna(row.get('Product')) else '',
                        'Grade': str(row.get('Grade', '')).strip() if pd.notna(row.get('Grade')) else '',
                        'Pattern': str(row.get('Pattern', '')).strip() if pd.notna(row.get('Pattern')) else '',
                        'Mill Cert': str(row.get('Mill_Cert', '')).strip() if pd.notna(row.get('Mill_Cert')) else '',
                        'Test_Cert1': str(row.get('Test_Cert1', '')).strip() if pd.notna(row.get('Test_Cert1')) else '',
                        'Test_Cert2': str(row.get('Test_Cert2', '')).strip() if pd.notna(row.get('Test_Cert2')) else '',
                        'Supplier': '',  # TR_Fill_in没有Supplier字段
                        'Stockist Cert': str(row.get('Stockist_Cert', '')).strip() if pd.notna(row.get('Stockist_Cert')) else '',
                        'PO_No(1)': str(row.get('PO_No', '')).strip() if pd.notna(row.get('PO_No')) else ''
                    }
                    mapped_data.append(mapped_row)
                
                if mapped_data:
                    new_materials_data = pd.DataFrame(mapped_data)
                    print(f"[INFO] Filled {len(new_materials_data)} materials records from TR_Fill_in table")
                    return new_materials_data
                else:
                    return materials_data
                    
            finally:
                sqlite_conn.close()
                
        except Exception as e:
            print(f"[WARNING] Failed to fill materials from TR_Fill_in: {e}")
            import traceback
            traceback.print_exc()
            return materials_data
    
    def _fill_missing_dia_from_tr_fill_in(self, order_no: int, materials_data: pd.DataFrame, order_info: pd.Series):
        """当某个Dia的数据为空时，从TR_Fill_in表获取该Dia的所有数据"""
        try:
            if not os.path.exists(self.sqlite_db_path):
                return materials_data
            
            sqlite_conn = sqlite3.connect(self.sqlite_db_path, timeout=30.0)
            # 启用 WAL 模式以提高并发性能
            sqlite_conn.execute("PRAGMA journal_mode=WAL")
            sqlite_conn.execute("PRAGMA synchronous=NORMAL")
            sqlite_conn.execute("PRAGMA busy_timeout=30000")
            try:
                # 检查每个Dia是否有有效的材料数据（Product、Pattern等不为空）
                # 按Dia分组，检查每个组是否有数据
                dia_groups = materials_data.groupby('Dia')
                missing_dias = []
                
                for dia, group in dia_groups:
                    # 检查该Dia组是否有有效的材料数据
                    # 如果所有关键字段（Product、Pattern、Mill_Cert）都为空，则认为该Dia数据为空
                    has_data = False
                    for _, row in group.iterrows():
                        # 如果Product、Pattern、Mill_Cert等关键字段至少有一个不为空，则认为有数据
                        product = str(row.get('Product', '')).strip() if pd.notna(row.get('Product')) else ''
                        pattern = str(row.get('Pattern', '')).strip() if pd.notna(row.get('Pattern')) else ''
                        mill_cert = str(row.get('Mill Cert', '')).strip() if pd.notna(row.get('Mill Cert')) else ''
                        
                        if product or pattern or mill_cert:
                            has_data = True
                            break
                    
                    if not has_data:
                        dia_str = str(dia) if pd.notna(dia) else ''
                        if dia_str:
                            missing_dias.append(dia_str)
                            print(f"[INFO] Dia '{dia_str}' has no valid material data, will fetch from TR_Fill_in")
                
                if not missing_dias:
                    return materials_data
                
                print(f"[INFO] Found {len(missing_dias)} Dia(s) with missing data: {missing_dias}, fetching from TR_Fill_in...")
                
                # 从TR_Fill_in表查询这些Dia的数据
                placeholders = ','.join('?' * len(missing_dias))
                tr_fill_in_query = f"""
                SELECT 
                    Dia,
                    Product,
                    Pattern,
                    Mill_Cert,
                    Test_Cert1,
                    Test_Cert2,
                    Stockist_Cert,
                    PO_No,
                    Grade
                FROM TR_Fill_in
                WHERE Dia IN ({placeholders})
                ORDER BY Dia, Tag_No
                """
                
                tr_fill_in_data = pd.read_sql(tr_fill_in_query, sqlite_conn, params=missing_dias)
                
                if tr_fill_in_data.empty:
                    print(f"[INFO] No data found in TR_Fill_in for Dia(s): {missing_dias}")
                    return materials_data
                
                print(f"[INFO] Found {len(tr_fill_in_data)} records in TR_Fill_in for Dia(s): {missing_dias}")
                
                # 将TR_Fill_in数据映射到materials数据结构
                job_no = order_info.get('Job_No', '')
                mapped_data = []
                
                for _, row in tr_fill_in_data.iterrows():
                    dia_value = str(row.get('Dia', '')).strip() if pd.notna(row.get('Dia')) else ''
                    
                    mapped_row = {
                        'Job_No': job_no,
                        'Dia': dia_value,
                        'Wt(ton)': None,  # TR_Fill_in没有重量信息，尝试从原materials_data中获取
                        'Product': str(row.get('Product', '')).strip() if pd.notna(row.get('Product')) else '',
                        'Grade': str(row.get('Grade', '')).strip() if pd.notna(row.get('Grade')) else '',
                        'Pattern': str(row.get('Pattern', '')).strip() if pd.notna(row.get('Pattern')) else '',
                        'Mill Cert': str(row.get('Mill_Cert', '')).strip() if pd.notna(row.get('Mill_Cert')) else '',
                        'Test_Cert1': str(row.get('Test_Cert1', '')).strip() if pd.notna(row.get('Test_Cert1')) else '',
                        'Test_Cert2': str(row.get('Test_Cert2', '')).strip() if pd.notna(row.get('Test_Cert2')) else '',
                        'Supplier': '',  # TR_Fill_in没有Supplier字段
                        'Stockist Cert': str(row.get('Stockist_Cert', '')).strip() if pd.notna(row.get('Stockist_Cert')) else '',
                        'PO_No(1)': str(row.get('PO_No', '')).strip() if pd.notna(row.get('PO_No')) else ''
                    }
                    
                    # 尝试从原materials_data中获取该Dia的Wt(ton)
                    if dia_value:
                        dia_materials = materials_data[materials_data['Dia'].astype(str).str.strip() == dia_value]
                        if not dia_materials.empty:
                            wt_value = dia_materials.iloc[0].get('Wt(ton)')
                            if pd.notna(wt_value):
                                mapped_row['Wt(ton)'] = wt_value
                    
                    mapped_data.append(mapped_row)
                
                if mapped_data:
                    # 移除原materials_data中对应Dia的空数据行
                    for dia in missing_dias:
                        materials_data = materials_data[materials_data['Dia'].astype(str).str.strip() != dia]
                    
                    # 添加从TR_Fill_in获取的数据
                    new_materials_data = pd.DataFrame(mapped_data)
                    materials_data = pd.concat([materials_data, new_materials_data], ignore_index=True)
                    
                    print(f"[INFO] Successfully filled {len(new_materials_data)} materials records from TR_Fill_in for Dia(s): {missing_dias}")
                
                return materials_data
                    
            finally:
                sqlite_conn.close()
                
        except Exception as e:
            print(f"[WARNING] Failed to fill missing Dia from TR_Fill_in: {e}")
            import traceback
            traceback.print_exc()
            return materials_data
    
    def generate_pdf(self, order_no: int, output_path: str | None = None):
        order_info, materials_data, use_test_cert1 = self.get_order_data(order_no)
        if order_info is None:
            print(f"Order {order_no} not found in database!")
            return False, None
        
        # 获取backend目录（脚本所在目录）
        backend_dir = os.path.dirname(__file__)
        
        if output_path is None:
            del_date = order_info.get("Del_Date", datetime.now().strftime("%Y-%m-%d"))
            # 使用绝对路径，基于backend目录
            pdf_dir = os.path.join(backend_dir, "Generated_PDFs", del_date)
            os.makedirs(pdf_dir, exist_ok=True)
            output_path = os.path.join(pdf_dir, f"TR_{order_no}.pdf")
            # 输出绝对路径用于调试
            abs_output_path = os.path.abspath(output_path)
            print(f"PDF output path (relative): {output_path}")
            print(f"PDF output path (absolute): {abs_output_path}")
        logo_path = os.path.join(backend_dir, "VSC Logo.png")
        logo_exists = os.path.exists(logo_path)
        if not logo_exists:
            alt_logo = os.path.join(backend_dir, "vsc logo.png")
            if os.path.exists(alt_logo):
                logo_path = alt_logo
                logo_exists = True

        signature_path = os.path.join(backend_dir, "signature_chop-removebg.png")
        signature_exists = os.path.exists(signature_path)
        if not signature_exists:
            signature_path_alt = os.path.join(backend_dir, "signature chop.PNG")
            if os.path.exists(signature_path_alt):
                signature_path = signature_path_alt
                signature_exists = True

        order_info_dict = {key: self._to_text(value) for key, value in order_info.items()}

        grouped_materials = self._group_material_rows(materials_data, use_test_cert1)

        template = self.jinja_env.get_template("tr_report.html")
        logo_rel_path = "VSC Logo.png" if logo_exists else ""
        if signature_exists:
            if "removebg" in os.path.basename(signature_path):
                signature_rel_path = "signature_chop-removebg.png"
            else:
                signature_rel_path = "signature chop.PNG"
        else:
            signature_rel_path = ""

        html_content = template.render(
            order_info=order_info_dict,
            grouped_materials=grouped_materials,
            logo_exists=logo_exists,
            logo_path=logo_rel_path,
            signature_exists=signature_exists,
            signature_path=signature_rel_path,
            use_test_cert1=use_test_cert1,
        )

        css_path = os.path.join(os.path.dirname(__file__), "templates", "tr_report.css")
        css = CSS(filename=css_path)

        backend_dir = os.path.dirname(__file__)
        base_url_path = backend_dir.replace("\\", "/")
        if not base_url_path.startswith("/"):
            if ":" in base_url_path:
                drive, path = base_url_path.split(":", 1)
                base_url_path = f"/{drive}:{path}"
        base_url = f"file://{base_url_path}/"

        try:
            # 如果目标文件已存在，先删除它以确保覆盖
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                    print(f"[INFO] Deleted existing PDF file: {output_path}")
                except Exception as e:
                    print(f"[WARNING] Failed to delete existing file, will continue: {e}")
            
            # 生成完整的 PDF
            html_doc = HTML(string=html_content, base_url=base_url)
            temp_output_path = output_path.replace('.pdf', '_temp.pdf')
            
            # 如果临时文件已存在，也先删除它
            if os.path.exists(temp_output_path):
                try:
                    os.remove(temp_output_path)
                except Exception as e:
                    print(f"[WARNING] Failed to delete existing temp file: {e}")
            
            html_doc.write_pdf(temp_output_path, stylesheets=[css])
            
            # 如果 PyPDF2 可用，则在每页插入 Header 和 Order Info
            if PYPDF2_AVAILABLE:
                self._add_header_to_all_pages(
                    temp_output_path, 
                    output_path, 
                    order_info_dict, 
                    logo_exists, 
                    logo_rel_path, 
                    signature_exists, 
                    signature_rel_path, 
                    use_test_cert1,
                    base_url,
                    css
                )
                # 删除临时文件
                if os.path.exists(temp_output_path):
                    try:
                        os.remove(temp_output_path)
                    except Exception as e:
                        print(f"[WARNING] Failed to delete temp file: {e}")
            else:
                # 如果 PyPDF2 不可用，直接使用临时文件
                if os.path.exists(temp_output_path):
                    os.rename(temp_output_path, output_path)
            
            # 注意：现在使用 CSS 的 header-spacer 来处理后续页面的 Header 空间
            # 不再使用 PyPDF2 进行页面处理
            
            print(f"PDF generated successfully: {output_path}")
            print(f"Order: {order_no}")
            print(f"Client: {order_info_dict.get('Client', 'N/A')}")
            print(f"Materials: {len(materials_data)} items")
            
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                print(f"File verified: {output_path} ({file_size} bytes)")
                # 返回相对路径（相对于backend目录），用于数据库存储和下载API
                # 这样下载API可以正确找到文件
                try:
                    rel_path = os.path.relpath(output_path, backend_dir)
                    # 在Windows上，使用正斜杠以确保跨平台兼容性
                    rel_path = rel_path.replace("\\", "/")
                    print(f"Returning relative path for database: {rel_path}")
                    return True, rel_path
                except ValueError:
                    # 如果无法转换为相对路径（例如在不同驱动器上），返回绝对路径
                    print(f"Warning: Cannot convert to relative path, returning absolute path")
                    return True, output_path
            else:
                print(f"WARNING: File does not exist: {output_path}")
                return False, None
        except Exception as e:
            print(f"Error generating PDF: {e}")
            import traceback
            traceback.print_exc()
            return False, None

    @staticmethod
    def _split_value(value: str):
        if value is None:
            return []
        text = str(value)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        parts = re.split(r"[\/\n]+", text)
        return [part.strip() for part in parts if part and part.strip()]

    def _format_multiline(self, value: str):
        """返回列表，用于在模板中渲染为块元素"""
        parts = self._split_value(value)
        if not parts:
            return []
        # 过滤空值并去除空白
        return [part.strip() for part in parts if part and part.strip()]
    
    def _format_multiline_cert(self, value: str):
        """证书字段的拆分：仅按换行符拆分，不按逗号/斜杠拆分，保持原始格式"""
        if value is None:
            return []
        text = str(value).replace("\r\n", "\n").replace("\r", "\n")
        # 仅按换行符拆分，不按逗号/分号/斜杠拆分，保持逗号分隔的格式
        # 这样 "162952/22, 158736/22, 158973/22" 会保持在一行
        parts = re.split(r"\n+", text)
        return [part.strip() for part in parts if part and part.strip()]

    def _group_material_rows(self, df: pd.DataFrame, use_test_cert1: bool = False):
        grouped = []
        if df is None or df.empty:
            return grouped

        for dia, group_df in df.groupby("Dia", sort=False):
            rows = []
            grade_values = []
            wt_value = None

            for idx, (_, row) in enumerate(group_df.iterrows()):
                if wt_value is None:
                    try:
                        wt_value = float(row["Wt(ton)"]) if row["Wt(ton)"] not in ("", None) else None
                    except (ValueError, TypeError):
                        wt_value = None

                grade_values.extend(self._split_value(row.get("Grade")))

                # 根据 use_test_cert1 选择使用 Test_Cert1 还是 Test_Cert2
                if use_test_cert1:
                    test_cert_value = row.get("Test_Cert1")
                else:
                    test_cert_value = row.get("Test_Cert2")

                row_entry = {
                    "product": self._format_multiline(row.get("Product")),
                    "grade": "",  # filled after dedupe
                    "pattern": self._format_multiline(row.get("Pattern")),
                    # 证书：仅按逗号/换行拆分，不按斜杠拆分
                    "mill_cert": self._format_multiline_cert(row.get("Mill Cert")),
                    "test_cert": self._format_multiline_cert(test_cert_value),  # 使用专门的格式化方法
                    "supplier": self._format_multiline(row.get("Supplier")),
                    "stockist": self._format_multiline(row.get("Stockist Cert")),
                    "po_no": self._format_multiline(row.get("PO_No(1)")),
                }
                rows.append(row_entry)

            deduped_grades = []
            for grade in grade_values:
                if grade and grade not in deduped_grades:
                    deduped_grades.append(grade)
            # Grade 改为返回列表，用于块元素渲染
            if rows:
                rows[0]["grade"] = deduped_grades if deduped_grades else []

            # Dia 和 Wt 也使用列表格式，即使只有一个值
            dia_text = self._to_text(dia)
            dia_list = self._format_multiline(dia_text) if dia_text else []
            # 如果只有一个值，保持为列表格式以便统一处理
            if not dia_list and dia_text:
                dia_list = [dia_text]
            
            grouped.append({
                "dia": dia_list,
                "wt_total": wt_value,  # Wt 保持为单个数值，在模板中处理
                "rows": rows,
            })

        return grouped

    def _add_top_margin_to_subsequent_pages(self, input_pdf_path, output_pdf_path):
        """在后续页面的表格前添加顶部边距（为 Header 留出空间）"""
        try:
            # 读取原始 PDF
            reader = PdfReader(input_pdf_path)
            writer = PdfWriter()
            
            # Header 和 Order Info 的高度（点，points）
            # 约 200 点（2.8 英寸）
            header_height = 200
            
            # 处理每一页
            for page_num, page in enumerate(reader.pages):
                if page_num == 0:
                    # 第一页：直接添加（已经包含 Header）
                    writer.add_page(page)
            else:
                    # 后续页面：在页面顶部添加空白边距
                    from PyPDF2.generic import Transformation, PageObject
                    
                    # 创建变换：将内容向下移动
                    transform = Transformation().translate(tx=0, ty=-header_height)
                    
                    # 应用变换
                    page.add_transformation(transform)
                    
                    # 添加页面
                    writer.add_page(page)
            
            # 写入输出文件
            with open(output_pdf_path, 'wb') as output_file:
                writer.write(output_file)
                
        except Exception as e:
            print(f"Warning: Failed to add top margin to subsequent pages: {e}")
            print("Falling back to original PDF.")
            import traceback
            traceback.print_exc()
            # 如果失败，直接复制原文件
            import shutil
            shutil.copy(input_pdf_path, output_pdf_path)
    
    def _add_page_number_to_page(self, page, page_text):
        """在页面上添加页码文本（底部右侧）"""
        try:
            # 尝试使用 reportlab 创建包含页码的 PDF，然后合并
            try:
                from reportlab.pdfgen import canvas
                from reportlab.lib.pagesizes import A4
                from reportlab.lib.units import mm
                import tempfile
                import io
                
                # 获取页面尺寸
                page_width = float(page.mediabox.width)
                page_height = float(page.mediabox.height)
                
                # 创建临时 PDF（包含页码文本）
                temp_pdf = io.BytesIO()
                c = canvas.Canvas(temp_pdf, pagesize=(page_width, page_height))
                
                # 设置字体和大小（与 CSS 中的 @bottom-right 一致）
                c.setFont("Helvetica-Bold", 9)
                
                # 页码位置：底部右侧（与 WeasyPrint 的 @bottom-right 位置一致）
                # CSS margin: 8mm 6mm 22mm 6mm (top right bottom left)
                # A4 landscape: 842 x 595 点
                # 底部边距 22mm = 22 * 2.83465 ≈ 62.36 点
                # 右侧边距 6mm = 6 * 2.83465 ≈ 17 点
                # WeasyPrint 的 @bottom-right 默认在底部边距内，右对齐
                # 精确位置：x = page_width - right_margin, y = bottom_margin
                right_margin_pt = 6 * 2.83465  # 6mm to points
                bottom_margin_pt = 11 * 2.83465  # 22mm to points
                
                x_position = page_width - right_margin_pt
                y_position = bottom_margin_pt
                
                # 绘制页码（右对齐，与 WeasyPrint 一致）
                c.drawRightString(x_position, y_position, page_text)
                c.save()
                
                # 读取临时 PDF
                temp_pdf.seek(0)
                page_reader = PdfReader(temp_pdf)
                page_number_page = page_reader.pages[0]
                
                # 合并页码页面到目标页面
                page.merge_page(page_number_page)
                
                print(f"Debug: Added page number using reportlab: {page_text}")
                return True
                
            except ImportError:
                # reportlab 不可用，使用内容流方法
                print("Warning: reportlab not available, using content stream method")
                return self._add_page_number_via_content_stream(page, page_text)
                
        except Exception as e:
            print(f"Warning: Failed to add page number to page: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    #page number location
    def _add_page_number_via_content_stream(self, page, page_text):
        """通过内容流添加页码（备用方法）"""
        try:
            # 获取页面尺寸
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)
            
            # 页码位置（与 WeasyPrint 的 @bottom-right 位置一致）
            # CSS margin: 8mm 6mm 22mm 6mm (top right bottom left)
            right_margin_pt = 4 * 2.83465  # 6mm to points
            bottom_margin_pt = 10 * 2.83465  # 22mm to points (与 reportlab 方法一致)
            x_position = page_width - right_margin_pt
            y_position = bottom_margin_pt
            
            # 转义特殊字符（PDF 文本字符串需要转义更多字符）
            escaped_text = (page_text
                          .replace('\\', '\\\\')
                          .replace('(', '\\(')
                          .replace(')', '\\)')
                          .replace('[', '\\[')
                          .replace(']', '\\]')
                          .replace('{', '\\{')
                          .replace('}', '\\}')
                          .replace('<', '\\<')
                          .replace('>', '\\>')
                          .replace('/', '\\/'))
            
            # 创建文本内容流
            # 使用粗体字体 /Helvetica-Bold（如果页面资源中有定义）
            # 或者使用 /F1（需要确保页面资源中已定义）
            font_size = 9
            # 估算文本宽度（Helvetica-Bold 9pt，大约每个字符 5.4 点）
            # 为了右对齐，需要从右边界减去文本宽度
            estimated_text_width = len(page_text) * 5.4
            x_aligned = x_position - estimated_text_width
            
            # 创建文本内容流（使用粗体字体并加粗）
            # 尝试使用 /Helvetica-Bold，如果不可用则使用 /F1 并添加文本渲染模式加粗
            # 使用文本渲染模式 Tr 2（描边+填充）来确保文字看起来更粗
            text_content = f"""BT
/Helvetica-Bold {font_size} Tf
0.3 w
2 Tr
1 0 0 1 {x_aligned} {y_position} Tm
({escaped_text}) Tj
ET
"""
            
            # 获取现有内容流
            # 合并后的页面可能有多个内容流对象，需要处理所有内容流
            if '/Contents' in page:
                contents = page['/Contents']
                
                # 处理内容流（可能是单个对象或列表）
                if isinstance(contents, list):
                    # 如果有多个内容流，在最后一个上添加页码（最上层）
                    if len(contents) > 0:
                        content_obj = contents[-1]
                        # 如果是间接引用，获取实际对象
                        if hasattr(content_obj, 'get_object'):
                            content_obj = content_obj.get_object()
                        
                        # pypdf的ContentStream对象使用.data属性（不是get_data方法）
                        if content_obj:
                            try:
                                # pypdf的ContentStream直接使用.data属性
                                if hasattr(content_obj, 'data'):
                                    # pypdf风格的ContentStream
                                    original_data = content_obj.data
                                    if isinstance(original_data, bytes):
                                        new_data = original_data + b'\n' + text_content.encode('utf-8')
                                        content_obj.data = new_data
                                        print(f"Debug: ✅ Added page number via content stream (list, using .data as bytes): {page_text}")
                                        print(f"Debug: Content stream size: {len(new_data)} bytes (original: {len(original_data)} bytes)")
                                        return True
                                    elif isinstance(original_data, str):
                                        new_data = original_data + '\n' + text_content
                                        content_obj.data = new_data
                                        print(f"Debug: ✅ Added page number via content stream (list, using .data as string): {page_text}")
                                        return True
                                elif hasattr(content_obj, 'get_data'):
                                    # PyPDF2风格的ContentStream
                                    original_data = content_obj.get_data()
                                    if isinstance(original_data, bytes):
                                        new_data = original_data + b'\n' + text_content.encode('utf-8')
                                        content_obj._data = new_data
                                        print(f"Debug: ✅ Added page number via content stream (list, using get_data): {page_text}")
                                        return True
                                
                                # 如果以上方法都失败
                                print(f"Warning: Cannot access content stream data in list item. Type: {type(content_obj)}")
                                attrs = [attr for attr in dir(content_obj) if not attr.startswith('__')]
                                print(f"Warning: Available attributes: {attrs[:15]}")
                            except Exception as e:
                                print(f"Warning: Error modifying content stream (list): {e}")
                                import traceback
                                traceback.print_exc()
                        else:
                            print(f"Warning: Content object is None in list")
                    else:
                        print(f"Warning: Contents list is empty")
                else:
                    # 单个内容流对象
                    content_obj = contents
                    original_type = type(content_obj)
                    
                    # 注意：pypdf的ContentStream对象不能调用get_object()，它会返回None
                    # 直接使用ContentStream对象，不要调用get_object()
                    # ContentStream和EncodedStreamObject都有get_data方法
                    
                    print(f"Debug: ContentStream type: {original_type}, skipping get_object()")
                    
                    # pypdf的ContentStream/EncodedStreamObject需要特殊处理
                    if content_obj:
                        try:
                            # 根据测试，pypdf的EncodedStreamObject有get_data方法
                            # 优先使用get_data方法（更标准）
                            if hasattr(content_obj, 'get_data'):
                                try:
                                    original_data = content_obj.get_data()
                                    if isinstance(original_data, bytes):
                                        new_data = original_data + b'\n' + text_content.encode('utf-8')
                                        # 设置数据：尝试不同的方法
                                        if hasattr(content_obj, '_data'):
                                            content_obj._data = new_data
                                        elif hasattr(content_obj, 'data'):
                                            content_obj.data = new_data
                                        print(f"Debug: ✅ Added page number via content stream (single, using get_data): {page_text}")
                                        print(f"Debug: Content stream size: {len(new_data)} bytes (original: {len(original_data)} bytes)")
                                        return True
                                except Exception as get_data_error:
                                    print(f"Debug: get_data() failed: {get_data_error}, trying other methods...")
                            
                            # 备用方法1：直接访问data属性
                            if hasattr(content_obj, 'data'):
                                try:
                                    original_data = content_obj.data
                                    if isinstance(original_data, bytes):
                                        new_data = original_data + b'\n' + text_content.encode('utf-8')
                                        content_obj.data = new_data
                                        print(f"Debug: ✅ Added page number via content stream (single, using .data as bytes): {page_text}")
                                        return True
                                    elif isinstance(original_data, str):
                                        new_data = original_data + '\n' + text_content
                                        content_obj.data = new_data
                                        print(f"Debug: ✅ Added page number via content stream (single, using .data as string): {page_text}")
                                        return True
                                except Exception as data_error:
                                    print(f"Debug: .data access failed: {data_error}")
                            
                            # 备用方法2：直接访问_data属性
                            if hasattr(content_obj, '_data'):
                                try:
                                    original_data = content_obj._data
                                    if isinstance(original_data, bytes):
                                        new_data = original_data + b'\n' + text_content.encode('utf-8')
                                        content_obj._data = new_data
                                        print(f"Debug: ✅ Added page number via content stream (single, using ._data): {page_text}")
                                        return True
                                except Exception as _data_error:
                                    print(f"Debug: ._data access failed: {_data_error}")
                            
                            # 如果以上方法都失败
                            print(f"Warning: All methods failed to access content stream data. Type: {type(content_obj)}")
                            attrs = [attr for attr in dir(content_obj) if not attr.startswith('__')]
                            print(f"Warning: Available attributes: {attrs[:15]}")
                        except Exception as e:
                            print(f"Warning: Error modifying content stream (single): {e}")
                            import traceback
                            traceback.print_exc()
                    else:
                        print(f"Warning: Content stream object is None")
            else:
                print(f"Warning: Page has no /Contents key")
                    
        except Exception as e:
            print(f"Warning: Content stream method failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _add_header_to_all_pages(self, input_pdf_path, output_pdf_path, order_info_dict, 
                                  logo_exists, logo_rel_path, signature_exists, 
                                  signature_rel_path, use_test_cert1, base_url, css):
        """在每页顶部插入 Header 和 Order Info，并将表格内容向下移动"""
        try:
            # 如果输出文件已存在，先删除它以确保覆盖
            if os.path.exists(output_pdf_path):
                try:
                    os.remove(output_pdf_path)
                    print(f"[INFO] 已删除已存在的输出文件: {output_pdf_path}")
                except Exception as e:
                    print(f"[WARNING] 删除已存在的输出文件失败，将继续尝试覆盖: {e}")
            
            # 读取原始 PDF
            reader = PdfReader(input_pdf_path)
            writer = PdfWriter()
            
            # 生成只包含 Header 和 Order Info 的 PDF
            header_template = self.jinja_env.get_template("tr_report_header_only.html")
            header_html = header_template.render(
                order_info=order_info_dict,
                logo_exists=logo_exists,
                logo_path=logo_rel_path,
                signature_exists=signature_exists,
                signature_path=signature_rel_path,
                use_test_cert1=use_test_cert1,
            )
            
            # 创建临时文件存储 Header PDF
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_header_file:
                temp_header_path = temp_header_file.name
            
            # 为 Header 使用单独的 CSS（不包含页码）
            header_css_path = os.path.join(os.path.dirname(__file__), "templates", "tr_report_header_only.css")
            if os.path.exists(header_css_path):
                header_css = CSS(filename=header_css_path)
            else:
                # 如果单独的 CSS 不存在，使用原 CSS（但会包含页码）
                header_css = css
                print(f"Warning: tr_report_header_only.css not found, using tr_report.css (may include page numbers)")
            
            header_doc = HTML(string=header_html, base_url=base_url)
            header_doc.write_pdf(temp_header_path, stylesheets=[header_css])
            
            # 读取 Header PDF
            header_reader = PdfReader(temp_header_path)
            header_page = header_reader.pages[0]
            
            # 计算 Header 和 Order Info 的实际高度
            # 从 Header PDF 中获取实际内容高度
            # A4 landscape: 842 x 595 点（宽 x 高），1英寸 = 72点
            # PDF坐标系统：原点在左下角，Y向上（0=底部，595=顶部）
            
            # 根据CSS估算Header实际高度：
            # - Logo: 0.7in (50点)
            # - Header margin-bottom: 0.5in (36点)
            # - Order Info Section: margin-top: -0.4in, margin-bottom: 0.2in, 实际内容约1.2in (86点)
            # - 安全边距: 额外20-40点
            # 总计约：192-232点（约2.7-3.2英寸）
            
            # 注意：这个值是将内容下移的距离，确保内容从Header下方开始
            # 如果需要调整第二页内容位置（避免与Header重叠），修改这个值：
            # - 增大值 = 内容下移更多（与 Header 距离更大，不会重叠）
            # - 减小值 = 内容上移（与 Header 距离更小，可能重叠）
            # 建议范围：150-280点（约2.1-3.9英寸）
            
            # 默认使用较大的值以确保不重叠
            # 如果您发现第二页内容仍然与Header重叠，请尝试更大的值（如250、280、300）
            header_content_height = 116  # 默认值，约 3.5 英寸（增加到250以更好地避免重叠）
            
            try:
                # 获取 Header 页面的 mediabox
                header_mediabox = header_page.mediabox
                print(f"Debug: Header mediabox: {header_mediabox}")
            except Exception as e:
                print(f"Debug: Error getting mediabox: {e}")
            
            print(f"Debug: Using header_content_height = {header_content_height} points (approx {header_content_height/72:.2f} inches)")
            print(f"Debug: To adjust second page content position:")
            print(f"       - Increase header_content_height to move content DOWN (more space from header)")
            print(f"       - Decrease header_content_height to move content UP (closer to header)")
            print(f"       - Suggested range: 150-280 points (2.1-3.9 inches)")
            
            print(f"Debug: Using header_content_height = {header_content_height} points")
            
            # 获取总页数（用于更新页码）
            total_pages = len(reader.pages)
            print(f"Debug: Total pages in original PDF: {total_pages}")
            
            # 如果只有一页，临时PDF已经包含Header，直接使用（不添加页码，因为WeasyPrint已经添加了）
            if total_pages == 1:
                print(f"Debug: Single page PDF detected - using original page directly (WeasyPrint already added page number)")
                page = reader.pages[0]
                # 直接添加原始页面，不进行任何修改
                writer.add_page(page)
                print(f"Debug: Added original page directly without modification")
            else:
                # 多页情况：处理每一页
                for page_num, page in enumerate(reader.pages):
                    if page_num == 0:
                        # 第一页：先添加原始页面确保内容显示，页码暂时不添加
                        # 由于修改页面对象会导致内容丢失，我们暂时保持第一页不添加页码
                        # 或者使用CSS重新启用第一页的页码
                        print(f"Debug: Page 1 - adding original page directly (page number will be added via CSS or skipped)")
                        
                        # 直接添加原始页面，不进行任何修改（确保内容正常显示）
                        writer.add_page(page)
                        print(f"Debug: Added page 1 directly without modification (content preserved)")
                        
                        # 注意：第一页的页码暂时不通过代码添加，因为修改页面对象会导致内容丢失
                        # 如果需要第一页显示页码，可以考虑：
                        # 1. 在CSS中重新启用@bottom-right（但会被第二页的处理方式覆盖）
                        # 2. 或者接受第一页没有页码（第二页有页码）
                        print(f"Debug: ⚠️ Page 1 page number not added to avoid content loss")
                    else:
                        # 后续页面：使用 pypdf 的简洁方法
                        try:
                            import copy
                            import re
                        
                            if USE_PYPDF and Transformation is not None:
                                # 使用 pypdf 的方法（推荐）
                                # PDF坐标系统：原点在左下角，Y轴向上（0=底部，595=顶部）
                                # 要将内容下移，需要使用负的ty值：translate(tx=0, ty=-value)
                                # 这意味着内容会向下移动，留出顶部空间给Header
                                
                                # 1. 创建新页面：先复制 header_page（包含 Header，保持在顶部）
                                new_page = copy.deepcopy(header_page)
                                
                                # 2. 创建内容页面的副本并应用变换（下移内容，为Header留出空间）
                                content_page = copy.deepcopy(page)
                                # ⚠️ 重要：ty=-header_content_height 会将整个页面内容向下移动，包括：
                                # - 主要内容（表格等）
                                # - 底部页码（由WeasyPrint的CSS @bottom-right添加）
                                # - 底部认证文字（由WeasyPrint的CSS @bottom-left添加）
                                # 下移后，底部的页码和认证文字会被移出页面底部，不可见
                                # 所以我们必须在合并后，在正确位置重新添加页码
                                transform = Transformation().translate(tx=0, ty=-header_content_height)
                                content_page.add_transformation(transform)
                                
                                print(f"Debug: Page {page_num + 1}: Applying transformation translate(tx=0, ty=-{header_content_height})")
                                print(f"Debug: This moves ALL content DOWN by {header_content_height} points ({header_content_height/72:.2f} inches)")
                                print(f"Debug: ⚠️ Original page number will be moved out of view - will re-add after merge")
                                
                                # 3. 将下移后的内容合并到Header页面上
                                # merge_page会将content_page叠加到new_page上
                                # 由于content_page已经下移，它的内容会在Header下方
                                # 注意：此时原始页码已经被下移，不可见了
                                new_page.merge_page(content_page)
                                
                                print(f"Debug: Applied pypdf transformation to page {page_num + 1} (header_height={header_content_height})")
                                print(f"Debug: Shifted content down by {header_content_height} points, then merged with header (header stays at top)")
                                
                                # 4. 在合并后的页面上添加页码到正确位置（底部右侧）
                                # 因为变换下移了整个页面内容（包括原来的页码），所以页码已经不可见
                                # 我们需要在合并后的新页面上重新添加页码到页面底部
                                current_page_num = page_num + 1
                                page_text = f"Page {current_page_num}/{total_pages}"
                                print(f"Debug: Re-adding page number '{page_text}' to merged page {page_num + 1} (original was moved down)")
                                
                                # 尝试多种方法添加页码，确保至少一种方法成功
                                page_number_added = False
                                
                                # 方法1：使用主方法（reportlab或content stream）
                                try:
                                    page_number_added = self._add_page_number_to_page(new_page, page_text)
                                    if page_number_added:
                                        print(f"Debug: ✅ Successfully added page number using primary method: {page_text}")
                                    else:
                                        print(f"Debug: Primary method returned False")
                                except Exception as method1_error:
                                    print(f"Warning: Primary method exception: {method1_error}")
                                    import traceback
                                    traceback.print_exc()
                                
                                # 方法2：如果主方法失败，直接使用content stream方法
                                if not page_number_added:
                                    print(f"Debug: Trying direct content stream method as fallback...")
                                    try:
                                        page_number_added = self._add_page_number_via_content_stream(new_page, page_text)
                                        if page_number_added:
                                            print(f"Debug: ✅ Successfully added page number using content stream method: {page_text}")
                                        else:
                                            print(f"Debug: Content stream method returned False")
                                    except Exception as method2_error:
                                        print(f"Warning: Content stream method exception: {method2_error}")
                                        import traceback
                                        traceback.print_exc()
                                
                                if not page_number_added:
                                    print(f"Warning: ❌ All methods failed to add page number to page {page_num + 1}")
                                    print(f"Debug: Page structure - has /Contents: {'/Contents' in new_page}")
                                    if '/Contents' in new_page:
                                        contents = new_page['/Contents']
                                        print(f"Debug: Contents type: {type(contents)}, is list: {isinstance(contents, list)}")
                                        
                                        # 尝试直接访问ContentStream（不调用get_object()，因为它会返回None）
                                        if not isinstance(contents, list):
                                            print(f"Debug: Contents is ContentStream, trying direct access (without get_object)...")
                                            try:
                                                # 对于ContentStream类型，直接使用，不要调用get_object()
                                                if hasattr(contents, 'get_data'):
                                                    print(f"Debug: ContentStream has get_data method, attempting to add page number directly...")
                                                    try:
                                                        original_data = contents.get_data()
                                                        if isinstance(original_data, bytes):
                                                            # 生成页码文本的PDF内容流（与_add_page_number_via_content_stream中的逻辑一致）
                                                            page_width = float(new_page.mediabox.width)
                                                            right_margin_pt = 4 * 2.83465
                                                            bottom_margin_pt = 10 * 2.83465
                                                            x_position = page_width - right_margin_pt
                                                            y_position = bottom_margin_pt
                                                            
                                                            # 转义页码文本
                                                            escaped_text = (page_text
                                                                          .replace('\\', '\\\\')
                                                                          .replace('(', '\\(')
                                                                          .replace(')', '\\)')
                                                                          .replace('/', '\\/'))
                                                            
                                                            font_size = 9
                                                            estimated_text_width = len(page_text) * 5.4
                                                            x_aligned = x_position - estimated_text_width
                                                            
                                                            # 生成页码文本的PDF内容流（使用粗体并加粗）
                                                            # 使用 /Helvetica-Bold 并添加文本渲染模式确保黑体效果
                                                            # 0.3 w 设置线宽，2 Tr 使用描边+填充模式
                                                            text_content_pdf = f"""BT
/Helvetica-Bold {font_size} Tf
0.3 w
2 Tr
1 0 0 1 {x_aligned} {y_position} Tm
({escaped_text}) Tj
ET
"""
                                                            
                                                            new_data = original_data + b'\n' + text_content_pdf.encode('utf-8')
                                                            # 设置数据到ContentStream
                                                            if hasattr(contents, '_data'):
                                                                contents._data = new_data
                                                                print(f"Debug: ✅ Successfully added page number directly to ContentStream: {page_text}")
                                                                page_number_added = True
                                                            else:
                                                                print(f"Debug: ContentStream has no _data attribute")
                                                        else:
                                                            print(f"Debug: get_data() returned non-bytes: {type(original_data)}")
                                                    except Exception as e:
                                                        print(f"Debug: Direct get_data()/set data call failed: {e}")
                                                        import traceback
                                                        traceback.print_exc()
                                                else:
                                                    print(f"Debug: ContentStream does not have get_data method")
                                            except Exception as e:
                                                print(f"Debug: Error accessing ContentStream directly: {e}")
                                                import traceback
                                                traceback.print_exc()
                                else:
                                    print(f"Debug: ✅ Page number successfully added to page {page_num + 1}")
                                # 无论页码是否添加成功，变换都已经应用，继续处理
                            else:
                                # 回退到 PyPDF2 的旧方法
                                # 创建新页面：先复制 header_page（包含 Header）
                                new_page = copy.deepcopy(header_page)
                                
                                # 创建内容页面的副本
                                content_page = copy.deepcopy(page)
                                
                                # 直接修改内容流，在内容前添加变换矩阵
                                transform_cmd = f"1 0 0 1 0 -{header_content_height} cm\n"
                                
                                # 修改内容页面的内容流
                                if '/Contents' in content_page:
                                    contents = content_page['/Contents']
                                    
                                    def wrap_content_stream(original_data):
                                        """使用 q/Q 包装内容流，确保变换生效"""
                                        q_cmd = b"q\n"
                                        transform_bytes = transform_cmd.encode('utf-8')
                                        Q_cmd = b"\nQ\n"
                                        return q_cmd + transform_bytes + original_data + Q_cmd
                                    
                                    if isinstance(contents, list):
                                        for content_item in contents:
                                            if hasattr(content_item, 'get_object'):
                                                content_obj = content_item.get_object()
                                            else:
                                                content_obj = content_item
                                            
                                            if content_obj and hasattr(content_obj, 'get_data'):
                                                try:
                                                    original_data = content_obj.get_data()
                                                    if not (original_data.startswith(b'q\n') and original_data.endswith(b'\nQ\n')):
                                                        new_data = wrap_content_stream(original_data)
                                                        content_obj._data = new_data
                                                        print(f"Debug: Wrapped content stream item for page {page_num + 1} (PyPDF2 fallback)")
                                                except Exception as e3:
                                                    print(f"Debug: Error modifying content stream item: {e3}")
                                    else:
                                        if hasattr(contents, 'get_object'):
                                            contents_obj = contents.get_object()
                                        else:
                                            contents_obj = contents
                                        
                                        if contents_obj and hasattr(contents_obj, 'get_data'):
                                            try:
                                                original_data = contents_obj.get_data()
                                                if not (original_data.startswith(b'q\n') and original_data.endswith(b'\nQ\n')):
                                                    new_data = wrap_content_stream(original_data)
                                                    contents_obj._data = new_data
                                                    print(f"Debug: Wrapped content stream for page {page_num + 1} (PyPDF2 fallback)")
                                            except Exception as e3:
                                                print(f"Debug: Error modifying content stream data: {e3}")
                                
                                # 合并内容页面（已经向下移动）
                                new_page.merge_page(content_page)
                                print(f"Debug: Merged content page to new page {page_num + 1} (PyPDF2 fallback)")
                                
                                # 添加页码
                                current_page_num = page_num + 1
                                page_text = f"Page {current_page_num}/{total_pages}"
                                try:
                                    page_number_added = self._add_page_number_to_page(new_page, page_text)
                                    if page_number_added:
                                        print(f"Debug: Added page number via PyPDF2 fallback: {page_text}")
                                    else:
                                        print(f"Warning: PyPDF2 fallback: Failed to add page number to page {page_num + 1}")
                                except Exception as page_num_error:
                                    print(f"Warning: PyPDF2 fallback: Error adding page number: {page_num_error}")
                            
                            writer.add_page(new_page)
                            print(f"Debug: Successfully processed page {page_num + 1} with header_content_height = {header_content_height}")
                            
                        except Exception as e:
                            print(f"Warning: Failed to process page {page_num + 1}: {e}")
                            import traceback
                            traceback.print_exc()
                            # 回退：即使出错也要应用变换（避免重叠）
                            try:
                                import copy
                                # 仍然应用变换，避免内容与Header重叠
                                new_page = copy.deepcopy(header_page)
                                content_page_fallback = copy.deepcopy(page)
                                
                                # 尝试应用变换（即使使用PyPDF2 fallback方法）
                                if USE_PYPDF and Transformation is not None:
                                    transform_fallback = Transformation().translate(tx=0, ty=-header_content_height)
                                    content_page_fallback.add_transformation(transform_fallback)
                                    print(f"Debug: Fallback: Applied transformation to page {page_num + 1} (header_height={header_content_height})")
                                
                                new_page.merge_page(content_page_fallback)
                                
                                # Fallback方法也需要添加页码
                                current_page_num = page_num + 1
                                page_text = f"Page {current_page_num}/{total_pages}"
                                try:
                                    page_number_added = self._add_page_number_to_page(new_page, page_text)
                                    if page_number_added:
                                        print(f"Debug: Fallback: Added page number: {page_text}")
                                    else:
                                        print(f"Warning: Fallback: Failed to add page number to page {page_num + 1}")
                                except Exception as page_num_error:
                                    print(f"Warning: Fallback: Error adding page number: {page_num_error}")
                                
                                writer.add_page(new_page)
                                print(f"Debug: Fallback: Merged page {page_num + 1} with transformation and page number")
                            except Exception as fallback_error:
                                print(f"Warning: Fallback also failed: {fallback_error}")
                                # 最后的回退：至少添加原页面（但会有重叠）
                                writer.add_page(page)
                                print(f"Warning: Using original page without transformation - content may overlap with header")
            
            # 写入输出文件
            with open(output_pdf_path, 'wb') as output_file:
                writer.write(output_file)
            
            # 清理临时文件
            if os.path.exists(temp_header_path):
                os.remove(temp_header_path)
                
        except Exception as e:
            print(f"Warning: Failed to add header to all pages: {e}")
            print("Falling back to original PDF without header insertion.")
            import traceback
            traceback.print_exc()
            # 如果失败，直接复制原文件
            import shutil
            shutil.copy(input_pdf_path, output_pdf_path)


def generate_landscape_pdf():
    print("=== Order Traceability PDF Generator (WeasyPrint) ===")
    db_path = r"C:\YYH\TR REPORT\TR database\data_3years.db"
    generator = OrderTraceabilityPDFGenerator(db_path)
    
    sample_order = 126831
    print(f"Generating landscape PDF for Order: {sample_order}")
    
    success, pdf_path = generator.generate_pdf(sample_order)
    if success:
        print("Landscape PDF generated successfully!")
        print(f"PDF saved to: {pdf_path}")
    else:
        print("Failed to generate PDF.")


if __name__ == "__main__":
    generate_landscape_pdf()
