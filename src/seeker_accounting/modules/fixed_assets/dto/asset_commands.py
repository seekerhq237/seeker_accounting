from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateAssetCommand:
    asset_number: str
    asset_name: str
    asset_category_id: int
    acquisition_date: date
    capitalization_date: date
    acquisition_cost: Decimal
    salvage_value: Decimal | None
    useful_life_months: int
    depreciation_method_code: str
    supplier_id: int | None = None
    purchase_bill_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateAssetCommand:
    asset_number: str
    asset_name: str
    asset_category_id: int
    acquisition_date: date
    capitalization_date: date
    acquisition_cost: Decimal
    salvage_value: Decimal | None
    useful_life_months: int
    depreciation_method_code: str
    status_code: str
    supplier_id: int | None = None
    purchase_bill_id: int | None = None
    notes: str | None = None
