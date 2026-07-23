#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rebuild PostgreSQL bbs_tr_status and ensure incomplete BBS appear in list tables.

Because TVSC.dbo.sync_tr_data (run as dbo) still drops incomplete BBS from the DW,
this step re-pulls eligible incomplete orders from the live Schnell source via
OPENQUERY and upserts them into PostgreSQL bbs_dd + TR_Report_Deduplication,
marked tr_status='incomplete'.

Complete orders present in DW are marked tr_status='complete'.

Requires: POSTGRES_DSN, SQL Server access (same as other generate_* scripts).
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

import pyodbc
from sqlalchemy import create_engine, text

from db_adapter import POSTGRES_DSN, is_postgres, sqlalchemy_postgres_dsn

LOG = logging.getLogger("rebuild_bbs_tr_status")


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def mssql_connect():
    server = os.getenv("SQL_SERVER", "192.168.80.242")
    database = os.getenv("SQL_DATABASE", "TVSC")
    username = os.getenv("SQL_USERNAME", "reportuser")
    password = os.getenv("SQL_PASSWORD", "HKSHA123")
    driver = os.getenv(
        "SQL_ODBC_DRIVER",
        os.getenv("SQL_DRIVER", "ODBC Driver 17 for SQL Server"),
    )
    conn_str = (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        f"UID={username};PWD={password};TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=120)


def ensure_pg_tables(engine):
    # Create status table first (no lock_timeout — short DDL)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS bbs_tr_status (
                        bbs_no BIGINT PRIMARY KEY,
                        tr_status TEXT NOT NULL DEFAULT 'complete',
                        missing_diameters TEXT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )
    except Exception as exc:
        LOG.warning("CREATE bbs_tr_status warn: %s", exc)

    try:
        with engine.begin() as conn:
            conn.execute(text("SET lock_timeout = '3s'"))
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_bbs_tr_status_status ON bbs_tr_status(tr_status)"
                )
            )
    except Exception as exc:
        LOG.warning("CREATE INDEX bbs_tr_status warn (non-fatal): %s", exc)

    def column_exists(table_name: str, column_name: str) -> bool:
        q = text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :tbl
              AND column_name = :col
            LIMIT 1
            """
        )
        with engine.connect() as conn:
            return conn.execute(q, {"tbl": table_name, "col": column_name}).fetchone() is not None

    # Prefer checking catalog first to avoid waiting on AccessExclusiveLock for ADD COLUMN.
    alter_targets = (
        ("bbs_dd", "tr_status", 'ALTER TABLE bbs_dd ADD COLUMN IF NOT EXISTS tr_status TEXT'),
        ("bbs_dd", "missing_diameters", 'ALTER TABLE bbs_dd ADD COLUMN IF NOT EXISTS missing_diameters TEXT'),
        (
            "TR_Report_Deduplication",
            "tr_status",
            'ALTER TABLE "TR_Report_Deduplication" ADD COLUMN IF NOT EXISTS tr_status TEXT',
        ),
        (
            "TR_Report_Deduplication",
            "missing_diameters",
            'ALTER TABLE "TR_Report_Deduplication" ADD COLUMN IF NOT EXISTS missing_diameters TEXT',
        ),
    )
    for table_name, column_name, ddl in alter_targets:
        if column_exists(table_name, column_name):
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text("SET lock_timeout = '3s'"))
                conn.execute(text(ddl))
            LOG.info("Added column %s.%s", table_name, column_name)
        except Exception as exc:
            LOG.warning(
                "Could not add %s.%s (will rely on bbs_tr_status): %s",
                table_name,
                column_name,
                exc,
            )


def fetch_incomplete_from_source(cn, complete_bbs: set[int]) -> list[dict]:
    """
    Find BBS that pass sync header eligibility but are absent from tr_bbs_header
    (dropped by missing-TR purge). Then load stub fields + missing diameters.
    """
    from datetime import date

    lookback = int(os.getenv("INCOMPLETE_LOOKBACK_MONTHS", "6"))
    y, m = date.today().year, date.today().month
    m -= lookback
    while m <= 0:
        m += 12
        y -= 1
    cutoff_s = date(y, m, 1).isoformat()
    LOG.info("Incomplete lookback months=%s cutoff=%s", lookback, cutoff_s)

    eligible_inner = f"""
        SELECT DISTINCT pp.id_pedido_produccion AS bbs_no
        FROM pedidos_produccion pp
        JOIN obras js ON pp.id_obra = js.id_obra
        WHERE pp.estado = 11
          AND js.id_tipo_forjado NOT IN (10, 12)
          AND pp.fecha_entrega_prevista >= '{cutoff_s}'
          AND EXISTS (
              SELECT 1 FROM pedidos_produccion_lin ppl
              WHERE ppl.id_pedido_produccion = pp.id_pedido_produccion
                AND ppl.cal_tipo_acero_fa <> '460'
                AND ppl.cal_mm_fa <> 0
                AND ppl.id_albaran_salida IS NOT NULL
          )
    """
    sql = "SELECT * FROM OPENQUERY(TVSC, '" + eligible_inner.replace("'", "''") + "')"
    cur = cn.cursor()
    LOG.info("Fetching eligible BBS list from source...")
    cur.execute(sql)
    eligible = {int(r[0]) for r in cur.fetchall()}
    LOG.info("Eligible BBS: %s", len(eligible))

    missing_bbs = sorted(eligible - complete_bbs)
    LOG.info("Eligible but not in tr_bbs_header (incomplete candidates): %s", len(missing_bbs))
    if not missing_bbs:
        return []

    by_bbs: dict[int, dict] = {}
    # Load header fields + missing diameters in chunks
    for i in range(0, len(missing_bbs), 100):
        chunk = missing_bbs[i : i + 100]
        in_list = ",".join(str(x) for x in chunk)
        detail_inner = f"""
            SELECT
                pp.id_pedido_produccion AS bbs_no,
                pp.id_obra AS jobsite_no,
                pp.descripcion AS order_desc,
                CASE WHEN js.id_tipo_forjado IN (2, 3, 7) THEN 'PRIVATE' ELSE 'IAT' END AS jobsite_type,
                js.nombre AS jobsite_name,
                js.arquitecto AS client,
                pp.fecha_entrega_prevista AS del_date,
                pp.referencia_1 AS ref_no,
                pp.referencia_2 AS bbs_po_no,
                ppl.cal_nombre_fa AS diameter,
                (SELECT COUNT(*) FROM pedidos_produccion_traza tr
                  WHERE tr.id_pedido_produccion_lin = ppl.id_pedido_produccion_lin) AS traza_cnt
            FROM pedidos_produccion pp
            JOIN obras js ON pp.id_obra = js.id_obra
            JOIN pedidos_produccion_lin ppl ON ppl.id_pedido_produccion = pp.id_pedido_produccion
            WHERE pp.id_pedido_produccion IN ({in_list})
              AND ppl.cal_tipo_acero_fa <> '460'
              AND ppl.cal_mm_fa <> 0
        """
        detail_sql = "SELECT * FROM OPENQUERY(TVSC, '" + detail_inner.replace("'", "''") + "')"
        cur.execute(detail_sql)
        cols = [c[0].lower() for c in cur.description]
        # diameters that have zero traza across all lines of that diameter
        dia_traza: dict[int, dict[str, int]] = {}
        for row in cur.fetchall():
            r = dict(zip(cols, row))
            bbs = int(r["bbs_no"])
            dia = (r.get("diameter") or "").strip()
            if bbs not in by_bbs:
                by_bbs[bbs] = {
                    "bbs_no": bbs,
                    "jobsite_no": r.get("jobsite_no"),
                    "order_desc": r.get("order_desc"),
                    "jobsite_type": r.get("jobsite_type"),
                    "jobsite_name": r.get("jobsite_name"),
                    "client": r.get("client"),
                    "del_date": r.get("del_date"),
                    "ref_no": r.get("ref_no"),
                    "bbs_po_no": r.get("bbs_po_no"),
                    "missing_diameters": set(),
                    "dd_no": None,
                    "dd_delivery_date": None,
                }
            if dia:
                dia_traza.setdefault(bbs, {})
                dia_traza[bbs][dia] = dia_traza[bbs].get(dia, 0) + int(r.get("traza_cnt") or 0)

        for bbs, dias in dia_traza.items():
            for dia, cnt in dias.items():
                if cnt <= 0:
                    by_bbs[bbs]["missing_diameters"].add(dia)

        dd_inner = f"""
            SELECT ddd.id_pedido_produccion AS bbs_no,
                   ddh.numero_albaran AS dd_no,
                   ddh.fecha_albaran AS dd_delivery_date
            FROM albaranes_salida ddh
            JOIN albaranes_salida_lin ddd
              ON ddh.id_albaran_salida = ddd.id_albaran_salida
            WHERE ddd.id_pedido_produccion IN ({in_list})
        """
        dd_sql = "SELECT * FROM OPENQUERY(TVSC, '" + dd_inner.replace("'", "''") + "')"
        try:
            cur.execute(dd_sql)
            dcols = [c[0].lower() for c in cur.description]
            for row in cur.fetchall():
                d = dict(zip(dcols, row))
                bbs = int(d["bbs_no"])
                if bbs in by_bbs and by_bbs[bbs]["dd_no"] is None:
                    by_bbs[bbs]["dd_no"] = d.get("dd_no")
                    by_bbs[bbs]["dd_delivery_date"] = d.get("dd_delivery_date")
        except Exception as exc:
            LOG.warning("DD lookup chunk failed: %s", exc)

        LOG.info("Processed incomplete chunk %s-%s", i + 1, min(i + 100, len(missing_bbs)))

    out = []
    for bbs, info in by_bbs.items():
        missing = sorted(info["missing_diameters"])
        # If we couldn't detect diameter gaps, still mark incomplete (absent from DW)
        info["missing_diameters"] = ",".join(missing) if missing else "UNKNOWN"
        info["tr_status"] = "incomplete"
        out.append(info)
    return out


def fetch_complete_bbs_from_dw(cn) -> set[int]:
    cur = cn.cursor()
    cur.execute("SELECT bbs_no FROM tr_bbs_header")
    return {int(r[0]) for r in cur.fetchall()}


def rebuild(engine, incomplete: list[dict], complete_bbs: set[int]):
    """Only store incomplete in bbs_tr_status; list columns default to complete."""
    del complete_bbs

    def has_col(table_name: str, column_name: str) -> bool:
        q = text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:tbl AND column_name=:col
            LIMIT 1
            """
        )
        with engine.connect() as c:
            return c.execute(q, {"tbl": table_name, "col": column_name}).fetchone() is not None

    bbs_has_status = has_col("bbs_dd", "tr_status")
    dedup_has_status = has_col("TR_Report_Deduplication", "tr_status")

    with engine.begin() as conn:
        # Replace status table contents atomically via upsert; avoid long full-table locks.
        conn.execute(text("DELETE FROM bbs_tr_status"))

        for info in incomplete:
            bbs = int(info["bbs_no"])
            missing = info.get("missing_diameters") or ""
            conn.execute(
                text(
                    """
                    INSERT INTO bbs_tr_status (bbs_no, tr_status, missing_diameters, updated_at)
                    VALUES (:bbs, 'incomplete', :missing, NOW())
                    ON CONFLICT (bbs_no) DO UPDATE SET
                        tr_status = EXCLUDED.tr_status,
                        missing_diameters = EXCLUDED.missing_diameters,
                        updated_at = NOW()
                    """
                ),
                {"bbs": bbs, "missing": missing},
            )

            if bbs_has_status:
                upd = conn.execute(
                    text(
                        """
                        UPDATE bbs_dd
                        SET tr_status = 'incomplete', missing_diameters = :missing
                        WHERE bbs_no = :bbs_no
                        """
                    ),
                    {"bbs_no": bbs, "missing": missing},
                )
            else:
                upd = conn.execute(
                    text("SELECT 1 FROM bbs_dd WHERE bbs_no = :bbs_no"),
                    {"bbs_no": bbs},
                )
                # rowcount for SELECT is not reliable across drivers; re-check existence
                exists = conn.execute(
                    text("SELECT 1 FROM bbs_dd WHERE bbs_no = :bbs_no LIMIT 1"),
                    {"bbs_no": bbs},
                ).fetchone()
                class _RC:
                    rowcount = 1 if exists else 0
                upd = _RC()
            if getattr(upd, "rowcount", 0) == 0:
                if bbs_has_status:
                    conn.execute(
                        text(
                            """
                            INSERT INTO bbs_dd (
                                bbs_no, order_desc, jobsite_no, jobsite_type,
                                dd_no, dd_delivery_date, tr_status, missing_diameters
                            ) VALUES (
                                :bbs_no, :order_desc, :jobsite_no, :jobsite_type,
                                :dd_no, :dd_delivery_date, 'incomplete', :missing
                            )
                            """
                        ),
                        {
                            "bbs_no": bbs,
                            "order_desc": info.get("order_desc"),
                            "jobsite_no": info.get("jobsite_no"),
                            "jobsite_type": info.get("jobsite_type"),
                            "dd_no": str(info["dd_no"]) if info.get("dd_no") is not None else None,
                            "dd_delivery_date": info.get("dd_delivery_date"),
                            "missing": missing,
                        },
                    )
                else:
                    conn.execute(
                        text(
                            """
                            INSERT INTO bbs_dd (
                                bbs_no, order_desc, jobsite_no, jobsite_type,
                                dd_no, dd_delivery_date
                            ) VALUES (
                                :bbs_no, :order_desc, :jobsite_no, :jobsite_type,
                                :dd_no, :dd_delivery_date
                            )
                            """
                        ),
                        {
                            "bbs_no": bbs,
                            "order_desc": info.get("order_desc"),
                            "jobsite_no": info.get("jobsite_no"),
                            "jobsite_type": info.get("jobsite_type"),
                            "dd_no": str(info["dd_no"]) if info.get("dd_no") is not None else None,
                            "dd_delivery_date": info.get("dd_delivery_date"),
                        },
                    )

            if dedup_has_status:
                upd2 = conn.execute(
                    text(
                        """
                        UPDATE "TR_Report_Deduplication"
                        SET tr_status = 'incomplete', missing_diameters = :missing
                        WHERE "Order_No" = :order_no
                        """
                    ),
                    {"order_no": bbs, "missing": missing},
                )
            else:
                exists2 = conn.execute(
                    text(
                        """
                        SELECT 1 FROM "TR_Report_Deduplication"
                        WHERE "Order_No" = :order_no LIMIT 1
                        """
                    ),
                    {"order_no": bbs},
                ).fetchone()
                class _RC2:
                    rowcount = 1 if exists2 else 0
                upd2 = _RC2()
            if getattr(upd2, "rowcount", 0) == 0:
                if dedup_has_status:
                    conn.execute(
                        text(
                            """
                            INSERT INTO "TR_Report_Deduplication" (
                                "Order_No", "Job_No", "Jobsite", "Order_Description", "Client",
                                "Jobsite_Type", "Del_Date", "Ref_No", "PO_No",
                                "Grade", "Wt", "rm_dn_no",
                                tr_status, missing_diameters
                            ) VALUES (
                                :order_no, :job_no, :jobsite, :order_desc, :client,
                                :jobsite_type, :del_date, :ref_no, :po_no,
                                NULL, NULL, NULL,
                                'incomplete', :missing
                            )
                            """
                        ),
                        {
                            "order_no": bbs,
                            "job_no": str(info["jobsite_no"])
                            if info.get("jobsite_no") is not None
                            else None,
                            "jobsite": info.get("jobsite_name"),
                            "order_desc": info.get("order_desc"),
                            "client": info.get("client"),
                            "jobsite_type": info.get("jobsite_type"),
                            "del_date": info.get("del_date"),
                            "ref_no": info.get("ref_no"),
                            "po_no": info.get("bbs_po_no"),
                            "missing": missing,
                        },
                    )
                else:
                    conn.execute(
                        text(
                            """
                            INSERT INTO "TR_Report_Deduplication" (
                                "Order_No", "Job_No", "Jobsite", "Order_Description", "Client",
                                "Jobsite_Type", "Del_Date", "Ref_No", "PO_No",
                                "Grade", "Wt", "rm_dn_no"
                            ) VALUES (
                                :order_no, :job_no, :jobsite, :order_desc, :client,
                                :jobsite_type, :del_date, :ref_no, :po_no,
                                NULL, NULL, NULL
                            )
                            """
                        ),
                        {
                            "order_no": bbs,
                            "job_no": str(info["jobsite_no"])
                            if info.get("jobsite_no") is not None
                            else None,
                            "jobsite": info.get("jobsite_name"),
                            "order_desc": info.get("order_desc"),
                            "client": info.get("client"),
                            "jobsite_type": info.get("jobsite_type"),
                            "del_date": info.get("del_date"),
                            "ref_no": info.get("ref_no"),
                            "po_no": info.get("bbs_po_no"),
                        },
                    )

        # Clear stale incomplete flags on list tables (only previously incomplete rows)
        if bbs_has_status:
            conn.execute(
                text(
                    """
                    UPDATE bbs_dd
                    SET tr_status = 'complete', missing_diameters = NULL
                    WHERE tr_status = 'incomplete'
                      AND bbs_no NOT IN (SELECT bbs_no FROM bbs_tr_status WHERE tr_status = 'incomplete')
                    """
                )
            )
        if dedup_has_status:
            conn.execute(
                text(
                    """
                    UPDATE "TR_Report_Deduplication"
                    SET tr_status = 'complete', missing_diameters = NULL
                    WHERE tr_status = 'incomplete'
                      AND "Order_No" NOT IN (
                          SELECT bbs_no FROM bbs_tr_status WHERE tr_status = 'incomplete'
                      )
                    """
                )
            )


def main() -> int:
    setup_logging()
    if not is_postgres():
        LOG.error("This step requires PostgreSQL")
        return 1

    engine = create_engine(sqlalchemy_postgres_dsn(), pool_pre_ping=True)
    LOG.info("Ensuring PG tables/columns...")
    ensure_pg_tables(engine)

    LOG.info("Connecting SQL Server...")
    cn = mssql_connect()
    try:
        LOG.info("Loading complete BBS from tr_bbs_header...")
        complete = fetch_complete_bbs_from_dw(cn)
        LOG.info("Complete candidates: %s", len(complete))

        LOG.info("Detecting incomplete BBS from source (OPENQUERY)...")
        incomplete = fetch_incomplete_from_source(cn, complete)
        LOG.info("Incomplete BBS: %s", len(incomplete))
        if incomplete:
            sample = incomplete[:5]
            for s in sample:
                LOG.info(
                    "  incomplete %s missing=%s job=%s",
                    s["bbs_no"],
                    s["missing_diameters"],
                    s.get("jobsite_no"),
                )
    finally:
        cn.close()

    LOG.info("Writing bbs_tr_status + upserting list rows...")
    rebuild(engine, incomplete, complete)
    incomplete_nos = {int(x["bbs_no"]) for x in incomplete}
    LOG.info(
        "Done. incomplete=%s complete=%s",
        len(incomplete),
        len(complete - incomplete_nos),
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
