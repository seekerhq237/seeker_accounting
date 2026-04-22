from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class InventoryDocumentLineCommand:
    item_id: int
    quantity: Decimal
    unit_cost: Decimal | None = None
    counterparty_account_id: int | None = None
    line_description: str | None = None
    transaction_uom_id: int | None = None
    contract_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class CreateInventoryDocumentCommand:
    document_type_code: str
    document_date: date
    location_id: int | None = None
    reference_number: str | None = None
    notes: str | None = None
    contract_id: int | None = None
    project_id: int | None = None
    lines: tuple[InventoryDocumentLineCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class UpdateInventoryDocumentCommand:
    document_type_code: str
    document_date: date
    location_id: int | None = None
    reference_number: str | None = None
    notes: str | None = None
    contract_id: int | None = None
    project_id: int | None = None
    lines: tuple[InventoryDocumentLineCommand, ...] = ()
