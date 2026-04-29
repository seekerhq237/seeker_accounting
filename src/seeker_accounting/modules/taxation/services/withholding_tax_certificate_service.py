"""Service for the withholding-tax certificate register.

Phase 5 / Slice T13. Provides record / update / void / list /
aggregate operations for the WHT register.

Permissions:
* ``taxation.withholding.view``   — list and aggregate
* ``taxation.withholding.manage`` — record, update, void
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.taxation.constants import (
    ALL_WHT_COUNTERPARTY_KINDS,
    ALL_WHT_DIRECTION_CODES,
    WHT_DIRECTION_INBOUND,
    WHT_DIRECTION_OUTBOUND,
    WHT_STATUS_ISSUED,
    WHT_STATUS_RECEIVED,
    WHT_STATUS_VOIDED,
)
from seeker_accounting.modules.taxation.dto.withholding_tax_certificate_dto import (
    LinkWithholdingCertificateToJournalEntryCommand,
    RecordWithholdingTaxCertificateCommand,
    UpdateWithholdingTaxCertificateCommand,
    VoidWithholdingTaxCertificateCommand,
    WithholdingTaxCertificateDTO,
    WithholdingTaxRegisterTotalsDTO,
)
from seeker_accounting.modules.taxation.models.withholding_tax_certificate import (
    WithholdingTaxCertificate,
)
from seeker_accounting.modules.taxation.repositories.withholding_tax_certificate_repository import (
    WithholdingTaxCertificateRepository,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService


WithholdingTaxCertificateRepositoryFactory = Callable[
    [Session], WithholdingTaxCertificateRepository
]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]


_ZERO = Decimal("0.00")


# ``source_document_type`` value used when an outbound certificate is
# linked to the supplier-payment journal entry that recorded the
# withholding deduction. Centralized here so both the service and the
# DSF/reporting layer share a single canonical token.
SOURCE_DOC_JOURNAL_ENTRY = "journal_entry"


class WithholdingTaxCertificateService:
    PERMISSION_VIEW = "taxation.withholding.view"
    PERMISSION_MANAGE = "taxation.withholding.manage"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        certificate_repository_factory: WithholdingTaxCertificateRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
        journal_entry_repository_factory: JournalEntryRepositoryFactory | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._certificate_repository_factory = certificate_repository_factory
        self._company_repository_factory = company_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service
        self._journal_entry_repository_factory = journal_entry_repository_factory

    # ---------------- Read ----------------

    def get_certificate(
        self, company_id: int, certificate_id: int
    ) -> WithholdingTaxCertificateDTO:
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._certificate_repository_factory(uow.session)
            certificate = repo.get_by_id(company_id, certificate_id)
            if certificate is None:
                raise NotFoundError(
                    f"Withholding tax certificate {certificate_id} was not found."
                )
            return self._to_dto(certificate)

    def list_certificates(
        self,
        company_id: int,
        *,
        direction: str | None = None,
        status_code: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[WithholdingTaxCertificateDTO]:
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        if direction is not None and direction not in ALL_WHT_DIRECTION_CODES:
            raise ValidationError(
                f"Direction '{direction}' is not recognized.",
            )
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._certificate_repository_factory(uow.session)
            rows = repo.list_by_company(
                company_id,
                direction=direction,
                status_code=status_code,
                date_from=date_from,
                date_to=date_to,
            )
            return [self._to_dto(r) for r in rows]

    def aggregate_totals(
        self,
        company_id: int,
        *,
        direction: str,
        date_from: date,
        date_to: date,
    ) -> WithholdingTaxRegisterTotalsDTO:
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        if direction not in ALL_WHT_DIRECTION_CODES:
            raise ValidationError(f"Direction '{direction}' is not recognized.")
        if date_from > date_to:
            raise ValidationError(
                "date_from cannot be after date_to.",
            )
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._certificate_repository_factory(uow.session)
            count, total_base, total_amount = repo.aggregate_totals(
                company_id,
                direction=direction,
                date_from=date_from,
                date_to=date_to,
            )
            return WithholdingTaxRegisterTotalsDTO(
                direction=direction,
                period_start=date_from,
                period_end=date_to,
                certificate_count=count,
                total_taxable_base=total_base,
                total_tax_amount=total_amount,
            )

    # ---------------- Write ----------------

    def record_certificate(
        self,
        company_id: int,
        command: RecordWithholdingTaxCertificateCommand,
        actor_user_id: int | None = None,
    ) -> WithholdingTaxCertificateDTO:
        self._permission_service.require_permission(self.PERMISSION_MANAGE)
        self._validate_payload(
            direction=command.direction,
            counterparty_kind=command.counterparty_kind,
            counterparty_name=command.counterparty_name,
            counterparty_niu=command.counterparty_niu,
            certificate_number=command.certificate_number,
            certificate_date=command.certificate_date,
            taxable_base=command.taxable_base,
            tax_amount=command.tax_amount,
            notes=command.notes,
            evidence_attachment_path=command.evidence_attachment_path,
        )

        actor_id = (
            actor_user_id
            if actor_user_id is not None
            else self._app_context.current_user_id
        )

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._certificate_repository_factory(uow.session)

            if (
                repo.find_existing_certificate_number(
                    company_id,
                    command.direction,
                    command.certificate_number.strip(),
                )
                is not None
            ):
                raise ConflictError(
                    "A withholding-tax certificate with this number already "
                    "exists for the same direction.",
                )

            certificate = WithholdingTaxCertificate(
                company_id=company_id,
                fiscal_period_id=command.fiscal_period_id,
                direction=command.direction,
                counterparty_kind=command.counterparty_kind,
                counterparty_id=command.counterparty_id,
                counterparty_name=command.counterparty_name.strip(),
                counterparty_niu=(
                    command.counterparty_niu.strip()
                    if command.counterparty_niu is not None
                    else None
                ),
                tax_code_id=command.tax_code_id,
                certificate_number=command.certificate_number.strip(),
                certificate_date=command.certificate_date,
                source_document_type=command.source_document_type,
                source_document_id=command.source_document_id,
                taxable_base=Decimal(command.taxable_base).quantize(Decimal("0.01")),
                tax_amount=Decimal(command.tax_amount).quantize(Decimal("0.01")),
                evidence_attachment_path=command.evidence_attachment_path,
                status_code=(
                    WHT_STATUS_RECEIVED
                    if command.direction == WHT_DIRECTION_INBOUND
                    else WHT_STATUS_ISSUED
                ),
                notes=(command.notes.strip() if command.notes else None),
                recorded_by_user_id=actor_id,
            )
            repo.add(certificate)

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Withholding tax certificate could not be saved due to a "
                    "data conflict.",
                ) from exc

            self._record_audit(
                company_id,
                "WITHHOLDING_TAX_CERTIFICATE_RECORDED",
                certificate.id,
                f"Recorded {command.direction} certificate "
                f"{certificate.certificate_number} for "
                f"{certificate.counterparty_name} "
                f"({certificate.tax_amount} on base {certificate.taxable_base}).",
            )

            return self._to_dto(certificate)

    def update_certificate(
        self,
        company_id: int,
        command: UpdateWithholdingTaxCertificateCommand,
    ) -> WithholdingTaxCertificateDTO:
        self._permission_service.require_permission(self.PERMISSION_MANAGE)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._certificate_repository_factory(uow.session)
            certificate = repo.get_by_id(company_id, command.certificate_id)
            if certificate is None:
                raise NotFoundError(
                    f"Withholding tax certificate {command.certificate_id} "
                    "was not found.",
                )
            if certificate.status_code == WHT_STATUS_VOIDED:
                raise ValidationError(
                    "Voided certificates cannot be updated.",
                )

            # direction is immutable on update — it determines the
            # status semantics and inbound/outbound aggregation; if the
            # direction was wrong, void and re-record.
            self._validate_payload(
                direction=certificate.direction,
                counterparty_kind=command.counterparty_kind,
                counterparty_name=command.counterparty_name,
                counterparty_niu=command.counterparty_niu,
                certificate_number=command.certificate_number,
                certificate_date=command.certificate_date,
                taxable_base=command.taxable_base,
                tax_amount=command.tax_amount,
                notes=command.notes,
                evidence_attachment_path=command.evidence_attachment_path,
            )

            new_number = command.certificate_number.strip()
            if new_number != certificate.certificate_number:
                if (
                    repo.find_existing_certificate_number(
                        company_id,
                        certificate.direction,
                        new_number,
                        exclude_id=certificate.id,
                    )
                    is not None
                ):
                    raise ConflictError(
                        "A withholding-tax certificate with this number "
                        "already exists for the same direction.",
                    )

            certificate.fiscal_period_id = command.fiscal_period_id
            certificate.counterparty_kind = command.counterparty_kind
            certificate.counterparty_id = command.counterparty_id
            certificate.counterparty_name = command.counterparty_name.strip()
            certificate.counterparty_niu = (
                command.counterparty_niu.strip()
                if command.counterparty_niu is not None
                else None
            )
            certificate.tax_code_id = command.tax_code_id
            certificate.certificate_number = new_number
            certificate.certificate_date = command.certificate_date
            certificate.source_document_type = command.source_document_type
            certificate.source_document_id = command.source_document_id
            certificate.taxable_base = Decimal(command.taxable_base).quantize(
                Decimal("0.01")
            )
            certificate.tax_amount = Decimal(command.tax_amount).quantize(
                Decimal("0.01")
            )
            certificate.evidence_attachment_path = command.evidence_attachment_path
            certificate.notes = (
                command.notes.strip() if command.notes else None
            )

            repo.save(certificate)

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Withholding tax certificate could not be saved due to a "
                    "data conflict.",
                ) from exc

            self._record_audit(
                company_id,
                "WITHHOLDING_TAX_CERTIFICATE_UPDATED",
                certificate.id,
                f"Updated {certificate.direction} certificate "
                f"{certificate.certificate_number}.",
            )

            return self._to_dto(certificate)

    def void_certificate(
        self,
        company_id: int,
        command: VoidWithholdingTaxCertificateCommand,
    ) -> WithholdingTaxCertificateDTO:
        self._permission_service.require_permission(self.PERMISSION_MANAGE)
        reason = (command.reason or "").strip() or None
        if reason is not None and len(reason) > 500:
            raise ValidationError("Void reason is too long (max 500 characters).")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._certificate_repository_factory(uow.session)
            certificate = repo.get_by_id(company_id, command.certificate_id)
            if certificate is None:
                raise NotFoundError(
                    f"Withholding tax certificate {command.certificate_id} "
                    "was not found.",
                )
            if certificate.status_code == WHT_STATUS_VOIDED:
                raise ValidationError(
                    "Certificate has already been voided.",
                )

            certificate.status_code = WHT_STATUS_VOIDED
            if reason is not None:
                existing_notes = certificate.notes or ""
                marker = f"[VOIDED] {reason}"
                certificate.notes = (
                    f"{existing_notes}\n{marker}".strip()
                    if existing_notes
                    else marker
                )
            repo.save(certificate)

            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Withholding tax certificate could not be voided.",
                ) from exc

            self._record_audit(
                company_id,
                "WITHHOLDING_TAX_CERTIFICATE_VOIDED",
                certificate.id,
                f"Voided {certificate.direction} certificate "
                f"{certificate.certificate_number}"
                + (f" — {reason}" if reason else "."),
            )

            return self._to_dto(certificate)

    def link_to_journal_entry(
        self,
        company_id: int,
        command: LinkWithholdingCertificateToJournalEntryCommand,
    ) -> WithholdingTaxCertificateDTO:
        """Attach (or detach) a posted journal entry to a certificate.

        The link is stored in ``source_document_type`` /
        ``source_document_id``. When ``journal_entry_id`` is ``None``
        the existing link is cleared. Validation rules:

        * the certificate must exist for the company and not be voided;
        * the journal entry (when provided) must exist within the same
          company and be POSTED;
        * the journal entry repository factory must be wired (it is
          optional only for legacy test stubs — production wiring
          always provides it).
        """
        self._permission_service.require_permission(self.PERMISSION_MANAGE)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._certificate_repository_factory(uow.session)
            certificate = repo.get_by_id(company_id, command.certificate_id)
            if certificate is None:
                raise NotFoundError(
                    f"Withholding tax certificate {command.certificate_id} "
                    "was not found.",
                )
            if certificate.status_code == WHT_STATUS_VOIDED:
                raise ValidationError(
                    "Voided certificates cannot be linked to a journal entry.",
                )

            if command.journal_entry_id is None:
                # Detach
                certificate.source_document_type = None
                certificate.source_document_id = None
                description_suffix = "Cleared journal-entry link."
            else:
                if self._journal_entry_repository_factory is None:
                    raise ValidationError(
                        "Journal entry linkage is not available "
                        "(repository factory not wired).",
                    )
                je_repo = self._journal_entry_repository_factory(uow.session)
                je = je_repo.get_by_id(company_id, command.journal_entry_id)
                if je is None:
                    raise NotFoundError(
                        f"Journal entry {command.journal_entry_id} was not "
                        "found for the active company.",
                    )
                if je.status_code != "POSTED":
                    raise ValidationError(
                        "Only posted journal entries can be linked to a "
                        "withholding-tax certificate.",
                    )
                certificate.source_document_type = SOURCE_DOC_JOURNAL_ENTRY
                certificate.source_document_id = je.id
                description_suffix = (
                    f"Linked to journal entry {je.entry_number} (id={je.id})."
                )

            repo.save(certificate)
            try:
                uow.commit()
            except IntegrityError as exc:  # pragma: no cover - defensive
                raise ConflictError(
                    "Withholding tax certificate link could not be saved.",
                ) from exc

            self._record_audit(
                company_id,
                "WITHHOLDING_TAX_CERTIFICATE_LINKED",
                certificate.id,
                f"{certificate.direction} certificate "
                f"{certificate.certificate_number}: {description_suffix}",
            )
            return self._to_dto(certificate)

    # ---------------- Helpers ----------------

    def _validate_payload(
        self,
        *,
        direction: str,
        counterparty_kind: str,
        counterparty_name: str,
        counterparty_niu: str | None,
        certificate_number: str,
        certificate_date: date,
        taxable_base: Decimal,
        tax_amount: Decimal,
        notes: str | None,
        evidence_attachment_path: str | None,
    ) -> None:
        if direction not in ALL_WHT_DIRECTION_CODES:
            raise ValidationError(
                f"Direction '{direction}' is not recognized.",
            )
        if counterparty_kind not in ALL_WHT_COUNTERPARTY_KINDS:
            raise ValidationError(
                f"Counterparty kind '{counterparty_kind}' is not recognized.",
            )
        if not counterparty_name or not counterparty_name.strip():
            raise ValidationError("Counterparty name is required.")
        if len(counterparty_name) > 200:
            raise ValidationError("Counterparty name is too long (max 200).")
        if counterparty_niu is not None and len(counterparty_niu) > 50:
            raise ValidationError("Counterparty NIU is too long (max 50).")
        if not certificate_number or not certificate_number.strip():
            raise ValidationError("Certificate number is required.")
        if len(certificate_number) > 80:
            raise ValidationError("Certificate number is too long (max 80).")
        if certificate_date is None:
            raise ValidationError("Certificate date is required.")
        if Decimal(taxable_base) < _ZERO:
            raise ValidationError("Taxable base cannot be negative.")
        if Decimal(tax_amount) < _ZERO:
            raise ValidationError("Tax amount cannot be negative.")
        if Decimal(tax_amount) > Decimal(taxable_base):
            raise ValidationError(
                "Tax amount cannot exceed the taxable base.",
            )
        if notes is not None and len(notes) > 2000:
            raise ValidationError("Notes are too long (max 2000 characters).")
        if (
            evidence_attachment_path is not None
            and len(evidence_attachment_path) > 500
        ):
            raise ValidationError(
                "Evidence attachment path is too long (max 500 characters).",
            )

    def _require_company_exists(self, session: Session, company_id: int) -> None:
        company_repo = self._company_repository_factory(session)
        if company_repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    @staticmethod
    def _to_dto(c: WithholdingTaxCertificate) -> WithholdingTaxCertificateDTO:
        return WithholdingTaxCertificateDTO(
            id=c.id,
            company_id=c.company_id,
            fiscal_period_id=c.fiscal_period_id,
            direction=c.direction,
            counterparty_kind=c.counterparty_kind,
            counterparty_id=c.counterparty_id,
            counterparty_name=c.counterparty_name,
            counterparty_niu=c.counterparty_niu,
            tax_code_id=c.tax_code_id,
            certificate_number=c.certificate_number,
            certificate_date=c.certificate_date,
            source_document_type=c.source_document_type,
            source_document_id=c.source_document_id,
            taxable_base=c.taxable_base,
            tax_amount=c.tax_amount,
            evidence_attachment_path=c.evidence_attachment_path,
            status_code=c.status_code,
            notes=c.notes,
            recorded_by_user_id=c.recorded_by_user_id,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_id: int | None,
        description: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import (
            RecordAuditEventCommand,
        )
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_TAXATION

        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_TAXATION,
                    entity_type="WithholdingTaxCertificate",
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass
