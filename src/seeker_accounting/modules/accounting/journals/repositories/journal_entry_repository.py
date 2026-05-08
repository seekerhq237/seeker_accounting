from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
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

    def list_filtered_page(
        self,
        company_id: int,
        query: str | None = None,
        status_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[JournalEntry]:
        stmt = self._build_filter(company_id, query, status_code)
        stmt = stmt.offset(max(offset, 0)).limit(max(limit, 1))
        return list(self._session.scalars(stmt))

    def count_filtered(
        self,
        company_id: int,
        query: str | None = None,
        status_code: str | None = None,
    ) -> int:
        inner = self._build_filter(company_id, query, status_code)
        count_stmt = select(func.count()).select_from(inner.subquery())
        return self._session.scalar(count_stmt) or 0

    def _build_filter(
        self,
        company_id: int,
        query: str | None = None,
        status_code: str | None = None,
    ):
        stmt = select(JournalEntry).where(JournalEntry.company_id == company_id)
        if status_code is not None:
            stmt = stmt.where(JournalEntry.status_code == status_code)
        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    JournalEntry.entry_number.ilike(pattern),
                    JournalEntry.reference.ilike(pattern),
                    JournalEntry.memo.ilike(pattern),
                )
            )
        return stmt.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())

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
