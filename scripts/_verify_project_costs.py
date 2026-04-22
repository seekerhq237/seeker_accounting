"""Verify project cost allocations."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///.seeker_runtime/data/seeker_accounting.db")
with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT p.project_code, p.project_name,
               COUNT(jel.id) as lines,
               SUM(jel.debit_amount) as total_cost
        FROM journal_entry_lines jel
        JOIN projects p ON p.id = jel.project_id
        JOIN journal_entries je ON je.id = jel.journal_entry_id
        WHERE je.status_code = 'POSTED' AND jel.debit_amount > 0
        GROUP BY p.id
        ORDER BY total_cost DESC
        LIMIT 15
    """)).fetchall()
    print("Top 15 projects by cost:")
    for r in rows:
        print(f"  {r[0]} {r[1][:35]:35s}  lines={r[2]:3d}  cost={r[3]:>14,}")

    rows2 = conn.execute(text("""
        SELECT pcc.code, pcc.name, COUNT(jel.id), SUM(jel.debit_amount)
        FROM journal_entry_lines jel
        JOIN project_cost_codes pcc ON pcc.id = jel.project_cost_code_id
        JOIN journal_entries je ON je.id = jel.journal_entry_id
        WHERE je.status_code = 'POSTED' AND jel.debit_amount > 0
        GROUP BY pcc.id
        ORDER BY SUM(jel.debit_amount) DESC
    """)).fetchall()
    print("\nCost by cost code:")
    for r in rows2:
        print(f"  {r[0]:4s} {r[1]:25s}  lines={r[2]:3d}  cost={r[3]:>14,}")

    total = conn.execute(text("""
        SELECT COUNT(*), SUM(debit_amount) FROM journal_entry_lines WHERE project_id IS NOT NULL AND debit_amount > 0
    """)).one()
    print(f"\nTotal allocated: {total[0]} lines, {total[1]:,} XAF")
