from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class StockMovementReportFilterDTO:
    company_id: int
    date_from: date | None
    date_to: date | None
    item_id: int | None = None
    location_id: int | None = None


@dataclass(frozen=True, slots=True)
class StockMovementWarningDTO:
    code: str
    severity_code: str
    message: str


@dataclass(frozen=True, slots=True)
class StockMovementSummaryRowDTO:
    item_id: int
    item_code: str
    item_name: str
    unit_of_measure_code: str
    opening_quantity: Decimal
    inward_quantity: Decimal
    outward_quantity: Decimal
    closing_quantity: Decimal
    movement_count: int


@dataclass(frozen=True, slots=True)
class StockMovementDetailRowDTO:
    document_line_id: int
    inventory_document_id: int
    posted_journal_entry_id: int | None
    item_id: int
    item_code: str
    item_name: str
    document_date: date
    document_number: str
    document_type_code: str
    reference_number: str | None
    location_id: int | None
    location_code: str | None
    location_name: str | None
    inward_quantity: Decimal
    outward_quantity: Decimal
    running_quantity: Decimal
    unit_cost: Decimal | None
    line_amount: Decimal | None


@dataclass(frozen=True, slots=True)
class StockMovementItemDetailDTO:
    company_id: int
    item_id: int
    item_code: str
    item_name: str
    unit_of_measure_code: str
    date_from: date | None
    date_to: date | None
    location_id: int | None
    opening_quantity: Decimal
    inward_quantity: Decimal
    outward_quantity: Decimal
    closing_quantity: Decimal
    rows: tuple[StockMovementDetailRowDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class StockMovementReportDTO:
    company_id: int
    date_from: date | None
    date_to: date | None
    item_id: int | None
    location_id: int | None
    location_label: str | None
    rows: tuple[StockMovementSummaryRowDTO, ...] = field(default_factory=tuple)
    total_opening_quantity: Decimal = Decimal("0.00")
    total_inward_quantity: Decimal = Decimal("0.00")
    total_outward_quantity: Decimal = Decimal("0.00")
    total_closing_quantity: Decimal = Decimal("0.00")
    warnings: tuple[StockMovementWarningDTO, ...] = field(default_factory=tuple)
