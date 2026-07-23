#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch dbo.sync_tr_data: keep BBS with missing TR in DW tables
(no longer DELETE whole BBS). Status is computed later into PostgreSQL bbs_tr_status.
"""

from __future__ import annotations

import os
import sys

import pyodbc

NEW_BLOCK = r"""
print('start: get list of BBS with missing TR (informational only; BBS are KEPT in DW)')
	-- Kept for ops visibility in sync log; no longer used to purge temp tables.
	SELECT DISTINCT tls.bbs_no
	INTO #bbs_with_missing_tr
	FROM #t_tr_line_size tls
	LEFT JOIN #t_tr_line_detail tld
		ON tls.bbs_no = tld.bbs_no
			AND tls.diameter = tld.diameter
	WHERE tld.product IS NULL

	DECLARE @missing_cnt INT = (SELECT COUNT(*) FROM #bbs_with_missing_tr)
	print('end: get list of BBS with missing TR, count=' + CAST(@missing_cnt AS VARCHAR(20)))
	-- incomplete BBS remain in #t_tr_* / #t_bbs_dd; PG bbs_tr_status marks selectable=false

	-- <<< tr_bbs_header  (KEEP incomplete BBS — do not delete)
	TRUNCATE TABLE tr_bbs_header

	INSERT INTO tr_bbs_header (bbs_no, order_desc, jobsite_no, jobsite_name, jobsite_type,
		main_contractor, delivery_date, bbs_ref_no, bbs_po_no)
	SELECT bbs_no, order_desc, jobsite_no, jobsite_name, jobsite_type,
		main_contractor, delivery_date, bbs_ref_no, bbs_po_no
	FROM #t_tr_bbs_header

	DROP TABLE #t_tr_bbs_header
	-- >>>

	-- <<< tr_line_size  (KEEP incomplete BBS)
	TRUNCATE TABLE tr_line_size

	INSERT INTO tr_line_size (jobsite_no, bbs_no, diameter, wt_ton)
	SELECT jobsite_no, bbs_no, diameter, wt_ton
	FROM #t_tr_line_size

	DROP TABLE #t_tr_line_size
	-- >>>

	-- <<< tr_line_detail
	TRUNCATE TABLE tr_line_detail

	INSERT INTO tr_line_detail ( jobsite_no, bbs_no, diameter,
		product, grade, pattern, mill_cert, test_cert1, test_cert2,
		supplier, stockist_cert, po_no, rm_dn_no )
	SELECT jobsite_no, bbs_no, diameter,
		product, grade, pattern, mill_cert, test_cert1, test_cert2,
		supplier, stockist_cert, po_no, rm_dn_no
	FROM #t_tr_line_detail

	DROP TABLE #t_tr_line_detail
	-- >>>

	-- <<< bbs_dd  (KEEP incomplete BBS)
	TRUNCATE TABLE bbs_dd

	INSERT INTO bbs_dd (bbs_no, order_desc, jobsite_no, jobsite_type,
		dd_no, dd_delivery_date)
	SELECT bbs_no, order_desc, jobsite_no, jobsite_type,
		dd_no, dd_delivery_date
	FROM #t_bbs_dd

	DROP TABLE #t_bbs_dd
	-- >>>

	IF OBJECT_ID('tempdb..#bbs_with_missing_tr') IS NOT NULL DROP TABLE #bbs_with_missing_tr
"""

OLD_START = "print('start: get list of BBS with missing TR')"
OLD_END_MARKER = "\tdrop table #t_bbs_dd\n\t-- >>>"


def connect():
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
    return pyodbc.connect(conn_str, timeout=60, autocommit=True)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cn = connect()
    cur = cn.cursor()

    cur.execute("SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.sync_tr_data'))")
    defn = cur.fetchone()[0]
    if not defn:
        print("ERROR: cannot read sync_tr_data definition")
        return 1

    norm = defn.replace("\r\n", "\n")
    if "KEEP incomplete BBS" in norm and "do not delete" in norm:
        print("sync_tr_data already patched; skip")
        cn.close()
        return 0

    start = norm.find(OLD_START)
    end = norm.find(OLD_END_MARKER)
    if start < 0 or end < 0:
        print("ERROR: markers not found", start, end)
        return 1
    end = end + len(OLD_END_MARKER)

    new_defn = norm[:start] + NEW_BLOCK.strip("\n") + "\n\t\n" + norm[end:]
    stripped = new_defn.lstrip()
    upper = stripped.upper()
    if upper.startswith("CREATE PROCEDURE"):
        new_defn = "ALTER PROCEDURE" + stripped[len("CREATE PROCEDURE") :]
    elif upper.startswith("CREATE PROC"):
        new_defn = "ALTER PROC" + stripped[len("CREATE PROC") :]

    new_defn = new_defn.replace(
        "BBS with missing TR will not sync to DW.  Only BBS with DD will sync to DW.",
        "BBS with missing TR still sync to DW; UI marks them incomplete via PG bbs_tr_status.",
    )

    out = os.path.join(os.path.dirname(__file__), "_sync_tr_data_patched.sql")
    with open(out, "w", encoding="utf-8") as f:
        f.write(new_defn)
    print("Wrote preview", out)

    print("Altering dbo.sync_tr_data ...")
    try:
        cur.execute(new_defn)
        print("OK ALTER sync_tr_data")
    except Exception as exc:
        print("ALTER failed:", exc)
        return 1

    cur.execute("SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.sync_tr_data'))")
    check = (cur.fetchone()[0] or "").replace("\r\n", "\n")
    print("has KEEP incomplete:", "KEEP incomplete BBS" in check)
    print(
        "still deletes from #t_tr_bbs_header via missing list:",
        "delete t\n\tfrom #t_tr_bbs_header t\n\tjoin #bbs_with_missing_tr" in check,
    )
    cn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
