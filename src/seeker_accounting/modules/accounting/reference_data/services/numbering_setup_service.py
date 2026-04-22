from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (
    CreateDocumentSequenceCommand,
    DocumentSequenceDTO,
    DocumentSequenceListItemDTO,
    DocumentSequencePreviewDTO,
    UpdateDocumentSequenceCommand,
)
from seeker_accounting.modules.accounting.reference_data.models.document_sequence import DocumentSequence
from seeker_accounting.modules.accounting.reference_data.repositories.document_sequence_repository import (
    DocumentSequenceRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

DocumentSequenceRepositoryFactory = Callable[[Session], DocumentSequenceRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]

_VALID_DOCUMENT_TYPE_CODES = frozenset({
    "sales_invoice",
    "customer_receipt",
    "purchase_bill",
    "supplier_payment",
    "treasury_transaction",
    "journal_entry",
    "inventory_document",
    "asset",
    "depreciation_run",
    "payroll_run",
    "payroll_input_batch",
    "payroll_remittance",
    "contract",
    "contract_change_order",
    "project",
    "project_commitment",
    "project_budget_version",
})


class NumberingSetupService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        document_sequence_repository_factory: DocumentSequenceRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._document_sequence_repository_factory = document_sequence_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_document_sequences(self, company_id: int, active_only: bool = False) -> list[DocumentSequenceListItemDTO]:
        self._permission_service.require_permission("reference.document_sequences.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_document_sequence_repository(uow.session)
            rows = repository.list_by_company(company_id, active_only=active_only)
            return [self._to_document_sequence_list_item_dto(row) for row in rows]

    def get_document_sequence(self, company_id: int, sequence_id: int) -> DocumentSequenceDTO:
        self._permission_service.require_permission("reference.document_sequences.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_document_sequence_repository(uow.session)
            sequence = repository.get_by_id(company_id, sequence_id)
            if sequence is None:
                raise NotFoundError(f"Document sequence with id {sequence_id} was not found.")
            return self._to_document_sequence_dto(sequence)

    def create_document_sequence(self, company_id: int, command: CreateDocumentSequenceCommand) -> DocumentSequenceDTO:
        self._permission_service.require_permission("reference.document_sequences.create")
        normalized_document_type_code = self._require_code(command.document_type_code, "Document type code")
        if normalized_document_type_code not in _VALID_DOCUMENT_TYPE_CODES:
            raise ValidationError(
                f"Invalid document type code: {normalized_document_type_code}. "
                f"Valid: {', '.join(sorted(_VALID_DOCUMENT_TYPE_CODES))}."
            )
        normalized_prefix = self._normalize_optional_text(command.prefix)
        normalized_suffix = self._normalize_optional_text(command.suffix)
        normalized_reset_frequency_code = self._normalize_optional_text(command.reset_frequency_code)
        self._validate_inputs(command.next_number, command.padding_width)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_document_sequence_repository(uow.session)
            if repository.document_type_exists(company_id, normalized_document_type_code):
                raise ConflictError("A document sequence already exists for this document type in the company.")

            sequence = DocumentSequence(
                company_id=company_id,
                document_type_code=normalized_document_type_code,
                prefix=normalized_prefix,
                suffix=normalized_suffix,
                next_number=command.next_number,
                padding_width=command.padding_width,
                reset_frequency_code=normalized_reset_frequency_code,
            )
            repository.add(sequence)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_document_sequence_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import DOCUMENT_SEQUENCE_CREATED
            self._record_audit(company_id, DOCUMENT_SEQUENCE_CREATED, "DocumentSequence", sequence.id, f"Created document sequence for '{normalized_document_type_code}'")
            return self._to_document_sequence_dto(sequence)

    def update_document_sequence(
        self,
        company_id: int,
        sequence_id: int,
        command: UpdateDocumentSequenceCommand,
    ) -> DocumentSequenceDTO:
        self._permission_service.require_permission("reference.document_sequences.edit")
        normalized_document_type_code = self._require_code(command.document_type_code, "Document type code")
        if normalized_document_type_code not in _VALID_DOCUMENT_TYPE_CODES:
            raise ValidationError(
                f"Invalid document type code: {normalized_document_type_code}. "
                f"Valid: {', '.join(sorted(_VALID_DOCUMENT_TYPE_CODES))}."
            )
        normalized_prefix = self._normalize_optional_text(command.prefix)
        normalized_suffix = self._normalize_optional_text(command.suffix)
        normalized_reset_frequency_code = self._normalize_optional_text(command.reset_frequency_code)
        self._validate_inputs(command.next_number, command.padding_width)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_document_sequence_repository(uow.session)
            sequence = repository.get_by_id(company_id, sequence_id)
            if sequence is None:
                raise NotFoundError(f"Document sequence with id {sequence_id} was not found.")

            if repository.document_type_exists(
                company_id,
                normalized_document_type_code,
                exclude_sequence_id=sequence_id,
            ):
                raise ConflictError("A document sequence already exists for this document type in the company.")

            sequence.document_type_code = normalized_document_type_code
            sequence.prefix = normalized_prefix
            sequence.suffix = normalized_suffix
            sequence.next_number = command.next_number
            sequence.padding_width = command.padding_width
            sequence.reset_frequency_code = normalized_reset_frequency_code
            repository.save(sequence)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_document_sequence_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import DOCUMENT_SEQUENCE_UPDATED
            self._record_audit(company_id, DOCUMENT_SEQUENCE_UPDATED, "DocumentSequence", sequence.id, f"Updated document sequence id={sequence_id}")
            return self._to_document_sequence_dto(sequence)

    def deactivate_document_sequence(self, company_id: int, sequence_id: int) -> None:
        self._permission_service.require_permission("reference.document_sequences.deactivate")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_document_sequence_repository(uow.session)
            sequence = repository.get_by_id(company_id, sequence_id)
            if sequence is None:
                raise NotFoundError(f"Document sequence with id {sequence_id} was not found.")

            sequence.is_active = False
            repository.save(sequence)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Document sequence could not be deactivated.") from exc
            from seeker_accounting.modules.audit.event_type_catalog import DOCUMENT_SEQUENCE_DEACTIVATED
            self._record_audit(company_id, DOCUMENT_SEQUENCE_DEACTIVATED, "DocumentSequence", sequence.id, f"Deactivated document sequence id={sequence_id}")

    def check_sequence_available(self, company_id: int, document_type_code: str) -> None:
        """Verify that an active document sequence exists for the given type without issuing a number.

        Raises ValidationError(MISSING_DOCUMENT_SEQUENCE) if not found or inactive.
        """
        normalized = document_type_code.strip().lower()
        with self._unit_of_work_factory() as uow:
            repository = self._require_document_sequence_repository(uow.session)
            sequence = repository.get_by_document_type(company_id, normalized)
            if sequence is None or not sequence.is_active:
                raise ValidationError(
                    f"No active document sequence is configured for {document_type_code}. "
                    "Set one up in Document Sequences before continuing.",
                    app_error_code=AppErrorCode.MISSING_DOCUMENT_SEQUENCE,
                    context={"company_id": company_id, "document_type_code": normalized},
                )

    def preview_document_number(self, company_id: int, sequence_id: int) -> DocumentSequencePreviewDTO:
        self._permission_service.require_permission("reference.document_sequences.preview")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_document_sequence_repository(uow.session)
            sequence = repository.get_by_id(company_id, sequence_id)
            if sequence is None:
                raise NotFoundError(f"Document sequence with id {sequence_id} was not found.")

            return DocumentSequencePreviewDTO(
                company_id=company_id,
                sequence_id=sequence.id,
                document_type_code=sequence.document_type_code,
                next_number=sequence.next_number,
                preview_number=self._format_preview_number(sequence),
            )

    def _require_document_sequence_repository(self, session: Session | None) -> DocumentSequenceRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._document_sequence_repository_factory(session)

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        company_repository = self._company_repository_factory(session)
        if company_repository.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _require_code(self, value: str, label: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValidationError(f"{label} is required.")
        return normalized

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def _validate_inputs(self, next_number: int, padding_width: int) -> None:
        if next_number < 1:
            raise ValidationError("Next number must be at least 1.")
        if padding_width < 0:
            raise ValidationError("Padding width cannot be negative.")

    def _translate_document_sequence_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message or "uq_document_sequences" in message:
            return ConflictError("A document sequence already exists for this document type in the company.")
        return ValidationError("Document sequence data could not be saved.")

    def _format_preview_number(self, sequence: DocumentSequence) -> str:
        number_portion = (
            str(sequence.next_number).zfill(sequence.padding_width)
            if sequence.padding_width > 0
            else str(sequence.next_number)
        )
        return f"{sequence.prefix or ''}{number_portion}{sequence.suffix or ''}"

    def _to_document_sequence_list_item_dto(self, row: DocumentSequence) -> DocumentSequenceListItemDTO:
        return DocumentSequenceListItemDTO(
            id=row.id,
            document_type_code=row.document_type_code,
            prefix=row.prefix,
            suffix=row.suffix,
            next_number=row.next_number,
            padding_width=row.padding_width,
            reset_frequency_code=row.reset_frequency_code,
            is_active=row.is_active,
            updated_at=row.updated_at,
        )

    def _to_document_sequence_dto(self, row: DocumentSequence) -> DocumentSequenceDTO:
        return DocumentSequenceDTO(
            id=row.id,
            company_id=row.company_id,
            document_type_code=row.document_type_code,
            prefix=row.prefix,
            suffix=row.suffix,
            next_number=row.next_number,
            padding_width=row.padding_width,
            reset_frequency_code=row.reset_frequency_code,
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_type: str,
        entity_id: int | None,
        description: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_REFERENCE
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_REFERENCE,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
