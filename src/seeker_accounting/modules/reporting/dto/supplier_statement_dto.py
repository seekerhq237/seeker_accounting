from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportWarningDTO,
)


@dataclass(frozen=True, slots=True)
class SupplierStatementLineDTO:
    movement_date: date
    movement_type_label: str
    document_number: str
    reference_text: str | None
    description: str | None
    bill_amount: Decimal
    payment_amount: Decimal
    running_balance: Decimal
    journal_entry_id: int | None
    source_document_type: str
    source_document_id: int


@dataclass(frozen=True, slots=True)
class SupplierStatementReportDTO:
    company_id: int
    supplier_id: int
    supplier_code: str
    supplier_name: str
    date_from: date | None
    date_to: date | None
    opening_balance: Decimal
    total_bills: Decimal
    total_payments: Decimal
    closing_balance: Decimal
    lines: tuple[SupplierStatementLineDTO, ...] = field(default_factory=tuple)
    warnings: tuple[OperationalReportWarningDTO, ...] = field(default_factory=tuple)
    has_activity: bool = False
