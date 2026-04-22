"""PayrollPayslipPreviewService — assemble payslip data for UI preview display.

Returns a structured view of a single employee's payroll run detail,
grouped by component type, suitable for rendering a payslip dialog.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    PayrollRunEmployeeDetailDTO,
    PayrollRunLineDTO,
)
from seeker_accounting.modules.payroll.repositories.employee_repository import EmployeeRepository
from seeker_accounting.modules.payroll.repositories.payroll_run_repository import (
    PayrollRunEmployeeRepository,
    PayrollRunRepository,
)
from seeker_accounting.modules.payroll.services.payroll_run_service import (
    PayrollRunService,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.treasury.repositories.financial_account_repository import FinancialAccountRepository

PayrollRunRepositoryFactory = Callable[[Session], PayrollRunRepository]
PayrollRunEmployeeRepositoryFactory = Callable[[Session], PayrollRunEmployeeRepository]
EmployeeRepositoryFactory = Callable[[Session], EmployeeRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
FinancialAccountRepositoryFactory = Callable[[Session], FinancialAccountRepository]


@dataclass(frozen=True, slots=True)
class PayslipSectionDTO:
    section_title: str
    lines: list[PayrollRunLineDTO]
    subtotal: Decimal


@dataclass(frozen=True, slots=True)
class PayslipPreviewDTO:
    employee_number: str
    employee_display_name: str
    period_label: str
    run_reference: str
    period_year: int
    period_month: int

    earnings_section: PayslipSectionDTO
    deductions_section: PayslipSectionDTO
    taxes_section: PayslipSectionDTO
    employer_contributions_section: PayslipSectionDTO

    gross_earnings: Decimal
    total_deductions: Decimal
    net_payable: Decimal
    employer_cost_base: Decimal

    # Bases for reference
    taxable_salary_base: Decimal
    cnps_contributory_base: Decimal
    tdl_base: Decimal

    # Employee enrichment fields
    employee_position_name: str | None
    employee_department_name: str | None
    employee_hire_date: date | None
    employee_nif: str | None
    employee_cnps_number: str | None

    # Payment account fields
    payment_account_name: str | None
    payment_account_type: str | None
    payment_account_reference: str | None

    # Company CNPS
    company_cnps_employer_number: str | None

    # Run-level fields
    payment_date: date | None


_MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


class PayrollPayslipPreviewService:
    """Build payslip preview DTO from an existing payroll run employee record."""

    def __init__(
        self,
        payroll_run_service: PayrollRunService,
        unit_of_work_factory: UnitOfWorkFactory,
        employee_repository_factory: EmployeeRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory | None = None,
        financial_account_repository_factory: FinancialAccountRepositoryFactory | None = None,
    ) -> None:
        self._run_service = payroll_run_service
        self._uow_factory = unit_of_work_factory
        self._employee_repo_factory = employee_repository_factory
        self._company_repo_factory = company_repository_factory
        self._fin_account_repo_factory = financial_account_repository_factory

    def get_payslip_preview(
        self, company_id: int, run_employee_id: int
    ) -> PayslipPreviewDTO:
        detail: PayrollRunEmployeeDetailDTO = self._run_service.get_run_employee_detail(
            company_id, run_employee_id
        )

        earnings_lines = [l for l in detail.lines if l.component_type_code == "earning"]
        deduction_lines = [l for l in detail.lines if l.component_type_code == "deduction"]
        tax_lines = [l for l in detail.lines if l.component_type_code == "tax"]
        employer_lines = [l for l in detail.lines if l.component_type_code == "employer_contribution"]

        period_label = f"{_MONTHS.get(detail.period_month, str(detail.period_month))} {detail.period_year}"

        # Load employee enrichment fields
        position_name: str | None = None
        department_name: str | None = None
        hire_date: date | None = None
        employee_nif: str | None = None
        employee_cnps_number: str | None = None
        default_payment_account_id: int | None = None
        payment_account_name: str | None = None
        payment_account_type: str | None = None
        payment_account_reference: str | None = None
        company_cnps_employer_number: str | None = None
        with self._uow_factory() as uow:
            emp_repo = self._employee_repo_factory(uow.session)
            emp = emp_repo.get_by_id(company_id, detail.employee_id)
            if emp is not None:
                position_name = emp.position.name if emp.position else None
                department_name = emp.department.name if emp.department else None
                hire_date = emp.hire_date
                employee_nif = emp.tax_identifier
                employee_cnps_number = emp.cnps_number
                default_payment_account_id = emp.default_payment_account_id

            if default_payment_account_id is not None and self._fin_account_repo_factory is not None:
                fin_repo = self._fin_account_repo_factory(uow.session)
                acct = fin_repo.get_by_id(company_id, default_payment_account_id)
                if acct is not None:
                    payment_account_name = acct.name
                    payment_account_type = acct.financial_account_type_code
                    payment_account_reference = acct.bank_account_number

            if self._company_repo_factory is not None:
                co_repo = self._company_repo_factory(uow.session)
                co = co_repo.get_by_id(company_id)
                if co is not None:
                    company_cnps_employer_number = co.cnps_employer_number

        # Load payment_date from the run
        run = self._run_service.get_run(company_id, detail.run_id)
        payment_date = run.payment_date

        return PayslipPreviewDTO(
            employee_number=detail.employee_number,
            employee_display_name=detail.employee_display_name,
            period_label=period_label,
            run_reference=detail.run_reference,
            period_year=detail.period_year,
            period_month=detail.period_month,
            earnings_section=PayslipSectionDTO(
                section_title="Earnings",
                lines=earnings_lines,
                subtotal=sum((l.component_amount for l in earnings_lines), Decimal("0")),
            ),
            deductions_section=PayslipSectionDTO(
                section_title="Employee Deductions",
                lines=deduction_lines,
                subtotal=sum((l.component_amount for l in deduction_lines), Decimal("0")),
            ),
            taxes_section=PayslipSectionDTO(
                section_title="Taxes",
                lines=tax_lines,
                subtotal=sum((l.component_amount for l in tax_lines), Decimal("0")),
            ),
            employer_contributions_section=PayslipSectionDTO(
                section_title="Employer Contributions",
                lines=employer_lines,
                subtotal=sum((l.component_amount for l in employer_lines), Decimal("0")),
            ),
            gross_earnings=detail.gross_earnings,
            total_deductions=detail.total_employee_deductions + detail.total_taxes,
            net_payable=detail.net_payable,
            employer_cost_base=detail.employer_cost_base,
            taxable_salary_base=detail.taxable_salary_base,
            cnps_contributory_base=detail.cnps_contributory_base,
            tdl_base=detail.tdl_base,
            employee_position_name=position_name,
            employee_department_name=department_name,
            employee_hire_date=hire_date,
            employee_nif=employee_nif,
            employee_cnps_number=employee_cnps_number,
            payment_account_name=payment_account_name,
            payment_account_type=payment_account_type,
            payment_account_reference=payment_account_reference,
            company_cnps_employer_number=company_cnps_employer_number,
            payment_date=payment_date,
        )
