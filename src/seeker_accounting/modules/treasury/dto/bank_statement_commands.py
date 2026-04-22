from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ImportBankStatementCommand:
    financial_account_id: int
    file_path: str
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CreateManualStatementLineCommand:
    financial_account_id: int
    line_date: date
    description: str
    debit_amount: Decimal
    credit_amount: Decimal
    value_date: date | None = None
    reference: str | None = None
