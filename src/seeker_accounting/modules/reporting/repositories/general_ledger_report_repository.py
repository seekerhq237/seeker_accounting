from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine


@dataclass(frozen=True, slots=True)
class LedgerLineRow:
    line_id: int
    journal_entry_id: int
    line_number: int
    entry_date: date
    entry_number: str | None
    reference_text: str | None
    journal_description: str | None
    line_description: str | None
    debit_amount: Decimal
    credit_amount: Decimal
    source_module_code: str | None
    source_document_type: str | None
    source_document_id: int | None
    posted_at: datetime | None


class GeneralLedgerReportRepository:
    """Report-shaped queries for the general ledger."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Account + balance helpers
    # ------------------------------------------------------------------

    def get_account(self, company_id: int, account_id: int) -> Account | None:
        statement = select(Account).where(
            Account.company_id == company_id,
            Account.id == account_id,
        )
        return self._session.scalar(statement)

    def sum_opening_amounts(
        self,
        company_id: int,
        account_id: int,
        date_from: date | None,
    ) -> tuple[Decimal, Decimal]:
        """Return total debit and credit amounts before the period start."""
        if date_from is None:
            return Decimal("0.00"), Decimal("0.00")

        conditions = [
            JournalEntry.company_id == company_id,
            JournalEntry.status_code == "POSTED",
            JournalEntry.posted_at.is_not(None),
            JournalEntryLine.account_id == account_id,
            JournalEntry.entry_date < date_from,
        ]
        statement = (
            select(
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("debit"),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("credit"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .where(*conditions)
        )
        row = self._session.execute(statement).one()
        return self._to_decimal(row.debit), self._to_decimal(row.credit)

    # ------------------------------------------------------------------
    # Ledger lines
    # ------------------------------------------------------------------

    def list_ledger_lines(
        self,
        company_id: int,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[LedgerLineRow]:
        conditions = [
            JournalEntry.company_id == company_id,
            JournalEntry.status_code == "POSTED",
            JournalEntry.posted_at.is_not(None),
            JournalEntryLine.account_id == account_id,
        ]
        if date_from is not None:
            conditions.append(JournalEntry.entry_date >= date_from)
        if date_to is not None:
            conditions.append(JournalEntry.entry_date <= date_to)

        statement = (
            select(
                JournalEntryLine.id.label("line_id"),
                JournalEntry.id.label("journal_entry_id"),
                JournalEntryLine.line_number,
                JournalEntry.entry_date,
                JournalEntry.entry_number,
                JournalEntry.reference_text,
                JournalEntry.description.label("journal_description"),
                JournalEntryLine.line_description,
                JournalEntryLine.debit_amount,
                JournalEntryLine.credit_amount,
                JournalEntry.source_module_code,
                JournalEntry.source_document_type,
                JournalEntry.source_document_id,
                JournalEntry.posted_at,
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .where(*conditions)
            .order_by(
                JournalEntry.entry_date.asc(),
                JournalEntry.id.asc(),
                JournalEntryLine.line_number.asc(),
                JournalEntryLine.id.asc(),
            )
        )

        result: list[LedgerLineRow] = []
        for row in self._session.execute(statement):
            result.append(
                LedgerLineRow(
                    line_id=row.line_id,
                    journal_entry_id=row.journal_entry_id,
                    line_number=row.line_number,
                    entry_date=row.entry_date,
                    entry_number=row.entry_number,
                    reference_text=row.reference_text,
                    journal_description=row.journal_description,
                    line_description=row.line_description,
                    debit_amount=self._to_decimal(row.debit_amount),
                    credit_amount=self._to_decimal(row.credit_amount),
                    source_module_code=row.source_module_code,
                    source_document_type=row.source_document_type,
                    source_document_id=row.source_document_id,
                    posted_at=row.posted_at,
                )
            )
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
