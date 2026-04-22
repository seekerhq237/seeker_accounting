from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportWarningDTO,
)


@dataclass(frozen=True, slots=True)
class PayrollSummaryRunRowDTO:
    run_id: int
    run_reference: str
    run_label: str
    period_year: int
    period_month: int
    run_date: date
    payment_date: date | None
    status_code: str
    employee_count: int
    gross_pay: Decimal
    deductions: Decimal
    employer_cost: Decimal
    net_pay: Decimal
    total_paid: Decimal
    outstanding_net_pay: Decimal
    journal_entry_id: int | None


@dataclass(frozen=True, slots=True)
class PayrollSummaryEmployeeRowDTO:
    employee_id: int
    employee_number: str
    employee_name: str
    run_id: int | None
    run_employee_id: int | None
    gross_pay: Decimal
    deductions: Decimal
    employer_cost: Decimal
    net_pay: Decimal


@dataclass(frozen=True, slots=True)
class PayrollSummaryStatutoryRowDTO:
    authority_code: str
    authority_label: str
    total_due: Decimal
    total_remitted: Decimal
    outstanding: Decimal
    batch_count: int


@dataclass(frozen=True, slots=True)
class PayrollSummaryReportDTO:
    company_id: int
    date_from: date | None
    date_to: date | None
    selected_run_id: int | None
    run_rows: tuple[PayrollSummaryRunRowDTO, ...] = field(default_factory=tuple)
    employee_rows: tuple[PayrollSummaryEmployeeRowDTO, ...] = field(default_factory=tuple)
    statutory_rows: tuple[PayrollSummaryStatutoryRowDTO, ...] = field(default_factory=tuple)
    warnings: tuple[OperationalReportWarningDTO, ...] = field(default_factory=tuple)
    total_gross_pay: Decimal = Decimal("0.00")
    total_deductions: Decimal = Decimal("0.00")
    total_employer_cost: Decimal = Decimal("0.00")
    total_net_pay: Decimal = Decimal("0.00")
    total_paid: Decimal = Decimal("0.00")
    total_outstanding: Decimal = Decimal("0.00")
    has_data: bool = False
