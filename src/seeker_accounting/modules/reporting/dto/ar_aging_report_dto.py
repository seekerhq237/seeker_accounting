from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportWarningDTO,
)


@dataclass(frozen=True, slots=True)
class ARAgingCustomerRowDTO:
    customer_id: int
    customer_code: str
    customer_name: str
    document_count: int
    current_amount: Decimal
    bucket_1_30_amount: Decimal
    bucket_31_60_amount: Decimal
    bucket_61_90_amount: Decimal
    bucket_91_plus_amount: Decimal
    total_amount: Decimal


@dataclass(frozen=True, slots=True)
class ARAgingReportDTO:
    company_id: int
    as_of_date: date
    rows: tuple[ARAgingCustomerRowDTO, ...] = field(default_factory=tuple)
    warnings: tuple[OperationalReportWarningDTO, ...] = field(default_factory=tuple)
    customer_count: int = 0
    total_current: Decimal = Decimal("0.00")
    total_bucket_1_30: Decimal = Decimal("0.00")
    total_bucket_31_60: Decimal = Decimal("0.00")
    total_bucket_61_90: Decimal = Decimal("0.00")
    total_bucket_91_plus: Decimal = Decimal("0.00")
    grand_total: Decimal = Decimal("0.00")
