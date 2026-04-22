from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DepreciationScheduleLineDTO:
    period_number: int           # 1-indexed month number from capitalization
    period_label: str            # e.g. "Month 1", "Month 24"
    opening_nbv: Decimal
    depreciation_amount: Decimal
    accumulated_depreciation: Decimal
    closing_nbv: Decimal


@dataclass(frozen=True, slots=True)
class DepreciationScheduleDTO:
    asset_id: int
    asset_number: str
    asset_name: str
    acquisition_cost: Decimal
    salvage_value: Decimal
    useful_life_months: int
    depreciation_method_code: str
    capitalization_date: date
    depreciable_base: Decimal
    total_depreciation: Decimal
    lines: tuple[DepreciationScheduleLineDTO, ...]


@dataclass(frozen=True, slots=True)
class AssetDepreciationRunLineDTO:
    id: int
    asset_id: int
    asset_number: str
    asset_name: str
    depreciation_amount: Decimal
    accumulated_depreciation_after: Decimal
    net_book_value_after: Decimal


@dataclass(frozen=True, slots=True)
class AssetDepreciationRunListItemDTO:
    id: int
    company_id: int
    run_number: str | None
    run_date: date
    period_end_date: date
    status_code: str
    posted_at: datetime | None
    asset_count: int
    total_depreciation: Decimal


@dataclass(frozen=True, slots=True)
class AssetDepreciationRunDetailDTO:
    id: int
    company_id: int
    run_number: str | None
    run_date: date
    period_end_date: date
    status_code: str
    posted_journal_entry_id: int | None
    posted_at: datetime | None
    posted_by_user_id: int | None
    created_at: datetime
    lines: tuple[AssetDepreciationRunLineDTO, ...]
    asset_count: int
    total_depreciation: Decimal


@dataclass(frozen=True, slots=True)
class DepreciationPostingResultDTO:
    run_id: int
    run_number: str
    company_id: int
    period_end_date: date
    posted_journal_entry_id: int
    asset_count: int
    total_depreciation: Decimal
    posted_at: datetime
    posted_by_user_id: int | None
