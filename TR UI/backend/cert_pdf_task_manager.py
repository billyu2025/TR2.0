#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Async PDF generation tasks for Certificate of Compliance (shipping_no PK)."""

import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional

from db_adapter import get_connection as get_db_connection, is_postgres
from logger_config import get_logger

logger = get_logger('cert_pdf')


class CertPDFTaskManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self):
        return get_db_connection()

    def _sql(self, sql_text: str) -> str:
        if is_postgres():
            return sql_text.replace('?', '%s')
        return sql_text

    def _execute(self, cursor, sql_text: str, params=()):
        return cursor.execute(self._sql(sql_text), params)

    def _status_table(self) -> str:
        return '"Cert_PDF_Status"' if is_postgres() else 'Cert_PDF_Status'

    def _upsert_pdf_status(
        self,
        cursor,
        shipping_no: int,
        pdf_status: str,
        pdf_path: Optional[str] = None,
        generated: bool = False,
    ):
        table_name = self._status_table()
        if is_postgres():
            if generated:
                self._execute(
                    cursor,
                    f"""
                    INSERT INTO {table_name} (shipping_no, pdf_status, pdf_path, generated_at, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (shipping_no) DO UPDATE SET
                        pdf_status = EXCLUDED.pdf_status,
                        pdf_path = EXCLUDED.pdf_path,
                        generated_at = EXCLUDED.generated_at,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (shipping_no, pdf_status, pdf_path),
                )
            else:
                self._execute(
                    cursor,
                    f"""
                    INSERT INTO {table_name} (shipping_no, pdf_status, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT (shipping_no) DO UPDATE SET
                        pdf_status = EXCLUDED.pdf_status,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (shipping_no, pdf_status),
                )
            return
        if generated:
            self._execute(
                cursor,
                f"""
                INSERT OR REPLACE INTO {table_name}
                (shipping_no, pdf_status, pdf_path, generated_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (shipping_no, pdf_status, pdf_path),
            )
        else:
            self._execute(
                cursor,
                f"""
                INSERT OR REPLACE INTO {table_name}
                (shipping_no, pdf_status, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (shipping_no, pdf_status),
            )

    def create_task(self, user_id: int, shipping_no: int) -> str:
        task_id = str(uuid.uuid4())
        expires_at = (datetime.now() + timedelta(days=1)).isoformat()
        conn = self._get_connection()
        cursor = conn.cursor()
        self._execute(
            cursor,
            """
            INSERT INTO cert_pdf_tasks
            (task_id, user_id, shipping_no, status, progress, expires_at, created_at)
            VALUES (?, ?, ?, 'pending', 0, ?, CURRENT_TIMESTAMP)
            """,
            (task_id, user_id, shipping_no, expires_at),
        )
        conn.commit()
        conn.close()
        logger.info(f"Created cert PDF task: task_id={task_id}, shipping_no={shipping_no}")
        return task_id

    def get_task_status(self, task_id: str, user_id: int) -> Optional[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        self._execute(
            cursor,
            'SELECT * FROM cert_pdf_tasks WHERE task_id = ? AND user_id = ?',
            (task_id, user_id),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_progress(self, task_id: str, progress: int, message: str = None):
        conn = self._get_connection()
        cursor = conn.cursor()
        if message:
            self._execute(
                cursor,
                'UPDATE cert_pdf_tasks SET progress = ?, message = ? WHERE task_id = ?',
                (progress, message, task_id),
            )
        else:
            self._execute(
                cursor,
                'UPDATE cert_pdf_tasks SET progress = ? WHERE task_id = ?',
                (progress, task_id),
            )
        conn.commit()
        conn.close()

    def update_status(self, task_id: str, status: str, **kwargs):
        conn = self._get_connection()
        cursor = conn.cursor()
        updates = ['status = ?']
        params = [status]
        if status == 'processing' and 'started_at' not in kwargs:
            kwargs['started_at'] = datetime.now().isoformat()
        if status == 'completed' and 'completed_at' not in kwargs:
            kwargs['completed_at'] = datetime.now().isoformat()
        for key, value in kwargs.items():
            if key in ('pdf_path', 'error_message', 'started_at', 'completed_at', 'progress', 'message'):
                updates.append(f'{key} = ?')
                params.append(value)
        params.append(task_id)
        self._execute(
            cursor,
            f"UPDATE cert_pdf_tasks SET {', '.join(updates)} WHERE task_id = ?",
            params,
        )
        conn.commit()
        conn.close()

    def process_task(self, task_id: str, shipping_no: int):
        try:
            logger.info(f"Processing cert PDF task: {task_id}, shipping_no={shipping_no}")
            self.update_status(task_id, 'processing', started_at=datetime.now().isoformat())
            self.update_progress(task_id, 10, 'Initializing cert PDF generator...')

            backend_dir = os.path.dirname(os.path.abspath(__file__))
            if backend_dir not in sys.path:
                sys.path.insert(0, backend_dir)

            try:
                import weasyprint  # noqa: F401
            except ImportError as weasy_err:
                raise ImportError(f'WeasyPrint not available: {weasy_err}') from weasy_err

            from generate_cert_compliance_pdf import CertCompliancePDFGenerator

            self.update_progress(task_id, 30, 'Generating certificate PDF...')
            generator = CertCompliancePDFGenerator()
            result = generator.generate_pdf(int(shipping_no))

            warning_message = None
            if isinstance(result, tuple):
                if len(result) >= 3:
                    success, pdf_path, warning_message = result[0], result[1], result[2]
                else:
                    success, pdf_path = result[0], result[1]
            else:
                success, pdf_path = bool(result), None

            import importlib
            tr_api = importlib.import_module('tr_fill_in_api')
            get_db_connection = tr_api.get_db_connection
            cache = getattr(tr_api, 'cache', None)

            if success and pdf_path:
                conn = get_db_connection()
                cursor = conn.cursor()
                try:
                    self._upsert_pdf_status(
                        cursor, shipping_no, 'generated', pdf_path, generated=True
                    )
                    conn.commit()
                    if cache:
                        try:
                            cache.delete('cert:list:*')
                        except Exception:
                            pass
                finally:
                    conn.close()

                msg = warning_message or 'Certificate PDF generated successfully'
                self.update_status(
                    task_id,
                    'completed',
                    pdf_path=pdf_path,
                    completed_at=datetime.now().isoformat(),
                    progress=100,
                    message=msg,
                )
                logger.info(f"Cert PDF completed: shipping_no={shipping_no}, path={pdf_path}")
            else:
                conn = get_db_connection()
                cursor = conn.cursor()
                try:
                    self._upsert_pdf_status(cursor, shipping_no, 'failed')
                    conn.commit()
                    if cache:
                        try:
                            cache.delete('cert:list:*')
                        except Exception:
                            pass
                finally:
                    conn.close()
                error_msg = f'Shipping {shipping_no} not found in cert_of_compliance (PostgreSQL)'
                self.update_status(
                    task_id,
                    'failed',
                    error_message=error_msg,
                    completed_at=datetime.now().isoformat(),
                    progress=0,
                    message='Certificate PDF generation failed',
                )
        except Exception as e:
            error_msg = str(e)
            logger.exception(f"Cert PDF task failed: {task_id}, shipping_no={shipping_no}, {error_msg}")
            try:
                import importlib
                tr_api = importlib.import_module('tr_fill_in_api')
                conn = tr_api.get_db_connection()
                cursor = conn.cursor()
                self._upsert_pdf_status(cursor, shipping_no, 'failed')
                conn.commit()
                conn.close()
            except Exception:
                pass
            self.update_status(
                task_id,
                'failed',
                error_message=error_msg,
                completed_at=datetime.now().isoformat(),
                progress=0,
                message=f'Certificate PDF generation failed: {error_msg}',
            )
