from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.event_type_catalog import (
    JOURNAL_ENTRY_CREATED,
    JOURNAL_ENTRY_DELETED,
    JOURNAL_ENTRY_UPDATED,
    MODULE_JOURNALS,
)
from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.dto.journal_commands import (
    CreateJournalEntryCommand,
    JournalLineCommand,
    UpdateJournalEntryCommand,
)
from seeker_accounting.modules.accounting.journals.dto.journal_dto import (
    JournalEntryDetailDTO,
    JournalEntryListItemDTO,
    JournalLineDTO,
    JournalTotalsDTO,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_line_repository import (
    JournalEntryLineRepository,
)
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.job_costing.services.project_dimension_validation_service import (
    ProjectDimensionValidationService,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

AccountRepositoryFactory = Callable[[Session], AccountRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
JournalEntryLineRepositoryFactory = Callable[[Session], JournalEntryLineRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]


class JournalService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        journal_entry_line_repository_factory: JournalEntryLineRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        project_dimension_validation_service: ProjectDimensionValidationService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._journal_entry_line_repository_factory = journal_entry_line_repository_factory
        self._account_repository_factory = account_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._company_repository_factory = company_repository_factory
        self._project_dimension_validation_service = project_dimension_validation_service
        self._audit_service = audit_service

    def list_journal_entries(
        self,
        company_id: int,
        status_code: str | None = None,
    ) -> list[JournalEntryListItemDTO]:
        normalized_status = status_code.strip().upper() if isinstance(status_code, str) and status_code.strip() else None

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            entry_repository = self._require_journal_entry_repository(uow.session)
            fiscal_period_repository = self._require_fiscal_period_repository(uow.session)
            periods_by_id = {
                period.id: period
                for period in fiscal_period_repository.list_by_company(company_id)
            }
            entries = entry_repository.list_by_company(company_id, normalized_status)
            return [self._to_journal_entry_list_item_dto(entry, periods_by_id) for entry in entries]

    def get_journal_entry(self, company_id: int, journal_entry_id: int) -> JournalEntryDetailDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            entry_repository = self._require_journal_entry_repository(uow.session)
            entry = entry_repository.get_detail(company_id, journal_entry_id)
            if entry is None:
                raise NotFoundError(f"Journal entry with id {journal_entry_id} was not found.")
            return self._to_journal_entry_detail_dto(entry)

    def create_draft_journal(
        self,
        company_id: int,
        command: CreateJournalEntryCommand,
    ) -> JournalEntryDetailDTO:
        normalized_command = self._normalize_create_command(command)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            fiscal_period_repository = self._require_fiscal_period_repository(uow.session)
            entry_repository = self._require_journal_entry_repository(uow.session)
            line_repository = self._require_journal_entry_line_repository(uow.session)

            fiscal_period = self._require_covering_period(
                fiscal_period_repository=fiscal_period_repository,
                company_id=company_id,
                entry_date=normalized_command.entry_date,
            )
            journal_lines = self._build_journal_lines(
                session=uow.session,
                account_repository=account_repository,
                company_id=company_id,
                lines=normalized_command.lines,
            )

            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period.id,
                entry_number=None,
                entry_date=normalized_command.entry_date,
                transaction_date=normalized_command.transaction_date,
                journal_type_code=normalized_command.journal_type_code,
                reference_text=normalized_command.reference_text,
                description=normalized_command.description,
                source_module_code=normalized_command.source_module_code,
                source_document_type=normalized_command.source_document_type,
                source_document_id=normalized_command.source_document_id,
                status_code="DRAFT",
                created_by_user_id=self._app_context.current_user_id,
            )
            entry_repository.add(journal_entry)
            uow.session.flush()
            line_repository.replace_lines(journal_entry.id, journal_lines)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_journal_integrity_error(exc) from exc

            self._record_audit(
                company_id, JOURNAL_ENTRY_CREATED, "JournalEntry",
                journal_entry.id, f"Draft journal entry created (id={journal_entry.id}).",
            )
            entry = entry_repository.get_detail(company_id, journal_entry.id)
            if entry is None:
                raise RuntimeError("Journal entry could not be reloaded after creation.")
            return self._to_journal_entry_detail_dto(entry)

    def update_draft_journal(
        self,
        company_id: int,
        journal_entry_id: int,
        command: UpdateJournalEntryCommand,
    ) -> JournalEntryDetailDTO:
        normalized_command = self._normalize_update_command(command)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            account_repository = self._require_account_repository(uow.session)
            fiscal_period_repository = self._require_fiscal_period_repository(uow.session)
            entry_repository = self._require_journal_entry_repository(uow.session)
            line_repository = self._require_journal_entry_line_repository(uow.session)

            journal_entry = entry_repository.get_by_id(company_id, journal_entry_id)
            if journal_entry is None:
                raise NotFoundError(f"Journal entry with id {journal_entry_id} was not found.")
            if journal_entry.status_code != "DRAFT":
                raise ValidationError("Posted journals cannot be edited through the draft workflow.")

            fiscal_period = self._require_covering_period(
                fiscal_period_repository=fiscal_period_repository,
                company_id=company_id,
                entry_date=normalized_command.entry_date,
            )
            journal_lines = self._build_journal_lines(
                session=uow.session,
                account_repository=account_repository,
                company_id=company_id,
                lines=normalized_command.lines,
                journal_entry_id=journal_entry_id,
            )

            journal_entry.fiscal_period_id = fiscal_period.id
            journal_entry.entry_date = normalized_command.entry_date
            journal_entry.transaction_date = normalized_command.transaction_date
            journal_entry.journal_type_code = normalized_command.journal_type_code
            journal_entry.reference_text = normalized_command.reference_text
            journal_entry.description = normalized_command.description
            journal_entry.source_module_code = normalized_command.source_module_code
            journal_entry.source_document_type = normalized_command.source_document_type
            journal_entry.source_document_id = normalized_command.source_document_id
            entry_repository.save(journal_entry)
            line_repository.replace_lines(journal_entry.id, journal_lines)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_journal_integrity_error(exc) from exc

            self._record_audit(
                company_id, JOURNAL_ENTRY_UPDATED, "JournalEntry",
                journal_entry.id, f"Draft journal entry {journal_entry.id} updated.",
            )
            entry = entry_repository.get_detail(company_id, journal_entry.id)
            if entry is None:
                raise RuntimeError("Journal entry could not be reloaded after update.")
            return self._to_journal_entry_detail_dto(entry)

    def delete_draft_journal(self, company_id: int, journal_entry_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            entry_repository = self._require_journal_entry_repository(uow.session)
            line_repository = self._require_journal_entry_line_repository(uow.session)

            journal_entry = entry_repository.get_by_id(company_id, journal_entry_id)
            if journal_entry is None:
                raise NotFoundError(f"Journal entry with id {journal_entry_id} was not found.")
            if journal_entry.status_code != "DRAFT":
                raise ValidationError("Posted journals cannot be deleted through the draft workflow.")

            line_repository.replace_lines(journal_entry.id, [])
            entry_repository.delete(journal_entry)
            uow.commit()

            self._record_audit(
                company_id, JOURNAL_ENTRY_DELETED, "JournalEntry",
                journal_entry_id, f"Draft journal entry {journal_entry_id} deleted.",
            )

    def _normalize_create_command(self, command: CreateJournalEntryCommand) -> CreateJournalEntryCommand:
        return CreateJournalEntryCommand(
            entry_date=command.entry_date if command.entry_date is not None else date.today(),
            transaction_date=command.transaction_date,
            journal_type_code=self._require_code(command.journal_type_code, "Journal type"),
            reference_text=self._normalize_optional_text(command.reference_text),
            description=self._normalize_optional_text(command.description),
            source_module_code=self._normalize_optional_code(command.source_module_code),
            source_document_type=self._normalize_optional_code(command.source_document_type),
            source_document_id=command.source_document_id,
            lines=self._normalize_line_commands(command.lines),
        )

    def _normalize_update_command(self, command: UpdateJournalEntryCommand) -> UpdateJournalEntryCommand:
        return UpdateJournalEntryCommand(
            entry_date=command.entry_date if command.entry_date is not None else date.today(),
            transaction_date=command.transaction_date,
            journal_type_code=self._require_code(command.journal_type_code, "Journal type"),
            reference_text=self._normalize_optional_text(command.reference_text),
            description=self._normalize_optional_text(command.description),
            source_module_code=self._normalize_optional_code(command.source_module_code),
            source_document_type=self._normalize_optional_code(command.source_document_type),
            source_document_id=command.source_document_id,
            lines=self._normalize_line_commands(command.lines),
        )

    def _normalize_line_commands(
        self,
        lines: tuple[JournalLineCommand, ...],
    ) -> tuple[JournalLineCommand, ...]:
        if len(lines) < 2:
            raise ValidationError("A journal entry must include at least two lines.")

        normalized_lines: list[JournalLineCommand] = []
        for line in lines:
            account_id = line.account_id if line.account_id > 0 else 0
            if account_id <= 0:
                raise ValidationError("Each journal line must reference an account.")

            debit_amount = self._normalize_amount(line.debit_amount)
            credit_amount = self._normalize_amount(line.credit_amount)

            if debit_amount > Decimal("0.00") and credit_amount > Decimal("0.00"):
                raise ValidationError("Journal lines cannot contain both debit and credit amounts.")
            if debit_amount == Decimal("0.00") and credit_amount == Decimal("0.00"):
                raise ValidationError("Each journal line must contain either a debit or a credit amount.")

            normalized_lines.append(
                JournalLineCommand(
                    account_id=account_id,
                    line_description=self._normalize_optional_text(line.line_description),
                    debit_amount=debit_amount,
                    credit_amount=credit_amount,
                    contract_id=self._normalize_optional_id(line.contract_id),
                    project_id=self._normalize_optional_id(line.project_id),
                    project_job_id=self._normalize_optional_id(line.project_job_id),
                    project_cost_code_id=self._normalize_optional_id(line.project_cost_code_id),
                )
            )
        return tuple(normalized_lines)

    def _build_journal_lines(
        self,
        *,
        session: Session,
        account_repository: AccountRepository,
        company_id: int,
        lines: tuple[JournalLineCommand, ...],
        journal_entry_id: int | None = None,
    ) -> list[JournalEntryLine]:
        built_lines: list[JournalEntryLine] = []
        for index, line in enumerate(lines, start=1):
            account = self._require_manual_posting_account(account_repository, company_id, line.account_id)
            self._project_dimension_validation_service.validate_line_dimensions(
                session=session,
                company_id=company_id,
                contract_id=line.contract_id,
                project_id=line.project_id,
                project_job_id=line.project_job_id,
                project_cost_code_id=line.project_cost_code_id,
                line_number=index,
            )
            built_lines.append(
                JournalEntryLine(
                    journal_entry_id=journal_entry_id or 0,
                    line_number=index,
                    account_id=account.id,
                    line_description=line.line_description,
                    debit_amount=line.debit_amount or Decimal("0.00"),
                    credit_amount=line.credit_amount or Decimal("0.00"),
                    contract_id=line.contract_id,
                    project_id=line.project_id,
                    project_job_id=line.project_job_id,
                    project_cost_code_id=line.project_cost_code_id,
                )
            )
        return built_lines

    def _require_manual_posting_account(
        self,
        account_repository: AccountRepository,
        company_id: int,
        account_id: int,
    ) -> Account:
        account = account_repository.get_by_id(company_id, account_id)
        if account is None:
            raise ValidationError("All journal lines must reference accounts in the active company.")
        if not account.is_active:
            raise ValidationError("Journal lines cannot reference inactive accounts.")
        if not account.allow_manual_posting:
            raise ValidationError("Journal lines cannot reference control-only accounts.")
        return account

    def _require_covering_period(
        self,
        *,
        fiscal_period_repository: FiscalPeriodRepository,
        company_id: int,
        entry_date: date,
    ):
        fiscal_period = fiscal_period_repository.get_covering_date(company_id, entry_date)
        if fiscal_period is None:
            raise ValidationError(
                "Entry date must fall within an existing fiscal period.",
                app_error_code=AppErrorCode.MISSING_FISCAL_PERIOD,
                context={
                    "company_id": company_id,
                    "entry_date": entry_date,
                    "origin_workflow": "journal_entry",
                },
            )
        if fiscal_period.status_code == "LOCKED":
            raise PeriodLockedError(
                f"Entry date falls in locked fiscal period {fiscal_period.period_code}.",
                app_error_code=AppErrorCode.LOCKED_FISCAL_PERIOD,
                context={
                    "company_id": company_id,
                    "entry_date": entry_date,
                    "fiscal_period_id": fiscal_period.id,
                    "fiscal_period_code": fiscal_period.period_code,
                    "origin_workflow": "journal_entry",
                },
            )
        return fiscal_period

    def _normalize_amount(self, value: Decimal | None) -> Decimal:
        if value is None:
            return Decimal("0.00")
        if value < Decimal("0.00"):
            raise ValidationError("Journal line amounts cannot be negative.")
        return value.quantize(Decimal("0.01"))

    def _normalize_optional_id(self, value: int | None) -> int | None:
        if value is None:
            return None
        if value <= 0:
            raise ValidationError("Dimension identifiers must be greater than zero.")
        return value

    def _require_date(self, value: date | None, label: str) -> date:
        if value is None:
            raise ValidationError(f"{label} is required.")
        return value

    def _require_text(self, value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValidationError(f"{label} is required.")
        return normalized

    def _require_code(self, value: str, label: str) -> str:
        return self._require_text(value, label).upper().replace(" ", "_")

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def _normalize_optional_code(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper().replace(" ", "_")
        return normalized or None

    def _translate_journal_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "entry_number" in message:
            return ConflictError("Journal entry numbering conflicts with an existing posted journal.")
        return ValidationError("Journal data could not be saved.")

    def _require_journal_entry_repository(self, session: Session | None) -> JournalEntryRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._journal_entry_repository_factory(session)

    def _require_journal_entry_line_repository(self, session: Session | None) -> JournalEntryLineRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._journal_entry_line_repository_factory(session)

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

    def _calculate_totals(self, entry: JournalEntry) -> JournalTotalsDTO:
        total_debit = sum((line.debit_amount for line in entry.lines), Decimal("0.00"))
        total_credit = sum((line.credit_amount for line in entry.lines), Decimal("0.00"))
        imbalance = total_debit - total_credit
        return JournalTotalsDTO(
            total_debit=total_debit,
            total_credit=total_credit,
            imbalance_amount=imbalance,
            is_balanced=imbalance == Decimal("0.00"),
        )

    def _to_journal_entry_list_item_dto(
        self,
        entry: JournalEntry,
        periods_by_id: dict[int, object],
    ) -> JournalEntryListItemDTO:
        totals = self._calculate_totals(entry)
        fiscal_period = periods_by_id.get(entry.fiscal_period_id)
        fiscal_period_code = getattr(fiscal_period, "period_code", "")
        return JournalEntryListItemDTO(
            id=entry.id,
            company_id=entry.company_id,
            fiscal_period_id=entry.fiscal_period_id,
            fiscal_period_code=fiscal_period_code,
            entry_number=entry.entry_number,
            entry_date=entry.entry_date,
            transaction_date=entry.transaction_date,
            journal_type_code=entry.journal_type_code,
            reference_text=entry.reference_text,
            description=entry.description,
            status_code=entry.status_code,
            total_debit=totals.total_debit,
            total_credit=totals.total_credit,
            is_balanced=totals.is_balanced,
            posted_at=entry.posted_at,
            updated_at=entry.updated_at,
        )

    def _to_journal_entry_detail_dto(self, entry: JournalEntry) -> JournalEntryDetailDTO:
        lines = tuple(
            JournalLineDTO(
                id=line.id,
                line_number=line.line_number,
                account_id=line.account_id,
                account_code=line.account.account_code,
                account_name=line.account.account_name,
                line_description=line.line_description,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
                contract_id=line.contract_id,
                project_id=line.project_id,
                project_job_id=line.project_job_id,
                project_cost_code_id=line.project_cost_code_id,
                created_at=line.created_at,
                updated_at=line.updated_at,
            )
            for line in sorted(entry.lines, key=lambda row: (row.line_number, row.id))
        )
        totals = self._calculate_totals(entry)
        fiscal_period_code = entry.fiscal_period.period_code if entry.fiscal_period is not None else ""
        return JournalEntryDetailDTO(
            id=entry.id,
            company_id=entry.company_id,
            fiscal_period_id=entry.fiscal_period_id,
            fiscal_period_code=fiscal_period_code,
            entry_number=entry.entry_number,
            entry_date=entry.entry_date,
            transaction_date=entry.transaction_date,
            journal_type_code=entry.journal_type_code,
            reference_text=entry.reference_text,
            description=entry.description,
            source_module_code=entry.source_module_code,
            source_document_type=entry.source_document_type,
            source_document_id=entry.source_document_id,
            status_code=entry.status_code,
            posted_at=entry.posted_at,
            posted_by_user_id=entry.posted_by_user_id,
            created_by_user_id=entry.created_by_user_id,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            totals=totals,
            lines=lines,
        )

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
        except Exception:  # noqa: BLE001 — audit must never break core journal flow
            pass
