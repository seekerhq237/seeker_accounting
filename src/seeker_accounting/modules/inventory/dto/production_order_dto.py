from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateProductionOrderCommand:
    bom_id: int
    order_date: date
    quantity_to_produce: Decimal
    location_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CompleteProductionOrderCommand:
    production_order_id: int
    component_issue_document_id: int
    finished_receipt_document_id: int
    completed_by_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class BuildProductionDocumentsCommand:
    production_order_id: int
    post_immediately: bool = False
    actor_user_id: int | None = None
    component_batch_ids: dict[int, int] | None = None
    component_serial_ids: dict[int, tuple[int, ...]] | None = None


@dataclass(frozen=True, slots=True)
class ProductionOrderDTO:
    id: int
    company_id: int
    order_number: str
    bom_id: int
    finished_item_id: int
    location_id: int | None
    order_date: date
    quantity_to_produce: Decimal
    status_code: str
    component_issue_document_id: int | None
    finished_receipt_document_id: int | None
    completed_at: datetime | None
    completed_by_user_id: int | None
    notes: str | None