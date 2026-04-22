from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ReconciliationMatchDTO:
    id: int
    company_id: int
    reconciliation_session_id: int
    bank_statement_line_id: int
    match_entity_type: str
    match_entity_id: int
    matched_amount: Decimal
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReconciliationSessionListItemDTO:
    id: int
    company_id: int
    financial_account_id: int
    financial_account_name: str
    statement_end_date: date
    statement_ending_balance: Decimal
    status_code: str
    match_count: int
    completed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReconciliationSessionDetailDTO:
    id: int
    company_id: int
    financial_account_id: int
    financial_account_name: str
    statement_end_date: date
    statement_ending_balance: Decimal
    status_code: str
    notes: str | None
    completed_at: datetime | None
    completed_by_user_id: int | None
    created_at: datetime
    created_by_user_id: int | None
    matches: tuple[ReconciliationMatchDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ReconciliationSummaryDTO:
    total_matched_amount: Decimal
    unmatched_statement_count: int
    matched_statement_count: int
