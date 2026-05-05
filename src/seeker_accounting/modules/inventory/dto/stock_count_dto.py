from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateStockCountPlanCommand:
    plan_date: date
    location_ids: tuple[int, ...]
    cycle_class_code: str | None = None
    item_filter_json: str | None = None
    notes: str | None = None
    created_by_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class StartStockCountSessionCommand:
    plan_id: int
    session_date: date
    notes: str | None = None
    frozen_by_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class EnterStockCountLineCommand:
    line_id: int
    counted_quantity: Decimal
    variance_reason_code_id: int | None = None
    counted_by_user_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ApproveStockCountSessionCommand:
    session_id: int
    approved_by_user_id: int | None = None
    notes: str | None = None
    post_adjustments_immediately: bool = False


@dataclass(frozen=True, slots=True)
class StockCountLineDTO:
    id: int
    session_id: int
    item_id: int
    location_id: int | None
    snapshot_quantity: Decimal
    snapshot_value: Decimal
    counted_quantity: Decimal | None
    variance_quantity: Decimal | None
    variance_value: Decimal | None
    variance_reason_code_id: int | None
    counted_by_user_id: int | None
    counted_at: datetime | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class StockCountPlanDTO:
    id: int
    company_id: int
    plan_number: str
    plan_date: date
    status_code: str
    location_ids: tuple[int, ...]
    cycle_class_code: str | None
    item_filter_json: str | None
    notes: str | None
    created_by_user_id: int | None


@dataclass(frozen=True, slots=True)
class StockCountSessionDTO:
    id: int
    company_id: int
    plan_id: int
    session_number: str
    session_date: date
    status_code: str
    frozen_at: datetime | None
    frozen_by_user_id: int | None
    approved_at: datetime | None
    approved_by_user_id: int | None
    posted_at: datetime | None
    posted_by_user_id: int | None
    notes: str | None
    lines: tuple[StockCountLineDTO, ...]
    adjustment_document_ids: tuple[int, ...] = ()