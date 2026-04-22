"""Audit employee and payroll seeding completeness."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///.seeker_runtime/data/seeker_accounting.db")
with engine.connect() as conn:
    def q(sql):
        return conn.execute(text(sql)).fetchall()
    def q1(sql):
        return conn.execute(text(sql)).one()

    # --- Employees ---
    emps = q("SELECT id, employee_number, first_name, last_name, is_active, hire_date, termination_date, department_id, position_id FROM employees ORDER BY id")
    print(f"=== EMPLOYEES: {len(emps)} ===")
    for e in emps:
        print(f"  {e[1]} {e[2]} {e[3]} active={e[4]} hired={e[5]} term={e[6]} dept={e[7]} pos={e[8]}")

    # Employee active status
    statuses = q("SELECT DISTINCT is_active, COUNT(*) FROM employees GROUP BY is_active")
    print(f"\nEmployee active flags: {[(s[0], s[1]) for s in statuses]}")

    # --- Departments ---
    depts = q("SELECT id, code, name FROM departments ORDER BY id")
    print(f"\n=== DEPARTMENTS: {len(depts)} ===")
    for d in depts:
        print(f"  {d[0]}: {d[1]} - {d[2]}")

    # --- Positions ---
    positions = q("SELECT id, code, name FROM positions ORDER BY id")
    print(f"\n=== POSITIONS: {len(positions)} ===")
    for p in positions:
        print(f"  {p[0]}: {p[1]} - {p[2]}")

    # --- Company Payroll Settings ---
    cps = q("SELECT * FROM company_payroll_settings")
    print(f"\n=== COMPANY PAYROLL SETTINGS: {len(cps)} ===")
    for c in cps:
        print(f"  {c}")

    # --- Payroll Components ---
    comps = q("SELECT id, code, name, component_type, is_active FROM payroll_components ORDER BY id")
    print(f"\n=== PAYROLL COMPONENTS: {len(comps)} ===")
    for c in comps:
        print(f"  {c[0]}: {c[1]} - {c[2]} type={c[3]} active={c[4]}")

    # --- Payroll Rule Sets ---
    rules = q("SELECT id, code, name, is_active FROM payroll_rule_sets ORDER BY id")
    print(f"\n=== PAYROLL RULE SETS: {len(rules)} ===")
    for r in rules:
        print(f"  {r[0]}: {r[1]} - {r[2]} active={r[3]}")

    # --- Payroll Rule Brackets ---
    brackets = q("SELECT rule_set_id, COUNT(*) FROM payroll_rule_brackets GROUP BY rule_set_id")
    print(f"\n=== PAYROLL RULE BRACKETS: {len(brackets)} rule sets with brackets ===")
    for b in brackets:
        print(f"  rule_set_id={b[0]}: {b[1]} brackets")

    # --- Compensation Profiles ---
    profiles = q("SELECT id, employee_id, base_salary, effective_date, is_current FROM employee_compensation_profiles ORDER BY employee_id")
    print(f"\n=== COMPENSATION PROFILES: {len(profiles)} ===")
    for p in profiles:
        print(f"  profile {p[0]}: emp={p[1]} salary={p[2]} effective={p[3]} current={p[4]}")

    # --- Component Assignments ---
    assigns = q("SELECT employee_id, COUNT(*) FROM employee_component_assignments GROUP BY employee_id")
    print(f"\n=== COMPONENT ASSIGNMENTS: {len(assigns)} employees with assignments ===")
    for a in assigns:
        print(f"  emp_id={a[0]}: {a[1]} assignments")

    # --- Payroll Runs ---
    runs = q("SELECT id, run_code, period_start, period_end, status_code, total_gross, total_net FROM payroll_runs ORDER BY id")
    print(f"\n=== PAYROLL RUNS: {len(runs)} ===")
    for r in runs:
        print(f"  {r[1]} [{r[4]}] {r[2]} to {r[3]} gross={r[5]} net={r[6]}")

    # --- Payroll Run Employees ---
    run_emps = q("SELECT payroll_run_id, COUNT(*), SUM(gross_pay), SUM(net_pay) FROM payroll_run_employees GROUP BY payroll_run_id")
    print(f"\n=== PAYROLL RUN EMPLOYEES: {len(run_emps)} runs ===")
    for r in run_emps:
        print(f"  run_id={r[0]}: {r[1]} employees, gross={r[2]}, net={r[3]}")

    # --- Payroll Run Lines ---
    run_lines = q("SELECT payroll_run_id, COUNT(*) FROM payroll_run_lines GROUP BY payroll_run_id")
    print(f"\n=== PAYROLL RUN LINES: {len(run_lines)} runs ===")
    for r in run_lines:
        print(f"  run_id={r[0]}: {r[1]} lines")

    # --- Payroll Input Batches ---
    inputs = q("SELECT id, batch_code, status_code FROM payroll_input_batches ORDER BY id")
    print(f"\n=== PAYROLL INPUT BATCHES: {len(inputs)} ===")
    for i in inputs:
        print(f"  {i[1]} [{i[2]}]")

    # --- Payment Records ---
    payments = q("SELECT COUNT(*) FROM payroll_payment_records")
    print(f"\n=== PAYROLL PAYMENT RECORDS: {payments[0][0]} ===")

    # --- Remittance Batches ---
    remittances = q("SELECT id, batch_code, status_code FROM payroll_remittance_batches ORDER BY id")
    print(f"\n=== REMITTANCE BATCHES: {len(remittances)} ===")
    for r in remittances:
        print(f"  {r[1]} [{r[2]}]")

    # --- Project allocations on payroll JEs ---
    payroll_jes = q("""
        SELECT COUNT(*), COUNT(jel.project_id)
        FROM journal_entry_lines jel
        JOIN journal_entries je ON je.id = jel.journal_entry_id
        WHERE je.source_module_code = 'payroll' AND je.status_code = 'POSTED'
    """)
    print(f"\n=== PAYROLL JE LINES: total={payroll_jes[0][0]}, with project={payroll_jes[0][1]} ===")
