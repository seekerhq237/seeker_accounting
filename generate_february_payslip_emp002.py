"""
Generate February 2026 payslip for EMP002 (Fatoumata Mbaye).

Creates a fresh company (unique name), runs February 2026 payroll for all 4 demo employees,
and exports only EMP002's payslip to the project root.

Usage:
    python generate_february_payslip_emp002.py
"""
from __future__ import annotations

import io
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from PySide6.QtWidgets import QApplication
from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import SetAccountRoleMappingCommand
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import CreateDocumentSequenceCommand
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import CreateFiscalYearCommand, GenerateFiscalPeriodsCommand
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.payroll.dto.payroll_setup_commands import UpsertCompanyPayrollSettingsCommand, CreateDepartmentCommand, CreatePositionCommand
from seeker_accounting.modules.payroll.dto.employee_dto import CreateEmployeeCommand
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import CreateCompensationProfileCommand, CreateComponentAssignmentCommand, CreatePayrollRunCommand
from seeker_accounting.modules.payroll.dto.payroll_component_dto import UpdatePayrollComponentCommand
from seeker_accounting.modules.administration.rbac_catalog import SYSTEM_PERMISSION_BY_CODE


def _find_component(components, code: str):
    for c in components:
        if c.component_code == code:
            return c
    return None


def _find_account_by_code(accounts, code_prefix: str):
    for a in accounts:
        if a.account_code.startswith(code_prefix) and a.allow_manual_posting and a.is_active:
            return a
    for a in accounts:
        if a.account_code.startswith(code_prefix) and a.is_active:
            return a
    return None


def _ensure_country_and_currency(reg) -> None:
    with reg.session_context.unit_of_work_factory() as uow:
        if not uow.session.get(Country, "CM"):
            uow.session.add(Country(code="CM", name="Cameroon", is_active=True))
        if not uow.session.get(Currency, "XAF"):
            uow.session.add(Currency(
                code="XAF", name="CFA Franc BEAC",
                symbol="FCFA", decimal_places=0, is_active=True,
            ))
        uow.commit()


def main() -> None:
    project_root = Path(__file__).parent
    print("=" * 65)
    print("  Seeker Accounting — February 2026 Payslip Generator (EMP002)")
    print("=" * 65)
    app = QApplication.instance() or QApplication([])
    bootstrap = bootstrap_script_runtime(
        app,
        permission_snapshot=tuple(SYSTEM_PERMISSION_BY_CODE.keys()),
    )
    reg = bootstrap.service_registry
    print("Runtime bootstrapped.")
    _ensure_country_and_currency(reg)
    print("Country/currency seed checked.")
    ts = int(time.time())
    company = reg.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"Seeker Demo Entreprise SARL {ts}",
            display_name=f"Seeker Demo {ts}",
            country_code="CM",
            base_currency_code="XAF",
            tax_identifier="M123456789Z",
            cnps_employer_number="CNPS-ER-00042",
            phone="+237 233 000 001",
            city="Douala",
            region="Littoral",
        )
    )
    cid = company.id
    print(f"Company created: id={cid} — {company.legal_name}")
    reg.chart_seed_service.ensure_global_chart_reference_seed()
    reg.company_seed_service.seed_built_in_chart(cid)
    accounts = reg.chart_of_accounts_service.list_accounts(cid, active_only=True)
    salary_expense = _find_account_by_code(accounts, "661") or _find_account_by_code(accounts, "66")
    payroll_payable = _find_account_by_code(accounts, "422") or _find_account_by_code(accounts, "42")
    social_expense = _find_account_by_code(accounts, "664") or salary_expense
    social_liability = _find_account_by_code(accounts, "431") or _find_account_by_code(accounts, "43")
    tax_liability = _find_account_by_code(accounts, "441") or _find_account_by_code(accounts, "44")
    if not all([salary_expense, payroll_payable, social_liability, tax_liability]):
        print("ERROR: Could not locate required payroll GL accounts. Aborting.")
        return
    print(
        f"GL accounts: salary_exp={salary_expense.account_code}, "
        f"payable={payroll_payable.account_code}, "
        f"social_liab={social_liability.account_code}, "
        f"tax_liab={tax_liability.account_code}"
    )
    reg.account_role_mapping_service.set_role_mapping(
        cid,
        SetAccountRoleMappingCommand(
            role_code="payroll_payable",
            account_id=payroll_payable.id,
        ),
    )
    for code, prefix, pad in [
        ("journal_entry",        "JRN-", 6),
        ("payroll_run",          "PR-",  5),
        ("payroll_input_batch",  "PIB-", 4),
        ("payroll_remittance",   "REM-", 4),
    ]:
        reg.numbering_setup_service.create_document_sequence(
            cid,
            CreateDocumentSequenceCommand(
                document_type_code=code,
                prefix=prefix,
                next_number=1,
                padding_width=pad,
            ),
        )
    print("Document sequences created.")
    fy = reg.fiscal_calendar_service.create_fiscal_year(
        cid,
        CreateFiscalYearCommand(
            year_code="FY2026",
            year_name="Fiscal Year 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        ),
    )
    calendar = reg.fiscal_calendar_service.generate_periods(
        cid, fy.id, GenerateFiscalPeriodsCommand()
    )
    print(f"Fiscal year 2026 created with {len(calendar.periods)} monthly periods.")
    reg.payroll_setup_service.upsert_company_payroll_settings(
        cid,
        UpsertCompanyPayrollSettingsCommand(
            default_pay_frequency_code="monthly",
            default_payroll_currency_code="XAF",
            statutory_pack_version_code="CMR_2024_V1",
            cnps_regime_code="general",
            accident_risk_class_code="A",
        ),
    )
    reg.payroll_statutory_pack_service.apply_pack(cid, "CMR_2024_V1")
    components = reg.payroll_component_service.list_components(cid)
    print(f"Statutory pack applied — {len(components)} components.")
    for comp in components:
        ct = (comp.component_type_code or "").lower()
        exp_id = None
        liab_id = None
        if ct == "earning":
            exp_id = salary_expense.id
        elif ct == "employer_contribution":
            exp_id = social_expense.id
            liab_id = social_liability.id
        elif ct == "deduction":
            liab_id = social_liability.id
        elif ct == "tax":
            liab_id = tax_liability.id
        if exp_id or liab_id:
            reg.payroll_component_service.update_component(
                cid, comp.id,
                UpdatePayrollComponentCommand(
                    component_code=comp.component_code,
                    component_name=comp.component_name,
                    component_type_code=comp.component_type_code,
                    calculation_method_code=comp.calculation_method_code,
                    is_taxable=comp.is_taxable,
                    is_pensionable=comp.is_pensionable,
                    is_active=comp.is_active,
                    expense_account_id=exp_id,
                    liability_account_id=liab_id,
                ),
            )
    components = reg.payroll_component_service.list_components(cid)
    mgmt_dept = reg.payroll_setup_service.create_department(
        cid, CreateDepartmentCommand(code="MGMT", name="Management")
    )
    ops_dept = reg.payroll_setup_service.create_department(
        cid, CreateDepartmentCommand(code="OPS", name="Operations")
    )
    fin_dept = reg.payroll_setup_service.create_department(
        cid, CreateDepartmentCommand(code="FIN", name="Finance")
    )
    ceo_pos = reg.payroll_setup_service.create_position(
        cid, CreatePositionCommand(code="CEO", name="Chief Executive Officer")
    )
    mgr_pos = reg.payroll_setup_service.create_position(
        cid, CreatePositionCommand(code="MGR", name="Operations Manager")
    )
    acct_pos = reg.payroll_setup_service.create_position(
        cid, CreatePositionCommand(code="ACCT", name="Accountant")
    )
    tech_pos = reg.payroll_setup_service.create_position(
        cid, CreatePositionCommand(code="TECH", name="Technician")
    )
    employee_data = [
        dict(
            number="EMP001",
            display_name="Amadou Koné",
            first_name="Amadou",
            last_name="Koné",
            hire_date=date(2022, 3, 1),
            dept=mgmt_dept,
            pos=ceo_pos,
            nif="M000111222A",
            cnps="CNPS-00-111-2022",
            salary=Decimal("1_200_000"),
        ),
        dict(
            number="EMP002",
            display_name="Fatoumata Mbaye",
            first_name="Fatoumata",
            last_name="Mbaye",
            hire_date=date(2023, 6, 1),
            dept=ops_dept,
            pos=mgr_pos,
            nif="M000333444B",
            cnps="CNPS-00-333-2023",
            salary=Decimal("650_000"),
        ),
        dict(
            number="EMP003",
            display_name="Jean-Pierre Tchoua",
            first_name="Jean-Pierre",
            last_name="Tchoua",
            hire_date=date(2021, 9, 15),
            dept=fin_dept,
            pos=acct_pos,
            nif="M000555666C",
            cnps="CNPS-00-555-2021",
            salary=Decimal("480_000"),
        ),
        dict(
            number="EMP004",
            display_name="Rose Akamba",
            first_name="Rose",
            last_name="Akamba",
            hire_date=date(2024, 1, 10),
            dept=ops_dept,
            pos=tech_pos,
            nif="M000777888D",
            cnps="CNPS-00-777-2024",
            salary=Decimal("320_000"),
        ),
    ]
    employees = []
    for ed in employee_data:
        emp = reg.employee_service.create_employee(
            cid,
            CreateEmployeeCommand(
                employee_number=ed["number"],
                display_name=ed["display_name"],
                first_name=ed["first_name"],
                last_name=ed["last_name"],
                hire_date=ed["hire_date"],
                base_currency_code="XAF",
                department_id=ed["dept"].id,
                position_id=ed["pos"].id,
                tax_identifier=ed["nif"],
                cnps_number=ed["cnps"],
            ),
        )
        employees.append(emp)
        print(f"  Employee created: {emp.employee_number} — {emp.display_name}")
    for emp, ed in zip(employees, employee_data):
        reg.compensation_profile_service.create_profile(
            cid,
            CreateCompensationProfileCommand(
                employee_id=emp.id,
                profile_name="2026 Standard",
                basic_salary=ed["salary"],
                currency_code="XAF",
                effective_from=date(2026, 1, 1),
            ),
        )
    print("Compensation profiles created.")
    standard_codes = [
        "BASE_SALARY",
        "EMPLOYEE_CNPS", "EMPLOYER_CNPS",
        "IRPP", "CAC", "TDL",
        "CRTV", "CFC_HLF",
        "FNE_EMPLOYEE", "FNE",
        "EMPLOYER_AF", "ACCIDENT_RISK_EMPLOYER",
    ]
    standard_comps = [_find_component(components, c) for c in standard_codes]
    standard_comps = [c for c in standard_comps if c is not None]
    for emp in employees:
        for comp in standard_comps:
            try:
                reg.component_assignment_service.create_assignment(
                    cid,
                    CreateComponentAssignmentCommand(
                        employee_id=emp.id,
                        component_id=comp.id,
                        effective_from=date(2026, 1, 1),
                    ),
                )
            except Exception as e:
                print(f"    WARN: {comp.component_code} for {emp.employee_number}: {e}")
    print("Component assignments complete.")
    print("\nCreating February 2026 payroll run...")
    run = reg.payroll_run_service.create_run(
        cid,
        CreatePayrollRunCommand(
            period_year=2026,
            period_month=2,
            run_label=f"February 2026 Payroll {ts}",
            currency_code="XAF",
            run_date=date(2026, 2, 28),
            payment_date=date(2026, 2, 28),
        ),
    )
    print(f"Run created: {run.run_reference}  (status={run.status_code})")
    calc_run = reg.payroll_run_service.calculate_run(cid, run.id)
    print(f"Run calculated.  status={calc_run.status_code}")
    run_employees = reg.payroll_run_service.list_run_employees(cid, run.id)
    target = next((re for re in run_employees if re.employee_number == "EMP002"), None)
    if not target:
        print("ERROR: EMP002 not found in run employees.")
        return
    if target.status_code != "included":
        print(f"ERROR: EMP002 status is {target.status_code}, not included.")
        return
    reg.payroll_run_service.approve_run(cid, run.id)
    print("Run approved.")
    safe_name = target.employee_display_name.replace(" ", "_").replace("/", "_")
    filename = f"payslip_FEB2026_{target.employee_number}_{safe_name}.pdf"
    output_path = str(project_root / filename)
    result = reg.payroll_export_service.export_payslip_pdf(
        company_id=cid,
        run_employee_id=target.id,
        output_path=output_path,
    )
    print(f"Payslip exported: {filename} ({result.period_label})\nFile: {output_path}")


if __name__ == "__main__":
    main()
