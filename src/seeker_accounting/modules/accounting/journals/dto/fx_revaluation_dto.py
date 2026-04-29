"""DTOs for FX Revaluation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FxRevaluationLineCommand:
    """One account being revalued.

    The caller supplies:
      - account_id: the account whose monetary balance is foreign-currency-denominated
      - current_book_amount: the account's current local-currency carrying balance
        (positive = debit-side balance, negative = credit-side balance)
      - target_amount: the new local-currency carrying balance after revaluation
        (same sign convention)

    The service writes a single line per row that brings the account from
    current_book_amount → target_amount, with the offset booked to the gain or
    loss account based on overall direction.
    """

    account_id: int
    current_book_amount: Decimal
    target_amount: Decimal
    description: str | None = None


@dataclass(frozen=True, slots=True)
class FxRevaluationCommand:
    revaluation_date: date
    lines: tuple[FxRevaluationLineCommand, ...]
    gain_account_id: int
    loss_account_id: int
    reference: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class FxRevaluationResultDTO:
    journal_entry_id: int
    journal_entry_number: str
    revaluation_date: date
    total_gain: Decimal
    total_loss: Decimal
    net_adjustment: Decimal
    line_count: int
    posted_at: datetime
