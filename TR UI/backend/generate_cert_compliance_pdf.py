#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate Certificate of Compliance PDF (WeasyPrint)."""

import os
import re
import sys
from datetime import datetime

import pandas as pd
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import create_engine, text

from db_adapter import is_postgres, sqlalchemy_postgres_dsn

try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError as e:
    WEASYPRINT_AVAILABLE = False
    IMPORT_ERROR = e


def _require_postgres_backend() -> None:
    if not is_postgres():
        raise RuntimeError(
            "Certificate PDF generation requires DB_BACKEND=postgres; SQLite is no longer supported."
        )


def _safe_log(level, msg):
    try:
        from logger_config import get_logger
        log = get_logger('cert_pdf')
        getattr(log, level)(msg)
    except Exception:
        print(f"[{level}] {msg}")


class CertCompliancePDFGenerator:
    def __init__(self, postgres_dsn: str | None = None):
        if not WEASYPRINT_AVAILABLE:
            raise ImportError(
                "WeasyPrint is not available. Install weasyprint and GTK runtime on Windows.\n"
                f"Original error: {IMPORT_ERROR}"
            )
        _require_postgres_backend()
        self.engine = create_engine(sqlalchemy_postgres_dsn(postgres_dsn), echo=False)
        templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
        self.jinja_env = Environment(loader=FileSystemLoader(templates_dir))
        self._to_text = lambda v: '' if v is None else str(v)

    def get_cert_data(self, shipping_no: int):
        conn = self.engine.connect()
        try:
            q = text("""
                SELECT
                    shipping_no,
                    del_date,
                    jobsite_no,
                    jobsite_name,
                    del_address,
                    asd_contract_no1,
                    asd_contract_no2,
                    work_order_no,
                    client_name,
                    main_contractor,
                    bbs_no_list
                FROM cert_of_compliance
                WHERE shipping_no = :shipping_no
                LIMIT 1
            """)
            df = pd.read_sql(q, conn, params={'shipping_no': int(shipping_no)})
            if df.empty:
                return None
            return df.iloc[0]
        finally:
            conn.close()

    @staticmethod
    def _format_del_date_folder(del_date) -> str:
        if del_date is None:
            return datetime.now().strftime('%Y-%m-%d')
        if hasattr(del_date, 'strftime'):
            return del_date.strftime('%Y-%m-%d')
        text_val = str(del_date).strip()
        return text_val[:10] if text_val else datetime.now().strftime('%Y-%m-%d')

    @staticmethod
    def _format_date_dispatched(del_date) -> str:
        if del_date is None:
            return ''
        if hasattr(del_date, 'strftime'):
            return del_date.strftime('%d-%m-%Y')
        text_val = str(del_date).strip().replace('/', '-')
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%m-%d-%Y'):
            try:
                return datetime.strptime(text_val[:10], fmt).strftime('%d-%m-%Y')
            except ValueError:
                continue
        return text_val[:10]

    @staticmethod
    def _normalize_asd_contract(value: str) -> tuple[str, bool]:
        """Return (contract_no, had_archsd_label)."""
        text_val = (value or '').strip()
        if not text_val:
            return '', False
        lowered = text_val.lower()
        prefixes = (
            'archsd contract no.:',
            'archsd contract no:',
            'archsd contract no.',
        )
        for prefix in prefixes:
            if lowered.startswith(prefix):
                return text_val[len(prefix):].strip(), True
        return text_val, False

    @staticmethod
    def _parse_bbs_orders(bbs_no_list) -> list[str]:
        if bbs_no_list is None:
            return []
        text_val = str(bbs_no_list).strip()
        if not text_val:
            return []
        return [part for part in re.split(r'[,;\s]+', text_val) if part]

    @staticmethod
    def _build_output_filename(shipping_no: int, order_nos: list[str]) -> str:
        base = f'Certificate of Compliance DD{shipping_no}'
        if not order_nos:
            return f'{base}.pdf'
        if len(order_nos) == 1:
            suffix = f', BBS_{order_nos[0]}'
        else:
            suffix = f', BBS_{order_nos[0]}, ' + ', '.join(order_nos[1:])
        return f'{base}{suffix}.pdf'

    @classmethod
    def find_existing_pdf(cls, backend_dir: str, shipping_no: int, del_date=None) -> str | None:
        """Locate generated COC PDF (new or legacy filename)."""
        folder = cls._format_del_date_folder(del_date)
        pdf_dir = os.path.join(backend_dir, 'Generated_Cert_PDFs', folder)
        if not os.path.isdir(pdf_dir):
            return None
        prefix = f'Certificate of Compliance DD{shipping_no}'
        for name in sorted(os.listdir(pdf_dir), reverse=True):
            if name.startswith(prefix) and name.lower().endswith('.pdf'):
                return os.path.join(pdf_dir, name)
        legacy = os.path.join(pdf_dir, f'Cert_{shipping_no}.pdf')
        if os.path.exists(legacy):
            return legacy
        return None

    def _resolve_archsd_contract(
        self, asd1_raw: str, asd2_raw: str, work_order_no: str
    ) -> tuple[str, list[str], str]:
        """Resolve ArchSD row, project extras, and optional asd1 marker line."""
        asd1, asd1_has_label = self._normalize_asd_contract(asd1_raw)
        asd2, asd2_has_label = self._normalize_asd_contract(asd2_raw)

        archsd_contract_no = ''
        if asd2_has_label and asd2:
            archsd_contract_no = asd2
        elif asd1_has_label and asd1:
            archsd_contract_no = asd1
        elif asd1.lower().startswith('tc '):
            archsd_contract_no = asd1
        elif asd2.lower().startswith('tc '):
            archsd_contract_no = asd2

        show_archsd_row = bool(archsd_contract_no) and (
            bool(work_order_no)
            or asd1_has_label
            or asd2_has_label
            or asd1.lower().startswith('tc ')
            or asd2.lower().startswith('tc ')
        )

        extras: list[str] = []
        asd_marker = ''
        if not show_archsd_row:
            for extra in (asd2_raw, asd1_raw):
                if extra:
                    extras.append(extra)
            return '', extras, ''

        if asd1_raw:
            consumed = (
                asd1_has_label
                or asd1.lower().startswith('tc ')
                or asd1 == archsd_contract_no
            )
            if not consumed:
                asd_marker = asd1_raw

        for raw in (asd1_raw, asd2_raw):
            val = (raw or '').strip()
            if not val or val == asd_marker:
                continue
            norm, has_label = self._normalize_asd_contract(val)
            if has_label or norm.lower().startswith('tc '):
                continue
            if norm == archsd_contract_no:
                continue
            extras.append(val)
        return archsd_contract_no, extras, asd_marker

    def _build_cert_context(self, row) -> dict:
        raw = {k: self._to_text(row[k]) for k in row.index}
        jobsite_name = raw.get('jobsite_name', '').strip()
        del_address = raw.get('del_address', '').strip()
        asd1_raw = raw.get('asd_contract_no1', '').strip()
        asd2_raw = raw.get('asd_contract_no2', '').strip()
        work_order_no = raw.get('work_order_no', '').strip()
        order_nos = self._parse_bbs_orders(raw.get('bbs_no_list', ''))

        project_lines: list[str] = []
        if del_address and del_address != jobsite_name:
            project_lines.append(del_address)

        archsd_contract_no, asd_extras, asd_marker = self._resolve_archsd_contract(
            asd1_raw, asd2_raw, work_order_no
        )
        project_lines.extend(asd_extras)

        return {
            'shipping_no': raw.get('shipping_no', ''),
            'ref_no': raw.get('shipping_no', ''),
            'jobsite_no': raw.get('jobsite_no', ''),
            'jobsite_name': jobsite_name,
            'client_name': raw.get('client_name', ''),
            'main_contractor': raw.get('main_contractor', ''),
            'project_lines': project_lines,
            'archsd_contract_no': archsd_contract_no,
            'asd_marker': asd_marker,
            'work_order_no': work_order_no,
            'order_nos': order_nos,
            'date_dispatched': self._format_date_dispatched(row.get('del_date')),
        }

    def generate_pdf(self, shipping_no: int, output_path: str | None = None):
        row = self.get_cert_data(shipping_no)
        if row is None:
            _safe_log('warning', f"Shipping {shipping_no} not found in PostgreSQL cert_of_compliance")
            return False, None, None

        cert = self._build_cert_context(row)
        backend_dir = os.path.dirname(__file__)

        if output_path is None:
            folder = self._format_del_date_folder(row.get('del_date'))
            pdf_dir = os.path.join(backend_dir, 'Generated_Cert_PDFs', folder)
            os.makedirs(pdf_dir, exist_ok=True)
            filename = self._build_output_filename(int(shipping_no), cert.get('order_nos') or [])
            output_path = os.path.join(pdf_dir, filename)
            legacy_path = os.path.join(pdf_dir, f'Cert_{int(shipping_no)}.pdf')
            if os.path.exists(legacy_path):
                try:
                    os.remove(legacy_path)
                except OSError as e:
                    _safe_log('warning', f"Could not remove legacy cert PDF: {e}")

        logo_path = os.path.join(backend_dir, 'VSC Logo.png')
        if not os.path.exists(logo_path):
            alt = os.path.join(backend_dir, 'vsc logo.png')
            logo_path = alt if os.path.exists(alt) else logo_path
        logo_exists = os.path.exists(logo_path)

        signature_path = os.path.join(backend_dir, 'signature_chop-removebg.png')
        if not os.path.exists(signature_path):
            alt_sig = os.path.join(backend_dir, 'signature chop.PNG')
            signature_path = alt_sig if os.path.exists(alt_sig) else signature_path
        signature_exists = os.path.exists(signature_path)

        template = self.jinja_env.get_template('cert_compliance.html')
        html_content = template.render(
            cert=cert,
            logo_exists=logo_exists,
            logo_path='VSC Logo.png' if logo_exists else '',
            signature_exists=signature_exists,
            signature_path=(
                'signature_chop-removebg.png'
                if signature_exists and 'removebg' in os.path.basename(signature_path)
                else 'signature chop.PNG'
            ) if signature_exists else '',
        )

        css_path = os.path.join(backend_dir, 'templates', 'cert_compliance.css')
        css = CSS(filename=css_path)
        base_url_path = backend_dir.replace('\\', '/')
        if not base_url_path.startswith('/') and ':' in base_url_path:
            drive, path = base_url_path.split(':', 1)
            base_url_path = f'/{drive}:{path}'
        base_url = f'file://{base_url_path}/'

        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as e:
                _safe_log('warning', f"Could not remove existing PDF: {e}")

        HTML(string=html_content, base_url=base_url).write_pdf(output_path, stylesheets=[css])
        rel_path = os.path.relpath(output_path, backend_dir).replace('\\', '/')
        return True, rel_path, None


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('shipping_no', type=int)
    args = parser.parse_args()
    gen = CertCompliancePDFGenerator()
    ok, path, _ = gen.generate_pdf(args.shipping_no)
    print('ok=', ok, 'path=', path)
    sys.exit(0 if ok else 1)
