from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DepreciationReportFilterDTO:
    company_id: int
    date_from: date | None
    date_to: date | None
    asset_id: int | None = None
    category_id: int | None = None
    status_code: str | None = None


@dataclass(frozen=True, slots=True)
class DepreciationReportWarningDTO:
    code: str
    severity_code: str
    message: str


@dataclass(frozen=True, slots=True)
class DepreciationReportRowDTO:
    asset_id: int
    asset_number: str
    asset_name: str
    category_id: int
    category_code: str
    category_name: str
    depreciation_method_code: str
    opening_accumulated_depreciation: Decimal
    current_period_depreciation: Decimal
    closing_accumulated_depreciation: Decimal
    carrying_amount: Decimal
    status_code: str


@dataclass(frozen=True, slots=True)
class DepreciationReportRunDetailRowDTO:
    run_id: int
    run_number: str | None
    run_date: date
    period_end_date: date
    depreciation_amount: Decimal
    accumulated_depreciation_after: Decimal
    carrying_amount_after: Decimal
    posted_journal_entry_id: int | None


@dataclass(frozen=True, slots=True)
class DepreciationReportDetailDTO:
    company_id: int
    asset_id: int
    date_from: date | None
    date_to: date | None
    asset_number: str
    asset_name: str
    opening_accumulated_depreciation: Decimal
    current_period_depreciation: Decimal
    closing_accumulated_depreciation: Decimal
    carrying_amount: Decimal
    rows: tuple[DepreciationReportRunDetailRowDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DepreciationReportDTO:
    company_id: int
    date_from: date | None
    date_to: date | None
    asset_id: int | None
    category_id: int | None
    status_code: str | None
    rows: tuple[DepreciationReportRowDTO, ...] = field(default_factory=tuple)
    total_opening_accumulated_depreciation: Decimal = Decimal("0.00")
    total_current_period_depreciation: Decimal = Decimal("0.00")
    total_closing_accumulated_depreciation: Decimal = Decimal("0.00")
    total_carrying_amount: Decimal = Decimal("0.00")
    warnings: tuple[DepreciationReportWarningDTO, ...] = field(default_factory=tuple)
