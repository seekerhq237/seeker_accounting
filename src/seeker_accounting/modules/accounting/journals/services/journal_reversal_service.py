"""JournalReversalService — creates a reversing journal entry from a posted source.

The reversal is a new journal entry with:
  - same lines as the source, but debit and credit amounts swapped
  - entry_date = command.reversal_date (must be in an OPEN fiscal period)
  - source_module_code/source_document_type/source_document_id linking back
    to the source journal entry id, so the lineage is queryable
  - reference_text including the source entry_number
  - by default auto_post=True → status_code POSTED at creation
  - if auto_post=False → status_code DRAFT (caller can post later)

The source entry must:
  - be POSTED
  - belong to the same company
  - not already be a JOURNAL_REVERSAL itself (cannot reverse a reversal)
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.dto.journal_reversal_dto import (
    JournalReversalResultDTO,
    ReverseJournalCommand,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import (
    JournalEntryLine,
)
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.audit.event_type_catalog import JOURNAL_ENTRY_REVERSED
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PeriodLockedError,
    ValidationError,
)
from seeker_accounting.platform.numbering.numbering_service import NumberingService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class JournalReversalService:
    SOURCE_MODULE_CODE = "ACCOUNTING"
    SOURCE_DOCUMENT_TYPE = "JOURNAL_REVERSAL"
    JOURNAL_TYPE_CODE = "JOURNAL_REVERSAL"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        numbering_service: NumberingService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._company_repository_factory = company_repository_factory
        self._numbering_service = numbering_service
        self._audit_service = audit_service

    def reverse_journal(
        self,
        company_id: int,
        source_journal_entry_id: int,
        command: ReverseJournalCommand,
        actor_user_id: int | None = None,
    ) -> JournalReversalResultDTO:
        if not command.reason or not command.reason.strip():
            raise ValidationError("Reversal reason is required.")

        with self._unit_of_work_factory() as uow:
            actor_id = (
                actor_user_id
                if actor_user_id is not None
                else self._app_context.current_user_id
            )
            self._require_company(uow.session, company_id)

            je_repo = self._journal_entry_repository_factory(uow.session)
            source = je_repo.get_detail(company_id, source_journal_entry_id)
            if source is None:
                raise NotFoundError(
                    f"Journal entry {source_journal_entry_id} not found."
                )
            if source.status_code != "POSTED":
                raise ValidationError(
                    "Only POSTED journal entries can be reversed."
                )
            if source.source_document_type == self.SOURCE_DOCUMENT_TYPE:
                raise ConflictError("Cannot reverse a reversal entry.")
            if source.journal_type_code == self.JOURNAL_TYPE_CODE:
                raise ConflictError("Cannot reverse a reversal entry.")
            if not source.lines:
                raise ValidationError("Source journal entry has no lines.")

            fp_repo = self._fiscal_period_repository_factory(uow.session)
            period = fp_repo.get_covering_date(company_id, command.reversal_date)
            if period is None:
                raise ValidationError(
                    "Reversal date must fall within an existing fiscal period."
                )
            if period.status_code == "LOCKED":
                raise PeriodLockedError("Cannot post into a locked fiscal period.")
            if command.auto_post and period.status_code != "OPEN":
                raise ValidationError("Can only post into an open fiscal period.")

            entry_number = self._numbering_service.issue_next_number(
                uow.session,
                company_id=company_id,
                document_type_code="JOURNAL_ENTRY",
            )
            now = datetime.utcnow()
            description = f"Reversal of {source.entry_number or source.id}: {command.reason}"
            reference = f"REV/{source.entry_number or source.id}"

            reversal = JournalEntry(
                company_id=company_id,
                fiscal_period_id=period.id,
                entry_date=command.reversal_date,
                journal_type_code=self.JOURNAL_TYPE_CODE,
                description=description[:255],
                source_module_code=self.SOURCE_MODULE_CODE,
                source_document_type=self.SOURCE_DOCUMENT_TYPE,
                source_document_id=source.id,
                status_code="POSTED" if command.auto_post else "DRAFT",
                posted_at=now if command.auto_post else None,
                posted_by_user_id=actor_id if command.auto_post else None,
                created_by_user_id=actor_id,
                entry_number=entry_number,
                reference_text=reference[:120],
            )
            uow.session.add(reversal)
            uow.session.flush()

            reversal_lines: list[JournalEntryLine] = []
            for src_line in sorted(source.lines, key=lambda ln: ln.line_number):
                rev_line = JournalEntryLine(
                    journal_entry_id=reversal.id,
                    line_number=src_line.line_number,
                    account_id=src_line.account_id,
                    debit_amount=Decimal(src_line.credit_amount),
                    credit_amount=Decimal(src_line.debit_amount),
                    line_description=(src_line.line_description or "Reversal"),
                    contract_id=src_line.contract_id,
                    project_id=src_line.project_id,
                    project_job_id=src_line.project_job_id,
                    project_cost_code_id=src_line.project_cost_code_id,
                )
                uow.session.add(rev_line)
                reversal_lines.append(rev_line)
            uow.session.flush()

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError(
                    "Journal reversal failed due to a data conflict."
                ) from exc

            self._record_audit(
                company_id,
                reversal.id,
                f"Reversal of journal {source.entry_number or source.id} posted "
                f"({len(reversal_lines)} lines). Reason: {command.reason}",
            )

            return JournalReversalResultDTO(
                source_journal_entry_id=source.id,
                source_entry_number=source.entry_number or str(source.id),
                reversal_journal_entry_id=reversal.id,
                reversal_entry_number=entry_number,
                reversal_date=command.reversal_date,
                line_count=len(reversal_lines),
                auto_posted=bool(command.auto_post),
                posted_at=now if command.auto_post else None,
            )

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

    def _record_audit(
        self,
        company_id: int,
        journal_entry_id: int,
        detail: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import (
            RecordAuditEventCommand,
        )
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_JOURNALS

        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=JOURNAL_ENTRY_REVERSED,
                    module_code=MODULE_JOURNALS,
                    entity_type="JournalEntry",
                    entity_id=journal_entry_id,
                    description=detail,
                ),
            )
        except Exception:
            pass
