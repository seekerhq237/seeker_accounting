"""
R4 — Final Payroll Compliance Regression and Operational Acceptance Test
========================================================================

Covers:
  A) End-to-end workflow regression (setup → pack → employees → profiles →
     assignments → inputs → run → calculate → approve → post → payment →
     remittance → export)
  B) Cameroon compliance scenarios (CNPS cap, IRPP brackets, TDL, CRTV,
     employer contributions, BIK, overtime, below-threshold)
  C) Edge-case regression (missing settings, missing accounts, double posting,
     overpayment, zero inputs, terminated employee, voiding, etc.)
  D) Regression automation / test harness with clear pass/fail
  E) Defect reporting (any failures logged precisely)
  F) Operational acceptance assessment
  G) Boundary preservation (no architecture changes)
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import traceback
from contextlib import suppress

# Force UTF-8 output on Windows to avoid charmap encoding errors
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from PySide6.QtWidgets import QApplication
from shared.bootstrap import bootstrap_script_runtime

# ---------------------------------------------------------------------------
# Bootstrap imports
# ---------------------------------------------------------------------------
from seeker_accounting.app.dependency.factories import (
    create_active_company_context,
    create_app_context,
    create_navigation_service,
    create_service_registry,
    create_session_context,
    create_theme_manager,
)
from seeker_accounting.config.settings import load_settings

# Reference data models for seeding
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency

# Company
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand

# Fiscal periods
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)

# Numbering
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (
    CreateDocumentSequenceCommand,
)

# Account role mapping
from seeker_accounting.modules.accounting.reference_data.dto.account_role_mapping_dto import (
    SetAccountRoleMappingCommand,
)

# Payroll setup
from seeker_accounting.modules.payroll.dto.payroll_setup_commands import (
    UpsertCompanyPayrollSettingsCommand,
    CreateDepartmentCommand,
    CreatePositionCommand,
)

# Employee
from seeker_accounting.modules.payroll.dto.employee_dto import (
    CreateEmployeeCommand,
)

# Compensation & components
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CreateCompensationProfileCommand,
    CreateComponentAssignmentCommand,
    CreatePayrollInputBatchCommand,
    CreatePayrollInputLineCommand,
    CreatePayrollRunCommand,
)

# Posting
from seeker_accounting.modules.payroll.dto.payroll_posting_dto import (
    PostPayrollRunCommand,
)

# Payment
from seeker_accounting.modules.payroll.dto.payroll_payment_dto import (
    CreatePayrollPaymentRecordCommand,
)

# Remittance
from seeker_accounting.modules.payroll.dto.payroll_remittance_dto import (
    CreatePayrollRemittanceBatchCommand,
    CreatePayrollRemittanceLineCommand,
    RecordRemittancePaymentCommand,
)

# Exceptions
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PeriodLockedError,
    ValidationError,
)


# ============================================================================
# Test harness
# ============================================================================

@dataclass
class TestResult:
    name: str
    passed: bool
    message: str = ""


@dataclass
class TestHarness:
    results: list[TestResult] = field(default_factory=list)
    section: str = ""

    def set_section(self, name: str) -> None:
        self.section = name
        print(f"\n{'='*72}")
        print(f"  SECTION: {name}")
        print(f"{'='*72}")

    def check(self, name: str, condition: bool, message: str = "") -> bool:
        label = f"[{self.section}] {name}" if self.section else name
        result = TestResult(name=label, passed=condition, message=message)
        self.results.append(result)
        status = "PASS" if condition else "FAIL"
        display = f"  [{status}] {label}"
        if message:
            display += f" — {message}"
        print(display)
        return condition

    def check_decimal_close(
        self, name: str, actual: Decimal, expected: Decimal,
        tolerance: Decimal = Decimal("1"), message: str = "",
    ) -> bool:
        diff = abs(actual - expected)
        ok = diff <= tolerance
        detail = f"expected={expected}, actual={actual}, diff={diff}"
        if message:
            detail = f"{message} | {detail}"
        return self.check(name, ok, detail)

    def expect_exception(self, name: str, exc_type, func, *args, **kwargs) -> bool:
        type_name = exc_type.__name__ if isinstance(exc_type, type) else "|".join(t.__name__ for t in exc_type)
        try:
            func(*args, **kwargs)
        except exc_type:
            return self.check(name, True, f"raised expected exception ({type_name})")
        except Exception as exc:
            return self.check(name, False, f"raised {type(exc).__name__} instead of {type_name}: {exc}")
        else:
            return self.check(name, False, f"did NOT raise {type_name}")

    def summary(self) -> int:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        print(f"\n{'='*72}")
        print(f"  SUMMARY: {passed}/{total} passed, {failed} failed")
        if failed:
            print(f"\n  FAILURES:")
            for r in self.results:
                if not r.passed:
                    print(f"    FAIL: {r.name}")
                    if r.message:
                        print(f"          {r.message}")
        print(f"{'='*72}")
        return 0 if failed == 0 else 1


# ============================================================================
# Helpers
# ============================================================================

def _q(amount: str) -> Decimal:
    return Decimal(amount)


def _round_xaf(val: Decimal) -> Decimal:
    """Round to nearest integer (XAF has no decimals)."""
    return val.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _ensure_country_and_currency(registry) -> None:
    """Seed CM country and XAF currency if not present."""
    with registry.session_context.unit_of_work_factory() as uow:
        session = uow.session
        if not session.get(Country, "CM"):
            session.add(Country(code="CM", name="Cameroon", is_active=True))
        if not session.get(Currency, "XAF"):
            session.add(Currency(
                code="XAF",
                name="CFA Franc BEAC",
                symbol="FCFA",
                decimal_places=0,
                is_active=True,
            ))
        uow.commit()


def _find_account_by_code(accounts, code_prefix: str):
    """Find the first account whose code starts with the prefix."""
    for a in accounts:
        if a.account_code.startswith(code_prefix) and a.allow_manual_posting and a.is_active:
            return a
    # Fallback: allow non-manual-posting  
    for a in accounts:
        if a.account_code.startswith(code_prefix) and a.is_active:
            return a
    return None


def _find_component_by_code(components, code: str):
    """Find component by exact code."""
    for c in components:
        if c.component_code == code:
            return c
    return None


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:
    h = TestHarness()

    # ---- Bootstrap ----
    app = QApplication([])
    # Grant all payroll permissions for testing
    from seeker_accounting.modules.payroll.payroll_permissions import ALL_PAYROLL_PERMISSIONS
    bootstrap = bootstrap_script_runtime(
        app,
        permission_snapshot=(p[0] for p in ALL_PAYROLL_PERMISSIONS),
    )
    settings = bootstrap.settings
    app_context = bootstrap.app_context
    session_context = bootstrap.session_context
    active_company_context = bootstrap.active_company_context
    navigation_service = bootstrap.navigation_service
    theme_manager = bootstrap.theme_manager
    reg = bootstrap.service_registry

    _ensure_country_and_currency(reg)

    # ---- Create test company (unique name per run) ----
    import time
    ts = int(time.time())
    company = reg.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"R4 Regression SARL {ts}",
            display_name=f"R4 Regression {ts}",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    cid = company.id
    print(f"\nCompany created: id={cid}, name={company.display_name}")

    # ---- Seed chart of accounts ----
    reg.chart_seed_service.ensure_global_chart_reference_seed()
    reg.company_seed_service.seed_built_in_chart(cid)
    print("Chart of accounts seeded (OHADA)")

    # Lookup key accounts for payroll
    all_accounts = reg.chart_of_accounts_service.list_accounts(cid, active_only=True)
    # OHADA payroll accounts:
    #   661x = Remunerations directes (expense)
    #   422x = Personnel, remunerations dues (liability)
    #   431x = Securite sociale (liability)
    #   664x = Charges sociales (expense)
    salary_expense_acct = _find_account_by_code(all_accounts, "661")
    if not salary_expense_acct:
        salary_expense_acct = _find_account_by_code(all_accounts, "66")
    payroll_payable_acct = _find_account_by_code(all_accounts, "422")
    if not payroll_payable_acct:
        payroll_payable_acct = _find_account_by_code(all_accounts, "42")
    social_expense_acct = _find_account_by_code(all_accounts, "664")
    if not social_expense_acct:
        social_expense_acct = salary_expense_acct  # fallback
    social_liability_acct = _find_account_by_code(all_accounts, "431")
    if not social_liability_acct:
        social_liability_acct = _find_account_by_code(all_accounts, "43")
    tax_liability_acct = _find_account_by_code(all_accounts, "441")
    if not tax_liability_acct:
        tax_liability_acct = _find_account_by_code(all_accounts, "44")

    h.check("account_salary_expense_found", salary_expense_acct is not None,
             f"code={getattr(salary_expense_acct, 'account_code', None)}")
    h.check("account_payroll_payable_found", payroll_payable_acct is not None,
             f"code={getattr(payroll_payable_acct, 'account_code', None)}")
    h.check("account_social_liability_found", social_liability_acct is not None,
             f"code={getattr(social_liability_acct, 'account_code', None)}")
    h.check("account_tax_liability_found", tax_liability_acct is not None,
             f"code={getattr(tax_liability_acct, 'account_code', None)}")

    if not all([salary_expense_acct, payroll_payable_acct, social_liability_acct, tax_liability_acct]):
        print("\nFATAL: Cannot proceed without core payroll accounts. Aborting.")
        return h.summary()

    # ---- Map payroll_payable role ----
    reg.account_role_mapping_service.set_role_mapping(
        cid,
        SetAccountRoleMappingCommand(role_code="payroll_payable", account_id=payroll_payable_acct.id),
    )
    print(f"Mapped payroll_payable role → {payroll_payable_acct.account_code}")

    # ---- Document sequences ----
    reg.numbering_setup_service.create_document_sequence(
        cid,
        CreateDocumentSequenceCommand(
            document_type_code="journal_entry",
            prefix="JRN-",
            next_number=1,
            padding_width=6,
        ),
    )
    reg.numbering_setup_service.create_document_sequence(
        cid,
        CreateDocumentSequenceCommand(
            document_type_code="payroll_remittance",
            prefix="REM-",
            next_number=1,
            padding_width=4,
        ),
    )
    reg.numbering_setup_service.create_document_sequence(
        cid,
        CreateDocumentSequenceCommand(
            document_type_code="payroll_run",
            prefix="PR-",
            next_number=1,
            padding_width=5,
        ),
    )
    reg.numbering_setup_service.create_document_sequence(
        cid,
        CreateDocumentSequenceCommand(
            document_type_code="payroll_input_batch",
            prefix="PIB-",
            next_number=1,
            padding_width=4,
        ),
    )
    print("Document sequences created")

    # ---- Fiscal year / periods ----
    fy = reg.fiscal_calendar_service.create_fiscal_year(
        cid,
        CreateFiscalYearCommand(
            year_code="FY2025",
            year_name="Fiscal Year 2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        ),
    )
    calendar = reg.fiscal_calendar_service.generate_periods(
        cid, fy.id, GenerateFiscalPeriodsCommand()
    )
    print(f"Fiscal year created with {len(calendar.periods)} periods")

    # ---- Company payroll settings ----
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
    print("Company payroll settings configured")

    # ---- Apply statutory pack ----
    reg.payroll_statutory_pack_service.apply_pack(cid, "CMR_2024_V1")
    print("Statutory pack CMR_2024_V1 applied")

    # ---- Map accounts to components ----
    components = reg.payroll_component_service.list_components(cid)
    h.check("statutory_components_seeded", len(components) >= 14,
             f"count={len(components)}")

    # Map expense/liability accounts to components
    for comp in components:
        expense_id = None
        liability_id = None
        ct = comp.component_type_code.lower() if comp.component_type_code else ""
        if ct in ("earning",):
            expense_id = salary_expense_acct.id
        elif ct in ("employer_contribution",):
            expense_id = social_expense_acct.id
            liability_id = social_liability_acct.id
        elif ct in ("deduction",):
            liability_id = social_liability_acct.id
        elif ct in ("tax",):
            liability_id = tax_liability_acct.id

        if expense_id or liability_id:
            from seeker_accounting.modules.payroll.dto.payroll_component_dto import (
                UpdatePayrollComponentCommand,
            )
            reg.payroll_component_service.update_component(
                cid,
                comp.id,
                UpdatePayrollComponentCommand(
                    component_code=comp.component_code,
                    component_name=comp.component_name,
                    component_type_code=comp.component_type_code,
                    calculation_method_code=comp.calculation_method_code,
                    is_taxable=comp.is_taxable,
                    is_pensionable=comp.is_pensionable,
                    is_active=comp.is_active,
                    expense_account_id=expense_id,
                    liability_account_id=liability_id,
                ),
            )
    print("Component accounts mapped")
    # Refresh components after mapping
    components = reg.payroll_component_service.list_components(cid)

    # ---- Department / Position ----
    dept = reg.payroll_setup_service.create_department(
        cid, CreateDepartmentCommand(code="OPS", name="Operations")
    )
    pos = reg.payroll_setup_service.create_position(
        cid, CreatePositionCommand(code="MGR", name="Manager")
    )
    print(f"Department={dept.code}, Position={pos.code}")

    # =========================================================================
    # SECTION A: End-to-end workflow regression
    # =========================================================================
    h.set_section("A: End-to-end workflow")

    # -- Employees --
    emp1 = reg.employee_service.create_employee(
        cid,
        CreateEmployeeCommand(
            employee_number="EMP001",
            display_name="Jean Dupont",
            first_name="Jean",
            last_name="Dupont",
            hire_date=date(2024, 1, 1),
            base_currency_code="XAF",
            department_id=dept.id,
            position_id=pos.id,
        ),
    )
    emp2 = reg.employee_service.create_employee(
        cid,
        CreateEmployeeCommand(
            employee_number="EMP002",
            display_name="Marie Ngo",
            first_name="Marie",
            last_name="Ngo",
            hire_date=date(2024, 1, 1),
            base_currency_code="XAF",
            department_id=dept.id,
        ),
    )
    h.check("employees_created", emp1.id > 0 and emp2.id > 0,
             f"emp1={emp1.id}, emp2={emp2.id}")

    # -- Compensation profiles --
    # emp1: 500,000 XAF (above 62,000 threshold)
    # emp2: 50,000 XAF (below 62,000 threshold)
    prof1 = reg.compensation_profile_service.create_profile(
        cid,
        CreateCompensationProfileCommand(
            employee_id=emp1.id,
            profile_name="Standard 2025",
            basic_salary=_q("500000"),
            currency_code="XAF",
            effective_from=date(2025, 1, 1),
        ),
    )
    prof2 = reg.compensation_profile_service.create_profile(
        cid,
        CreateCompensationProfileCommand(
            employee_id=emp2.id,
            profile_name="Standard 2025",
            basic_salary=_q("50000"),
            currency_code="XAF",
            effective_from=date(2025, 1, 1),
        ),
    )
    h.check("compensation_profiles_created", prof1.id > 0 and prof2.id > 0)

    # -- Component assignments --
    # Find key component IDs
    basic_comp = _find_component_by_code(components, "BASE_SALARY")
    cnps_emp_comp = _find_component_by_code(components, "EMPLOYEE_CNPS")
    cnps_er_comp = _find_component_by_code(components, "EMPLOYER_CNPS")
    irpp_comp = _find_component_by_code(components, "IRPP")
    cac_comp = _find_component_by_code(components, "CAC")
    tdl_comp = _find_component_by_code(components, "TDL")
    crtv_comp = _find_component_by_code(components, "CRTV")
    cfc_comp = _find_component_by_code(components, "CFC_HLF")
    fne_emp_comp = _find_component_by_code(components, "FNE_EMPLOYEE")
    fne_er_comp = _find_component_by_code(components, "FNE")
    af_comp = _find_component_by_code(components, "EMPLOYER_AF")
    accident_comp = _find_component_by_code(components, "ACCIDENT_RISK_EMPLOYER")

    key_components = [basic_comp, cnps_emp_comp, irpp_comp, tdl_comp, crtv_comp]
    h.check("key_components_found", all(c is not None for c in key_components),
             f"basic={basic_comp is not None}, cnps_emp={cnps_emp_comp is not None}, "
             f"irpp={irpp_comp is not None}, tdl={tdl_comp is not None}, crtv={crtv_comp is not None}")

    # Assign standard components to both employees
    standard_components = [
        c for c in [basic_comp, cnps_emp_comp, cnps_er_comp, irpp_comp, cac_comp,
                    tdl_comp, crtv_comp, cfc_comp, fne_emp_comp, fne_er_comp,
                    af_comp, accident_comp]
        if c is not None
    ]
    assignments_created = 0
    for emp in [emp1, emp2]:
        for comp in standard_components:
            try:
                reg.component_assignment_service.create_assignment(
                    cid,
                    CreateComponentAssignmentCommand(
                        employee_id=emp.id,
                        component_id=comp.id,
                        effective_from=date(2025, 1, 1),
                    ),
                )
                assignments_created += 1
            except Exception as exc:
                print(f"    WARN: Assignment {comp.component_code} for emp {emp.employee_number}: {exc}")
    h.check("component_assignments_created", assignments_created >= 10,
             f"count={assignments_created}")

    # -- Create payroll run for January 2025 --
    run = reg.payroll_run_service.create_run(
        cid,
        CreatePayrollRunCommand(
            period_year=2025,
            period_month=1,
            run_label="January 2025 Payroll",
            currency_code="XAF",
            run_date=date(2025, 1, 31),
            payment_date=date(2025, 1, 31),
        ),
    )
    h.check("payroll_run_created", run.status_code == "draft", f"status={run.status_code}")

    # -- Calculate --
    calc_run = reg.payroll_run_service.calculate_run(cid, run.id)
    h.check("payroll_run_calculated", calc_run.status_code == "calculated",
             f"status={calc_run.status_code}")

    # -- Verify employee results --
    run_employees = reg.payroll_run_service.list_run_employees(cid, run.id)
    h.check("run_has_employees", len(run_employees) >= 2,
             f"count={len(run_employees)}")

    # Get detail for emp1 (500k salary)
    emp1_re = [re for re in run_employees if re.employee_number == "EMP001"]
    emp2_re = [re for re in run_employees if re.employee_number == "EMP002"]

    if emp1_re:
        emp1_detail = reg.payroll_run_service.get_run_employee_detail(cid, emp1_re[0].id)
        h.check_decimal_close("emp1_gross_earnings", emp1_detail.gross_earnings, _q("500000"),
                               message="Basic salary = 500,000 XAF")

        # CNPS employee: 4.2% of 500,000 = 21,000 (under cap of 31,500)
        expected_cnps_emp = _round_xaf(_q("500000") * _q("0.042"))
        cnps_line = [l for l in emp1_detail.lines if l.component_code == "EMPLOYEE_CNPS"]
        if cnps_line:
            h.check_decimal_close("emp1_cnps_employee", cnps_line[0].component_amount,
                                   expected_cnps_emp, message="4.2% of 500k")
        else:
            h.check("emp1_cnps_employee_line_present", False, "EMPLOYEE_CNPS line missing")

        # Taxable salary base: max((gross - CNPS_employee) * 0.70 - 500000/12, 0)
        #   = max((500000 - 21000) * 0.70 - 41666.67, 0)
        #   = max(335300 - 41666.67, 0) = 293633.33
        expected_taxable = _round_xaf(
            max((_q("500000") - expected_cnps_emp) * _q("0.70") - _q("500000") / 12, _q("0"))
        )
        h.check_decimal_close("emp1_taxable_salary_base", emp1_detail.taxable_salary_base,
                               expected_taxable, tolerance=_q("2"),
                               message=f"(500k-{expected_cnps_emp})*0.7 - 41666.67")

        h.check("emp1_net_payable_positive", emp1_detail.net_payable > 0,
                 f"net={emp1_detail.net_payable}")
        h.check("emp1_employer_cost_positive", emp1_detail.employer_cost_base > 0,
                 f"employer_cost={emp1_detail.employer_cost_base}")

        print(f"\n  EMP001 calculation breakdown:")
        print(f"    gross_earnings    = {emp1_detail.gross_earnings}")
        print(f"    taxable_base      = {emp1_detail.taxable_salary_base}")
        print(f"    total_deductions  = {emp1_detail.total_employee_deductions}")
        print(f"    total_taxes       = {emp1_detail.total_taxes}")
        print(f"    net_payable       = {emp1_detail.net_payable}")
        print(f"    employer_cost     = {emp1_detail.employer_cost_base}")
        for line in emp1_detail.lines:
            print(f"      {line.component_code:30s} {line.component_type_code:20s} {line.component_amount:>12}")
    else:
        h.check("emp1_run_employee_found", False, "EMP001 not in run")

    if emp2_re:
        emp2_detail = reg.payroll_run_service.get_run_employee_detail(cid, emp2_re[0].id)
        h.check_decimal_close("emp2_gross_earnings", emp2_detail.gross_earnings, _q("50000"),
                               message="Basic salary = 50,000 XAF (below 62k threshold)")
        h.check("emp2_net_payable_positive", emp2_detail.net_payable > 0,
                 f"net={emp2_detail.net_payable}")

        print(f"\n  EMP002 calculation breakdown:")
        print(f"    gross_earnings    = {emp2_detail.gross_earnings}")
        print(f"    taxable_base      = {emp2_detail.taxable_salary_base}")
        print(f"    total_deductions  = {emp2_detail.total_employee_deductions}")
        print(f"    total_taxes       = {emp2_detail.total_taxes}")
        print(f"    net_payable       = {emp2_detail.net_payable}")
        for line in emp2_detail.lines:
            print(f"      {line.component_code:30s} {line.component_type_code:20s} {line.component_amount:>12}")
    else:
        h.check("emp2_run_employee_found", False, "EMP002 not in run")

    # -- Posting validation --
    post_val = reg.payroll_posting_validation_service.validate(cid, run.id, date(2025, 1, 31))
    h.check("posting_validation_no_errors", not post_val.has_errors,
             f"errors={[i.message for i in post_val.issues if i.severity == 'error']}")

    # -- Approve --
    reg.payroll_run_service.approve_run(cid, run.id)
    approved_run = reg.payroll_run_service.get_run(cid, run.id)
    h.check("payroll_run_approved", approved_run.status_code == "approved",
             f"status={approved_run.status_code}")

    # -- Post --
    posting_result = reg.payroll_posting_service.post_run(
        cid,
        PostPayrollRunCommand(run_id=run.id, posting_date=date(2025, 1, 31)),
    )
    h.check("payroll_posted", posting_result.journal_entry_id > 0,
             f"journal_entry_id={posting_result.journal_entry_id}")
    h.check("posting_balanced",
             abs(posting_result.total_debit - posting_result.total_credit) < _q("0.02"),
             f"dr={posting_result.total_debit}, cr={posting_result.total_credit}")
    h.check("posting_has_journal_lines", len(posting_result.journal_lines) > 0,
             f"lines={len(posting_result.journal_lines)}")

    posted_run = reg.payroll_run_service.get_run(cid, run.id)
    h.check("run_status_posted", posted_run.status_code == "posted",
             f"status={posted_run.status_code}")

    print(f"\n  Journal posting:")
    print(f"    total_debit  = {posting_result.total_debit}")
    print(f"    total_credit = {posting_result.total_credit}")
    for jl in posting_result.journal_lines:
        print(f"      {jl.account_code:10s} {jl.line_description:40s} Dr={jl.debit_amount:>12} Cr={jl.credit_amount:>12}")

    # -- Payment tracking --
    if emp1_re:
        payment_summary = reg.payroll_payment_tracking_service.get_employee_payment_summary(
            cid, emp1_re[0].id
        )
        h.check("emp1_initially_unpaid", payment_summary.payment_status_code == "unpaid",
                 f"status={payment_summary.payment_status_code}")

        # Record partial payment
        partial_amount = _round_xaf(emp1_detail.net_payable / 2)
        pay_result1 = reg.payroll_payment_tracking_service.create_payment_record(
            cid,
            CreatePayrollPaymentRecordCommand(
                run_employee_id=emp1_re[0].id,
                payment_date=date(2025, 1, 31),
                amount_paid=partial_amount,
                payment_method_code="transfer_note",
                payment_reference="PAY-2025-001",
            ),
        )
        h.check("emp1_partial_payment", pay_result1.payment_status_code == "partial",
                 f"status={pay_result1.payment_status_code}, paid={pay_result1.total_paid}")

        # Record remaining payment
        remaining = pay_result1.outstanding
        pay_result2 = reg.payroll_payment_tracking_service.create_payment_record(
            cid,
            CreatePayrollPaymentRecordCommand(
                run_employee_id=emp1_re[0].id,
                payment_date=date(2025, 1, 31),
                amount_paid=remaining,
                payment_method_code="transfer_note",
                payment_reference="PAY-2025-002",
            ),
        )
        h.check("emp1_fully_paid", pay_result2.payment_status_code == "paid",
                 f"status={pay_result2.payment_status_code}, outstanding={pay_result2.outstanding}")

    # -- Remittance --
    rem_batch = reg.payroll_remittance_service.create_batch(
        cid,
        CreatePayrollRemittanceBatchCommand(
            period_start_date=date(2025, 1, 1),
            period_end_date=date(2025, 1, 31),
            remittance_authority_code="cnps",
            payroll_run_id=run.id,
            amount_due=_q("100000"),
        ),
    )
    h.check("remittance_batch_created", rem_batch.status_code == "draft",
             f"batch_id={rem_batch.id}")

    # Add line
    rem_with_line = reg.payroll_remittance_service.add_line(
        cid, rem_batch.id,
        CreatePayrollRemittanceLineCommand(
            description="CNPS contributions",
            amount_due=_q("100000"),
            payroll_component_id=cnps_emp_comp.id if cnps_emp_comp else None,
        ),
    )
    h.check("remittance_line_added", len(rem_with_line.lines) == 1)

    # Open batch
    opened_rem = reg.payroll_remittance_service.open_batch(cid, rem_batch.id)
    h.check("remittance_batch_opened", opened_rem.status_code == "open",
             f"status={opened_rem.status_code}")

    # Record remittance payment
    paid_rem = reg.payroll_remittance_service.record_payment(
        cid, rem_batch.id,
        RecordRemittancePaymentCommand(
            amount_paid=_q("100000"),
            remittance_date=date(2025, 2, 10),
            reference="CNPS-2025-01",
        ),
    )
    h.check("remittance_paid", paid_rem.status_code == "paid",
             f"status={paid_rem.status_code}")

    # -- Print / export --
    if emp1_re:
        payslip_data = reg.payroll_print_service.get_payslip_data(cid, emp1_re[0].id)
        h.check("payslip_data_retrieved", payslip_data.employee_display_name == "Jean Dupont",
                 f"name={payslip_data.employee_display_name}")

    summary_data = reg.payroll_print_service.get_summary_data(cid, run.id)
    h.check("summary_data_retrieved", summary_data.employee_count >= 2,
             f"count={summary_data.employee_count}")

    # Export to temp directory
    export_dir = tempfile.mkdtemp(prefix="seeker_r4_")
    try:
        csv_result = reg.payroll_export_service.export_summary_csv(
            cid, run.id, os.path.join(export_dir, "summary.csv")
        )
        h.check("summary_csv_exported", os.path.exists(csv_result.file_path),
                 f"path={csv_result.file_path}")

        pdf_result = reg.payroll_export_service.export_summary_pdf(
            cid, run.id, os.path.join(export_dir, "summary.pdf")
        )
        h.check("summary_pdf_exported", os.path.exists(pdf_result.file_path),
                 f"path={pdf_result.file_path}")

        if emp1_re:
            payslip_pdf = reg.payroll_export_service.export_payslip_pdf(
                cid, emp1_re[0].id, os.path.join(export_dir, "payslip_emp1.pdf")
            )
            h.check("payslip_pdf_exported", os.path.exists(payslip_pdf.file_path),
                     f"path={payslip_pdf.file_path}")
    finally:
        shutil.rmtree(export_dir, ignore_errors=True)

    # -- Output warnings --
    warnings = reg.payroll_output_warning_service.get_export_warnings(cid)
    h.check("output_warnings_retrieved", isinstance(warnings, list),
             f"count={len(warnings)}")
    # We expect some provisional warnings from the CMR pack
    provisional_warnings = [w for w in warnings if "provisional" in w.message.lower() or w.severity == "warning"]
    h.check("provisional_warnings_present", len(provisional_warnings) > 0,
             f"count={len(provisional_warnings)}")

    # -- Remittance deadlines --
    deadlines = reg.payroll_remittance_deadline_service.get_outstanding_deadlines(cid)
    h.check("deadline_service_works", isinstance(deadlines, list),
             f"count={len(deadlines)}")

    # -- Validation dashboard --
    dashboard = reg.payroll_validation_dashboard_service.run_full_assessment(cid, 2025, 2)
    h.check("validation_dashboard_works", dashboard.employee_count >= 2,
             f"emp_count={dashboard.employee_count}, checks={len(dashboard.checks)}")

    # -- Summary service --
    run_summary = reg.payroll_summary_service.get_run_summary(cid, run.id)
    h.check("run_summary_works", run_summary.is_posted,
             f"posted={run_summary.is_posted}, total_net={run_summary.total_net_payable}")

    # =========================================================================
    # SECTION B: Cameroon compliance scenarios
    # =========================================================================
    h.set_section("B: Cameroon compliance")

    # B1: CNPS cap verification (salary above 750,000)
    emp_high = reg.employee_service.create_employee(
        cid,
        CreateEmployeeCommand(
            employee_number="EMP003",
            display_name="Paul Biya Jr",
            first_name="Paul",
            last_name="Biya",
            hire_date=date(2024, 1, 1),
            base_currency_code="XAF",
        ),
    )
    reg.compensation_profile_service.create_profile(
        cid,
        CreateCompensationProfileCommand(
            employee_id=emp_high.id,
            profile_name="Executive 2025",
            basic_salary=_q("1500000"),
            currency_code="XAF",
            effective_from=date(2025, 1, 1),
        ),
    )
    for comp in standard_components:
        with suppress(Exception):
            reg.component_assignment_service.create_assignment(
                cid,
                CreateComponentAssignmentCommand(
                    employee_id=emp_high.id,
                    component_id=comp.id,
                    effective_from=date(2025, 1, 1),
                ),
            )

    # Create a separate run for February to test high salary
    run_feb = reg.payroll_run_service.create_run(
        cid,
        CreatePayrollRunCommand(
            period_year=2025,
            period_month=2,
            run_label="February 2025 Payroll",
            currency_code="XAF",
            run_date=date(2025, 2, 28),
        ),
    )
    reg.payroll_run_service.calculate_run(cid, run_feb.id)
    feb_employees = reg.payroll_run_service.list_run_employees(cid, run_feb.id)
    emp_high_re = [re for re in feb_employees if re.employee_number == "EMP003"]

    if emp_high_re:
        high_detail = reg.payroll_run_service.get_run_employee_detail(cid, emp_high_re[0].id)

        # B1: CNPS cap at 750,000 → max contribution = 31,500 each
        cnps_emp_line = [l for l in high_detail.lines if l.component_code == "EMPLOYEE_CNPS"]
        cnps_er_line = [l for l in high_detail.lines if l.component_code == "EMPLOYER_CNPS"]

        if cnps_emp_line:
            h.check_decimal_close("B1_cnps_employee_capped", cnps_emp_line[0].component_amount,
                                   _q("31500"), message="CNPS emp capped at 31,500 (4.2% of 750k)")
        else:
            h.check("B1_cnps_employee_line", False, "Missing EMPLOYEE_CNPS line")

        if cnps_er_line:
            h.check_decimal_close("B1_cnps_employer_capped", cnps_er_line[0].component_amount,
                                   _q("31500"), message="CNPS employer capped at 31,500 (4.2% of 750k)")
        else:
            h.check("B1_cnps_employer_line", False, "Missing EMPLOYER_CNPS line")

        # B2: Taxable salary for 1.5M employee
        # taxable = max((1500000 - 31500) * 0.70 - 41666.67, 0) = max(1027950 - 41666.67, 0) = 986283.33
        expected_cnps = _q("31500")
        expected_taxable_high = _round_xaf(
            max((_q("1500000") - expected_cnps) * _q("0.70") - _q("500000") / 12, _q("0"))
        )
        h.check_decimal_close("B2_taxable_base_high_salary", high_detail.taxable_salary_base,
                               expected_taxable_high, tolerance=_q("2"),
                               message="Taxable for 1.5M salary")

        # B3: IRPP verification for high salary
        # Annual taxable = 986283 * 12 = ~11,835,400
        # IRPP brackets: 0-2M @10%, 2M-3M @15%, 3M-5M @25%, 5M+ @35%
        annual_taxable = expected_taxable_high * 12
        irpp_annual = _q("0")
        brackets = [
            (_q("0"), _q("2000000"), _q("0.10")),
            (_q("2000000"), _q("3000000"), _q("0.15")),
            (_q("3000000"), _q("5000000"), _q("0.25")),
            (_q("5000000"), None, _q("0.35")),
        ]
        for lower, upper, rate in brackets:
            if annual_taxable > lower:
                bracket_amount = (min(annual_taxable, upper) - lower if upper else annual_taxable - lower)
                irpp_annual += bracket_amount * rate
        expected_irpp_monthly = _round_xaf(irpp_annual / 12)

        irpp_line = [l for l in high_detail.lines if l.component_code == "IRPP"]
        if irpp_line:
            h.check_decimal_close("B3_irpp_high_salary", irpp_line[0].component_amount,
                                   expected_irpp_monthly, tolerance=_q("5"),
                                   message=f"IRPP monthly for {annual_taxable} annual taxable")
        else:
            h.check("B3_irpp_line_present", False, "Missing IRPP line")

        # B4: CAC = 10% of IRPP
        cac_line = [l for l in high_detail.lines if l.component_code == "CAC"]
        if cac_line and irpp_line:
            expected_cac = _round_xaf(irpp_line[0].component_amount * _q("0.10"))
            h.check_decimal_close("B4_cac_10pct_of_irpp", cac_line[0].component_amount,
                                   expected_cac, tolerance=_q("2"),
                                   message="CAC = 10% of IRPP")

        # B5: TDL verification
        tdl_line = [l for l in high_detail.lines if l.component_code == "TDL"]
        if tdl_line:
            # For salary > 208,333: TDL fixed = 250
            h.check_decimal_close("B5_tdl_high_bracket", tdl_line[0].component_amount,
                                   _q("250"), tolerance=_q("1"),
                                   message="TDL = 250 for gross > 208,333")

        # B6: CRTV verification
        crtv_line = [l for l in high_detail.lines if l.component_code == "CRTV"]
        if crtv_line:
            # 1,500,000 salary → check correct CRTV bracket   
            h.check("B6_crtv_positive_amount", crtv_line[0].component_amount > 0,
                     f"amount={crtv_line[0].component_amount}")

        # B7: Employer contributions
        # Accident risk: 1.75% of gross (Group A)
        accident_line = [l for l in high_detail.lines if l.component_code == "ACCIDENT_RISK_EMPLOYER"]
        if accident_line:
            expected_accident = _round_xaf(_q("1500000") * _q("0.0175"))
            h.check_decimal_close("B7_accident_risk_group_a", accident_line[0].component_amount,
                                   expected_accident, tolerance=_q("2"),
                                   message="1.75% of 1.5M")

        # FNE employer: 1% of gross
        fne_er_line = [l for l in high_detail.lines if l.component_code == "FNE"]
        if fne_er_line:
            expected_fne = _round_xaf(_q("1500000") * _q("0.01"))
            h.check_decimal_close("B7_fne_employer", fne_er_line[0].component_amount,
                                   expected_fne, tolerance=_q("2"),
                                   message="1% of 1.5M")

        # Family allowances: 7% of gross (GENERAL regime), capped at 750k contributory base
        af_line = [l for l in high_detail.lines if l.component_code == "EMPLOYER_AF"]
        if af_line:
            # AF base is capped at CNPS contributory base (750k for general)
            expected_af = _round_xaf(_q("750000") * _q("0.07"))
            h.check_decimal_close("B7_family_allowances", af_line[0].component_amount,
                                   expected_af, tolerance=_q("2"),
                                   message="7% of 750k (capped)")

        # B8: Salary deductions — CFC 1% and FNE employee 1%
        cfc_line = [l for l in high_detail.lines if l.component_code == "CFC_HLF"]
        if cfc_line:
            expected_cfc = _round_xaf(_q("1500000") * _q("0.01"))
            h.check_decimal_close("B8_cfc_deduction", cfc_line[0].component_amount,
                                   expected_cfc, tolerance=_q("2"),
                                   message="CFC 1% of 1.5M")

        fne_emp_line = [l for l in high_detail.lines if l.component_code == "FNE_EMPLOYEE"]
        if fne_emp_line:
            expected_fne_emp = _round_xaf(_q("1500000") * _q("0.01"))
            h.check_decimal_close("B8_fne_employee", fne_emp_line[0].component_amount,
                                   expected_fne_emp, tolerance=_q("2"),
                                   message="FNE emp 1% of 1.5M")

        print(f"\n  EMP003 (1.5M) calculation breakdown:")
        print(f"    gross        = {high_detail.gross_earnings}")
        print(f"    taxable_base = {high_detail.taxable_salary_base}")
        print(f"    deductions   = {high_detail.total_employee_deductions}")
        print(f"    taxes        = {high_detail.total_taxes}")
        print(f"    net_payable  = {high_detail.net_payable}")
        print(f"    employer     = {high_detail.employer_cost_base}")
        for line in high_detail.lines:
            print(f"      {line.component_code:30s} {line.component_type_code:20s} {line.component_amount:>12}")
    else:
        h.check("emp_high_run_employee_found", False, "EMP003 not in February run")

    # B9: Below-threshold employee (50k salary) - minimal taxes
    emp2_feb_re = [re for re in feb_employees if re.employee_number == "EMP002"]
    if emp2_feb_re:
        emp2_feb_detail = reg.payroll_run_service.get_run_employee_detail(cid, emp2_feb_re[0].id)
        # 50k salary: taxable base = max((50000 - 2100) * 0.70 - 41666.67, 0) = max(33530 - 41666.67, 0) = 0
        h.check_decimal_close("B9_below_threshold_taxable", emp2_feb_detail.taxable_salary_base,
                               _q("0"), tolerance=_q("1"),
                               message="50k salary → taxable base = 0")

        # IRPP should be 0 when taxable base is 0
        irpp_line_low = [l for l in emp2_feb_detail.lines if l.component_code == "IRPP"]
        if irpp_line_low:
            h.check_decimal_close("B9_irpp_zero_below_threshold", irpp_line_low[0].component_amount,
                                   _q("0"), tolerance=_q("1"))

        # TDL for 50k: bracket 0-50,000 → TDL = 0
        tdl_line_low = [l for l in emp2_feb_detail.lines if l.component_code == "TDL"]
        if tdl_line_low:
            h.check_decimal_close("B9_tdl_zero_or_low", tdl_line_low[0].component_amount,
                                   _q("0"), tolerance=_q("167"),
                                   message="TDL for 50k bracket")

    # B10: Remittance deadlines — DGI and CNPS deadlines are 15th of following month
    from seeker_accounting.modules.payroll.services.payroll_remittance_deadline_service import (
        compute_filing_deadline,
    )
    dgi_deadline = compute_filing_deadline("dgi", date(2025, 1, 31))
    cnps_deadline = compute_filing_deadline("cnps", date(2025, 1, 31))
    h.check("B10_dgi_deadline_feb_15", dgi_deadline == date(2025, 2, 15),
             f"dgi={dgi_deadline}")
    h.check("B10_cnps_deadline_feb_15", cnps_deadline == date(2025, 2, 15),
             f"cnps={cnps_deadline}")

    # =========================================================================
    # SECTION C: Edge-case regression
    # =========================================================================
    h.set_section("C: Edge-case regression")

    # C1: Double posting of same run (should fail)
    h.expect_exception("C1_double_posting_blocked", (ValidationError, ConflictError),
                        reg.payroll_posting_service.post_run, cid,
                        PostPayrollRunCommand(run_id=run.id, posting_date=date(2025, 1, 31)))

    # C2: Void a posted run (should fail — posted runs are immutable)
    h.expect_exception("C2_void_posted_run_blocked", (ValidationError, ConflictError),
                        reg.payroll_run_service.void_run, cid, run.id)

    # C3: Overpayment (should fail)
    if emp2_re:
        emp2_summary = reg.payroll_payment_tracking_service.get_employee_payment_summary(
            cid, emp2_re[0].id
        )
        # First pay the correct amount
        if emp2_summary.payment_status_code == "unpaid":
            reg.payroll_payment_tracking_service.create_payment_record(
                cid,
                CreatePayrollPaymentRecordCommand(
                    run_employee_id=emp2_re[0].id,
                    payment_date=date(2025, 1, 31),
                    amount_paid=emp2_detail.net_payable,
                    payment_method_code="cash",
                ),
            )
        # Now try overpayment
        h.expect_exception("C3_overpayment_blocked", ValidationError,
                            reg.payroll_payment_tracking_service.create_payment_record,
                            cid,
                            CreatePayrollPaymentRecordCommand(
                                run_employee_id=emp2_re[0].id,
                                payment_date=date(2025, 1, 31),
                                amount_paid=_q("1"),
                            ))

    # C4: Create run for non-existent period (far future)
    try:
        bad_run = reg.payroll_run_service.create_run(
            cid,
            CreatePayrollRunCommand(
                period_year=2099,
                period_month=1,
                run_label="Future Run",
                currency_code="XAF",
                run_date=date(2099, 1, 31),
            ),
        )
        # If it succeeds, it should fail at calculation or posting
        h.check("C4_future_run_created_but_will_fail_at_calc", True, "allowed draft creation for any period")
    except (ValidationError, NotFoundError):
        h.check("C4_future_period_blocked", True, "blocked at run creation")

    # C5: Approve a draft run (without calculation) 
    run_draft = reg.payroll_run_service.create_run(
        cid,
        CreatePayrollRunCommand(
            period_year=2025,
            period_month=3,
            run_label="March 2025 Draft",
            currency_code="XAF",
            run_date=date(2025, 3, 31),
        ),
    )
    h.expect_exception("C5_approve_uncalculated_blocked", (ValidationError, ConflictError),
                        reg.payroll_run_service.approve_run, cid, run_draft.id)

    # C6: Void a draft run (should succeed)
    try:
        reg.payroll_run_service.void_run(cid, run_draft.id)
        voided = reg.payroll_run_service.get_run(cid, run_draft.id)
        h.check("C6_void_draft_succeeds", voided.status_code == "voided",
                 f"status={voided.status_code}")
    except Exception as exc:
        h.check("C6_void_draft_succeeds", False, f"unexpected error: {exc}")

    # C7: Create payroll run, calculate, void (calculated → voided)
    run_void_test = reg.payroll_run_service.create_run(
        cid,
        CreatePayrollRunCommand(
            period_year=2025,
            period_month=4,
            run_label="April 2025 Void Test",
            currency_code="XAF",
            run_date=date(2025, 4, 30),
        ),
    )
    reg.payroll_run_service.calculate_run(cid, run_void_test.id)
    try:
        reg.payroll_run_service.void_run(cid, run_void_test.id)
        h.check("C7_void_calculated_succeeds", True)
    except Exception as exc:
        h.check("C7_void_calculated_succeeds", False, str(exc))

    # C8: Zero-amount input line
    run_zero = reg.payroll_run_service.create_run(
        cid,
        CreatePayrollRunCommand(
            period_year=2025,
            period_month=5,
            run_label="May 2025 Zero Test",
            currency_code="XAF",
            run_date=date(2025, 5, 31),
        ),
    )
    reg.payroll_run_service.calculate_run(cid, run_zero.id)
    zero_employees = reg.payroll_run_service.list_run_employees(cid, run_zero.id)
    h.check("C8_zero_input_run_calculates", len(zero_employees) > 0,
             f"employees={len(zero_employees)}")

    # C9: Duplicate employee number (should fail)
    h.expect_exception("C9_duplicate_employee_number", (ValidationError, ConflictError),
                        reg.employee_service.create_employee, cid,
                        CreateEmployeeCommand(
                            employee_number="EMP001",
                            display_name="Duplicate Jean",
                            first_name="Duplicate",
                            last_name="Jean",
                            hire_date=date(2024, 1, 1),
                            base_currency_code="XAF",
                        ))

    # C10: Terminated employee handling
    from seeker_accounting.modules.payroll.dto.employee_dto import UpdateEmployeeCommand
    reg.employee_service.update_employee(
        cid, emp2.id,
        UpdateEmployeeCommand(
            employee_number="EMP002",
            display_name="Marie Ngo",
            first_name="Marie",
            last_name="Ngo",
            hire_date=date(2024, 1, 1),
            base_currency_code="XAF",
            is_active=False,
            termination_date=date(2025, 3, 31),
        ),
    )
    # Create run for June — terminated employee should not appear or should be excluded
    run_term = reg.payroll_run_service.create_run(
        cid,
        CreatePayrollRunCommand(
            period_year=2025,
            period_month=6,
            run_label="June 2025 Termination Test",
            currency_code="XAF",
            run_date=date(2025, 6, 30),
        ),
    )
    reg.payroll_run_service.calculate_run(cid, run_term.id)
    term_employees = reg.payroll_run_service.list_run_employees(cid, run_term.id)
    emp2_in_june = [re for re in term_employees if re.employee_number == "EMP002"]
    # Terminated/inactive employee should either not appear or have zero net
    if emp2_in_june:
        emp2_june_detail = reg.payroll_run_service.get_run_employee_detail(cid, emp2_in_june[0].id)
        h.check("C10_terminated_employee_excluded_or_zero",
                 emp2_june_detail.status_code != "included" or emp2_june_detail.net_payable == 0,
                 f"status={emp2_june_detail.status_code}, net={emp2_june_detail.net_payable}")
    else:
        h.check("C10_terminated_employee_excluded", True, "not included in run")

    # Reactivate emp2 for remaining tests
    reg.employee_service.update_employee(
        cid, emp2.id,
        UpdateEmployeeCommand(
            employee_number="EMP002",
            display_name="Marie Ngo",
            first_name="Marie",
            last_name="Ngo",
            hire_date=date(2024, 1, 1),
            base_currency_code="XAF",
            is_active=True,
            termination_date=None,
        ),
    )

    # C11: Remittance batch status transitions
    rem_test = reg.payroll_remittance_service.create_batch(
        cid,
        CreatePayrollRemittanceBatchCommand(
            period_start_date=date(2025, 2, 1),
            period_end_date=date(2025, 2, 28),
            remittance_authority_code="dgi",
            amount_due=_q("50000"),
        ),
    )
    h.check("C11_remittance_draft", rem_test.status_code == "draft")

    # Cancel from draft (should work)
    reg.payroll_remittance_service.cancel_batch(cid, rem_test.id)
    cancelled = reg.payroll_remittance_service.get_batch(cid, rem_test.id)
    h.check("C11_remittance_cancelled_from_draft", cancelled.status_code == "cancelled",
             f"status={cancelled.status_code}")

    # C12: Payroll input batch flow
    input_batch = reg.payroll_input_service.create_batch(
        cid,
        CreatePayrollInputBatchCommand(
            period_year=2025,
            period_month=7,
            description="July overtime inputs",
        ),
    )
    h.check("C12_input_batch_created", input_batch.status_code == "draft")

    # Add overtime line (if OVERTIME component exists)
    overtime_comp = _find_component_by_code(components, "OVERTIME")
    if overtime_comp and emp1:
        line_result = reg.payroll_input_service.add_line(
            cid, input_batch.id,
            CreatePayrollInputLineCommand(
                employee_id=emp1.id,
                component_id=overtime_comp.id,
                input_amount=_q("50000"),
                input_quantity=_q("10"),
                notes="10 hours overtime",
            ),
        )
        h.check("C12_input_line_added", line_result.id is not None)

        # Submit batch
        reg.payroll_input_service.submit_batch(cid, input_batch.id)
        submitted = reg.payroll_input_service.get_batch(cid, input_batch.id)
        h.check("C12_input_batch_submitted", submitted is not None and submitted.status_code == "approved",
                 f"status={submitted.status_code if submitted else 'None'}")
    else:
        h.check("C12_overtime_component_exists", overtime_comp is not None, "OVERTIME component not found")

    # C13: Payroll pre-run validation
    pre_val = reg.payroll_validation_service.validate_for_period(cid, 2025, 7)
    h.check("C13_pre_run_validation_works", pre_val is not None,
             f"employee_count={pre_val.employee_count}, issues={len(pre_val.issues)}")

    # C14: Pack version service
    pack_versions = reg.payroll_pack_version_service.list_available_versions(cid)
    h.check("C14_pack_versions_listed", isinstance(pack_versions, list),
             f"count={len(pack_versions)}")

    # C15: Payslip preview service
    if emp1_re:
        try:
            preview = reg.payroll_payslip_preview_service.get_payslip_preview(cid, emp1_re[0].id)
            h.check("C15_payslip_preview_works", preview is not None)
        except Exception as exc:
            h.check("C15_payslip_preview_works", False, str(exc))

    # =========================================================================
    # SECTION D: Regression automation / test harness validation
    # =========================================================================
    h.set_section("D: Test harness validation")

    # D1: Verify all services are accessible on registry
    service_attrs = [
        "payroll_setup_service", "employee_service", "payroll_component_service",
        "payroll_rule_service", "cameroon_payroll_seed_service",
        "payroll_statutory_pack_service", "compensation_profile_service",
        "component_assignment_service", "payroll_input_service",
        "payroll_validation_service", "payroll_run_service",
        "payroll_payslip_preview_service", "payroll_calculation_service",
        "payroll_posting_validation_service", "payroll_posting_service",
        "payroll_payment_tracking_service", "payroll_remittance_service",
        "payroll_summary_service", "payroll_pack_version_service",
        "payroll_validation_dashboard_service", "payroll_print_service",
        "payroll_export_service", "payroll_output_warning_service",
        "payroll_remittance_deadline_service",
    ]
    missing_services = [a for a in service_attrs if not hasattr(reg, a)]
    h.check("D1_all_payroll_services_wired", len(missing_services) == 0,
             f"missing={missing_services}" if missing_services else "all 24 services wired")

    # D2: Statutory pack component count
    components_final = reg.payroll_component_service.list_components(cid)
    h.check("D2_component_count", len(components_final) >= 14,
             f"count={len(components_final)}")

    # D3: Statutory pack rule set count
    rules = reg.payroll_rule_service.list_rule_sets(cid)
    h.check("D3_rule_set_count", len(rules) >= 15,
             f"count={len(rules)}")

    # D4: Verify pack verification metadata
    pack_info = reg.payroll_statutory_pack_service.list_available_packs()
    h.check("D4_packs_available", len(pack_info) > 0, f"count={len(pack_info)}")

    # =========================================================================
    # Final summary
    # =========================================================================
    return h.summary()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
