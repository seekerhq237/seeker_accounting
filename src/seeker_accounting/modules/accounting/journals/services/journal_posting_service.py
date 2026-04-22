from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.event_type_catalog import JOURNAL_ENTRY_POSTED, MODULE_JOURNALS
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.dto.journal_dto import JournalPostResultDTO
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PeriodLockedError,
    ValidationError,
)
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.numbering.numbering_service import NumberingService
from seeker_accounting.modules.administration.services.permission_service import PermissionService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

AccountRepositoryFactory = Callable[[Session], AccountRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class JournalPostingService:
    DOCUMENT_TYPE_CODE = "journal_entry"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        numbering_service: NumberingService,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._account_repository_factory = account_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._company_repository_factory = company_repository_factory
        self._numbering_service = numbering_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def post_journal(
        self,
        company_id: int,
        journal_entry_id: int,
        actor_user_id: int | None = None,
    ) -> JournalPostResultDTO:
        self._permission_service.require_permission("journals.post")
        with self._unit_of_work_factory() as uow:
            actor_id = actor_user_id if actor_user_id is not None else self._app_context.current_user_id
            self._require_company_exists(uow.session, company_id)
            entry_repository = self._require_journal_entry_repository(uow.session)
            account_repository = self._require_account_repository(uow.session)
            fiscal_period_repository = self._require_fiscal_period_repository(uow.session)

            entry = entry_repository.get_detail(company_id, journal_entry_id)
            if entry is None:
                raise NotFoundError(f"Journal entry with id {journal_entry_id} was not found.")
            if entry.status_code != "DRAFT":
                raise ValidationError("Only draft journal entries can be posted.")
            if len(entry.lines) < 2:
                raise ValidationError("Posted journal entries must contain at least two lines.")

            total_debit = Decimal("0.00")
            total_credit = Decimal("0.00")
            for line in entry.lines:
                if line.account.company_id != company_id:
                    raise ValidationError("All journal lines must reference accounts in the active company.")
                if not line.account.is_active:
                    raise ValidationError("Posted journal entries cannot reference inactive accounts.")
                if not line.account.allow_manual_posting:
                    raise ValidationError("Posted journal entries cannot reference control-only accounts.")
                if line.debit_amount > Decimal("0.00") and line.credit_amount > Decimal("0.00"):
                    raise ValidationError("Journal lines cannot contain both debit and credit amounts.")
                if line.debit_amount == Decimal("0.00") and line.credit_amount == Decimal("0.00"):
                    raise ValidationError("Journal lines must contain either a debit or a credit amount.")
                total_debit += line.debit_amount
                total_credit += line.credit_amount

            if total_debit != total_credit:
                raise ValidationError("Journal entry cannot be posted until total debits equal total credits.")

            fiscal_period = fiscal_period_repository.get_covering_date(company_id, entry.entry_date)
            if fiscal_period is None:
                raise ValidationError("Journal entry date must fall within an existing fiscal period.")
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError(
                    f"Journal entry cannot be posted into locked fiscal period {fiscal_period.period_code}.",
                    app_error_code=AppErrorCode.LOCKED_FISCAL_PERIOD,
                    context={
                        "company_id": company_id,
                        "entry_date": entry.entry_date,
                        "fiscal_period_id": fiscal_period.id,
                        "fiscal_period_code": fiscal_period.period_code,
                        "origin_workflow": "journal_entry",
                    },
                )
            if fiscal_period.status_code != "OPEN":
                raise ValidationError("Journal entry can only be posted into an open fiscal period.")

            if entry.entry_number is None:
                entry.entry_number = self._numbering_service.issue_next_number(
                    uow.session,
                    company_id=company_id,
                    document_type_code=self.DOCUMENT_TYPE_CODE,
                )
            else:
                existing_entry = entry_repository.get_by_entry_number(company_id, entry.entry_number)
                if existing_entry is not None and existing_entry.id != entry.id:
                    raise ConflictError("Journal entry numbering conflicts with an existing posted journal.")

            entry.fiscal_period_id = fiscal_period.id
            entry.status_code = "POSTED"
            entry.posted_at = datetime.utcnow()
            entry.posted_by_user_id = actor_id
            entry_repository.save(entry)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_posting_integrity_error(exc) from exc

            self._record_audit(
                company_id, JOURNAL_ENTRY_POSTED, "JournalEntry",
                entry.id,
                f"Journal entry {entry.entry_number or entry.id} posted (period={fiscal_period.period_code}).",
            )
            return JournalPostResultDTO(
                journal_entry_id=entry.id,
                company_id=entry.company_id,
                fiscal_period_id=entry.fiscal_period_id,
                fiscal_period_code=fiscal_period.period_code,
                entry_number=entry.entry_number or "",
                entry_date=entry.entry_date,
                transaction_date=entry.transaction_date,
                status_code=entry.status_code,
                posted_at=entry.posted_at or datetime.utcnow(),
                posted_by_user_id=entry.posted_by_user_id,
            )

    def _require_journal_entry_repository(self, session: Session | None) -> JournalEntryRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._journal_entry_repository_factory(session)

    def _require_account_repository(self, session: Session | None) -> AccountRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_repository_factory(session)

    def _require_fiscal_period_repository(self, session: Session | None) -> FiscalPeriodRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._fiscal_period_repository_factory(session)

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        company_repository = self._company_repository_factory(session)
        if company_repository.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _translate_posting_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "entry_number" in message:
            return ConflictError("A journal entry with this entry number already exists.")
        return ValidationError("Journal entry could not be posted.")

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_type: str,
        entity_id: int | None,
        description: str,
        detail_json: str | None = None,
    ) -> None:
        if self._audit_service is None:
            return
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_JOURNALS,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                    detail_json=detail_json,
                ),
            )
        except Exception:  # noqa: BLE001 — audit must never break core posting flow
            pass
