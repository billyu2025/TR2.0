import sqlite3, os, re

dbs = [r'C:\TR-master\TR database\data_3years.db', r'C:\TR-master\TR UI\backend\tr_system.db']
needles = ['SS79853', 'SS79851']

def iter_tables(conn):
    cur = conn.cursor()
    cur.execute('select name from sqlite_master where type=\'table\' and name not like \"sqlite_%\"')
    return [r[0] for r in cur.fetchall()]

def table_info(conn, t):
    cur = conn.cursor()
    cur.execute(f'pragma table_info({t})')
    return [(r[1], r[2] or '') for r in cur.fetchall()]

def find_matches(db_path):
    if not os.path.exists(db_path):
        print('DB missing:', db_path)
        return
    print('\n' + '=' * 90)
    print('DB:', db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    tables = iter_tables(conn)
    print('tables:', len(tables))

    for needle in needles:
        print('\n-- Searching', needle)
        found_any = False
        for t in tables:
            cols = table_info(conn, t)
            for c, typ in cols:
                tl = (typ or '').lower()
                if tl and not any(k in tl for k in ['char', 'text', 'clob', 'json', 'varchar']):
                    if not re.search(r'(no|id|code|name|report|dn|ss|heat|stock)', c, re.I):
                        continue
                try:
                    cur = conn.cursor()
                    cur.execute(f'select * from {t} where cast({c} as text) like ? limit 5', (f'%{needle}%',))
                    rows = cur.fetchall()
                except Exception:
                    continue

                if rows:
                    found_any = True
                    print(f'  table={t} col={c} matches={len(rows)}')
                    for r in rows[:2]:
                        keys = list(r.keys())
                        preferred = [k for k in keys if re.search(r'stockist|dn|ss|no|id|report', k, re.I)]
                        show = (preferred[:12] or keys[:12])
                        print('    ' + ', '.join(f'{k}={r[k]}' for k in show))

        if not found_any:
            print('  (no hits)')

    conn.close()

for db in dbs:
    find_matches(db)
