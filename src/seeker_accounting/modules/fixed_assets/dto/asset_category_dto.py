from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AssetCategoryListItemDTO:
    id: int
    company_id: int
    code: str
    name: str
    asset_account_id: int
    asset_account_code: str
    asset_account_name: str
    accumulated_depreciation_account_id: int
    accumulated_depreciation_account_code: str
    accumulated_depreciation_account_name: str
    depreciation_expense_account_id: int
    depreciation_expense_account_code: str
    depreciation_expense_account_name: str
    default_useful_life_months: int
    default_depreciation_method_code: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class AssetCategoryDetailDTO:
    id: int
    company_id: int
    code: str
    name: str
    asset_account_id: int
    asset_account_code: str
    asset_account_name: str
    accumulated_depreciation_account_id: int
    accumulated_depreciation_account_code: str
    accumulated_depreciation_account_name: str
    depreciation_expense_account_id: int
    depreciation_expense_account_code: str
    depreciation_expense_account_name: str
    default_useful_life_months: int
    default_depreciation_method_code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
