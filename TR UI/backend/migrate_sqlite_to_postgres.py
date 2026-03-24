#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sqlite3

import psycopg
from psycopg.rows import dict_row


_current_dir = os.path.dirname(os.path.abspath(__file__))
_default_sqlite = os.path.join(_current_dir, "data_3years.db")

SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", _default_sqlite)
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@127.0.0.1:5432/tr_db")

TABLES = [
    "user_accounts",
    "user_job_access",
    "user_sessions",
    "download_tasks",
    "pdf_tasks",
    "PDF_Status",
    "file_index_cache",
    "file_index_metadata",
    "bbs_dd",
    "TR_Report",
    "TR_Report_Deduplication",
]


def log(msg: str) -> None:
    print(f"[MIGRATE] {msg}")


def sqlite_conn():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def pg_conn():
    return psycopg.connect(POSTGRES_DSN, row_factory=dict_row)


def to_bool(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return bool(int(v))


def to_jsonb(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return "{}"
        try:
            json.loads(v)
            return v
        except Exception:
            return json.dumps({"raw": v}, ensure_ascii=False)
    return json.dumps(v, ensure_ascii=False)


def normalize_timestamp(v):
    if v in (None, ""):
        return None
    return v


def fetch_sqlite_rows(conn, table_name):
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM "{table_name}"')
    return [dict(row) for row in cur.fetchall()]


def migrate_user_accounts(sqlite, pg):
    rows = fetch_sqlite_rows(sqlite, "user_accounts")
    if not rows:
        return 0

    sql = """
        INSERT INTO user_accounts (
            id, username, password_hash, password_salt,
            full_name, role, is_active, created_at, updated_at,
            password_changed_at, password_expires_at
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            username = EXCLUDED.username,
            password_hash = EXCLUDED.password_hash,
            password_salt = EXCLUDED.password_salt,
            full_name = EXCLUDED.full_name,
            role = EXCLUDED.role,
            is_active = EXCLUDED.is_active,
            created_at = EXCLUDED.created_at,
            updated_at = EXCLUDED.updated_at,
            password_changed_at = EXCLUDED.password_changed_at,
            password_expires_at = EXCLUDED.password_expires_at
    """
    data = []
    for r in rows:
        data.append((
            r.get("id"),
            r.get("username"),
            r.get("password_hash"),
            r.get("password_salt"),
            r.get("full_name"),
            r.get("role"),
            to_bool(r.get("is_active")),
            normalize_timestamp(r.get("created_at")),
            normalize_timestamp(r.get("updated_at")),
            normalize_timestamp(r.get("password_changed_at")),
            normalize_timestamp(r.get("password_expires_at")),
        ))

    with pg.cursor() as cur:
        cur.executemany(sql, data)
    return len(data)


def migrate_user_job_access(sqlite, pg):
    rows = fetch_sqlite_rows(sqlite, "user_job_access")
    if not rows:
        return 0

    sql = """
        INSERT INTO user_job_access (id, user_id, job_no, created_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            job_no = EXCLUDED.job_no,
            created_at = EXCLUDED.created_at
    """
    data = [
        (r.get("id"), r.get("user_id"), r.get("job_no"), normalize_timestamp(r.get("created_at")))
        for r in rows
    ]
    with pg.cursor() as cur:
        cur.executemany(sql, data)
    return len(data)


def migrate_user_sessions(sqlite, pg):
    rows = fetch_sqlite_rows(sqlite, "user_sessions")
    if not rows:
        return 0

    sql = """
        INSERT INTO user_sessions (token, user_id, created_at, expires_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (token) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            created_at = EXCLUDED.created_at,
            expires_at = EXCLUDED.expires_at
    """
    data = [
        (
            r.get("token"),
            r.get("user_id"),
            normalize_timestamp(r.get("created_at")),
            normalize_timestamp(r.get("expires_at")),
        )
        for r in rows
    ]
    with pg.cursor() as cur:
        cur.executemany(sql, data)
    return len(data)


def migrate_download_tasks(sqlite, pg):
    rows = fetch_sqlite_rows(sqlite, "download_tasks")
    if not rows:
        return 0

    sql = """
        INSERT INTO download_tasks (
            task_id, user_id, task_type, request_params, status, progress,
            total_files, processed_files, zip_path, zip_size, error_message,
            warning_message, created_at, started_at, completed_at, expires_at
        )
        VALUES (
            %s, %s, %s, %s::jsonb, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        ON CONFLICT (task_id) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            task_type = EXCLUDED.task_type,
            request_params = EXCLUDED.request_params,
            status = EXCLUDED.status,
            progress = EXCLUDED.progress,
            total_files = EXCLUDED.total_files,
            processed_files = EXCLUDED.processed_files,
            zip_path = EXCLUDED.zip_path,
            zip_size = EXCLUDED.zip_size,
            error_message = EXCLUDED.error_message,
            warning_message = EXCLUDED.warning_message,
            created_at = EXCLUDED.created_at,
            started_at = EXCLUDED.started_at,
            completed_at = EXCLUDED.completed_at,
            expires_at = EXCLUDED.expires_at
    """
    data = []
    for r in rows:
        data.append((
            r.get("task_id"),
            r.get("user_id"),
            r.get("task_type"),
            to_jsonb(r.get("request_params")),
            r.get("status"),
            r.get("progress", 0),
            r.get("total_files", 0),
            r.get("processed_files", 0),
            r.get("zip_path"),
            r.get("zip_size"),
            r.get("error_message"),
            r.get("warning_message"),
            normalize_timestamp(r.get("created_at")),
            normalize_timestamp(r.get("started_at")),
            normalize_timestamp(r.get("completed_at")),
            normalize_timestamp(r.get("expires_at")),
        ))
    with pg.cursor() as cur:
        cur.executemany(sql, data)
    return len(data)


def migrate_pdf_tasks(sqlite, pg):
    rows = fetch_sqlite_rows(sqlite, "pdf_tasks")
    if not rows:
        return 0

    sql = """
        INSERT INTO pdf_tasks (
            task_id, user_id, order_no, status, progress, message,
            pdf_path, error_message, created_at, started_at, completed_at, expires_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (task_id) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            order_no = EXCLUDED.order_no,
            status = EXCLUDED.status,
            progress = EXCLUDED.progress,
            message = EXCLUDED.message,
            pdf_path = EXCLUDED.pdf_path,
            error_message = EXCLUDED.error_message,
            created_at = EXCLUDED.created_at,
            started_at = EXCLUDED.started_at,
            completed_at = EXCLUDED.completed_at,
            expires_at = EXCLUDED.expires_at
    """
    data = [
        (
            r.get("task_id"),
            r.get("user_id"),
            r.get("order_no"),
            r.get("status"),
            r.get("progress", 0),
            r.get("message"),
            r.get("pdf_path"),
            r.get("error_message"),
            normalize_timestamp(r.get("created_at")),
            normalize_timestamp(r.get("started_at")),
            normalize_timestamp(r.get("completed_at")),
            normalize_timestamp(r.get("expires_at")),
        )
        for r in rows
    ]
    with pg.cursor() as cur:
        cur.executemany(sql, data)
    return len(data)


def migrate_pdf_status(sqlite, pg):
    rows = fetch_sqlite_rows(sqlite, "PDF_Status")
    if not rows:
        return 0

    sql = """
        INSERT INTO "PDF_Status" (
            "Order_No", pdf_status, pdf_path, generated_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT ("Order_No") DO UPDATE SET
            pdf_status = EXCLUDED.pdf_status,
            pdf_path = EXCLUDED.pdf_path,
            generated_at = EXCLUDED.generated_at,
            updated_at = EXCLUDED.updated_at
    """
    data = [
        (
            r.get("Order_No"),
            r.get("pdf_status"),
            r.get("pdf_path"),
            normalize_timestamp(r.get("generated_at")),
            normalize_timestamp(r.get("updated_at")),
        )
        for r in rows
    ]
    with pg.cursor() as cur:
        cur.executemany(sql, data)
    return len(data)


def migrate_file_index_cache(sqlite, pg):
    rows = fetch_sqlite_rows(sqlite, "file_index_cache")
    if not rows:
        return 0

    sql = """
        INSERT INTO file_index_cache (
            id, file_path, file_name, folder_path, folder_type,
            file_size, modified_time, created_time, last_checked,
            extracted_keywords, identifiers, file_hash, is_deleted
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            file_path = EXCLUDED.file_path,
            file_name = EXCLUDED.file_name,
            folder_path = EXCLUDED.folder_path,
            folder_type = EXCLUDED.folder_type,
            file_size = EXCLUDED.file_size,
            modified_time = EXCLUDED.modified_time,
            created_time = EXCLUDED.created_time,
            last_checked = EXCLUDED.last_checked,
            extracted_keywords = EXCLUDED.extracted_keywords,
            identifiers = EXCLUDED.identifiers,
            file_hash = EXCLUDED.file_hash,
            is_deleted = EXCLUDED.is_deleted
    """
    data = [
        (
            r.get("id"),
            r.get("file_path"),
            r.get("file_name"),
            r.get("folder_path"),
            r.get("folder_type"),
            r.get("file_size"),
            r.get("modified_time"),
            normalize_timestamp(r.get("created_time")),
            normalize_timestamp(r.get("last_checked")),
            r.get("extracted_keywords"),
            r.get("identifiers"),
            r.get("file_hash"),
            to_bool(r.get("is_deleted")) or False,
        )
        for r in rows
    ]
    with pg.cursor() as cur:
        cur.executemany(sql, data)
    return len(data)


def migrate_file_index_metadata(sqlite, pg):
    rows = fetch_sqlite_rows(sqlite, "file_index_metadata")
    if not rows:
        return 0

    sql = """
        INSERT INTO file_index_metadata (key, value, updated_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            updated_at = EXCLUDED.updated_at
    """
    data = [
        (r.get("key"), r.get("value"), normalize_timestamp(r.get("updated_at")))
        for r in rows
    ]
    with pg.cursor() as cur:
        cur.executemany(sql, data)
    return len(data)


def migrate_bbs_dd(sqlite, pg):
    rows = fetch_sqlite_rows(sqlite, "bbs_dd")
    if not rows:
        return 0

    sql = """
        INSERT INTO bbs_dd (
            bbs_no, jobsite_no, dd_no, dd_delivery_date, order_desc, jobsite_type
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    data = [
        (
            r.get("bbs_no"),
            r.get("jobsite_no"),
            r.get("dd_no"),
            r.get("dd_delivery_date"),
            r.get("order_desc"),
            r.get("jobsite_type"),
        )
        for r in rows
    ]
    with pg.cursor() as cur:
        cur.executemany(sql, data)
    return len(data)


def migrate_tr_report(sqlite, pg):
    rows = fetch_sqlite_rows(sqlite, "TR_Report")
    if not rows:
        return 0

    sql = """
        INSERT INTO "TR_Report" (
            "Job_No", jobsite, order_no, order_describution, client, del_date,
            ref_no, bbs_po_no, jobsite_type, diameter, wt_ton, product, grade,
            pattern, mill_cert, test_cert1, test_cert2, supplier, stockist_cert,
            po_no, rm_dn_no
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s
        )
    """
    data = [
        (
            r.get("Job_No"),
            r.get("jobsite"),
            r.get("order_no"),
            r.get("order_describution"),
            r.get("client"),
            r.get("del_date"),
            r.get("ref_no"),
            r.get("bbs_po_no"),
            r.get("jobsite_type"),
            r.get("diameter"),
            r.get("wt_ton"),
            r.get("product"),
            r.get("grade"),
            r.get("pattern"),
            r.get("mill_cert"),
            r.get("test_cert1"),
            r.get("test_cert2"),
            r.get("supplier"),
            r.get("stockist_cert"),
            r.get("po_no"),
            r.get("rm_dn_no"),
        )
        for r in rows
    ]
    with pg.cursor() as cur:
        cur.executemany(sql, data)
    return len(data)


def migrate_tr_report_dedup(sqlite, pg):
    rows = fetch_sqlite_rows(sqlite, "TR_Report_Deduplication")
    if not rows:
        return 0

    sql = """
        INSERT INTO "TR_Report_Deduplication" (
            "Order_No", "Job_No", "Jobsite", "Order_Description", "Client",
            "Del_Date", "Ref_No", "PO_No", "Jobsite_Type", "Wt", "Grade", "rm_dn_no"
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT ("Order_No") DO UPDATE SET
            "Job_No" = EXCLUDED."Job_No",
            "Jobsite" = EXCLUDED."Jobsite",
            "Order_Description" = EXCLUDED."Order_Description",
            "Client" = EXCLUDED."Client",
            "Del_Date" = EXCLUDED."Del_Date",
            "Ref_No" = EXCLUDED."Ref_No",
            "PO_No" = EXCLUDED."PO_No",
            "Jobsite_Type" = EXCLUDED."Jobsite_Type",
            "Wt" = EXCLUDED."Wt",
            "Grade" = EXCLUDED."Grade",
            "rm_dn_no" = EXCLUDED."rm_dn_no"
    """
    data = [
        (
            r.get("Order_No"),
            r.get("Job_No"),
            r.get("Jobsite"),
            r.get("Order_Description"),
            r.get("Client"),
            r.get("Del_Date"),
            r.get("Ref_No"),
            r.get("PO_No"),
            r.get("Jobsite_Type"),
            r.get("Wt"),
            r.get("Grade"),
            r.get("rm_dn_no"),
        )
        for r in rows
    ]
    with pg.cursor() as cur:
        cur.executemany(sql, data)
    return len(data)


MIGRATORS = {
    "user_accounts": migrate_user_accounts,
    "user_job_access": migrate_user_job_access,
    "user_sessions": migrate_user_sessions,
    "download_tasks": migrate_download_tasks,
    "pdf_tasks": migrate_pdf_tasks,
    "PDF_Status": migrate_pdf_status,
    "file_index_cache": migrate_file_index_cache,
    "file_index_metadata": migrate_file_index_metadata,
    "bbs_dd": migrate_bbs_dd,
    "TR_Report": migrate_tr_report,
    "TR_Report_Deduplication": migrate_tr_report_dedup,
}


def clear_target_tables(pg):
    tables = [
        '"TR_Report_Deduplication"',
        '"TR_Report"',
        "bbs_dd",
        "file_index_metadata",
        "file_index_cache",
        '"PDF_Status"',
        "pdf_tasks",
        "download_tasks",
        "user_sessions",
        "user_job_access",
        "user_accounts",
    ]
    with pg.cursor() as cur:
        for t in tables:
            # Check if table exists before truncating
            table_name = t.strip('"')
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                ) AS exists
            """, (table_name.lower(),))
            row = cur.fetchone()
            exists = row['exists'] if isinstance(row, dict) else row[0]
            if exists:
                cur.execute(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE")
                log(f"  Cleared {t}")
            else:
                log(f"  Skipped {t} (table does not exist)")


def verify_counts(sqlite, pg):
    log("Verifying row counts...")
    with pg.cursor() as cur:
        for table in TABLES:
            s_count = len(fetch_sqlite_rows(sqlite, table))
            quoted = f'"{table}"' if table in ("PDF_Status", "TR_Report", "TR_Report_Deduplication") else table
            cur.execute(f"SELECT COUNT(*) AS c FROM {quoted}")
            p_count = cur.fetchone()["c"]
            print(f"{table}: sqlite={s_count}, postgres={p_count}")


def main():
    if not os.path.exists(SQLITE_DB_PATH):
        raise FileNotFoundError(f"SQLite DB not found: {SQLITE_DB_PATH}")

    log(f"SQLite: {SQLITE_DB_PATH}")
    log(f"PostgreSQL: {POSTGRES_DSN}")

    sqlite = sqlite_conn()
    pg = pg_conn()

    try:
        with pg.transaction():
            clear_target_tables(pg)

            for table in TABLES:
                log(f"Migrating {table} ...")
                count = MIGRATORS[table](sqlite, pg)
                log(f"{table}: migrated {count} rows")

        verify_counts(sqlite, pg)
        log("Migration completed successfully")

    finally:
        sqlite.close()
        pg.close()


if __name__ == "__main__":
    main()
