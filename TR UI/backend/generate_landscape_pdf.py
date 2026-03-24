import os
from datetime import datetime
from html import escape

import re

import pandas as pd

# 导入日志器（安全导入，如果不可用则使用 print）
try:
    from logger_config import get_logger
    logger = get_logger('pdf_generator')
    _has_logger = True
except ImportError:
    _has_logger = False
    logger = None

def _safe_log(level, message):
    """安全日志输出，如果 logger 不可用则跳过"""
    if _has_logger and logger:
        try:
            if level == 'info':
                logger.info(message)
            elif level == 'debug':
                logger.debug(message)
            elif level == 'warning':
                logger.warning(message)
            elif level == 'error':
                logger.error(message)
        except Exception:
            pass  # 如果日志失败，静默忽略

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
    # Try pypdf first (new version)
    from pypdf import PdfReader, PdfWriter, Transformation
    PYPDF2_AVAILABLE = True
    USE_PYPDF = True
except ImportError:
    try:
        # Fallback to PyPDF2 (old version)
        from PyPDF2 import PdfReader, PdfWriter
        PYPDF2_AVAILABLE = True
        USE_PYPDF = False
        Transformation = None  # PyPDF2 may not have Transformation
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

        # Database configuration: prefer passed config, otherwise use default SQL Server config
        if db_config:
            self.db_config = db_config
        else:
            # Default SQL Server configuration
            self.db_config = {
                'server': os.getenv('SQL_SERVER', '192.168.80.242'),
                'database': os.getenv('SQL_DATABASE', 'TVSC'),
                'username': os.getenv('SQL_USERNAME', 'reportuser'),
                'password': os.getenv('SQL_PASSWORD', 'HKSHA123'),
                'driver': 'SQL Server'
            }
        
        # Create SQL Server connection string
        connection_string = (
            f"mssql+pyodbc://{self.db_config['username']}:{self.db_config['password']}"
            f"@{self.db_config['server']}/{self.db_config['database']}"
            f"?driver={self.db_config['driver']}"
        )
        self.engine = create_engine(connection_string, echo=False)
        
        # Keep db_path for compatibility (if needed in the future)
        self.db_path = db_path
        
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

    def _is_blank(self, value) -> bool:
        if value is None:
            return True
        try:
            if pd.isna(value):
                return True
        except Exception:
            pass
        return str(value).strip() == ""

    def _count_empty_key_rows(self, materials_data: pd.DataFrame) -> int:
        """Count rows where all key material fields are empty at the same time."""
        if materials_data is None or materials_data.empty:
            return 0

        key_fields = [
            "Product",
            "Grade",
            "Pattern",
            "Mill Cert",
            "Test_Cert1",
            "Test_Cert2",
            "Supplier",
            "Stockist Cert",
            "PO_No(1)",
            "rm_dn_no",
        ]

        empty_count = 0
        for _, row in materials_data.iterrows():
            if all(self._is_blank(row.get(field)) for field in key_fields):
                empty_count += 1
        return empty_count

    def get_order_data(self, order_no: int):
        # Use SQL Server connection
        conn = self.engine.connect()
        try:
            # Query order basic information (order level)
            # SQL Server uses TOP instead of LIMIT
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

            # Get Jobsite_Type and decide whether to use Test_Cert1 or Test_Cert2
            # Jobsite_Type may be string "IAT" or "PRIVATE", or a number
            # Rule: PRIVATE → Test_Cert1, IAT → Test_Cert2
            jobsite_type = order_info.iloc[0]["Jobsite_Type"]
            use_test_cert1 = False
            if pd.notna(jobsite_type):
                # Try to process as string first
                if isinstance(jobsite_type, str):
                    jobsite_type_upper = jobsite_type.upper().strip()
                    if jobsite_type_upper == "PRIVATE":
                        use_test_cert1 = True
                    # If "IAT" or other value, use Test_Cert2 (use_test_cert1 = False)
                else:
                    # If number, check if in specified list
                    try:
                        jobsite_type_int = int(jobsite_type)
                        if jobsite_type_int in [1, 4, 5, 6, 8, 11]:
                            use_test_cert1 = True
                    except (ValueError, TypeError):
                        pass

            # Query material detailed information (material level)
            # Decide whether to use Test_Cert1 or Test_Cert2 based on Jobsite_Type
            # Now query both test_cert1 and test_cert2, select which one to use based on logic
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
                tld.po_no AS "PO_No(1)",
                tld.rm_dn_no AS rm_dn_no
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
            
            return order_info.iloc[0], materials_data, use_test_cert1
        finally:
            conn.close()
    
    def generate_pdf(self, order_no: int, output_path: str | None = None):
        order_info, materials_data, use_test_cert1 = self.get_order_data(order_no)
        if order_info is None:
            _safe_log('warning', f"Order {order_no} not found in database!")
            return False, None

        empty_key_rows = self._count_empty_key_rows(materials_data)
        warning_message = None
        if empty_key_rows > 0:
            warning_message = (
                f"存在空数据：检测到 {empty_key_rows} 条材料记录的 "
                "Product/Grade/Pattern/Mill_Cert/Test_Cert1/Test_Cert2/"
                "Supplier/Stockist_Cert/PO_No/rm_dn_no 同时为空。"
            )
        
        # Get backend directory (directory where script is located)
        backend_dir = os.path.dirname(__file__)
        
        if output_path is None:
            del_date = order_info.get("Del_Date", datetime.now().strftime("%Y-%m-%d"))
            # Use absolute path, based on backend directory
            pdf_dir = os.path.join(backend_dir, "Generated_PDFs", del_date)
            os.makedirs(pdf_dir, exist_ok=True)
            output_path = os.path.join(pdf_dir, f"TR_{order_no}.pdf")
            # Output absolute path for debugging
            abs_output_path = os.path.abspath(output_path)
            _safe_log('debug', f"PDF output path (relative): {output_path}")
            _safe_log('debug', f"PDF output path (absolute): {abs_output_path}")
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
            # If target file exists, delete it first to ensure overwrite
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                    _safe_log('info', f"Deleted existing PDF file: {output_path}")
                except Exception as e:
                    _safe_log('warning', f"Failed to delete existing file, will continue: {e}")
            
            # Generate complete PDF
            html_doc = HTML(string=html_content, base_url=base_url)
            temp_output_path = output_path.replace('.pdf', '_temp.pdf')
            
            # If temporary file exists, delete it first
            if os.path.exists(temp_output_path):
                try:
                    os.remove(temp_output_path)
                except Exception as e:
                    print(f"[WARNING] Failed to delete existing temp file: {e}")
            
            html_doc.write_pdf(temp_output_path, stylesheets=[css])
            
            # If PyPDF2 is available, insert Header and Order Info on each page
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
                # Delete temporary file
                if os.path.exists(temp_output_path):
                    try:
                        os.remove(temp_output_path)
                    except Exception as e:
                        print(f"[WARNING] Failed to delete temp file: {e}")
            else:
                # If PyPDF2 is not available, use temporary file directly
                if os.path.exists(temp_output_path):
                    os.rename(temp_output_path, output_path)
            
            # Note: Now using CSS header-spacer to handle Header space on subsequent pages
            # No longer using PyPDF2 for page processing
            
            _safe_log('info', f"PDF generated successfully: {output_path}")
            _safe_log('debug', f"Order: {order_no}")
            _safe_log('debug', f"Client: {order_info_dict.get('Client', 'N/A')}")
            _safe_log('debug', f"Materials: {len(materials_data)} items")
            
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                _safe_log('debug', f"File verified: {output_path} ({file_size} bytes)")
                # Return relative path (relative to backend directory), for database storage and download API
                # This way download API can correctly find the file
                try:
                    rel_path = os.path.relpath(output_path, backend_dir)
                    # On Windows, use forward slash to ensure cross-platform compatibility
                    rel_path = rel_path.replace("\\", "/")
                    _safe_log('debug', f"Returning relative path for database: {rel_path}")
                    return True, rel_path, warning_message
                except ValueError:
                    # If cannot convert to relative path (e.g., on different drive), return absolute path
                    _safe_log('warning', f"Warning: Cannot convert to relative path, returning absolute path")
                    return True, output_path, warning_message
            else:
                _safe_log('warning', f"WARNING: File does not exist: {output_path}")
                return False, None
        except Exception as e:
            _safe_log('error', f"Error generating PDF: {e}")
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
        """Return list for rendering as block elements in template"""
        parts = self._split_value(value)
        if not parts:
            return []
        # Filter empty values and strip whitespace
        return [part.strip() for part in parts if part and part.strip()]
    
    def _format_multiline_cert(self, value: str):
        """Certificate field splitting: split only by newline, not by comma/slash, keep original format"""
        if value is None:
            return []
        text = str(value).replace("\r\n", "\n").replace("\r", "\n")
        # Split only by newline, not by comma/semicolon/slash, keep comma-separated format
        # This way "162952/22, 158736/22, 158973/22" will stay on one line
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

                # Choose to use Test_Cert1 or Test_Cert2 based on use_test_cert1
                if use_test_cert1:
                    test_cert_value = row.get("Test_Cert1")
                else:
                    test_cert_value = row.get("Test_Cert2")

                row_entry = {
                    "product": self._format_multiline(row.get("Product")),
                    "grade": "",  # filled after dedupe
                    "pattern": self._format_multiline(row.get("Pattern")),
                    # Certificate: split only by comma/newline, not by slash
                    "mill_cert": self._format_multiline_cert(row.get("Mill Cert")),
                    "test_cert": self._format_multiline_cert(test_cert_value),  # Use dedicated formatting method
                    "supplier": self._format_multiline(row.get("Supplier")),
                    "stockist": self._format_multiline(row.get("Stockist Cert")),
                    "po_no": self._format_multiline(row.get("PO_No(1)")),
                }
                rows.append(row_entry)

            deduped_grades = []
            for grade in grade_values:
                if grade and grade not in deduped_grades:
                    deduped_grades.append(grade)
            # Grade changed to return list for block element rendering
            if rows:
                rows[0]["grade"] = deduped_grades if deduped_grades else []

            # Dia and Wt also use list format, even if only one value
            dia_text = self._to_text(dia)
            dia_list = self._format_multiline(dia_text) if dia_text else []
            # If only one value, keep as list format for unified processing
            if not dia_list and dia_text:
                dia_list = [dia_text]
            
            grouped.append({
                "dia": dia_list,
                "wt_total": wt_value,  # Wt kept as single value, processed in template
                "rows": rows,
            })

        return grouped

    def _add_top_margin_to_subsequent_pages(self, input_pdf_path, output_pdf_path):
        """Add top margin before table on subsequent pages (to leave space for Header)"""
        try:
            # Read original PDF
            reader = PdfReader(input_pdf_path)
            writer = PdfWriter()
            
            # Height of Header and Order Info (points)
            # Approximately 200 points (2.8 inches)
            header_height = 200
            
            # Process each page
            for page_num, page in enumerate(reader.pages):
                if page_num == 0:
                    # First page: add directly (already contains Header)
                    writer.add_page(page)
            else:
                    # Subsequent pages: add blank margin at top of page
                    from PyPDF2.generic import Transformation, PageObject
                    
                    # Create transformation: move content down
                    transform = Transformation().translate(tx=0, ty=-header_height)
                    
                    # Apply transformation
                    page.add_transformation(transform)
                    
                    # Add page
                    writer.add_page(page)
            
            # Write to output file
            with open(output_pdf_path, 'wb') as output_file:
                writer.write(output_file)
                
        except Exception as e:
            print(f"Warning: Failed to add top margin to subsequent pages: {e}")
            print("Falling back to original PDF.")
            import traceback
            traceback.print_exc()
            # If failed, copy original file directly
            import shutil
            shutil.copy(input_pdf_path, output_pdf_path)
    
    def _add_page_number_to_page(self, page, page_text):
        """Add page number text on page (bottom right)"""
        try:
            # Try to use reportlab to create PDF with page numbers, then merge
            try:
                from reportlab.pdfgen import canvas
                from reportlab.lib.pagesizes import A4
                from reportlab.lib.units import mm
                import tempfile
                import io
                
                # Get page size
                page_width = float(page.mediabox.width)
                page_height = float(page.mediabox.height)
                
                # Create temporary PDF (contains page number text)
                temp_pdf = io.BytesIO()
                c = canvas.Canvas(temp_pdf, pagesize=(page_width, page_height))
                
                # Set font and size (consistent with @bottom-right in CSS)
                c.setFont("Helvetica-Bold", 9)
                
                # Page number position: bottom right (consistent with WeasyPrint @bottom-right position)
                # CSS margin: 8mm 6mm 22mm 6mm (top right bottom left)
                # A4 landscape: 842 x 595 points
                # Bottom margin 22mm = 22 * 2.83465 ≈ 62.36 points
                # Right margin 6mm = 6 * 2.83465 ≈ 17 points
                # WeasyPrint @bottom-right defaults to within bottom margin, right-aligned
                # Exact position: x = page_width - right_margin, y = bottom_margin
                right_margin_pt = 6 * 2.83465  # 6mm to points
                bottom_margin_pt = 11 * 2.83465  # 22mm to points
                
                x_position = page_width - right_margin_pt
                y_position = bottom_margin_pt
                
                # Draw page number (right-aligned, consistent with WeasyPrint)
                c.drawRightString(x_position, y_position, page_text)
                c.save()
                
                # Read temporary PDF
                temp_pdf.seek(0)
                page_reader = PdfReader(temp_pdf)
                page_number_page = page_reader.pages[0]
                
                # Merge page number page to target page
                page.merge_page(page_number_page)
                
                print(f"Debug: Added page number using reportlab: {page_text}")
                return True
                
            except ImportError:
                # reportlab not available, use content stream method
                print("Warning: reportlab not available, using content stream method")
                return self._add_page_number_via_content_stream(page, page_text)
                
        except Exception as e:
            print(f"Warning: Failed to add page number to page: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    #page number location
    def _add_page_number_via_content_stream(self, page, page_text):
        """Add page number via content stream (fallback method)"""
        try:
            # Get page size
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)
            
            # Page number position (consistent with WeasyPrint @bottom-right position)
            # CSS margin: 8mm 6mm 22mm 6mm (top right bottom left)
            right_margin_pt = 4 * 2.83465  # 6mm to points
            bottom_margin_pt = 10 * 2.83465  # 22mm to points (consistent with reportlab method)
            x_position = page_width - right_margin_pt
            y_position = bottom_margin_pt
            
            # Escape special characters (PDF text strings need to escape more characters)
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
            
            # Create text content stream
            # Use bold font /Helvetica-Bold (if defined in page resources)
            # Or use /F1 (need to ensure defined in page resources)
            font_size = 9
            # Estimate text width (Helvetica-Bold 9pt, approximately 5.4 points per character)
            # For right alignment, need to subtract text width from right boundary
            estimated_text_width = len(page_text) * 5.4
            x_aligned = x_position - estimated_text_width
            
            # Create text content stream (using bold font and bold)
            # Try to use /Helvetica-Bold, if not available use /F1 and add text rendering mode bold
            # Use text rendering mode Tr 2 (stroke+fill) to ensure text looks bolder
            text_content = f"""BT
/Helvetica-Bold {font_size} Tf
0.3 w
2 Tr
1 0 0 1 {x_aligned} {y_position} Tm
({escaped_text}) Tj
ET
"""
            
            # Get existing content stream
            # Merged page may have multiple content stream objects, need to process all content streams
            if '/Contents' in page:
                contents = page['/Contents']
                
                # Process content stream (may be single object or list)
                if isinstance(contents, list):
                    # If multiple content streams, add page number on last one (topmost)
                    if len(contents) > 0:
                        content_obj = contents[-1]
                        # If indirect reference, get actual object
                        if hasattr(content_obj, 'get_object'):
                            content_obj = content_obj.get_object()
                        
                        # pypdf ContentStream object uses .data attribute (not get_data method)
                        if content_obj:
                            try:
                                # pypdf ContentStream directly uses .data attribute
                                if hasattr(content_obj, 'data'):
                                    # pypdf style ContentStream
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
                                    # PyPDF2 style ContentStream
                                    original_data = content_obj.get_data()
                                    if isinstance(original_data, bytes):
                                        new_data = original_data + b'\n' + text_content.encode('utf-8')
                                        content_obj._data = new_data
                                        print(f"Debug: ✅ Added page number via content stream (list, using get_data): {page_text}")
                                        return True
                                
                                # If all above methods fail
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
                    # Single content stream object
                    content_obj = contents
                    original_type = type(content_obj)
                    
                    # Note: pypdf ContentStream object cannot call get_object(), it returns None
                    # Use ContentStream object directly, do not call get_object()
                    # ContentStream and EncodedStreamObject both have get_data method
                    
                    print(f"Debug: ContentStream type: {original_type}, skipping get_object()")
                    
                    # pypdf ContentStream/EncodedStreamObject need special handling
                    if content_obj:
                        try:
                            # According to tests, pypdf EncodedStreamObject has get_data method
                            # Prefer using get_data method (more standard)
                            if hasattr(content_obj, 'get_data'):
                                try:
                                    original_data = content_obj.get_data()
                                    if isinstance(original_data, bytes):
                                        new_data = original_data + b'\n' + text_content.encode('utf-8')
                                        # Set data: try different methods
                                        if hasattr(content_obj, '_data'):
                                            content_obj._data = new_data
                                        elif hasattr(content_obj, 'data'):
                                            content_obj.data = new_data
                                        print(f"Debug: ✅ Added page number via content stream (single, using get_data): {page_text}")
                                        print(f"Debug: Content stream size: {len(new_data)} bytes (original: {len(original_data)} bytes)")
                                        return True
                                except Exception as get_data_error:
                                    print(f"Debug: get_data() failed: {get_data_error}, trying other methods...")
                            
                            # Fallback method 1: directly access data attribute
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
                            
                            # Fallback method 2: directly access _data attribute
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
                            
                            # If all above methods fail
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
        """Insert Header and Order Info at top of each page, and move table content down"""
        try:
            # If output file exists, delete it first to ensure overwrite
            if os.path.exists(output_pdf_path):
                try:
                    os.remove(output_pdf_path)
                    print(f"[INFO] Deleted existing output file: {output_pdf_path}")
                except Exception as e:
                    print(f"[WARNING] Failed to delete existing output file, will continue to try overwrite: {e}")
            
            # Read original PDF
            reader = PdfReader(input_pdf_path)
            writer = PdfWriter()
            
            # Generate PDF containing only Header and Order Info
            header_template = self.jinja_env.get_template("tr_report_header_only.html")
            header_html = header_template.render(
                order_info=order_info_dict,
                logo_exists=logo_exists,
                logo_path=logo_rel_path,
                signature_exists=signature_exists,
                signature_path=signature_rel_path,
                use_test_cert1=use_test_cert1,
            )
            
            # Create temporary file to store Header PDF
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_header_file:
                temp_header_path = temp_header_file.name
            
            # Use separate CSS for Header (does not contain page numbers)
            header_css_path = os.path.join(os.path.dirname(__file__), "templates", "tr_report_header_only.css")
            if os.path.exists(header_css_path):
                header_css = CSS(filename=header_css_path)
            else:
                # If separate CSS does not exist, use original CSS (but will contain page numbers)
                header_css = css
                print(f"Warning: tr_report_header_only.css not found, using tr_report.css (may include page numbers)")
            
            header_doc = HTML(string=header_html, base_url=base_url)
            header_doc.write_pdf(temp_header_path, stylesheets=[header_css])
            
            # Read Header PDF
            header_reader = PdfReader(temp_header_path)
            header_page = header_reader.pages[0]
            
            # Calculate actual height of Header and Order Info
            # Get actual content height from Header PDF
            # A4 landscape: 842 x 595 points (width x height), 1 inch = 72 points
            # PDF coordinate system: origin at bottom left, Y upward (0=bottom, 595=top)
            
            # Estimate Header actual height based on CSS:
            # - Logo: 0.7in (50 points)
            # - Header margin-bottom: 0.5in (36 points)
            # - Order Info Section: margin-top: -0.4in, margin-bottom: 0.2in, actual content about 1.2in (86 points)
            # - Safety margin: additional 20-40 points
            # Total approximately: 192-232 points (about 2.7-3.2 inches)
            
            # Note: This value is the distance to move content down, ensuring content starts below Header
            # If need to adjust second page content position (to avoid overlap with Header), modify this value:
            # - Increase value = content moves down more (greater distance from Header, will not overlap)
            # - Decrease value = content moves up (smaller distance from Header, may overlap)
            # Recommended range: 150-280 points (about 2.1-3.9 inches)
            
            # Default to larger value to ensure no overlap
            # If you find second page content still overlaps with Header, try larger values (like 250, 280, 300)
            header_content_height = 116  # Default value, about 3.5 inches (increase to 250 to better avoid overlap)
            
            try:
                # Get Header page mediabox
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
            
            # Get total page count (for updating page numbers)
            total_pages = len(reader.pages)
            print(f"Debug: Total pages in original PDF: {total_pages}")
            
            # If only one page, temporary PDF already contains Header, use directly (no page number added, because WeasyPrint already added it)
            if total_pages == 1:
                print(f"Debug: Single page PDF detected - using original page directly (WeasyPrint already added page number)")
                page = reader.pages[0]
                # Add original page directly, no modifications
                writer.add_page(page)
                print(f"Debug: Added original page directly without modification")
            else:
                # Multi-page case: process each page
                for page_num, page in enumerate(reader.pages):
                    if page_num == 0:
                        # First page: add original page first to ensure content displays, page number temporarily not added
                        # Because modifying page object causes content loss, we temporarily keep first page without page number
                        # Or use CSS to re-enable first page page number
                        print(f"Debug: Page 1 - adding original page directly (page number will be added via CSS or skipped)")
                        
                        # Add original page directly, no modifications (ensure content displays normally)
                        writer.add_page(page)
                        print(f"Debug: Added page 1 directly without modification (content preserved)")
                        
                        # Note: First page page number temporarily not added via code, because modifying page object causes content loss
                        # If need first page to display page number, can consider:
                        # 1. Re-enable @bottom-right in CSS (but will be overridden by second page processing)
                        # 2. Or accept first page has no page number (second page has page number)
                        print(f"Debug: ⚠️ Page 1 page number not added to avoid content loss")
                    else:
                        # Subsequent pages: use pypdf concise method
                        try:
                            import copy
                            import re
                        
                            if USE_PYPDF and Transformation is not None:
                                # Use pypdf method (recommended)
                                # PDF coordinate system: origin at bottom left, Y axis upward (0=bottom, 595=top)
                                # To move content down, need to use negative ty value: translate(tx=0, ty=-value)
                                # This means content will move down, leaving top space for Header
                                
                                # 1. Create new page: first copy header_page (contains Header, stays at top)
                                new_page = copy.deepcopy(header_page)
                                
                                # 2. Create copy of content page and apply transformation (move content down, leave space for Header)
                                content_page = copy.deepcopy(page)
                                # ⚠️ Important: ty=-header_content_height will move entire page content down, including:
                                # - Main content (tables, etc.)
                                # - Bottom page number (added by WeasyPrint CSS @bottom-right)
                                # - Bottom certification text (added by WeasyPrint CSS @bottom-left)
                                # After moving down, bottom page number and certification text will be moved out of page bottom, invisible
                                # So we must re-add page number at correct position after merging
                                transform = Transformation().translate(tx=0, ty=-header_content_height)
                                content_page.add_transformation(transform)
                                
                                print(f"Debug: Page {page_num + 1}: Applying transformation translate(tx=0, ty=-{header_content_height})")
                                print(f"Debug: This moves ALL content DOWN by {header_content_height} points ({header_content_height/72:.2f} inches)")
                                print(f"Debug: ⚠️ Original page number will be moved out of view - will re-add after merge")
                                
                                # 3. Merge moved-down content to Header page
                                # merge_page will overlay content_page onto new_page
                                # Because content_page has been moved down, its content will be below Header
                                # Note: Original page number has been moved down, invisible now
                                new_page.merge_page(content_page)
                                
                                print(f"Debug: Applied pypdf transformation to page {page_num + 1} (header_height={header_content_height})")
                                print(f"Debug: Shifted content down by {header_content_height} points, then merged with header (header stays at top)")
                                
                                # 4. Add page number to correct position on merged page (bottom right)
                                # Because transformation moved entire page content down (including original page number), page number is now invisible
                                # We need to re-add page number to page bottom on merged new page
                                current_page_num = page_num + 1
                                page_text = f"Page {current_page_num}/{total_pages}"
                                print(f"Debug: Re-adding page number '{page_text}' to merged page {page_num + 1} (original was moved down)")
                                
                                # Try multiple methods to add page number, ensure at least one method succeeds
                                page_number_added = False
                                
                                # Method 1: Use primary method (reportlab or content stream)
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
                                
                                # Method 2: If primary method fails, directly use content stream method
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
                                        
                                        # Try to directly access ContentStream (do not call get_object(), because it returns None)
                                        if not isinstance(contents, list):
                                            print(f"Debug: Contents is ContentStream, trying direct access (without get_object)...")
                                            try:
                                                # For ContentStream type, use directly, do not call get_object()
                                                if hasattr(contents, 'get_data'):
                                                    print(f"Debug: ContentStream has get_data method, attempting to add page number directly...")
                                                    try:
                                                        original_data = contents.get_data()
                                                        if isinstance(original_data, bytes):
                                                            # Generate PDF content stream for page number text (consistent with logic in _add_page_number_via_content_stream)
                                                            page_width = float(new_page.mediabox.width)
                                                            right_margin_pt = 4 * 2.83465
                                                            bottom_margin_pt = 10 * 2.83465
                                                            x_position = page_width - right_margin_pt
                                                            y_position = bottom_margin_pt
                                                            
                                                            # Escape page number text
                                                            escaped_text = (page_text
                                                                          .replace('\\', '\\\\')
                                                                          .replace('(', '\\(')
                                                                          .replace(')', '\\)')
                                                                          .replace('/', '\\/'))
                                                            
                                                            font_size = 9
                                                            estimated_text_width = len(page_text) * 5.4
                                                            x_aligned = x_position - estimated_text_width
                                                            
                                                            # Generate PDF content stream for page number text (using bold and bold)
                                                            # Use /Helvetica-Bold and add text rendering mode to ensure bold effect
                                                            # 0.3 w sets line width, 2 Tr uses stroke+fill mode
                                                            text_content_pdf = f"""BT
/Helvetica-Bold {font_size} Tf
0.3 w
2 Tr
1 0 0 1 {x_aligned} {y_position} Tm
({escaped_text}) Tj
ET
"""
                                                            
                                                            new_data = original_data + b'\n' + text_content_pdf.encode('utf-8')
                                                            # Set data to ContentStream
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
                                # Whether page number was added successfully or not, transformation has been applied, continue processing
                            else:
                                # Fallback to PyPDF2 old method
                                # Create new page: first copy header_page (contains Header)
                                new_page = copy.deepcopy(header_page)
                                
                                # Create copy of content page
                                content_page = copy.deepcopy(page)
                                
                                # Directly modify content stream, add transformation matrix before content
                                transform_cmd = f"1 0 0 1 0 -{header_content_height} cm\n"
                                
                                # Modify content page content stream
                                if '/Contents' in content_page:
                                    contents = content_page['/Contents']
                                    
                                    def wrap_content_stream(original_data):
                                        """Wrap content stream with q/Q to ensure transformation takes effect"""
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
                                
                                # Merge content page (already moved down)
                                new_page.merge_page(content_page)
                                print(f"Debug: Merged content page to new page {page_num + 1} (PyPDF2 fallback)")
                                
                                # Add page number
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
                            # Fallback: apply transformation even if error occurs (to avoid overlap)
                            try:
                                import copy
                                # Still apply transformation to avoid content overlapping with Header
                                new_page = copy.deepcopy(header_page)
                                content_page_fallback = copy.deepcopy(page)
                                
                                # Try to apply transformation (even using PyPDF2 fallback method)
                                if USE_PYPDF and Transformation is not None:
                                    transform_fallback = Transformation().translate(tx=0, ty=-header_content_height)
                                    content_page_fallback.add_transformation(transform_fallback)
                                    print(f"Debug: Fallback: Applied transformation to page {page_num + 1} (header_height={header_content_height})")
                                
                                new_page.merge_page(content_page_fallback)
                                
                                # Fallback method also needs to add page number
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
                                # Final fallback: at least add original page (but will have overlap)
                                writer.add_page(page)
                                print(f"Warning: Using original page without transformation - content may overlap with header")
            
            # Write to output file
            with open(output_pdf_path, 'wb') as output_file:
                writer.write(output_file)
            
            # Clean up temporary files
            if os.path.exists(temp_header_path):
                os.remove(temp_header_path)
                
        except Exception as e:
            _safe_log('warning', f"Warning: Failed to add header to all pages: {e}")
            _safe_log('warning', "Falling back to original PDF without header insertion.")
            import traceback
            try:
                _safe_log('error', traceback.format_exc())
            except:
                pass
            # If failed, copy original file directly
            import shutil
            shutil.copy(input_pdf_path, output_pdf_path)


def generate_landscape_pdf():
    print("=== Order Traceability PDF Generator (WeasyPrint) ===")
    db_path = r"C:\YYH\TR REPORT\TR database\data_3years.db"
    generator = OrderTraceabilityPDFGenerator(db_path)
    
    sample_order = 126831
    print(f"Generating landscape PDF for Order: {sample_order}")
    
    result = generator.generate_pdf(sample_order)
    success, pdf_path = result[0], result[1]
    if success:
        print("Landscape PDF generated successfully!")
        print(f"PDF saved to: {pdf_path}")
    else:
        print("Failed to generate PDF.")


if __name__ == "__main__":
    generate_landscape_pdf()
