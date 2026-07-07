#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TR Database Tables Auto Update Script (PostgreSQL)
Function: Update bbs_dd, cert_of_compliance, TR_Report and TR_Report_Deduplication tables
Author: TR Report System
Date: 2026-03-12
"""

import sys
import os
import io
import subprocess
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Set UTF-8 encoding environment variable (fix display issues on Windows)
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Add backend directory to path for db_adapter import
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(script_dir, '..', 'TR UI', 'backend')
backend_dir = os.path.normpath(backend_dir)
sys.path.insert(0, backend_dir)

# ==================== Configuration Section ====================
# PostgreSQL Configuration
POSTGRES_DSN = os.getenv('POSTGRES_DSN', 'postgresql://postgres:postgres@127.0.0.1:5432/tr_db')
DB_BACKEND = os.getenv('DB_BACKEND', 'postgres')

# Email Configuration (optional, leave empty if email notification is not needed)
EMAIL_CONFIG = {
    'smtp_server': 'corpmail1.netvigator.com',
    'smtp_port': 25,
    'username': 'tr@hkshalliance.com',  # Leave empty to disable email
    'password': '',
    'to_email': 'henry.yu@hkshalliance.com,yuyuhang1991@163.com'
}
# ==================== End of Configuration ====================

# Setup Logging
def setup_logging():
    """Setup logging configuration"""
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_filename = os.path.join(log_dir, f'update_tr_tables_postgres_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)

def get_table_count(table_name):
    """Get record count from a table"""
    conn = None
    try:
        # Set environment variables before importing db_adapter
        os.environ['DB_BACKEND'] = DB_BACKEND
        os.environ['POSTGRES_DSN'] = POSTGRES_DSN
        
        from db_adapter import get_connection, is_postgres
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Handle PostgreSQL case-sensitive table names
        if is_postgres():
            # PostgreSQL: use quoted table name for case-sensitive names
            quoted_table = f'"{table_name}"' if table_name in [
                'TR_Report', 'TR_Report_Deduplication', 'bbs_dd', 'file_index_cache'
            ] else table_name
            cursor.execute(f'SELECT COUNT(*) as cnt FROM {quoted_table}')
        else:
            cursor.execute(f'SELECT COUNT(*) as cnt FROM {table_name}')
        
        row = cursor.fetchone()
        
        # Handle both dict and tuple row formats
        if row is None:
            if logger:
                logger.warning(f"[WARNING] No result returned for table {table_name}")
            if conn:
                conn.close()
            return None
        
        # PostgreSQL uses dict_row, SQLite uses Row (dict-like)
        count = None
        if isinstance(row, dict):
            # Direct dict access
            count = row.get('cnt') or row.get('count') or row.get('COUNT(*)')
        elif hasattr(row, 'keys'):
            # Row-like object (SQLite)
            count = row.get('cnt') or row.get('count') or row.get('COUNT(*)')
            if count is None and len(row) > 0:
                # Get first value if no key matches
                try:
                    count = list(row.values())[0] if hasattr(row, 'values') else row[list(row.keys())[0]]
                except:
                    count = row[0] if hasattr(row, '__getitem__') else None
        elif hasattr(row, '__getitem__'):
            # Tuple-like access
            count = row[0]
        else:
            count = row
        
        if conn:
            conn.close()
        
        # Convert to int
        if count is not None:
            try:
                count_int = int(count)
                if logger:
                    logger.info(f"[INFO] Table {table_name} count: {count_int:,}")
                return count_int
            except (ValueError, TypeError) as e:
                if logger:
                    logger.warning(f"[WARNING] Failed to convert count to int for table {table_name}: {count} (type: {type(count)}), error: {e}")
                return None
        else:
            if logger:
                logger.warning(f"[WARNING] Count is None for table {table_name}, row: {row}")
            return None
            
    except Exception as e:
        if logger:
            logger.warning(f"[WARNING] Failed to get count for table {table_name}: {type(e).__name__}: {e}")
            import traceback
            logger.debug(f"[DEBUG] Traceback: {traceback.format_exc()}")
        if conn:
            try:
                conn.close()
            except:
                pass
        return None

def send_notification(success, message, update_results, logger_instance=None):
    """Send notification email (optional)
    Supports multiple recipients: Use comma to separate multiple email addresses in to_email
    Example: 'email1@company.com,email2@company.com' or ['email1@company.com', 'email2@company.com']
    """
    if logger_instance is None:
        logger_instance = logger
    
    if not EMAIL_CONFIG['username'] or EMAIL_CONFIG['username'] == '':
        return
    
    # Handle multiple recipients
    to_email = EMAIL_CONFIG['to_email']
    if isinstance(to_email, str):
        # If string, split by comma and strip spaces
        recipients = [email.strip() for email in to_email.split(',') if email.strip()]
    elif isinstance(to_email, list):
        # If list, use directly
        recipients = [email.strip() for email in to_email if email.strip()]
    else:
        if logger_instance:
            logger_instance.error("[ERROR] to_email configuration format error, should be string or list")
        return
    
    if not recipients:
        if logger_instance:
            logger_instance.warning("[WARNING] No valid recipient email addresses")
        return
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['username']
        # Multiple recipients separated by comma in email header
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = f"TR Database Auto Update {'Success' if success else 'Failed'}"
        
        # Format update results with count information
        results_lines = []
        for k, v in update_results.items():
            if isinstance(v, dict):
                # Format: "Table: status (count records)" or "Table: status"
                status = v.get('status', 'Unknown')
                count = v.get('count')
                # Special handling for file_index_cache
                if k == 'file_index_cache' and 'files_checked' in v:
                    files_checked = v.get('files_checked', 0)
                    if count is not None:
                        results_lines.append(f"- {k}: {status} ({count:,} total records, checked {files_checked:,} files)")
                    else:
                        results_lines.append(f"- {k}: {status} (checked {files_checked:,} files)")
                elif count is not None:
                    results_lines.append(f"- {k}: {status} ({count:,} records)")
                else:
                    results_lines.append(f"- {k}: {status}")
            else:
                # Simple string format (backward compatibility)
                results_lines.append(f"- {k}: {v}")
        
        body = f"""
TR Database Auto Update Report
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Status: {'Success' if success else 'Failed'}
Details: {message}

Update Results:
{chr(10).join(results_lines)}
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        # Try to login (if server supports authentication)
        # If authentication is not supported, skip login and send directly (for internal anonymous SMTP servers)
        try:
            if EMAIL_CONFIG.get('password') and EMAIL_CONFIG['password'] != '':
                server.login(EMAIL_CONFIG['username'], EMAIL_CONFIG['password'])
        except smtplib.SMTPAuthenticationError:
            # If authentication fails, try anonymous send (some internal servers allow)
            if logger_instance:
                logger_instance.warning("[WARNING] SMTP authentication failed, trying anonymous send...")
        except smtplib.SMTPException as e:
            # If server does not support authentication, skip login
            if 'not supported' in str(e).lower() or 'AUTH' in str(e):
                if logger_instance:
                    logger_instance.info("Server does not support SMTP authentication, using anonymous send...")
            else:
                raise
        
        # Send to all recipients
        server.send_message(msg, to_addrs=recipients)
        server.quit()
        
        if logger_instance:
            logger_instance.info(f"[OK] Notification email sent successfully, sent to {len(recipients)} recipients: {', '.join(recipients)}")
    except Exception as e:
        if logger_instance:
            logger_instance.error(f"[ERROR] Failed to send notification email: {e}")

def run_script(script_name, description):
    """Run a Python script and return success status"""
    # Python scripts are in TR UI\backend directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(script_dir, '..', 'TR UI', 'backend')
    backend_dir = os.path.normpath(backend_dir)
    script_path = os.path.join(backend_dir, script_name)
    
    if not os.path.exists(script_path):
        logger.error(f"[ERROR] Script not found: {script_path}")
        return False
    
    logger.info(f"[INFO] Running {description}...")
    logger.info(f"[INFO] Script: {script_path}")
    
    try:
        # Set environment variables for PostgreSQL
        env = os.environ.copy()
        env['DB_BACKEND'] = DB_BACKEND
        env['POSTGRES_DSN'] = POSTGRES_DSN
        env['PYTHONIOENCODING'] = 'utf-8'
        
        # Run the script from backend directory
        result = subprocess.run(
            [sys.executable, script_path],
            env=env,
            cwd=backend_dir,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        # Log output
        if result.stdout:
            logger.info(f"[OUTPUT] {description} output:")
            for line in result.stdout.strip().split('\n'):
                logger.info(f"  {line}")
        
        if result.stderr:
            logger.warning(f"[WARNING] {description} warnings/errors:")
            for line in result.stderr.strip().split('\n'):
                logger.warning(f"  {line}")
        
        if result.returncode == 0:
            logger.info(f"[SUCCESS] {description} completed successfully")
            return True
        else:
            logger.error(f"[ERROR] {description} failed with exit code: {result.returncode}")
            return False
            
    except Exception as e:
        logger.error(f"[ERROR] Failed to run {description}: {e}")
        import traceback
        logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
        return False

# Initialize logger as module-level variable
logger = None

def update_file_index():
    """Update file index cache"""
    try:
        logger.info("=" * 60)
        logger.info("Step: Update file index cache")
        logger.info("=" * 60)
        
        # Try to import file index updater
        try:
            # Add backend directory to path
            script_dir = os.path.dirname(os.path.abspath(__file__))
            backend_dir = os.path.join(script_dir, '..', 'TR UI', 'backend')
            backend_dir = os.path.normpath(backend_dir)
            sys.path.insert(0, backend_dir)
            
            from file_index_updater import FileIndexUpdater
        except ImportError as e:
            logger.warning(f"[WARNING] Cannot import file index updater: {e}")
            logger.warning("Skipping file index update")
            return {'status': 'skipped', 'reason': 'Module import failed'}
        
        # Get base folder path (from environment variable or use default)
        base_folder = os.getenv('STOCKIST_TEST_FOLDER', r'D:\Stockist&Test Report')
        
        # Check if folder exists
        if not os.path.exists(base_folder):
            logger.warning(f"[WARNING] Folder does not exist: {base_folder}")
            logger.warning("Skipping file index update")
            return {'status': 'skipped', 'reason': f'Folder does not exist: {base_folder}'}
        
        # Set environment variables for PostgreSQL (FileIndexUpdater uses db_adapter which respects these)
        os.environ['DB_BACKEND'] = DB_BACKEND
        os.environ['POSTGRES_DSN'] = POSTGRES_DSN
        
        # Create updater (db_path is not needed for PostgreSQL, but pass empty string for compatibility)
        # FileIndexUpdater uses db_adapter.get_connection() which respects DB_BACKEND env var
        updater = FileIndexUpdater('', base_folder)
        result = updater.update_index()
        
        if result.get('success'):
            stats = {
                'files_added': result.get('files_added', 0),
                'files_updated': result.get('files_updated', 0),
                'files_deleted': result.get('files_deleted', 0),
                'files_checked': result.get('files_checked', 0)
            }
            logger.info("[SUCCESS] File index cache update successful")
            logger.info(f"  Added: {stats['files_added']}, Updated: {stats['files_updated']}, Deleted: {stats['files_deleted']}, Checked: {stats['files_checked']}")
            return {'status': 'success', 'stats': stats}
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"[ERROR] File index cache update failed: {error_msg}")
            return {'status': 'failed', 'error': error_msg}
        
    except Exception as e:
        logger.error(f"[ERROR] File index update exception: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'status': 'failed', 'error': str(e)}

def main():
    """Main function"""
    global logger
    logger = setup_logging()
    
    logger.info("=" * 50)
    logger.info("TR Database Tables Update Started")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)
    logger.info(f"[INFO] PostgreSQL DSN: {POSTGRES_DSN}")
    logger.info(f"[INFO] Database Backend: {DB_BACKEND}")
    logger.info("")
    
    # Initialize update results
    update_results = {}
    update_success = True
    error_message = ""
    
    # Step 1: Update bbs_dd table
    logger.info("[Step 1/5] Updating bbs_dd table...")
    if run_script('generate_bbs_dd_3years.py', 'bbs_dd table update'):
        count = get_table_count('bbs_dd')
        if count is not None:
            update_results['bbs_dd'] = {'status': 'Updated', 'count': count}
            logger.info(f"[SUCCESS] bbs_dd table update completed ({count:,} records)")
        else:
            update_results['bbs_dd'] = {'status': 'Updated', 'count': None}
            logger.info("[SUCCESS] bbs_dd table update completed")
    else:
        update_results['bbs_dd'] = {'status': 'Failed', 'count': None}
        update_success = False
        error_message = "bbs_dd table update failed"
        logger.error("[ERROR] bbs_dd table update failed!")
    
    logger.info("")

    # Step 2: Update cert_of_compliance table
    logger.info("[Step 2/5] Updating cert_of_compliance table...")
    if run_script('generate_cert_of_compliance_3years.py', 'cert_of_compliance table update'):
        count = get_table_count('cert_of_compliance')
        if count is not None:
            update_results['cert_of_compliance'] = {'status': 'Updated', 'count': count}
            logger.info(f"[SUCCESS] cert_of_compliance table update completed ({count:,} records)")
        else:
            update_results['cert_of_compliance'] = {'status': 'Updated', 'count': None}
            logger.info("[SUCCESS] cert_of_compliance table update completed")
    else:
        update_results['cert_of_compliance'] = {'status': 'Failed', 'count': None}
        update_success = False
        if not error_message:
            error_message = "cert_of_compliance table update failed"
        logger.error("[ERROR] cert_of_compliance table update failed!")

    logger.info("")
    
    # Step 3: Update TR_Report table
    logger.info("[Step 3/5] Updating TR_Report table...")
    if run_script('generate_tr_report_3years.py', 'TR_Report table update'):
        count = get_table_count('TR_Report')
        if count is not None:
            update_results['TR_Report'] = {'status': 'Updated', 'count': count}
            logger.info(f"[SUCCESS] TR_Report table update completed ({count:,} records)")
        else:
            update_results['TR_Report'] = {'status': 'Updated', 'count': None}
            logger.info("[SUCCESS] TR_Report table update completed")
    else:
        update_results['TR_Report'] = {'status': 'Failed', 'count': None}
        update_success = False
        if not error_message:
            error_message = "TR_Report table update failed"
        logger.error("[ERROR] TR_Report table update failed!")
    
    logger.info("")
    
    # Step 4: Update TR_Report_Deduplication table
    logger.info("[Step 4/5] Updating TR_Report_Deduplication table...")
    if run_script('update_tr_report_deduplication.py', 'TR_Report_Deduplication table update'):
        count = get_table_count('TR_Report_Deduplication')
        if count is not None:
            update_results['TR_Report_Deduplication'] = {'status': 'Updated', 'count': count}
            logger.info(f"[SUCCESS] TR_Report_Deduplication table update completed ({count:,} records)")
        else:
            update_results['TR_Report_Deduplication'] = {'status': 'Updated', 'count': None}
            logger.info("[SUCCESS] TR_Report_Deduplication table update completed")
    else:
        update_results['TR_Report_Deduplication'] = {'status': 'Failed', 'count': None}
        update_success = False
        if not error_message:
            error_message = "TR_Report_Deduplication table update failed"
        logger.error("[ERROR] TR_Report_Deduplication table update failed!")
    
    logger.info("")
    
    # Step 5: Update file_index_cache table
    logger.info("[Step 5/5] Updating file_index_cache table...")
    file_index_result = update_file_index()
    if file_index_result.get('status') == 'success':
        stats = file_index_result.get('stats', {})
        files_checked = stats.get('files_checked', 0)
        # Get total count from database
        count = get_table_count('file_index_cache')
        if count is not None:
            update_results['file_index_cache'] = {'status': 'Updated', 'count': count, 'files_checked': files_checked}
            logger.info(f"[SUCCESS] file_index_cache table update completed ({count:,} total records, checked {files_checked:,} files)")
        else:
            update_results['file_index_cache'] = {'status': 'Updated', 'count': None, 'files_checked': files_checked}
            logger.info(f"[SUCCESS] file_index_cache table update completed (checked {files_checked:,} files)")
    elif file_index_result.get('status') == 'skipped':
        update_results['file_index_cache'] = {'status': 'Skipped', 'count': None, 'reason': file_index_result.get('reason', 'Unknown reason')}
        logger.info(f"[INFO] file_index_cache table update skipped: {file_index_result.get('reason', 'Unknown reason')}")
    else:
        update_results['file_index_cache'] = {'status': 'Failed', 'count': None, 'error': file_index_result.get('error', 'Unknown error')}
        # Don't mark overall update as failed for file_index_cache errors (non-critical)
        logger.warning(f"[WARNING] file_index_cache table update failed: {file_index_result.get('error', 'Unknown error')}")
    
    logger.info("")
    logger.info("=" * 50)
    logger.info("TR Database Tables Update Completed")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)
    
    # Send notification email
    if update_success:
        message = (
            "bbs_dd, cert_of_compliance, TR_Report, TR_Report_Deduplication "
            "and file_index_cache tables updated successfully"
        )
    else:
        message = error_message
    
    send_notification(update_success, message, update_results, logger)
    
    # Exit with appropriate code
    if update_success:
        logger.info("")
        logger.info("Update completed successfully!")
        return 0
    else:
        logger.error("")
        logger.error("Update failed! Please check error messages!")
        return 1

if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        if logger:
            logger.error("[ERROR] Script interrupted by user")
        else:
            print("[ERROR] Script interrupted by user")
        sys.exit(1)
    except Exception as e:
        if logger:
            logger.error(f"[ERROR] Unexpected error: {e}")
            import traceback
            logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
        else:
            print(f"[ERROR] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
        sys.exit(1)
