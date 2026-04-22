from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PayrollRunSummaryDTO:
    run_id: int
    run_reference: str
    run_label: str
    period_year: int
    period_month: int
    status_code: str
    currency_code: str
    total_gross_earnings: Decimal
    total_net_payable: Decimal
    total_taxes: Decimal
    total_employee_deductions: Decimal
    total_employer_contributions: Decimal
    total_employer_cost: Decimal
    included_count: int
    error_count: int
    paid_count: int
    partial_count: int
    unpaid_count: int
    is_posted: bool
    journal_entry_id: int | None


@dataclass(frozen=True, slots=True)
class PayrollStatutoryExposureDTO:
    remittance_authority_code: str
    authority_label: str
    total_due: Decimal
    total_remitted: Decimal
    outstanding: Decimal
    batch_count: int


@dataclass(frozen=True, slots=True)
class PayrollNetPayExposureDTO:
    total_net_payable: Decimal
    total_paid: Decimal
    outstanding: Decimal
    paid_count: int
    partial_count: int
    unpaid_count: int


@dataclass(frozen=True, slots=True)
class PayrollPeriodSummaryDTO:
    company_id: int
    period_year: int
    period_month: int
    run_summary: PayrollRunSummaryDTO | None
    net_pay_exposure: PayrollNetPayExposureDTO
    statutory_exposures: tuple[PayrollStatutoryExposureDTO, ...]
