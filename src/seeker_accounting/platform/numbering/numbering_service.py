from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.reference_data.repositories.document_sequence_repository import (
    DocumentSequenceRepository,
)
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode

DocumentSequenceRepositoryFactory = Callable[[Session], DocumentSequenceRepository]


class NumberingService:
    def __init__(
        self,
        document_sequence_repository_factory: DocumentSequenceRepositoryFactory,
    ) -> None:
        self._document_sequence_repository_factory = document_sequence_repository_factory

    def issue_next_number(
        self,
        session: Session,
        company_id: int,
        document_type_code: str,
    ) -> str:
        normalized_type = document_type_code.strip().lower()
        repository = self._document_sequence_repository_factory(session)
        sequence = repository.get_by_document_type(company_id, normalized_type)
        if sequence is None or not sequence.is_active:
            raise ValidationError(
                f"An active document sequence for {document_type_code} must be configured before posting.",
                app_error_code=AppErrorCode.MISSING_DOCUMENT_SEQUENCE,
                context={"company_id": company_id, "document_type_code": normalized_type},
            )
        if sequence.next_number < 1:
            raise ValidationError("Document sequence next number must be greater than zero.")

        number = self._format_number(
            prefix=sequence.prefix,
            next_number=sequence.next_number,
            padding_width=sequence.padding_width,
            suffix=sequence.suffix,
        )
        sequence.next_number += 1
        repository.save(sequence)
        return number

    def _format_number(
        self,
        *,
        prefix: str | None,
        next_number: int,
        padding_width: int,
        suffix: str | None,
    ) -> str:
        number_text = str(next_number).zfill(max(padding_width, 0))
        return f"{prefix or ''}{number_text}{suffix or ''}"
