from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine


class JournalEntryLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_entry(self, journal_entry_id: int) -> list[JournalEntryLine]:
        statement = select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == journal_entry_id)
        statement = statement.order_by(JournalEntryLine.line_number.asc(), JournalEntryLine.id.asc())
        return list(self._session.scalars(statement))

    def replace_lines(
        self,
        journal_entry_id: int,
        lines: list[JournalEntryLine],
    ) -> list[JournalEntryLine]:
        for existing_line in self.list_for_entry(journal_entry_id):
            self._session.delete(existing_line)
        self._session.flush()
        for line in lines:
            line.journal_entry_id = journal_entry_id
            self._session.add(line)
        return lines

    def add(self, line: JournalEntryLine) -> JournalEntryLine:
        self._session.add(line)
        return line

    def save(self, line: JournalEntryLine) -> JournalEntryLine:
        self._session.add(line)
        return line
