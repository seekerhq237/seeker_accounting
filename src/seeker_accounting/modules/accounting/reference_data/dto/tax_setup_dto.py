from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TaxCodeListItemDTO:
    id: int
    code: str
    name: str
    tax_type_code: str
    calculation_method_code: str
    rate_percent: Decimal | None
    effective_from: date
    effective_to: date | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class TaxCodeDTO:
    id: int
    company_id: int
    code: str
    name: str
    tax_type_code: str
    calculation_method_code: str
    rate_percent: Decimal | None
    is_recoverable: bool | None
    effective_from: date
    effective_to: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CreateTaxCodeCommand:
    code: str
    name: str
    tax_type_code: str
    calculation_method_code: str
    effective_from: date
    rate_percent: Decimal | None = None
    is_recoverable: bool | None = None
    effective_to: date | None = None


@dataclass(frozen=True, slots=True)
class UpdateTaxCodeCommand:
    code: str
    name: str
    tax_type_code: str
    calculation_method_code: str
    effective_from: date
    rate_percent: Decimal | None = None
    is_recoverable: bool | None = None
    effective_to: date | None = None
