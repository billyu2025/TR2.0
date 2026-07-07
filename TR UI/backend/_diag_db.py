import os
import psycopg

dsn = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@127.0.0.1:5432/tr_db")
with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        for tbl in ('"TR_Report"', '"TR_Report_Deduplication"', "bbs_dd", "cert_of_compliance"):
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            print(f"{tbl}: {cur.fetchone()[0]}")
        cur.execute('SELECT MAX("Del_Date") FROM "TR_Report_Deduplication"')
        print("dedup max Del_Date:", cur.fetchone()[0])
