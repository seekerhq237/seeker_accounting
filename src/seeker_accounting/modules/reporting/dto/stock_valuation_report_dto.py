from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class StockValuationReportFilterDTO:
    company_id: int
    as_of_date: date | None
    item_id: int | None = None
    location_id: int | None = None


@dataclass(frozen=True, slots=True)
class StockValuationWarningDTO:
    code: str
    severity_code: str
    message: str


@dataclass(frozen=True, slots=True)
class StockValuationRowDTO:
    item_id: int
    item_code: str
    item_name: str
    unit_of_measure_code: str
    valuation_basis_label: str
    quantity_on_hand: Decimal
    unit_value: Decimal | None
    total_value: Decimal
    has_metadata_warning: bool = False


@dataclass(frozen=True, slots=True)
class StockValuationReportDTO:
    company_id: int
    as_of_date: date | None
    item_id: int | None
    location_id: int | None
    location_label: str | None
    rows: tuple[StockValuationRowDTO, ...] = field(default_factory=tuple)
    total_quantity_on_hand: Decimal = Decimal("0.00")
    total_inventory_value: Decimal = Decimal("0.00")
    warnings: tuple[StockValuationWarningDTO, ...] = field(default_factory=tuple)
