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
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.treasury.dto.treasury_transaction_dto import TreasuryTransactionPostingResultDTO
from seeker_accounting.modules.treasury.repositories.financial_account_repository import FinancialAccountRepository
from seeker_accounting.modules.treasury.repositories.treasury_transaction_repository import (
    TreasuryTransactionRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService
from seeker_accounting.modules.administration.services.permission_service import PermissionService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
TreasuryTransactionRepositoryFactory = Callable[[Session], TreasuryTransactionRepository]
FinancialAccountRepositoryFactory = Callable[[Session], FinancialAccountRepository]

_RECEIPT_TYPES = {"cash_receipt", "bank_receipt"}
_PAYMENT_TYPES = {"cash_payment", "bank_payment"}


class TreasuryTransactionPostingService:
    DOCUMENT_TYPE_CODE = "TREASURY_TRANSACTION"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        treasury_transaction_repository_factory: TreasuryTransactionRepositoryFactory,
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
        self._treasury_transaction_repository_factory = treasury_transaction_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._financial_account_repository_factory = financial_account_repository_factory
        self._company_repository_factory = company_repository_factory
        self._numbering_service = numbering_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def post_transaction(
        self,
        company_id: int,
        transaction_id: int,
        actor_user_id: int | None = None,
    ) -> TreasuryTransactionPostingResultDTO:
        self._permission_service.require_permission("treasury.transactions.post")
        with self._unit_of_work_factory() as uow:
            actor_id = actor_user_id if actor_user_id is not None else self._app_context.current_user_id
            self._require_company_exists(uow.session, company_id)

            txn_repo = self._treasury_transaction_repository_factory(uow.session)
            journal_repo = self._journal_entry_repository_factory(uow.session)
            fp_repo = self._fiscal_period_repository_factory(uow.session)
            fa_repo = self._financial_account_repository_factory(uow.session)

            txn = txn_repo.get_detail(company_id, transaction_id)
            if txn is None:
                raise NotFoundError(f"Treasury transaction with id {transaction_id} was not found.")
            if txn.status_code != "draft":
                raise ValidationError("Only draft transactions can be posted.")
            if not txn.lines:
                raise ValidationError("Transaction must have at least one line to be posted.")

            # --- Period validation ---
            fiscal_period = fp_repo.get_covering_date(company_id, txn.transaction_date)
            if fiscal_period is None:
                raise ValidationError("Transaction date must fall within an existing fiscal period.")
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError("Transaction cannot be posted into a locked fiscal period.")
            if fiscal_period.status_code != "OPEN":
                raise ValidationError("Transaction can only be posted into an open fiscal period.")

            # --- Financial account GL ---
            fa = fa_repo.get_by_id(company_id, txn.financial_account_id)
            if fa is None or not fa.is_active:
                raise ValidationError("Financial account must be active to post a transaction.")
            gl_account_id = fa.gl_account_id

            # --- Build journal lines ---
            journal_lines: list[JournalEntryLine] = []
            line_number = 1
            is_receipt = txn.transaction_type_code in _RECEIPT_TYPES

            for txn_line in txn.lines:
                if is_receipt:
                    journal_lines.append(
                        JournalEntryLine(
                            journal_entry_id=0,
                            line_number=line_number,
                            account_id=gl_account_id,
                            line_description=f"Treasury receipt {txn.transaction_number}",
                            debit_amount=txn_line.amount,
                            credit_amount=Decimal("0.00"),
                            contract_id=txn_line.contract_id,
                            project_id=txn_line.project_id,
                            project_job_id=txn_line.project_job_id,
                            project_cost_code_id=txn_line.project_cost_code_id,
                        )
                    )
                    line_number += 1
                    journal_lines.append(
                        JournalEntryLine(
                            journal_entry_id=0,
                            line_number=line_number,
                            account_id=txn_line.account_id,
                            line_description=txn_line.line_description or f"Receipt line {txn_line.line_number}",
                            debit_amount=Decimal("0.00"),
                            credit_amount=txn_line.amount,
                            contract_id=txn_line.contract_id,
                            project_id=txn_line.project_id,
                            project_job_id=txn_line.project_job_id,
                            project_cost_code_id=txn_line.project_cost_code_id,
                        )
                    )
                else:
                    journal_lines.append(
                        JournalEntryLine(
                            journal_entry_id=0,
                            line_number=line_number,
                            account_id=txn_line.account_id,
                            line_description=txn_line.line_description or f"Payment line {txn_line.line_number}",
                            debit_amount=txn_line.amount,
                            credit_amount=Decimal("0.00"),
                            contract_id=txn_line.contract_id,
                            project_id=txn_line.project_id,
                            project_job_id=txn_line.project_job_id,
                            project_cost_code_id=txn_line.project_cost_code_id,
                        )
                    )
                    line_number += 1
                    journal_lines.append(
                        JournalEntryLine(
                            journal_entry_id=0,
                            line_number=line_number,
                            account_id=gl_account_id,
                            line_description=f"Treasury payment {txn.transaction_number}",
                            debit_amount=Decimal("0.00"),
                            credit_amount=txn_line.amount,
                            contract_id=txn_line.contract_id,
                            project_id=txn_line.project_id,
                            project_job_id=txn_line.project_job_id,
                            project_cost_code_id=txn_line.project_cost_code_id,
                        )
                    )
                line_number += 1

            # --- Create journal entry ---
            journal_type = "RECEIPT" if is_receipt else "PAYMENT"
            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period.id,
                entry_number=None,
                entry_date=txn.transaction_date,
                journal_type_code=journal_type,
                reference_text=txn.transaction_number,
                description=f"Treasury {txn.transaction_type_code} {txn.transaction_number}",
                source_module_code="treasury",
                source_document_type="treasury_transaction",
                source_document_id=txn.id,
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

            # --- Assign transaction number and update status ---
            txn.transaction_number = self._numbering_service.issue_next_number(
                uow.session,
                company_id=company_id,
                document_type_code=self.DOCUMENT_TYPE_CODE,
            )
            txn.status_code = "posted"
            txn.posted_journal_entry_id = journal_entry.id
            txn.posted_at = datetime.utcnow()
            txn.posted_by_user_id = actor_id
            txn_repo.save(txn)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_posting_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import TREASURY_TRANSACTION_POSTED
            self._record_audit(company_id, TREASURY_TRANSACTION_POSTED, "TreasuryTransaction", txn.id, "Posted treasury transaction")
            return TreasuryTransactionPostingResultDTO(
                company_id=company_id,
                transaction_id=txn.id,
                transaction_number=txn.transaction_number,
                journal_entry_id=journal_entry.id,
                journal_entry_number=journal_entry.entry_number or "",
                posted_at=txn.posted_at or datetime.utcnow(),
                posted_by_user_id=txn.posted_by_user_id,
            )

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _translate_posting_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "transaction_number" in message:
            return ConflictError("A treasury transaction with this number already exists.")
        if "unique" in message and "entry_number" in message:
            return ConflictError("Journal entry numbering conflicts with an existing posted entry.")
        return ValidationError("Treasury transaction could not be posted.")

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
