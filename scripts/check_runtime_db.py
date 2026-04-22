"""Check runtime database state."""
import sqlite3

conn = sqlite3.connect(".seeker_runtime/data/seeker_accounting.db")
c = conn.cursor()

tables = c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
print(f"Tables count: {len(tables)}")
for t in tables:
    print(f"  {t[0]}")
print()

for q, label in [
    ("SELECT id, legal_name FROM companies", "Companies"),
    ("SELECT id, username, display_name FROM users", "Users"),
    ("SELECT id, code, name FROM roles", "Roles"),
    ("SELECT id, code, name FROM account_classes", "AccountClasses"),
    ("SELECT id, code, name FROM account_types LIMIT 5", "AccountTypes (top 5)"),
    ("SELECT COUNT(*) FROM permissions", "Permissions count"),
    ("SELECT COUNT(*) FROM accounts", "Accounts count"),
    ("SELECT COUNT(*) FROM depreciation_methods", "DepMethods count"),
    ("SELECT COUNT(*) FROM fiscal_years", "FiscalYears count"),
    ("SELECT COUNT(*) FROM customers", "Customers count"),
    ("SELECT COUNT(*) FROM employees", "Employees count"),
    ("SELECT COUNT(*) FROM journal_entries", "JournalEntries count"),
    ("SELECT COUNT(*) FROM role_permissions", "RolePermissions count"),
    ("SELECT COUNT(*) FROM user_roles", "UserRoles count"),
]:
    try:
        rows = c.execute(q).fetchall()
        print(f"{label}: {rows}")
    except Exception as e:
        print(f"{label}: ERROR - {e}")

conn.close()
