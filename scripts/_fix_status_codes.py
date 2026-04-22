"""One-time fix: uppercase fiscal year/period status_code values in DB."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///.seeker_runtime/data/seeker_accounting.db")
with engine.begin() as conn:
    r1 = conn.execute(text("UPDATE fiscal_years SET status_code = UPPER(status_code) WHERE status_code != UPPER(status_code)"))
    print(f"Fiscal years updated: {r1.rowcount}")
    r2 = conn.execute(text("UPDATE fiscal_periods SET status_code = UPPER(status_code) WHERE status_code != UPPER(status_code)"))
    print(f"Fiscal periods updated: {r2.rowcount}")
    # Verify
    rows = conn.execute(text("SELECT DISTINCT status_code FROM fiscal_years")).fetchall()
    print(f"Fiscal year statuses: {[r[0] for r in rows]}")
    rows = conn.execute(text("SELECT DISTINCT status_code FROM fiscal_periods")).fetchall()
    print(f"Fiscal period statuses: {[r[0] for r in rows]}")
