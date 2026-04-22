from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.reference_data.models.document_sequence import DocumentSequence


class DocumentSequenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[DocumentSequence]:
        statement = select(DocumentSequence).where(DocumentSequence.company_id == company_id)
        if active_only:
            statement = statement.where(DocumentSequence.is_active.is_(True))
        statement = statement.order_by(DocumentSequence.document_type_code.asc(), DocumentSequence.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, sequence_id: int) -> DocumentSequence | None:
        statement = select(DocumentSequence).where(
            DocumentSequence.company_id == company_id,
            DocumentSequence.id == sequence_id,
        )
        return self._session.scalar(statement)

    def get_by_document_type(self, company_id: int, document_type_code: str) -> DocumentSequence | None:
        statement = select(DocumentSequence).where(
            DocumentSequence.company_id == company_id,
            DocumentSequence.document_type_code == document_type_code,
        ).with_for_update()
        return self._session.scalar(statement)

    def add(self, sequence: DocumentSequence) -> DocumentSequence:
        self._session.add(sequence)
        return sequence

    def save(self, sequence: DocumentSequence) -> DocumentSequence:
        self._session.add(sequence)
        return sequence

    def document_type_exists(
        self,
        company_id: int,
        document_type_code: str,
        exclude_sequence_id: int | None = None,
    ) -> bool:
        predicate = (
            (DocumentSequence.company_id == company_id)
            & (DocumentSequence.document_type_code == document_type_code)
        )
        if exclude_sequence_id is not None:
            predicate = predicate & (DocumentSequence.id != exclude_sequence_id)
        return bool(self._session.scalar(select(exists().where(predicate))))
