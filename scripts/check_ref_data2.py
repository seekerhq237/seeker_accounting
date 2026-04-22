"""Check remaining reference data."""
import sqlite3

conn = sqlite3.connect(".seeker_runtime/data/seeker_accounting.db")
c = conn.cursor()

# Depreciation methods columns
cols = c.execute("PRAGMA table_info(depreciation_methods)").fetchall()
print("=== depreciation_methods columns ===")
for col in cols:
    print(col)

print("\n=== Depreciation methods ===")
for row in c.execute("SELECT * FROM depreciation_methods LIMIT 5").fetchall():
    print(row)

print("\n=== Tax codes ===")
cols = c.execute("PRAGMA table_info(tax_codes)").fetchall()
for col in cols:
    print(col)

print("\n=== Tax codes data ===")
for row in c.execute("SELECT * FROM tax_codes LIMIT 5").fetchall():
    print(row)

print("\n=== payment_terms columns ===")
cols = c.execute("PRAGMA table_info(payment_terms)").fetchall()
for col in cols:
    print(col)

print("\n=== Payment terms data ===")
for row in c.execute("SELECT * FROM payment_terms LIMIT 5").fetchall():
    print(row)

# Check how many accounts exist per company
print("\n=== Accounts per company ===")
for row in c.execute("SELECT company_id, COUNT(*) FROM accounts GROUP BY company_id").fetchall():
    print(f"  Company {row[0]}: {row[1]} accounts")

# Get some key account IDs for company_id=3 (Seeker)
print("\n=== Key accounts for company 3 ===")
for code in ['411', '401', '521', '571', '601', '602', '701', '311', '6011', '6022', '24']:
    row = c.execute("SELECT id, account_code, account_name FROM accounts WHERE company_id=3 AND account_code=?", (code,)).fetchone()
    if row:
        print(f"  {row}")

# Role permissions count per role
print("\n=== Role permissions count ===")
for row in c.execute("SELECT r.code, COUNT(*) FROM role_permissions rp JOIN roles r ON r.id=rp.role_id GROUP BY r.code").fetchall():
    print(f"  {row[0]}: {row[1]}")

# Document sequences  
print("\n=== Document sequences columns ===")
cols = c.execute("PRAGMA table_info(document_sequences)").fetchall()
for col in cols:
    print(col)

conn.close()
