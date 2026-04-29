from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine


class JournalEntryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, status_code: str | None = None) -> list[JournalEntry]:
        statement = select(JournalEntry).where(JournalEntry.company_id == company_id)
        if status_code is not None:
            statement = statement.where(JournalEntry.status_code == status_code)
        statement = statement.options(selectinload(JournalEntry.lines))
        statement = statement.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
        return list(self._session.scalars(statement))

    def list_posted_between(
        self,
        company_id: int,
        from_date: date,
        to_date: date,
    ) -> list[JournalEntry]:
        """Return posted journal entries with entry_date in the inclusive range.

        Eager-loads lines and their accounts so callers can render or export
        the entries without triggering N+1 queries.
        """
        statement = (
            select(JournalEntry)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.status_code == "POSTED",
                JournalEntry.entry_date >= from_date,
                JournalEntry.entry_date <= to_date,
            )
            .options(
                selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account),
            )
            .order_by(JournalEntry.entry_date.asc(), JournalEntry.id.asc())
        )
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, journal_entry_id: int) -> JournalEntry | None:
        statement = select(JournalEntry).where(
            JournalEntry.company_id == company_id,
            JournalEntry.id == journal_entry_id,
        )
        return self._session.scalar(statement)

    def get_detail(self, company_id: int, journal_entry_id: int) -> JournalEntry | None:
        statement = select(JournalEntry).where(
            JournalEntry.company_id == company_id,
            JournalEntry.id == journal_entry_id,
        )
        statement = statement.options(
            selectinload(JournalEntry.fiscal_period),
            selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account),
        )
        return self._session.scalar(statement)

    def get_by_entry_number(self, company_id: int, entry_number: str) -> JournalEntry | None:
        statement = select(JournalEntry).where(
            JournalEntry.company_id == company_id,
            JournalEntry.entry_number == entry_number,
        )
        return self._session.scalar(statement)

    def add(self, journal_entry: JournalEntry) -> JournalEntry:
        self._session.add(journal_entry)
        return journal_entry

    def save(self, journal_entry: JournalEntry) -> JournalEntry:
        self._session.add(journal_entry)
        return journal_entry

    def delete(self, journal_entry: JournalEntry) -> None:
        self._session.delete(journal_entry)
