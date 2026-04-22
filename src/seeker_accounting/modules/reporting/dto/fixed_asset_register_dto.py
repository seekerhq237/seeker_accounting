from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FixedAssetRegisterFilterDTO:
    company_id: int
    as_of_date: date | None
    asset_id: int | None = None
    category_id: int | None = None
    status_code: str | None = None


@dataclass(frozen=True, slots=True)
class FixedAssetRegisterWarningDTO:
    code: str
    severity_code: str
    message: str


@dataclass(frozen=True, slots=True)
class FixedAssetRegisterRowDTO:
    asset_id: int
    asset_number: str
    asset_name: str
    category_id: int
    category_code: str
    category_name: str
    acquisition_date: date
    acquisition_cost: Decimal
    useful_life_months: int
    depreciation_method_code: str
    accumulated_depreciation: Decimal
    carrying_amount: Decimal
    status_code: str


@dataclass(frozen=True, slots=True)
class FixedAssetDepreciationHistoryRowDTO:
    run_id: int
    run_number: str | None
    run_date: date
    period_end_date: date
    depreciation_amount: Decimal
    accumulated_depreciation_after: Decimal
    carrying_amount_after: Decimal
    posted_journal_entry_id: int | None


@dataclass(frozen=True, slots=True)
class FixedAssetRegisterDetailDTO:
    company_id: int
    asset_id: int
    as_of_date: date | None
    asset_number: str
    asset_name: str
    category_name: str
    acquisition_cost: Decimal
    accumulated_depreciation: Decimal
    carrying_amount: Decimal
    history_rows: tuple[FixedAssetDepreciationHistoryRowDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class FixedAssetRegisterReportDTO:
    company_id: int
    as_of_date: date | None
    asset_id: int | None
    category_id: int | None
    status_code: str | None
    rows: tuple[FixedAssetRegisterRowDTO, ...] = field(default_factory=tuple)
    total_acquisition_cost: Decimal = Decimal("0.00")
    total_accumulated_depreciation: Decimal = Decimal("0.00")
    total_carrying_amount: Decimal = Decimal("0.00")
    warnings: tuple[FixedAssetRegisterWarningDTO, ...] = field(default_factory=tuple)
