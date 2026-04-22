import sqlite3

conn = sqlite3.connect(".seeker_runtime/data/seeker_accounting.db")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('sales_orders', 'sales_order_lines')").fetchall()
print("Tables to drop:", tables)
conn.execute("DROP TABLE IF EXISTS sales_order_lines")
conn.execute("DROP TABLE IF EXISTS sales_orders")
conn.commit()
conn.close()
print("Done - cleaned partial migration state")
