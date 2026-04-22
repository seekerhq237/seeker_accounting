from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BankStatementLineDTO:
    id: int
    company_id: int
    financial_account_id: int
    import_batch_id: int | None
    line_date: date
    value_date: date | None
    description: str
    reference: str | None
    debit_amount: Decimal
    credit_amount: Decimal
    is_reconciled: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BankStatementImportBatchDTO:
    id: int
    company_id: int
    financial_account_id: int
    file_name: str | None
    import_source: str
    statement_start_date: date | None
    statement_end_date: date | None
    line_count: int
    notes: str | None
    imported_at: datetime
    imported_by_user_id: int | None


@dataclass(frozen=True, slots=True)
class ImportResultDTO:
    batch_id: int
    lines_imported: int
    statement_start_date: date | None
    statement_end_date: date | None
