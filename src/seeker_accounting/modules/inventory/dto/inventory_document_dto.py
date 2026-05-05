from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class InventoryDocumentLineDTO:
    id: int
    line_number: int
    item_id: int
    item_code: str
    item_name: str
    batch_id: int | None
    batch_number: str | None
    serial_ids: tuple[int, ...]
    serial_numbers: tuple[str, ...]
    quantity: Decimal
    unit_cost: Decimal | None
    line_amount: Decimal | None
    counterparty_account_id: int | None
    counterparty_account_code: str | None
    line_description: str | None
    transaction_uom_id: int | None = None
    transaction_uom_code: str | None = None
    uom_ratio_snapshot: Decimal | None = None
    base_quantity: Decimal | None = None
    contract_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class InventoryDocumentListItemDTO:
    id: int
    company_id: int
    document_number: str
    document_type_code: str
    document_date: date
    status_code: str
    reference_number: str | None
    total_value: Decimal
    posted_at: datetime | None
    updated_at: datetime
    submitted_at: datetime | None = None
    submitted_by_user_id: int | None = None
    reversal_document_id: int | None = None
    reversal_of_document_id: int | None = None


@dataclass(frozen=True, slots=True)
class InventoryDocumentDetailDTO:
    id: int
    company_id: int
    document_number: str
    document_type_code: str
    document_date: date
    status_code: str
    location_id: int | None
    reference_number: str | None
    notes: str | None
    total_value: Decimal
    posted_journal_entry_id: int | None
    posted_at: datetime | None
    posted_by_user_id: int | None
    submitted_at: datetime | None
    submitted_by_user_id: int | None
    approved_at: datetime | None
    approved_by_user_id: int | None
    cancellation_reason_code_id: int | None
    cancelled_at: datetime | None
    cancelled_by_user_id: int | None
    reversal_of_document_id: int | None
    reversal_document_id: int | None
    reverse_reason_code_id: int | None
    reversed_at: datetime | None
    reversed_by_user_id: int | None
    reversing_journal_entry_id: int | None
    created_at: datetime
    updated_at: datetime
    contract_id: int | None = None
    project_id: int | None = None
    reason_code_id: int | None = None
    reason_code_code: str | None = None
    source_module_code: str | None = None
    source_document_type: str | None = None
    source_document_id: int | None = None
    stock_count_session_id: int | None = None
    bom_id: int | None = None
    production_order_id: int | None = None
    lines: tuple[InventoryDocumentLineDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class InventoryPostingResultDTO:
    company_id: int
    document_id: int
    document_number: str
    journal_entry_id: int
    journal_entry_number: str
    posted_at: datetime
    posted_by_user_id: int | None


@dataclass(frozen=True, slots=True)
class InventoryReversalResultDTO:
    company_id: int
    original_document_id: int
    reversal_document_id: int
    reversal_document_number: str
    reversing_journal_entry_id: int
    reversing_journal_entry_number: str
    reversed_at: datetime
    reversed_by_user_id: int | None
