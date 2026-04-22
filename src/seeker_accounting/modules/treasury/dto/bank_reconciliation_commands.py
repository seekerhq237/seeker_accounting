from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateReconciliationSessionCommand:
    financial_account_id: int
    statement_end_date: date
    statement_ending_balance: Decimal
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class AddReconciliationMatchCommand:
    bank_statement_line_id: int
    match_entity_type: str
    match_entity_id: int
    matched_amount: Decimal
