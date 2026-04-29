"""Repository helpers for the Cash Flow Forecast service.

Computes posted-only GL balances for a set of cash/bank GL accounts as at a
given date. Read-only.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine


class CashFlowForecastRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def sum_cash_balance_as_of(
        self,
        company_id: int,
        gl_account_ids: Iterable[int],
        as_of_date: date,
    ) -> Decimal:
        """Return debit − credit (cash assets are debit-natural) across the
        given GL accounts as at the date, posted only.
        """
        ids = list({int(a) for a in gl_account_ids})
        if not ids:
            return Decimal("0.00")
        stmt = (
            select(
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("debit"),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("credit"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.status_code == "POSTED",
                JournalEntry.posted_at.is_not(None),
                JournalEntry.entry_date <= as_of_date,
                JournalEntryLine.account_id.in_(ids),
            )
        )
        row = self._session.execute(stmt).one()
        debit = Decimal(str(row.debit or 0))
        credit = Decimal(str(row.credit or 0))
        return (debit - credit).quantize(Decimal("0.01"))
