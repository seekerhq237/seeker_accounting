from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportWarningDTO,
)


@dataclass(frozen=True, slots=True)
class TreasuryAccountSummaryRowDTO:
    financial_account_id: int
    account_code: str
    account_name: str
    account_type_code: str
    opening_balance: Decimal
    inflow_amount: Decimal
    outflow_amount: Decimal
    closing_balance: Decimal
    movement_count: int


@dataclass(frozen=True, slots=True)
class TreasuryMovementRowDTO:
    financial_account_id: int
    account_code: str
    account_name: str
    account_type_code: str
    transaction_date: date
    document_number: str
    movement_type_label: str
    reference_text: str | None
    description: str | None
    inflow_amount: Decimal
    outflow_amount: Decimal
    running_balance: Decimal
    journal_entry_id: int | None
    source_document_type: str
    source_document_id: int


@dataclass(frozen=True, slots=True)
class TreasuryReportDTO:
    company_id: int
    date_from: date | None
    date_to: date | None
    selected_financial_account_id: int | None
    account_rows: tuple[TreasuryAccountSummaryRowDTO, ...] = field(default_factory=tuple)
    movement_rows: tuple[TreasuryMovementRowDTO, ...] = field(default_factory=tuple)
    warnings: tuple[OperationalReportWarningDTO, ...] = field(default_factory=tuple)
    total_opening: Decimal = Decimal("0.00")
    total_inflow: Decimal = Decimal("0.00")
    total_outflow: Decimal = Decimal("0.00")
    total_closing: Decimal = Decimal("0.00")
    has_activity: bool = False
