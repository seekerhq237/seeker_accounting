from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AssetListItemDTO:
    id: int
    company_id: int
    asset_number: str
    asset_name: str
    asset_category_id: int
    asset_category_code: str
    asset_category_name: str
    acquisition_date: date
    capitalization_date: date
    acquisition_cost: Decimal
    salvage_value: Decimal | None
    useful_life_months: int
    depreciation_method_code: str
    status_code: str
    supplier_id: int | None
    supplier_name: str | None


@dataclass(frozen=True, slots=True)
class AssetDetailDTO:
    id: int
    company_id: int
    asset_number: str
    asset_name: str
    asset_category_id: int
    asset_category_code: str
    asset_category_name: str
    acquisition_date: date
    capitalization_date: date
    acquisition_cost: Decimal
    salvage_value: Decimal | None
    useful_life_months: int
    depreciation_method_code: str
    status_code: str
    supplier_id: int | None
    supplier_name: str | None
    purchase_bill_id: int | None
    notes: str | None
    # Category account mapping (inherited)
    asset_account_id: int
    asset_account_code: str
    accumulated_depreciation_account_id: int
    depreciation_expense_account_id: int
    created_at: datetime
    updated_at: datetime
