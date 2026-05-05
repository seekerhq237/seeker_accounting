from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class InventoryImportRowCommand:
    row_number: int
    status_code: str
    normalized_json: str | None = None
    error_messages_json: str | None = None


@dataclass(frozen=True, slots=True)
class CreateInventoryImportJobCommand:
    template_code: str
    source_filename: str | None = None
    preview_json: str | None = None
    error_summary: str | None = None
    created_by_user_id: int | None = None
    rows: tuple[InventoryImportRowCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class ApplyInventoryImportJobCommand:
    job_id: int
    applied_by_user_id: int | None = None
    post_documents_immediately: bool = False


@dataclass(frozen=True, slots=True)
class InventoryImportJobRowDTO:
    id: int
    job_id: int
    row_number: int
    status_code: str
    normalized_json: str | None
    error_messages_json: str | None


@dataclass(frozen=True, slots=True)
class InventoryImportJobDTO:
    id: int
    company_id: int
    template_code: str
    source_filename: str | None
    status_code: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    conflict_rows: int
    applied_at: datetime | None
    applied_by_user_id: int | None
    created_by_user_id: int | None
    preview_json: str | None
    error_summary: str | None
    rows: tuple[InventoryImportJobRowDTO, ...]