"""Audit employee and payroll seeding - schema-safe version."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///.seeker_runtime/data/seeker_accounting.db")
with engine.connect() as conn:
    def q(sql):
        return conn.execute(text(sql)).fetchall()

    def schema(table):
        rows = q(f"PRAGMA table_info({table})")
        cols = [r[1] for r in rows]
        return cols

    # Show schemas for key tables
    for tbl in ["payroll_components", "payroll_rule_sets", "payroll_rule_brackets",
                "employee_compensation_profiles", "employee_component_assignments",
                "payroll_runs", "payroll_run_employees", "payroll_run_lines",
                "payroll_input_batches", "payroll_input_lines",
                "payroll_payment_records", "payroll_remittance_batches", "payroll_remittance_lines",
                "payroll_run_employee_project_allocations"]:
        cols = schema(tbl)
        print(f"{tbl}: {cols}")

    print("\n" + "="*60)

    # --- Payroll Components ---
    comps = q("SELECT * FROM payroll_components ORDER BY id")
    print(f"\n=== PAYROLL COMPONENTS: {len(comps)} ===")
    comp_cols = schema("payroll_components")
    for c in comps:
        d = dict(zip(comp_cols, c))
        print(f"  {d.get('id')}: {d.get('component_code', d.get('code', '?'))} - {d.get('name', d.get('component_name', '?'))} type={d.get('component_type', '?')} active={d.get('is_active', '?')}")

    # --- Payroll Rule Sets ---
    rules = q("SELECT * FROM payroll_rule_sets ORDER BY id")
    print(f"\n=== PAYROLL RULE SETS: {len(rules)} ===")
    rule_cols = schema("payroll_rule_sets")
    for r in rules:
        d = dict(zip(rule_cols, r))
        print(f"  {d}")

    # --- Payroll Rule Brackets ---
    brackets = q("SELECT rule_set_id, COUNT(*) FROM payroll_rule_brackets GROUP BY rule_set_id")
    print(f"\n=== PAYROLL RULE BRACKETS: {len(brackets)} rule sets ===")
    for b in brackets:
        print(f"  rule_set_id={b[0]}: {b[1]} brackets")

    # --- Compensation Profiles ---
    profiles = q("SELECT * FROM employee_compensation_profiles ORDER BY employee_id")
    print(f"\n=== COMPENSATION PROFILES: {len(profiles)} ===")
    prof_cols = schema("employee_compensation_profiles")
    for p in profiles:
        d = dict(zip(prof_cols, p))
        print(f"  emp={d.get('employee_id')} salary={d.get('base_salary')} effective={d.get('effective_date')} current={d.get('is_current')}")

    # --- Component Assignments ---
    assigns = q("SELECT * FROM employee_component_assignments ORDER BY employee_id")
    print(f"\n=== COMPONENT ASSIGNMENTS: {len(assigns)} ===")
    if assigns:
        assign_cols = schema("employee_component_assignments")
        for a in assigns[:10]:
            d = dict(zip(assign_cols, a))
            print(f"  {d}")

    # --- Payroll Runs ---
    runs = q("SELECT * FROM payroll_runs ORDER BY id")
    print(f"\n=== PAYROLL RUNS: {len(runs)} ===")
    if runs:
        run_cols = schema("payroll_runs")
        for r in runs:
            d = dict(zip(run_cols, r))
            print(f"  {d.get('run_code', '?')} [{d.get('status_code', '?')}] {d.get('period_start')} to {d.get('period_end')} gross={d.get('total_gross')} net={d.get('total_net')}")

    # --- Payroll Run Employees ---
    run_emps = q("SELECT payroll_run_id, COUNT(*) FROM payroll_run_employees GROUP BY payroll_run_id")
    print(f"\n=== PAYROLL RUN EMPLOYEES: {len(run_emps)} runs ===")
    for r in run_emps:
        print(f"  run_id={r[0]}: {r[1]} employees")

    # --- Payroll Run Lines ---
    run_lines = q("SELECT payroll_run_id, COUNT(*) FROM payroll_run_lines GROUP BY payroll_run_id")
    print(f"\n=== PAYROLL RUN LINES: {len(run_lines)} runs ===")
    for r in run_lines:
        print(f"  run_id={r[0]}: {r[1]} lines")

    # --- Project Allocations on Payroll Runs ---
    allocs = q("SELECT * FROM payroll_run_employee_project_allocations")
    print(f"\n=== PAYROLL PROJECT ALLOCATIONS: {len(allocs)} ===")

    # --- Input Batches ---
    inputs = q("SELECT * FROM payroll_input_batches ORDER BY id")
    print(f"\n=== PAYROLL INPUT BATCHES: {len(inputs)} ===")

    # --- Payment Records ---
    payments = q("SELECT COUNT(*) FROM payroll_payment_records")
    print(f"\n=== PAYROLL PAYMENT RECORDS: {payments[0][0]} ===")

    # --- Remittance Batches ---
    remittances = q("SELECT * FROM payroll_remittance_batches ORDER BY id")
    print(f"\n=== REMITTANCE BATCHES: {len(remittances)} ===")
