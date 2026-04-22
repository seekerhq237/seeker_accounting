"""One-time fix: uppercase journal_entry status_code values in DB."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///.seeker_runtime/data/seeker_accounting.db")
with engine.begin() as conn:
    r = conn.execute(text("UPDATE journal_entries SET status_code = UPPER(status_code) WHERE status_code != UPPER(status_code)"))
    print(f"Journal entries updated: {r.rowcount}")
    rows = conn.execute(text("SELECT DISTINCT status_code, COUNT(*) FROM journal_entries GROUP BY status_code")).fetchall()
    print(f"Journal entry statuses now: {[(r[0], r[1]) for r in rows]}")
