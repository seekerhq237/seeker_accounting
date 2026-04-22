from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class JournalLineCommand:
    account_id: int
    line_description: str | None = None
    debit_amount: Decimal | None = None
    credit_amount: Decimal | None = None
    contract_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class CreateJournalEntryCommand:
    entry_date: date | None = None
    transaction_date: date | None = None
    journal_type_code: str = ""
    reference_text: str | None = None
    description: str | None = None
    source_module_code: str | None = None
    source_document_type: str | None = None
    source_document_id: int | None = None
    lines: tuple[JournalLineCommand, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class UpdateJournalEntryCommand:
    entry_date: date | None = None
    transaction_date: date | None = None
    journal_type_code: str = ""
    reference_text: str | None = None
    description: str | None = None
    source_module_code: str | None = None
    source_document_type: str | None = None
    source_document_id: int | None = None
    lines: tuple[JournalLineCommand, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PostJournalCommand:
    actor_user_id: int | None = None
