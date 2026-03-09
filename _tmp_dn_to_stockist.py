import sqlite3

db = r'C:\TR-master\TR database\data_3years.db'
conn = sqlite3.connect(db)
cur = conn.cursor()
for dn in ['SS79853','SS79851']:
    cur.execute('select distinct stockist_cert from TR_Report where rm_dn_no = ?', (dn,))
    certs = [r[0] for r in cur.fetchall()]
    cur.execute('select count(*) from TR_Report where rm_dn_no = ?', (dn,))
    cnt = cur.fetchone()[0]
    print(f'{dn}: rows={cnt}, stockist_cert={certs}')
conn.close()
