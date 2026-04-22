"""Quick check of existing database state."""
import sqlite3

conn = sqlite3.connect("seeker_accounting.db")
c = conn.cursor()

tables = c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
print("Tables:", [t[0] for t in tables])
print()

for q, label in [
    ("SELECT id, legal_name FROM companies", "Companies"),
    ("SELECT id, username, display_name FROM users", "Users"),
    ("SELECT id, code, name FROM roles", "Roles"),
    ("SELECT id, code, name FROM account_classes", "AccountClasses"),
    ("SELECT id, code, name FROM account_types", "AccountTypes"),
    ("SELECT COUNT(*) FROM permissions", "Permissions count"),
    ("SELECT COUNT(*) FROM accounts", "Accounts count"),
    ("SELECT COUNT(*) FROM depreciation_methods", "DepreciationMethods count"),
    ("SELECT COUNT(*) FROM fiscal_years", "FiscalYears count"),
    ("SELECT COUNT(*) FROM customers", "Customers count"),
    ("SELECT COUNT(*) FROM suppliers", "Suppliers count"),
    ("SELECT COUNT(*) FROM employees", "Employees count"),
    ("SELECT COUNT(*) FROM journal_entries", "JournalEntries count"),
    ("SELECT COUNT(*) FROM sales_invoices", "SalesInvoices count"),
    ("SELECT COUNT(*) FROM purchase_bills", "PurchaseBills count"),
    ("SELECT COUNT(*) FROM assets", "Assets count"),
    ("SELECT COUNT(*) FROM contracts", "Contracts count"),
    ("SELECT COUNT(*) FROM projects", "Projects count"),
    ("SELECT COUNT(*) FROM items", "Items count"),
    ("SELECT COUNT(*) FROM financial_accounts", "FinancialAccounts count"),
    ("SELECT id, code, name FROM payment_terms WHERE company_id IS NOT NULL LIMIT 5", "PaymentTerms sample"),
    ("SELECT id, code, name, rate FROM tax_codes LIMIT 5", "TaxCodes sample"),
]:
    try:
        rows = c.execute(q).fetchall()
        print(f"{label}: {rows}")
    except Exception as e:
        print(f"{label}: ERROR - {e}")

conn.close()
