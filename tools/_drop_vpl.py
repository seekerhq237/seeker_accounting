"""Drop vat_period_locks table so migration can create it fresh."""
import sqlalchemy as sa

db = ".seeker_runtime/data/seeker_accounting.db"
engine = sa.create_engine(f"sqlite:///{db}")
with engine.begin() as conn:
    result = conn.execute(sa.text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='vat_period_locks'"
    ))
    rows = result.fetchall()
    print("exists:", rows)
    conn.execute(sa.text("DROP TABLE IF EXISTS vat_period_locks"))
    print("dropped (if existed)")
