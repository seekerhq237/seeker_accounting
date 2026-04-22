from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PrintPayslipRequestDTO:
    company_id: int
    run_id: int
    run_employee_ids: tuple[int, ...]  # empty = all included employees


@dataclass(frozen=True, slots=True)
class PrintPayrollSummaryRequestDTO:
    company_id: int
    run_id: int


@dataclass(frozen=True, slots=True)
class PayslipPrintDataDTO:
    """All data needed to render one printable payslip."""
    # Company (employer) block
    company_name: str
    company_tax_identifier: str | None
    company_address: str | None
    company_city: str | None
    company_phone: str | None
    company_logo_storage_path: str | None
    # Employee block
    employee_number: str
    employee_display_name: str
    employee_position: str | None
    employee_department: str | None
    employee_hire_date: date | None
    employee_nif: str | None
    employee_cnps_number: str | None
    # Company CNPS
    company_cnps_employer_number: str | None
    # Payment account
    payment_account_name: str | None
    payment_account_type: str | None
    payment_account_reference: str | None
    # Period / payment info
    period_label: str
    period_year: int
    period_month: int
    payment_date: date | None
    run_reference: str
    currency_code: str
    # Sections
    earnings: tuple[tuple[str, Decimal], ...]  # (component_name, amount)
    deductions: tuple[tuple[str, Decimal], ...]
    taxes: tuple[tuple[str, Decimal], ...]
    employer_contributions: tuple[tuple[str, Decimal], ...]
    # Totals
    gross_earnings: Decimal
    total_deductions: Decimal
    total_taxes: Decimal
    net_payable: Decimal
    employer_cost: Decimal
    total_employer_contributions: Decimal
    # Statutory bases
    taxable_salary_base: Decimal
    cnps_contributory_base: Decimal
    tdl_base: Decimal


@dataclass(frozen=True, slots=True)
class PayrollSummaryPrintDataDTO:
    """All data needed to render a payroll run summary report."""
    company_name: str
    run_reference: str
    run_label: str
    period_label: str
    currency_code: str
    employee_count: int
    total_gross_earnings: Decimal
    total_deductions: Decimal
    total_taxes: Decimal
    total_net_payable: Decimal
    total_employer_contributions: Decimal
    total_employer_cost: Decimal
    employee_lines: tuple[tuple[str, str, Decimal, Decimal, Decimal], ...]
    # (employee_number, display_name, gross, deductions+taxes, net)
