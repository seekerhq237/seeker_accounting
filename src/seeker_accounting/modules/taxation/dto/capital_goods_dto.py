"""DTOs for the VAT Capital-Goods Register (T38)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class CapitalGoodDTO:
    """Read-only view of a registered capital asset."""

    id: int
    company_id: int
    fixed_asset_id: int | None
    asset_description: str
    acquisition_date: date
    base_amount: Decimal
    vat_recovered_initial: Decimal
    monitored_years: int
    status_code: str
    disposal_date: date | None
    notes: str | None

    @property
    def is_active(self) -> bool:
        return self.status_code == "ACTIVE"


@dataclass(frozen=True)
class RegisterCapitalGoodCommand:
    """Command to register a new capital asset in the scheme."""

    asset_description: str
    acquisition_date: date
    base_amount: Decimal
    vat_recovered_initial: Decimal
    monitored_years: int = 5
    fixed_asset_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True)
class CapitalGoodAdjustmentDTO:
    """One row in the annual adjustment report for a capital asset."""

    capital_good_id: int
    asset_description: str
    acquisition_date: date
    year_number: int          # 1-based year within monitoring period
    calendar_year: int
    pro_rata_used: float      # pro-rata at time of adjustment (0–100)
    initial_pro_rata: float   # pro-rata at acquisition
    adjustment_amount: Decimal  # positive = clawback, negative = further recovery
    base_annual_vat: Decimal
