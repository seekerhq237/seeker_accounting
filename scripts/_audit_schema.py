"""Dump all table columns from the DB for merge audit."""
from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///.seeker_runtime/data/seeker_accounting.db")
with engine.connect() as c:
    tables = [r[0] for r in c.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")).fetchall()]
    for t in tables:
        cols = [r[1] for r in c.execute(text(f"PRAGMA table_info({t})")).fetchall()]
        print(f"{t}: {cols}")
