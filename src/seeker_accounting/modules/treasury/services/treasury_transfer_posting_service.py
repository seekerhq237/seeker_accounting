from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.treasury.dto.treasury_transfer_dto import TreasuryTransferPostingResultDTO
from seeker_accounting.modules.treasury.repositories.financial_account_repository import FinancialAccountRepository
from seeker_accounting.modules.treasury.repositories.treasury_transfer_repository import TreasuryTransferRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
TreasuryTransferRepositoryFactory = Callable[[Session], TreasuryTransferRepository]
FinancialAccountRepositoryFactory = Callable[[Session], FinancialAccountRepository]


class TreasuryTransferPostingService:
    DOCUMENT_TYPE_CODE = "TREASURY_TRANSFER"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        treasury_transfer_repository_factory: TreasuryTransferRepositoryFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        financial_account_repository_factory: FinancialAccountRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        numbering_service: NumberingService,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._treasury_transfer_repository_factory = treasury_transfer_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._financial_account_repository_factory = financial_account_repository_factory
        self._company_repository_factory = company_repository_factory
        self._numbering_service = numbering_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def post_transfer(
        self,
        company_id: int,
        transfer_id: int,
        actor_user_id: int | None = None,
    ) -> TreasuryTransferPostingResultDTO:
        self._permission_service.require_permission("treasury.transfers.post")
        with self._unit_of_work_factory() as uow:
            actor_id = actor_user_id if actor_user_id is not None else self._app_context.current_user_id
            self._require_company_exists(uow.session, company_id)

            transfer_repo = self._treasury_transfer_repository_factory(uow.session)
            journal_repo = self._journal_entry_repository_factory(uow.session)
            fp_repo = self._fiscal_period_repository_factory(uow.session)
            fa_repo = self._financial_account_repository_factory(uow.session)

            transfer = transfer_repo.get_detail(company_id, transfer_id)
            if transfer is None:
                raise NotFoundError(f"Treasury transfer with id {transfer_id} was not found.")
            if transfer.status_code != "draft":
                raise ValidationError("Only draft transfers can be posted.")

            # --- Period validation ---
            fiscal_period = fp_repo.get_covering_date(company_id, transfer.transfer_date)
            if fiscal_period is None:
                raise ValidationError("Transfer date must fall within an existing fiscal period.")
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError("Transfer cannot be posted into a locked fiscal period.")
            if fiscal_period.status_code != "OPEN":
                raise ValidationError("Transfer can only be posted into an open fiscal period.")

            # --- Validate both financial accounts ---
            from_fa = fa_repo.get_by_id(company_id, transfer.from_financial_account_id)
            if from_fa is None or not from_fa.is_active:
                raise ValidationError("Source financial account must be active to post a transfer.")
            to_fa = fa_repo.get_by_id(company_id, transfer.to_financial_account_id)
            if to_fa is None or not to_fa.is_active:
                raise ValidationError("Destination financial account must be active to post a transfer.")

            # --- Build journal lines ---
            # Debit destination GL, credit source GL
            journal_lines = [
                JournalEntryLine(
                    journal_entry_id=0,
                    line_number=1,
                    account_id=to_fa.gl_account_id,
                    line_description=f"Transfer in from {from_fa.name}",
                    debit_amount=transfer.amount,
                    credit_amount=Decimal("0.00"),
                ),
                JournalEntryLine(
                    journal_entry_id=0,
                    line_number=2,
                    account_id=from_fa.gl_account_id,
                    line_description=f"Transfer out to {to_fa.name}",
                    debit_amount=Decimal("0.00"),
                    credit_amount=transfer.amount,
                ),
            ]

            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period.id,
                entry_number=None,
                entry_date=transfer.transfer_date,
                journal_type_code="TRANSFER",
                reference_text=transfer.transfer_number,
                description=f"Treasury transfer {transfer.transfer_number}",
                source_module_code="treasury",
                source_document_type="treasury_transfer",
                source_document_id=transfer.id,
                status_code="POSTED",
                posted_at=datetime.utcnow(),
                posted_by_user_id=actor_id,
                created_by_user_id=actor_id,
            )
            journal_repo.add(journal_entry)
            uow.session.flush()

            journal_entry.entry_number = self._numbering_service.issue_next_number(
                uow.session,
                company_id=company_id,
                document_type_code="JOURNAL_ENTRY",
            )
            journal_repo.save(journal_entry)

            for jl in journal_lines:
                jl.journal_entry_id = journal_entry.id
            uow.session.add_all(journal_lines)

            # --- Assign transfer number and update status ---
            transfer.transfer_number = self._numbering_service.issue_next_number(
                uow.session,
                company_id=company_id,
                document_type_code=self.DOCUMENT_TYPE_CODE,
            )
            transfer.status_code = "posted"
            transfer.posted_journal_entry_id = journal_entry.id
            transfer.posted_at = datetime.utcnow()
            transfer.posted_by_user_id = actor_id
            transfer_repo.save(transfer)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_posting_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import TREASURY_TRANSFER_POSTED
            self._record_audit(company_id, TREASURY_TRANSFER_POSTED, "TreasuryTransfer", transfer.id, "Posted treasury transfer")
            return TreasuryTransferPostingResultDTO(
                company_id=company_id,
                transfer_id=transfer.id,
                transfer_number=transfer.transfer_number,
                journal_entry_id=journal_entry.id,
                journal_entry_number=journal_entry.entry_number or "",
                posted_at=transfer.posted_at or datetime.utcnow(),
                posted_by_user_id=transfer.posted_by_user_id,
            )

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _translate_posting_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "transfer_number" in message:
            return ConflictError("A treasury transfer with this number already exists.")
        if "unique" in message and "entry_number" in message:
            return ConflictError("Journal entry numbering conflicts with an existing posted entry.")
        return ValidationError("Treasury transfer could not be posted.")

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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_TREASURY
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_TREASURY,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
