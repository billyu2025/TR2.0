import sqlite3

db = r'C:\TR-master\TR database\data_3years.db'
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("select name from sqlite_master where type='table' and name='PDF_Status'")
print('PDF_Status exists:', cur.fetchone() is not None)
cur.execute("select count(*) from sqlite_master where type='table'")
print('table_count:', cur.fetchone()[0])
cur.execute("select name from sqlite_master where type='table' order by name")
print('tables:', [r[0] for r in cur.fetchall()])
conn.close()
