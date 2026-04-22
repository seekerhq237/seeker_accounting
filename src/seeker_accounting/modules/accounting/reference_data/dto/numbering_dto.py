from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DocumentSequenceListItemDTO:
    id: int
    document_type_code: str
    prefix: str | None
    suffix: str | None
    next_number: int
    padding_width: int
    reset_frequency_code: str | None
    is_active: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DocumentSequenceDTO:
    id: int
    company_id: int
    document_type_code: str
    prefix: str | None
    suffix: str | None
    next_number: int
    padding_width: int
    reset_frequency_code: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DocumentSequencePreviewDTO:
    company_id: int
    sequence_id: int
    document_type_code: str
    next_number: int
    preview_number: str


@dataclass(frozen=True, slots=True)
class CreateDocumentSequenceCommand:
    document_type_code: str
    next_number: int
    padding_width: int
    prefix: str | None = None
    suffix: str | None = None
    reset_frequency_code: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateDocumentSequenceCommand:
    document_type_code: str
    next_number: int
    padding_width: int
    prefix: str | None = None
    suffix: str | None = None
    reset_frequency_code: str | None = None
