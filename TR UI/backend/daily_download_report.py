#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daily download summary report — collect stats and email (scheduled at 19:00)."""

from __future__ import annotations

import argparse
import logging
import os
import re
import smtplib
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_TR_DATABASE_DIR = os.path.normpath(os.path.join(_BACKEND_DIR, '..', '..', 'TR database'))
if _TR_DATABASE_DIR not in sys.path:
    sys.path.insert(0, _TR_DATABASE_DIR)

from update_tr_tables_postgres import EMAIL_CONFIG  # noqa: E402

NGINX_ACCESS_LOG = os.path.normpath(
    os.path.join(_BACKEND_DIR, '..', 'nginx-1.28.0', 'logs', 'access.log')
)
BACKEND_ACCESS_LOG = os.path.join(_BACKEND_DIR, 'logs', 'access.log')
REPORT_LOG_DIR = os.path.join(_BACKEND_DIR, 'logs')

AUDIT_RE = re.compile(
    r'DOWNLOAD_AUDIT action=(\S+) user=(\S+) uid=(\S+) ip=(\S+) count=(\d+) orders=([^\s]+)'
)
NGINX_LINE_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+) [^"]*" (?P<status>\d+)'
)
NGINX_DATE_RE = re.compile(r'^(\d{2})/(\w{3})/(\d{4})')

MONTH_MAP = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
}

DOWNLOAD_PATH_RULES = [
    ('cert_pdf', re.compile(r'^/api/cert-of-compliance/download/\d+')),
    ('cert_batch', re.compile(r'^/api/cert-of-compliance/batch-download')),
    ('tr_pdf_single', re.compile(r'^/api/pdf/download/\d+')),
    ('tr_pdf_batch', re.compile(r'^/api/pdf/batch-download')),
    ('stockist_by_date', re.compile(r'^/api/stockist-test/download-by-order-nos-grouped-by-date')),
    ('stockist_all', re.compile(r'^/api/stockist-test/download-all-stockist-nos')),
    ('async_zip', re.compile(r'^/api/download/download/')),
]
TR_PDF_ORDER_RE = re.compile(r'/api/pdf/download/(\d+)')
CERT_DD_RE = re.compile(r'/api/cert-of-compliance/download/(\d+)')


def setup_logging() -> logging.Logger:
    os.makedirs(REPORT_LOG_DIR, exist_ok=True)
    log_file = os.path.join(
        REPORT_LOG_DIR,
        f'daily_download_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
    )
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger('daily_download_report')


def _parse_nginx_date(time_field: str) -> date | None:
    m = NGINX_DATE_RE.match(time_field.split(':', 1)[0].strip())
    if not m:
        return None
    day, mon, year = int(m.group(1)), MONTH_MAP.get(m.group(2)), int(m.group(3))
    if not mon:
        return None
    return date(year, mon, day)


def _classify_nginx_path(path: str) -> str | None:
    for name, pattern in DOWNLOAD_PATH_RULES:
        if pattern.search(path):
            return name
    return None


def collect_audit_entries(report_date: date) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not os.path.isfile(BACKEND_ACCESS_LOG):
        return entries
    prefix = report_date.strftime('%Y-%m-%d')
    with open(BACKEND_ACCESS_LOG, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if prefix not in line or 'DOWNLOAD_AUDIT' not in line:
                continue
            m = AUDIT_RE.search(line)
            if not m:
                continue
            action, user, uid, ip, count, orders = m.groups()
            entries.append({
                'action': action,
                'user': user,
                'uid': uid,
                'ip': ip,
                'count': int(count),
                'orders': [o for o in orders.split(',') if o],
                'source': 'audit',
            })
    return entries


def collect_nginx_downloads(report_date: date) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not os.path.isfile(NGINX_ACCESS_LOG):
        return grouped
    with open(NGINX_ACCESS_LOG, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            m = NGINX_LINE_RE.match(line)
            if not m:
                continue
            d = _parse_nginx_date(m.group('time'))
            if d != report_date:
                continue
            path = m.group('path')
            kind = _classify_nginx_path(path)
            if not kind or '/task-status/' in path:
                continue
            status = int(m.group('status'))
            if status not in (200, 304):
                continue
            grouped[kind].append({
                'time': m.group('time'),
                'ip': m.group('ip'),
                'method': m.group('method'),
                'path': path,
                'status': status,
            })
    return grouped


def collect_download_tasks(report_date: date) -> list[dict[str, Any]]:
    os.environ.setdefault('DB_BACKEND', 'postgres')
    try:
        from db_adapter import get_connection, close_all
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT task_id, user_id, task_type, request_params, status,
                   zip_size, total_files, created_at, completed_at
            FROM download_tasks
            WHERE created_at::date = %s
            ORDER BY created_at
            """,
            (report_date,),
        )
        for row in cursor.fetchall():
            if isinstance(row, dict):
                rows.append(row)
            else:
                cols = [d[0] for d in cursor.description]
                rows.append(dict(zip(cols, row)))
    except Exception:
        logging.exception('Failed to query download_tasks')
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        try:
            close_all()
        except Exception:
            pass
    return rows


def _nginx_tr_pdf_orders(nginx_groups: dict[str, list[dict[str, Any]]]) -> list[str]:
    orders: list[str] = []
    for hit in nginx_groups.get('tr_pdf_single', []):
        if hit.get('status') != 200:
            continue
        m = TR_PDF_ORDER_RE.search(hit.get('path', ''))
        if m:
            orders.append(m.group(1))
    return orders


def build_report(report_date: date) -> str:
    audit_entries = collect_audit_entries(report_date)
    nginx_groups = collect_nginx_downloads(report_date)
    db_tasks = collect_download_tasks(report_date)

    audit_by_action = Counter(e['action'] for e in audit_entries)
    audit_orders = set()
    for e in audit_entries:
        audit_orders.update(e['orders'])

    nginx_tr_single_200 = sum(
        1 for h in nginx_groups.get('tr_pdf_single', []) if h.get('status') == 200
    )
    nginx_tr_batch = len(nginx_groups.get('tr_pdf_batch', []))
    nginx_tr_orders = _nginx_tr_pdf_orders(nginx_groups)

    lines = [
        'TR System Daily Download Report',
        f'Date: {report_date.isoformat()}',
        f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        '',
        '=== Summary ===',
        f'TR PDF single download (audit): {audit_by_action.get("tr_pdf_single", 0)}',
        f'TR PDF batch ZIP (audit): {audit_by_action.get("tr_pdf_batch", 0)}',
        f'TR PDF unique orders (audit): {len(audit_orders)}',
        f'TR PDF single (nginx 200): {nginx_tr_single_200}',
        f'TR PDF batch ZIP (nginx): {nginx_tr_batch}',
        f'Async download tasks (DB): {len(db_tasks)}',
        '',
        '=== Nginx download API (successful 200/304) ===',
    ]
    for kind in (
        'tr_pdf_single', 'tr_pdf_batch', 'cert_pdf', 'cert_batch',
        'stockist_by_date', 'stockist_all', 'async_zip',
    ):
        hits = nginx_groups.get(kind, [])
        lines.append(f'  {kind}: {len(hits)}')

    lines.append('')
    lines.append('=== TR PDF detail ===')
    if audit_entries:
        for e in audit_entries:
            lines.append(
                f"  [audit/{e['action']}] user={e['user']} ip={e['ip']} "
                f"count={e['count']} orders={','.join(e['orders'])}"
            )
    else:
        lines.append('  (audit log empty — using nginx fallback below)')
    for hit in nginx_groups.get('tr_pdf_single', []):
        m = TR_PDF_ORDER_RE.search(hit.get('path', ''))
        if not m:
            continue
        cache = 'cached' if hit.get('status') == 304 else 'downloaded'
        lines.append(
            f"  [nginx/single] {hit['time']} ip={hit['ip']} order={m.group(1)} ({cache})"
        )
    for hit in nginx_groups.get('tr_pdf_batch', []):
        lines.append(
            f"  [nginx/batch] {hit['time']} ip={hit['ip']} POST batch-download (ZIP)"
        )
    if nginx_tr_orders:
        lines.append(f"  unique orders (nginx 200 only): {','.join(dict.fromkeys(nginx_tr_orders))}")

    lines.append('')
    lines.append('=== Async download tasks (Stockist etc.) ===')
    if db_tasks:
        for t in db_tasks:
            params = t.get('request_params') or {}
            order_nos = params.get('order_nos') if isinstance(params, dict) else []
            lines.append(
                f"  {t.get('created_at')} type={t.get('task_type')} status={t.get('status')} "
                f"files={t.get('total_files')} zip_size={t.get('zip_size')} "
                f"orders={len(order_nos or [])}"
            )
            if order_nos:
                preview = ','.join(str(o) for o in order_nos[:20])
                if len(order_nos) > 20:
                    preview += f',... (+{len(order_nos) - 20} more)'
                lines.append(f'    order_nos: {preview}')
    else:
        lines.append('  (none)')

    lines.append('')
    lines.append('=== CERT / Stockist / async ZIP (nginx) ===')
    for kind in ('cert_pdf', 'cert_batch', 'stockist_by_date', 'stockist_all', 'async_zip'):
        for hit in nginx_groups.get(kind, []):
            extra = ''
            if kind == 'cert_pdf':
                m = CERT_DD_RE.search(hit.get('path', ''))
                if m:
                    extra = f' dd_no={m.group(1)}'
            lines.append(f"  [{kind}] {hit['time']} {hit['ip']} {hit['path']}{extra}")

    return '\n'.join(lines)


def send_report_email(report_date: date, body: str, logger: logging.Logger) -> bool:
    if not EMAIL_CONFIG.get('username'):
        logger.warning('EMAIL_CONFIG.username empty — skip email')
        return False

    to_email = EMAIL_CONFIG.get('to_email', '')
    if isinstance(to_email, str):
        recipients = [e.strip() for e in to_email.split(',') if e.strip()]
    elif isinstance(to_email, list):
        recipients = [e.strip() for e in to_email if e.strip()]
    else:
        recipients = []

    if not recipients:
        logger.warning('No recipients configured')
        return False

    subject = f"TR Daily Download Report - {report_date.isoformat()}"
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['username']
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        try:
            if EMAIL_CONFIG.get('password'):
                server.login(EMAIL_CONFIG['username'], EMAIL_CONFIG['password'])
        except smtplib.SMTPAuthenticationError:
            logger.warning('SMTP auth failed, trying anonymous send...')
        except smtplib.SMTPException as exc:
            if 'not supported' not in str(exc).lower() and 'AUTH' not in str(exc):
                raise

        server.send_message(msg, to_addrs=recipients)
        server.quit()
        logger.info('Email sent to %s', ', '.join(recipients))
        return True
    except Exception as exc:
        logger.error('Failed to send email: %s', exc)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description='TR daily download report')
    parser.add_argument(
        '--date',
        help='Report date YYYY-MM-DD (default: today)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print report only, do not send email',
    )
    args = parser.parse_args()

    logger = setup_logging()
    if args.date:
        report_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    else:
        report_date = date.today()

    logger.info('Building download report for %s', report_date)
    body = build_report(report_date)
    print(body)

    if args.dry_run:
        logger.info('Dry run — email not sent')
        return 0

    ok = send_report_email(report_date, body, logger)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
