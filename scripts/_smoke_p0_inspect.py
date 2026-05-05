import sqlite3
c = sqlite3.connect(r".seeker_runtime/data/seeker_accounting.db")
new_tables = c.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
    "('inventory_document_types','inventory_reason_codes','item_uom_conversions','item_account_overrides') "
    "ORDER BY name"
).fetchall()
print("NEW TABLES:", new_tables)
print("items cols:", [r[1] for r in c.execute("PRAGMA table_info(items)").fetchall()])
print("inv_doc cols:", [r[1] for r in c.execute("PRAGMA table_info(inventory_documents)").fetchall()])
print("doctype seed count:", c.execute("SELECT count(*) FROM inventory_document_types").fetchone())
print("reason seed count:", c.execute("SELECT count(*) FROM inventory_reason_codes").fetchone())
print("companies:", c.execute("SELECT count(*) FROM companies").fetchone())
