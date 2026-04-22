from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateTreasuryTransferCommand:
    from_financial_account_id: int
    to_financial_account_id: int
    transfer_date: date
    currency_code: str
    amount: Decimal
    reference_number: str | None = None
    description: str | None = None
    notes: str | None = None
    exchange_rate: Decimal | None = None


@dataclass(frozen=True, slots=True)
class UpdateTreasuryTransferCommand:
    from_financial_account_id: int
    to_financial_account_id: int
    transfer_date: date
    currency_code: str
    amount: Decimal
    reference_number: str | None = None
    description: str | None = None
    notes: str | None = None
    exchange_rate: Decimal | None = None
