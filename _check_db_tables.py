import sqlite3
conn = sqlite3.connect('seeker_accounting.db')
r = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
tables = [x[0] for x in r]
print(tables[:15])
# Check tax_returns specifically
tax_tables = [t for t in tables if 'tax' in t.lower()]
print('tax tables:', tax_tables)
# Check if is_amended column exists
if 'tax_returns' in tables:
    cols = [row[1] for row in conn.execute("PRAGMA table_info(tax_returns)").fetchall()]
    print('tax_returns columns:', cols)
conn.close()
