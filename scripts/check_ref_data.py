"""Check key reference data for seed script."""
import sqlite3

conn = sqlite3.connect(".seeker_runtime/data/seeker_accounting.db")
c = conn.cursor()

# Account types with IDs
print("=== Account Types ===")
for row in c.execute("SELECT id, code, name, normal_balance, financial_statement_section_code FROM account_types").fetchall():
    print(row)

print("\n=== Sample Accounts (first 30) ===")
for row in c.execute("SELECT id, company_id, account_code, account_name, account_class_id, account_type_id, normal_balance, is_control_account FROM accounts WHERE company_id=3 LIMIT 30").fetchall():
    print(row)

print("\n=== Account code patterns ===")
for row in c.execute("SELECT DISTINCT substr(account_code,1,2), COUNT(*) FROM accounts WHERE company_id=3 GROUP BY substr(account_code,1,2) ORDER BY 1 LIMIT 20").fetchall():
    print(row)

print("\n=== Depreciation methods ===")
for row in c.execute("SELECT id, code, name, method_family FROM depreciation_methods").fetchall():
    print(row)

print("\n=== Tax codes (if any) ===")
for row in c.execute("SELECT * FROM tax_codes LIMIT 5").fetchall():
    print(row)

print("\n=== Payment terms (if any) ===")
for row in c.execute("SELECT * FROM payment_terms LIMIT 5").fetchall():
    print(row)

print("\n=== Document sequences ===")
for row in c.execute("SELECT * FROM document_sequences WHERE company_id=3 LIMIT 10").fetchall():
    print(row)

conn.close()
