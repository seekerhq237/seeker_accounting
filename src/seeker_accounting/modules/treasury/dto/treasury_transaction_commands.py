from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TreasuryTransactionLineCommand:
    account_id: int
    line_description: str
    amount: Decimal
    party_type: str | None = None
    party_id: int | None = None
    tax_code_id: int | None = None
    contract_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class CreateTreasuryTransactionCommand:
    transaction_type_code: str
    financial_account_id: int
    transaction_date: date
    currency_code: str
    reference_number: str | None = None
    description: str | None = None
    notes: str | None = None
    exchange_rate: Decimal | None = None
    contract_id: int | None = None
    project_id: int | None = None
    lines: tuple[TreasuryTransactionLineCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class UpdateTreasuryTransactionCommand:
    transaction_type_code: str
    financial_account_id: int
    transaction_date: date
    currency_code: str
    reference_number: str | None = None
    description: str | None = None
    notes: str | None = None
    exchange_rate: Decimal | None = None
    contract_id: int | None = None
    project_id: int | None = None
    lines: tuple[TreasuryTransactionLineCommand, ...] = ()
