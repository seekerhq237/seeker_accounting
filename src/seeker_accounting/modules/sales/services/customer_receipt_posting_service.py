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
from seeker_accounting.modules.accounting.reference_data.repositories.account_role_mapping_repository import (
    AccountRoleMappingRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.sales.dto.customer_receipt_dto import ReceiptPostingResultDTO
from seeker_accounting.modules.sales.repositories.customer_receipt_allocation_repository import (
    CustomerReceiptAllocationRepository,
)
from seeker_accounting.modules.sales.repositories.customer_receipt_repository import CustomerReceiptRepository
from seeker_accounting.modules.sales.repositories.sales_invoice_repository import SalesInvoiceRepository
from seeker_accounting.modules.treasury.repositories.financial_account_repository import FinancialAccountRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CustomerReceiptRepositoryFactory = Callable[[Session], CustomerReceiptRepository]
CustomerReceiptAllocationRepositoryFactory = Callable[[Session], CustomerReceiptAllocationRepository]
SalesInvoiceRepositoryFactory = Callable[[Session], SalesInvoiceRepository]
AccountRoleMappingRepositoryFactory = Callable[[Session], AccountRoleMappingRepository]
FinancialAccountRepositoryFactory = Callable[[Session], FinancialAccountRepository]


class CustomerReceiptPostingService:
    DOCUMENT_TYPE_CODE = "CUSTOMER_RECEIPT"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        customer_receipt_repository_factory: CustomerReceiptRepositoryFactory,
        customer_receipt_allocation_repository_factory: CustomerReceiptAllocationRepositoryFactory,
        sales_invoice_repository_factory: SalesInvoiceRepositoryFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        account_role_mapping_repository_factory: AccountRoleMappingRepositoryFactory,
        financial_account_repository_factory: FinancialAccountRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        numbering_service: NumberingService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._customer_receipt_repository_factory = customer_receipt_repository_factory
        self._customer_receipt_allocation_repository_factory = customer_receipt_allocation_repository_factory
        self._sales_invoice_repository_factory = sales_invoice_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._account_role_mapping_repository_factory = account_role_mapping_repository_factory
        self._financial_account_repository_factory = financial_account_repository_factory
        self._company_repository_factory = company_repository_factory
        self._numbering_service = numbering_service
        self._audit_service = audit_service

    def post_receipt(
        self,
        company_id: int,
        receipt_id: int,
        actor_user_id: int | None = None,
    ) -> ReceiptPostingResultDTO:
        with self._unit_of_work_factory() as uow:
            actor_id = actor_user_id if actor_user_id is not None else self._app_context.current_user_id
            self._require_company_exists(uow.session, company_id)

            receipt_repo = self._require_receipt_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)
            invoice_repo = self._require_invoice_repository(uow.session)
            journal_repo = self._require_journal_entry_repository(uow.session)
            fiscal_period_repo = self._require_fiscal_period_repository(uow.session)
            role_mapping_repo = self._require_role_mapping_repository(uow.session)
            fa_repo = self._require_financial_account_repository(uow.session)

            receipt = receipt_repo.get_detail(company_id, receipt_id)
            if receipt is None:
                raise NotFoundError(f"Customer receipt with id {receipt_id} was not found.")
            if receipt.status_code != "draft":
                raise ValidationError("Only draft receipts can be posted.")

            # --- Period validation ---
            fiscal_period = fiscal_period_repo.get_covering_date(company_id, receipt.receipt_date)
            if fiscal_period is None:
                raise ValidationError("Receipt date must fall within an existing fiscal period.")
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError("Receipt cannot be posted into a locked fiscal period.")
            if fiscal_period.status_code != "OPEN":
                raise ValidationError("Receipt can only be posted into an open fiscal period.")

            # --- AR control account ---
            ar_mapping = role_mapping_repo.get_by_role_code(company_id, "ar_control")
            if ar_mapping is None:
                raise ValidationError(
                    "An AR control account mapping must be configured before posting customer receipts."
                )
            ar_account_id = ar_mapping.account_id

            # --- Financial account GL account ---
            financial_account = fa_repo.get_by_id(company_id, receipt.financial_account_id)
            if financial_account is None or not financial_account.is_active:
                raise ValidationError("Financial account must be active to post a receipt.")
            gl_account_id = financial_account.gl_account_id

            # --- Build journal entry ---
            journal_lines: list[JournalEntryLine] = []

            # Debit bank/cash GL account
            journal_lines.append(
                JournalEntryLine(
                    journal_entry_id=0,
                    line_number=1,
                    account_id=gl_account_id,
                    line_description=f"Receipt {receipt.receipt_number} - Bank/Cash",
                    debit_amount=receipt.amount_received,
                    credit_amount=Decimal("0.00"),
                )
            )

            # Credit AR control
            journal_lines.append(
                JournalEntryLine(
                    journal_entry_id=0,
                    line_number=2,
                    account_id=ar_account_id,
                    line_description=f"Receipt {receipt.receipt_number} - AR",
                    debit_amount=Decimal("0.00"),
                    credit_amount=receipt.amount_received,
                )
            )

            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period.id,
                entry_number=None,
                entry_date=receipt.receipt_date,
                journal_type_code="RECEIPT",
                reference_text=receipt.receipt_number,
                description=f"Customer receipt {receipt.receipt_number}",
                source_module_code="sales",
                source_document_type="customer_receipt",
                source_document_id=receipt.id,
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

            # --- Assign receipt number and update status ---
            receipt.receipt_number = self._numbering_service.issue_next_number(
                uow.session,
                company_id=company_id,
                document_type_code=self.DOCUMENT_TYPE_CODE,
            )
            receipt.status_code = "posted"
            receipt.posted_journal_entry_id = journal_entry.id
            receipt.posted_at = datetime.utcnow()
            receipt.posted_by_user_id = actor_id
            receipt_repo.save(receipt)

            # --- Refresh invoice payment statuses ---
            allocations = alloc_repo.list_for_receipt(company_id, receipt.id)
            affected_invoice_ids = list({a.sales_invoice_id for a in allocations})
            if affected_invoice_ids:
                posted_alloc_totals = alloc_repo.get_allocated_totals_for_invoice_ids(
                    company_id, affected_invoice_ids, posted_only=True
                )
                for inv_id in affected_invoice_ids:
                    inv = invoice_repo.get_by_id(company_id, inv_id)
                    if inv is None or inv.status_code != "posted":
                        continue
                    allocated = posted_alloc_totals.get(inv_id, Decimal("0.00"))
                    # Include THIS receipt's allocations which are now posted
                    for a in allocations:
                        if a.sales_invoice_id == inv_id:
                            allocated += a.allocated_amount
                    if allocated >= inv.total_amount:
                        inv.payment_status_code = "paid"
                    elif allocated > Decimal("0.00"):
                        inv.payment_status_code = "partial"
                    else:
                        inv.payment_status_code = "unpaid"
                    invoice_repo.save(inv)

            # --- Calculate result ---
            total_allocated = sum((a.allocated_amount for a in allocations), Decimal("0.00"))
            remaining = receipt.amount_received - total_allocated
            if remaining < Decimal("0.00"):
                remaining = Decimal("0.00")

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_posting_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import CUSTOMER_RECEIPT_POSTED
            self._record_audit(company_id, CUSTOMER_RECEIPT_POSTED, "CustomerReceipt", receipt.id, "Posted customer receipt")
            return ReceiptPostingResultDTO(
                company_id=company_id,
                customer_receipt_id=receipt.id,
                receipt_number=receipt.receipt_number,
                journal_entry_id=journal_entry.id,
                journal_entry_number=journal_entry.entry_number or "",
                posted_at=receipt.posted_at or datetime.utcnow(),
                posted_by_user_id=receipt.posted_by_user_id,
                allocated_amount=total_allocated,
                remaining_unallocated_amount=remaining,
            )

    # ------------------------------------------------------------------
    # Repository factory helpers
    # ------------------------------------------------------------------

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _require_receipt_repository(self, session: Session | None) -> CustomerReceiptRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._customer_receipt_repository_factory(session)

    def _require_allocation_repository(self, session: Session | None) -> CustomerReceiptAllocationRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._customer_receipt_allocation_repository_factory(session)

    def _require_invoice_repository(self, session: Session | None) -> SalesInvoiceRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._sales_invoice_repository_factory(session)

    def _require_journal_entry_repository(self, session: Session | None) -> JournalEntryRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._journal_entry_repository_factory(session)

    def _require_fiscal_period_repository(self, session: Session | None) -> FiscalPeriodRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._fiscal_period_repository_factory(session)

    def _require_role_mapping_repository(self, session: Session | None) -> AccountRoleMappingRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_role_mapping_repository_factory(session)

    def _require_financial_account_repository(self, session: Session | None) -> FinancialAccountRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._financial_account_repository_factory(session)

    def _translate_posting_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "receipt_number" in message:
            return ConflictError("A customer receipt with this number already exists.")
        if "unique" in message and "entry_number" in message:
            return ConflictError("Journal entry numbering conflicts with an existing posted entry.")
        return ValidationError("Customer receipt could not be posted.")

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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_SALES
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_SALES,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
