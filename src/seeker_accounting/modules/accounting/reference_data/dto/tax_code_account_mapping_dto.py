from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TaxCodeAccountMappingDTO:
    tax_code_id: int
    tax_code_code: str
    tax_code_name: str
    sales_account_id: int | None
    sales_account_code: str | None
    sales_account_name: str | None
    purchase_account_id: int | None
    purchase_account_code: str | None
    purchase_account_name: str | None
    tax_liability_account_id: int | None
    tax_liability_account_code: str | None
    tax_liability_account_name: str | None
    tax_asset_account_id: int | None
    tax_asset_account_code: str | None
    tax_asset_account_name: str | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class SetTaxCodeAccountMappingCommand:
    tax_code_id: int
    sales_account_id: int | None = None
    purchase_account_id: int | None = None
    tax_liability_account_id: int | None = None
    tax_asset_account_id: int | None = None
