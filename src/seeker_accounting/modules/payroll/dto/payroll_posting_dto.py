from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PostPayrollRunCommand:
    run_id: int
    posting_date: date
    narration: str | None = None


@dataclass(frozen=True, slots=True)
class PayrollPostingValidationIssueDTO:
    issue_code: str
    message: str
    severity: str  # "error" or "warning"


@dataclass(frozen=True, slots=True)
class PayrollPostingValidationResultDTO:
    run_id: int
    run_reference: str
    period_label: str
    has_errors: bool
    issues: tuple[PayrollPostingValidationIssueDTO, ...]

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


@dataclass(frozen=True, slots=True)
class PostingJournalLineDTO:
    account_id: int
    account_code: str
    account_name: str
    line_description: str
    debit_amount: Decimal
    credit_amount: Decimal


@dataclass(frozen=True, slots=True)
class PayrollPostingResultDTO:
    run_id: int
    run_reference: str
    journal_entry_id: int
    entry_number: str
    posting_date: date
    total_debit: Decimal
    total_credit: Decimal
    posted_at: datetime
    journal_lines: tuple[PostingJournalLineDTO, ...]
