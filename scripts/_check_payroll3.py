"""Safe payroll audit using SELECT * and PRAGMA for column discovery."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///.seeker_runtime/data/seeker_accounting.db")
with engine.connect() as conn:
    def q(sql):
        return conn.execute(text(sql)).fetchall()

    def count(tbl):
        return q(f"SELECT COUNT(*) FROM {tbl}")[0][0]

    def show(tbl, limit=5):
        cols = [r[1] for r in q(f"PRAGMA table_info({tbl})")]
        rows = q(f"SELECT * FROM {tbl} LIMIT {limit}")
        print(f"\n--- {tbl}: {count(tbl)} rows  cols={cols}")
        for r in rows:
            d = dict(zip(cols, r))
            # show compact
            print(f"  {d}")

    tables = [
        "employees", "departments", "positions",
        "company_payroll_settings",
        "payroll_components",
        "payroll_rule_sets", "payroll_rule_brackets",
        "employee_compensation_profiles", "employee_component_assignments",
        "payroll_runs", "payroll_run_employees", "payroll_run_lines",
        "payroll_input_batches", "payroll_input_lines",
        "payroll_payment_records",
        "payroll_remittance_batches", "payroll_remittance_lines",
        "payroll_run_employee_project_allocations",
    ]
    for t in tables:
        try:
            show(t, limit=3)
        except Exception as e:
            print(f"\n--- {t}: ERROR {e}")

    # Status code check on payroll_runs
    print("\n\n=== STATUS CODE CHECK ===")
    for tbl in ["payroll_runs", "payroll_run_employees", "payroll_input_batches", "payroll_remittance_batches"]:
        try:
            rows = q(f"SELECT DISTINCT status_code, COUNT(*) FROM {tbl} GROUP BY status_code")
            print(f"{tbl} statuses: {[(r[0], r[1]) for r in rows]}")
        except:
            pass
    for tbl in ["payroll_run_employees"]:
        try:
            rows = q(f"SELECT DISTINCT payment_status_code, COUNT(*) FROM {tbl} GROUP BY payment_status_code")
            print(f"{tbl} payment_statuses: {[(r[0], r[1]) for r in rows]}")
        except:
            pass
