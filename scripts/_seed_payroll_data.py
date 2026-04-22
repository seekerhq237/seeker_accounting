"""Seed complete payroll data: compensation profiles, component assignments,
payroll runs (with employee lines), and payment records.

This fills the gaps left by the original seed_demo_org.py which only created
aggregate salary JEs in the GL but not the payroll module's own records.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import date, datetime, timedelta
from decimal import Decimal
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from seeker_accounting.db.model_registry import load_model_registry
load_model_registry()

from seeker_accounting.modules.payroll.models.employee_compensation_profile import EmployeeCompensationProfile
from seeker_accounting.modules.payroll.models.employee_component_assignment import EmployeeComponentAssignment
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee
from seeker_accounting.modules.payroll.models.payroll_run_line import PayrollRunLine
from seeker_accounting.modules.payroll.models.payroll_payment_record import PayrollPaymentRecord
from seeker_accounting.modules.payroll.models.payroll_run_employee_project_allocation import PayrollRunEmployeeProjectAllocation

engine = create_engine("sqlite:///.seeker_runtime/data/seeker_accounting.db")
CID = 1
ADMIN_ID = 1
NOW = datetime(2026, 4, 1, 12, 0, 0)

# Employee data: (emp_num, salary, hire_date)
EMP_DATA = [
    ("EMP001", 3_500_000, date(2023, 7, 1)),
    ("EMP002", 2_800_000, date(2023, 7, 1)),
    ("EMP003", 2_800_000, date(2023, 7, 1)),
    ("EMP004", 1_800_000, date(2023, 8, 1)),
    ("EMP005", 1_800_000, date(2023, 9, 1)),
    ("EMP006", 1_500_000, date(2023, 10, 1)),
    ("EMP007", 1_500_000, date(2024, 1, 15)),
    ("EMP008",   800_000, date(2024, 2, 1)),
    ("EMP009",   600_000, date(2024, 3, 1)),
    ("EMP010",   600_000, date(2024, 3, 1)),
    ("EMP011",   550_000, date(2024, 4, 15)),
    ("EMP012", 1_200_000, date(2024, 1, 1)),
    ("EMP013",   450_000, date(2024, 6, 1)),
    ("EMP014", 1_100_000, date(2024, 3, 15)),
    ("EMP015", 1_100_000, date(2024, 7, 1)),
    ("EMP016",   900_000, date(2025, 1, 15)),
    ("EMP017",   400_000, date(2025, 3, 1)),
]

# CNPS rates
CNPS_EMP_RATE = Decimal("0.042")       # 4.2% employee
CNPS_ER_RATE = Decimal("0.042")        # 4.2% employer pension
CNPS_AF_RATE = Decimal("0.07")         # 7.0% family allowances
CNPS_AT_RATE = Decimal("0.0175")       # 1.75% accident risk (class 2)
FNE_ER_RATE = Decimal("0.01")          # 1.0% employer
FNE_EMP_RATE = Decimal("0.01")         # 1.0% employee
CFC_RATE = Decimal("0.01")             # 1.0% employee
CRTV_FLAT = Decimal(13_000)            # flat monthly
CNPS_CEILING = Decimal(750_000)        # monthly ceiling for pension

# Simple IRPP approximation using brackets
def calc_irpp(annual_taxable: Decimal) -> Decimal:
    """Approximate Cameroon IRPP on annual taxable income, return monthly."""
    brackets = [
        (2_000_000, Decimal("0.10")),
        (3_000_000, Decimal("0.15")),
        (5_000_000, Decimal("0.25")),
        (99_999_999_999, Decimal("0.35")),
    ]
    # Professional expenses abattement: 30% capped at 4.8M
    abattement = min(annual_taxable * Decimal("0.30"), Decimal(4_800_000))
    taxable = max(annual_taxable - abattement, 0)

    tax = Decimal(0)
    prev = Decimal(0)
    for upper, rate in brackets:
        upper_d = Decimal(upper)
        if taxable <= prev:
            break
        bracket_income = min(taxable, upper_d) - prev
        tax += bracket_income * rate
        prev = upper_d

    return (tax / 12).quantize(Decimal("1"))


with Session(engine) as S:
    # Load employee IDs
    emp_rows = S.execute(text("SELECT id, employee_number FROM employees WHERE company_id = :cid ORDER BY id"),
                         {"cid": CID}).fetchall()
    emp_by_num = {r[1]: r[0] for r in emp_rows}
    print(f"Found {len(emp_by_num)} employees")

    # Load component IDs
    comp_rows = S.execute(text("SELECT id, component_code FROM payroll_components WHERE company_id = :cid"),
                          {"cid": CID}).fetchall()
    comp_by_code = {r[1]: r[0] for r in comp_rows}
    print(f"Found {len(comp_by_code)} components")

    # Load projects for allocation
    proj_rows = S.execute(text("SELECT id, project_code FROM projects WHERE company_id = :cid AND status_code = 'active'"),
                          {"cid": CID}).fetchall()
    proj_ids = [r[0] for r in proj_rows]

    # Load cost code for LAB
    cc_lab_id = S.execute(text("SELECT id FROM project_cost_codes WHERE code = 'LAB'")).scalar()

    # Get payroll JE ids (for linking posted runs to existing JEs)
    payroll_jes = S.execute(text("""
        SELECT id, entry_date FROM journal_entries
        WHERE company_id = :cid AND source_module_code = 'payroll' AND status_code = 'POSTED'
        ORDER BY entry_date
    """), {"cid": CID}).fetchall()
    je_by_month = {}
    for je_id, entry_date in payroll_jes:
        d = date.fromisoformat(entry_date) if isinstance(entry_date, str) else entry_date
        key = (d.year, d.month)
        je_by_month[key] = je_id

    # =====================================================================
    # 1. COMPENSATION PROFILES - delete existing manual ones, create proper ones
    # =====================================================================
    print("\n[1] Seeding compensation profiles...")

    # Delete any manually-created profiles first
    S.execute(text("DELETE FROM employee_compensation_profiles WHERE company_id = :cid"), {"cid": CID})
    S.flush()

    profile_count = 0
    for emp_num, salary, hire in EMP_DATA:
        emp_id = emp_by_num.get(emp_num)
        if not emp_id:
            print(f"  WARNING: {emp_num} not found, skipping")
            continue
        profile = EmployeeCompensationProfile(
            company_id=CID,
            employee_id=emp_id,
            profile_name=f"{emp_num} standard",
            basic_salary=Decimal(salary),
            currency_code="XAF",
            effective_from=hire,
            effective_to=None,
            number_of_parts=Decimal("1.0"),
            is_active=True,
            created_at=NOW, updated_at=NOW,
        )
        S.add(profile)
        profile_count += 1

    S.flush()
    print(f"  Created {profile_count} compensation profiles")

    # =====================================================================
    # 2. COMPONENT ASSIGNMENTS - standard set for each employee
    # =====================================================================
    print("\n[2] Seeding component assignments...")

    S.execute(text("DELETE FROM employee_component_assignments WHERE company_id = :cid"), {"cid": CID})
    S.flush()

    # Standard components for all employees
    standard_components = [
        "BASE_SALARY",
        "EMPLOYEE_CNPS",
        "IRPP",
        "CAC",
        "TDL",
        "CRTV",
        "CFC_HLF",
        "FNE_EMPLOYEE",
        "EMPLOYER_CNPS",
        "FNE",
        "ACCIDENT_RISK_EMPLOYER",
        "EMPLOYER_AF",
    ]
    # Some employees get allowances too
    allowance_emps = ["EMP001", "EMP002", "EMP003", "EMP004", "EMP005", "EMP006", "EMP007"]

    assign_count = 0
    for emp_num, salary, hire in EMP_DATA:
        emp_id = emp_by_num.get(emp_num)
        if not emp_id:
            continue
        comps = list(standard_components)
        if emp_num in allowance_emps:
            comps.extend(["HOUSING_ALLOWANCE", "TRANSPORT_ALLOWANCE"])

        for comp_code in comps:
            comp_id = comp_by_code.get(comp_code)
            if not comp_id:
                continue
            assign = EmployeeComponentAssignment(
                company_id=CID,
                employee_id=emp_id,
                component_id=comp_id,
                effective_from=hire,
                effective_to=None,
                is_active=True,
                created_at=NOW, updated_at=NOW,
            )
            S.add(assign)
            assign_count += 1

    S.flush()
    print(f"  Created {assign_count} component assignments")

    # =====================================================================
    # 3. PAYROLL RUNS - monthly from Jan 2024 to Mar 2026
    # =====================================================================
    print("\n[3] Seeding payroll runs...")

    months = []
    # Start from Jul 2023 (first employees hired) through Mar 2026
    for m in range(7, 13):
        months.append((2023, m))
    for yr in [2024, 2025]:
        for m in range(1, 13):
            months.append((yr, m))
    for m in range(1, 4):
        months.append((2026, m))

    run_counter = 0
    total_run_employees = 0
    total_payments = 0
    import random
    RNG = random.Random(42)

    for yr, m in months:
        month_start = date(yr, m, 1)
        if m == 12:
            month_end = date(yr, 12, 31)
        else:
            month_end = date(yr, m + 1, 1) - timedelta(days=1)
        run_date = date(yr, m, min(28, month_end.day))
        pay_date = date(yr, m, min(28, month_end.day))

        run_counter += 1
        run_ref = f"PAYR-{run_counter:05d}"
        run_label = f"Payroll {date(yr, m, 1).strftime('%B')} {yr}"

        je_id = je_by_month.get((yr, m))

        run = PayrollRun(
            company_id=CID,
            run_reference=run_ref,
            run_label=run_label,
            period_year=yr,
            period_month=m,
            status_code="posted",
            currency_code="XAF",
            run_date=run_date,
            payment_date=pay_date,
            calculated_at=datetime(yr, m, min(25, month_end.day), 10, 0, 0),
            approved_at=datetime(yr, m, min(26, month_end.day), 14, 0, 0),
            posted_at=datetime(yr, m, min(28, month_end.day), 12, 0, 0),
            posted_by_user_id=ADMIN_ID,
            posted_journal_entry_id=je_id,
            created_at=datetime(yr, m, min(20, month_end.day), 9, 0, 0),
            updated_at=datetime(yr, m, min(28, month_end.day), 12, 0, 0),
        )
        S.add(run)
        S.flush()

        # Process each employee active during this month
        for emp_num, salary, hire in EMP_DATA:
            if hire > month_end:
                continue  # not yet hired
            emp_id = emp_by_num.get(emp_num)
            if not emp_id:
                continue

            basic = Decimal(salary)
            # Allowances for senior staff
            housing = Decimal(0)
            transport = Decimal(0)
            if emp_num in allowance_emps:
                housing = (basic * Decimal("0.10")).quantize(Decimal("1"))
                transport = Decimal(50_000)

            # Occasional overtime for operational staff (pseudo-random by month+emp)
            overtime = Decimal(0)
            ot_hours = 0
            if emp_num in ["EMP004", "EMP005", "EMP008", "EMP009", "EMP010", "EMP011", "EMP016"]:
                seed_val = hash((yr, m, emp_num)) % 5
                if seed_val < 2:  # ~40% of months
                    hourly = basic / Decimal(173)
                    ot_hours = RNG.choice([4, 8, 12, 16, 20])
                    overtime = (hourly * Decimal("1.50") * ot_hours).quantize(Decimal("1"))

            gross = basic + housing + transport + overtime

            # CNPS employee (capped)
            cnps_base = min(gross, CNPS_CEILING)
            cnps_emp = (cnps_base * CNPS_EMP_RATE).quantize(Decimal("1"))

            # FNE employee
            fne_emp = (gross * FNE_EMP_RATE).quantize(Decimal("1"))

            # CFC
            cfc = (gross * CFC_RATE).quantize(Decimal("1"))

            # IRPP
            annual_taxable = gross * 12
            irpp = calc_irpp(annual_taxable)

            # CAC (10% of IRPP)
            cac = (irpp * Decimal("0.10")).quantize(Decimal("1"))

            # TDL (1% of gross)
            tdl = (gross * Decimal("0.01")).quantize(Decimal("1"))

            # CRTV
            crtv = CRTV_FLAT

            total_emp_deductions = cnps_emp + fne_emp + cfc + irpp + cac + tdl + crtv
            net = gross - total_emp_deductions

            # Employer contributions
            cnps_er = (cnps_base * CNPS_ER_RATE).quantize(Decimal("1"))
            cnps_af = (gross * CNPS_AF_RATE).quantize(Decimal("1"))
            cnps_at = (gross * CNPS_AT_RATE).quantize(Decimal("1"))
            fne_er = (gross * FNE_ER_RATE).quantize(Decimal("1"))
            total_er = cnps_er + cnps_af + cnps_at + fne_er

            total_taxes = irpp + cac + tdl + crtv

            run_emp = PayrollRunEmployee(
                company_id=CID,
                run_id=run.id,
                employee_id=emp_id,
                gross_earnings=gross,
                taxable_salary_base=gross,
                tdl_base=gross,
                cnps_contributory_base=cnps_base,
                employer_cost_base=gross,
                net_payable=net,
                total_earnings=gross,
                total_employee_deductions=total_emp_deductions,
                total_employer_contributions=total_er,
                total_taxes=total_taxes,
                status_code="included",
                payment_status_code="paid",
                payment_date=pay_date,
                created_at=run.created_at, updated_at=run.updated_at,
            )
            S.add(run_emp)
            S.flush()
            total_run_employees += 1

            # --- Run Lines ---
            _ln = [0]

            def add_line(comp_code, comp_type, basis, rate, amount):
                comp_id = comp_by_code.get(comp_code)
                if not comp_id:
                    return
                _ln[0] += 1
                S.add(PayrollRunLine(
                    company_id=CID,
                    run_id=run.id,
                    run_employee_id=run_emp.id,
                    employee_id=emp_id,
                    component_id=comp_id,
                    component_type_code=comp_type,
                    calculation_basis=basis,
                    rate_applied=rate,
                    component_amount=amount,
                    created_at=run.created_at, updated_at=run.updated_at,
                ))

            # Earnings
            add_line("BASE_SALARY", "earning", basic, None, basic)
            if housing > 0:
                add_line("HOUSING_ALLOWANCE", "earning", basic, Decimal("0.10"), housing)
            if transport > 0:
                add_line("TRANSPORT_ALLOWANCE", "earning", Decimal(0), None, transport)
            if overtime > 0:
                add_line("OVERTIME_150", "earning", basic / Decimal(173), Decimal("1.50"), overtime)

            # Employee deductions
            add_line("EMPLOYEE_CNPS", "deduction", cnps_base, CNPS_EMP_RATE, cnps_emp)
            add_line("FNE_EMPLOYEE", "deduction", gross, FNE_EMP_RATE, fne_emp)
            add_line("CFC_HLF", "deduction", gross, CFC_RATE, cfc)
            add_line("IRPP", "tax", gross, None, irpp)
            add_line("CAC", "tax", irpp, Decimal("0.10"), cac)
            add_line("TDL", "tax", gross, Decimal("0.01"), tdl)
            add_line("CRTV", "tax", Decimal(0), None, crtv)

            # Employer contributions
            add_line("EMPLOYER_CNPS", "employer_contribution", cnps_base, CNPS_ER_RATE, cnps_er)
            add_line("EMPLOYER_AF", "employer_contribution", gross, CNPS_AF_RATE, cnps_af)
            add_line("ACCIDENT_RISK_EMPLOYER", "employer_contribution", gross, CNPS_AT_RATE, cnps_at)
            add_line("FNE", "employer_contribution", gross, FNE_ER_RATE, fne_er)

            # --- Payment Record ---
            payment = PayrollPaymentRecord(
                company_id=CID,
                run_employee_id=run_emp.id,
                payment_date=pay_date,
                amount_paid=net,
                payment_method_code="manual_bank",
                payment_reference=f"{run_ref}-{emp_num}",
                created_by_user_id=ADMIN_ID,
                created_at=run.created_at, updated_at=run.updated_at,
            )
            S.add(payment)
            total_payments += 1

            # --- Project Allocation (for engineering/construction/IT staff) ---
            if emp_num in ["EMP004", "EMP005", "EMP006", "EMP007", "EMP008",
                           "EMP009", "EMP010", "EMP011", "EMP014", "EMP015", "EMP016"]:
                if proj_ids:
                    proj_id = RNG.choice(proj_ids)
                    alloc = PayrollRunEmployeeProjectAllocation(
                        payroll_run_employee_id=run_emp.id,
                        line_number=1,
                        project_id=proj_id,
                        project_cost_code_id=cc_lab_id,
                        allocation_basis_code="percentage",
                        allocation_percent=Decimal("100.0000"),
                        allocated_cost_amount=gross + total_er,
                        created_at=run.created_at,
                    )
                    S.add(alloc)

        S.flush()

    S.commit()

    print(f"\n=== SUMMARY ===")
    print(f"  Payroll runs: {run_counter}")
    print(f"  Run employees: {total_run_employees}")
    print(f"  Payment records: {total_payments}")

    # Verify
    print("\n=== VERIFICATION ===")
    for tbl, label in [
        ("employee_compensation_profiles", "Comp profiles"),
        ("employee_component_assignments", "Comp assignments"),
        ("payroll_runs", "Payroll runs"),
        ("payroll_run_employees", "Run employees"),
        ("payroll_run_lines", "Run lines"),
        ("payroll_payment_records", "Payment records"),
        ("payroll_run_employee_project_allocations", "Project allocs"),
    ]:
        cnt = S.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
        print(f"  {label}: {cnt}")

    # Status check
    runs_status = S.execute(text(
        "SELECT DISTINCT status_code, COUNT(*) FROM payroll_runs GROUP BY status_code"
    )).fetchall()
    print(f"\n  Run statuses: {[(r[0], r[1]) for r in runs_status]}")

    emp_status = S.execute(text(
        "SELECT DISTINCT payment_status_code, COUNT(*) FROM payroll_run_employees GROUP BY payment_status_code"
    )).fetchall()
    print(f"  Employee payment statuses: {[(r[0], r[1]) for r in emp_status]}")
