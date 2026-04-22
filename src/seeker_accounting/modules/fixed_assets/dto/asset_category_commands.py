from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateAssetCategoryCommand:
    code: str
    name: str
    asset_account_id: int
    accumulated_depreciation_account_id: int
    depreciation_expense_account_id: int
    default_useful_life_months: int
    default_depreciation_method_code: str


@dataclass(frozen=True, slots=True)
class UpdateAssetCategoryCommand:
    code: str
    name: str
    asset_account_id: int
    accumulated_depreciation_account_id: int
    depreciation_expense_account_id: int
    default_useful_life_months: int
    default_depreciation_method_code: str
    is_active: bool
