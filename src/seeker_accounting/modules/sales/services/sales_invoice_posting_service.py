from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import AccountRepository
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
from seeker_accounting.modules.accounting.reference_data.repositories.tax_code_account_mapping_repository import (
    TaxCodeAccountMappingRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.sales.dto.sales_invoice_dto import SalesPostingResultDTO
from seeker_accounting.modules.sales.repositories.customer_receipt_allocation_repository import (
    CustomerReceiptAllocationRepository,
)
from seeker_accounting.modules.sales.repositories.sales_invoice_repository import SalesInvoiceRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.numbering.numbering_service import NumberingService
from seeker_accounting.modules.administration.services.permission_service import PermissionService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

AccountRepositoryFactory = Callable[[Session], AccountRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
SalesInvoiceRepositoryFactory = Callable[[Session], SalesInvoiceRepository]
AccountRoleMappingRepositoryFactory = Callable[[Session], AccountRoleMappingRepository]
TaxCodeAccountMappingRepositoryFactory = Callable[[Session], TaxCodeAccountMappingRepository]
CustomerReceiptAllocationRepositoryFactory = Callable[[Session], CustomerReceiptAllocationRepository]


class SalesInvoicePostingService:
    DOCUMENT_TYPE_CODE = "SALES_INVOICE"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        sales_invoice_repository_factory: SalesInvoiceRepositoryFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        account_role_mapping_repository_factory: AccountRoleMappingRepositoryFactory,
        tax_code_account_mapping_repository_factory: TaxCodeAccountMappingRepositoryFactory,
        customer_receipt_allocation_repository_factory: CustomerReceiptAllocationRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        numbering_service: NumberingService,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._sales_invoice_repository_factory = sales_invoice_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._account_repository_factory = account_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._account_role_mapping_repository_factory = account_role_mapping_repository_factory
        self._tax_code_account_mapping_repository_factory = tax_code_account_mapping_repository_factory
        self._customer_receipt_allocation_repository_factory = customer_receipt_allocation_repository_factory
        self._company_repository_factory = company_repository_factory
        self._numbering_service = numbering_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def post_invoice(
        self,
        company_id: int,
        invoice_id: int,
        actor_user_id: int | None = None,
    ) -> SalesPostingResultDTO:
        self._permission_service.require_permission("sales.invoices.post")
        with self._unit_of_work_factory() as uow:
            actor_id = actor_user_id if actor_user_id is not None else self._app_context.current_user_id
            self._require_company_exists(uow.session, company_id)

            invoice_repo = self._require_invoice_repository(uow.session)
            journal_repo = self._require_journal_entry_repository(uow.session)
            fiscal_period_repo = self._require_fiscal_period_repository(uow.session)
            role_mapping_repo = self._require_role_mapping_repository(uow.session)
            tax_mapping_repo = self._require_tax_mapping_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)

            invoice = invoice_repo.get_detail(company_id, invoice_id)
            if invoice is None:
                raise NotFoundError(f"Sales invoice with id {invoice_id} was not found.")
            if invoice.status_code != "draft":
                raise ValidationError("Only draft invoices can be posted.")
            if not invoice.lines:
                raise ValidationError("Invoice must have at least one line to be posted.")

            # --- Period validation ---
            fiscal_period = fiscal_period_repo.get_covering_date(company_id, invoice.invoice_date)
            if fiscal_period is None:
                raise ValidationError("Invoice date must fall within an existing fiscal period.")
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError("Invoice cannot be posted into a locked fiscal period.")
            if fiscal_period.status_code != "OPEN":
                raise ValidationError("Invoice can only be posted into an open fiscal period.")

            # --- AR control account ---
            ar_mapping = role_mapping_repo.get_by_role_code(company_id, "ar_control")
            if ar_mapping is None:
                raise ValidationError(
                    "An AR control account mapping must be configured before posting sales invoices.",
                    app_error_code=AppErrorCode.MISSING_ACCOUNT_ROLE_MAPPING,
                    context={
                        "company_id": company_id,
                        "role_code": "ar_control",
                        "origin_workflow": "sales_invoice",
                    },
                )
            ar_account_id = ar_mapping.account_id

            # --- Build journal lines ---
            journal_lines: list[JournalEntryLine] = []
            line_number = 1

            # Debit AR control for the total
            journal_lines.append(
                JournalEntryLine(
                    journal_entry_id=0,
                    line_number=line_number,
                    account_id=ar_account_id,
                    line_description=f"AR - Invoice {invoice.invoice_number}",
                    debit_amount=invoice.total_amount,
                    credit_amount=Decimal("0.00"),
                )
            )
            line_number += 1

            # Credit revenue accounts from lines
            revenue_credits: dict[int, Decimal] = {}
            tax_credits: dict[int, Decimal] = {}

            for inv_line in invoice.lines:
                revenue_credits[inv_line.revenue_account_id] = (
                    revenue_credits.get(inv_line.revenue_account_id, Decimal("0.00"))
                    + inv_line.line_subtotal_amount
                )
                if inv_line.tax_code_id is not None and inv_line.line_tax_amount > Decimal("0.00"):
                    tax_mapping = tax_mapping_repo.get_by_tax_code(company_id, inv_line.tax_code_id)
                    if tax_mapping is None or tax_mapping.tax_liability_account_id is None:
                        raise ValidationError(
                            f"Tax account mapping for tax code on line {inv_line.line_number} "
                            "must be configured before posting."
                        )
                    tax_account_id = tax_mapping.tax_liability_account_id
                    tax_credits[tax_account_id] = (
                        tax_credits.get(tax_account_id, Decimal("0.00"))
                        + inv_line.line_tax_amount
                    )

            for rev_account_id, amount in revenue_credits.items():
                journal_lines.append(
                    JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=rev_account_id,
                        line_description=f"Revenue - Invoice {invoice.invoice_number}",
                        debit_amount=Decimal("0.00"),
                        credit_amount=amount,
                    )
                )
                line_number += 1

            for tax_account_id, amount in tax_credits.items():
                journal_lines.append(
                    JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=tax_account_id,
                        line_description=f"Tax liability - Invoice {invoice.invoice_number}",
                        debit_amount=Decimal("0.00"),
                        credit_amount=amount,
                    )
                )
                line_number += 1

            # --- Create journal entry ---
            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period.id,
                entry_number=None,
                entry_date=invoice.invoice_date,
                journal_type_code="SALES",
                reference_text=invoice.invoice_number,
                description=f"Sales invoice {invoice.invoice_number}",
                source_module_code="sales",
                source_document_type="sales_invoice",
                source_document_id=invoice.id,
                status_code="POSTED",
                posted_at=datetime.utcnow(),
                posted_by_user_id=actor_id,
                created_by_user_id=actor_id,
            )
            journal_repo.add(journal_entry)
            uow.session.flush()

            # Assign entry number via numbering service
            journal_entry.entry_number = self._numbering_service.issue_next_number(
                uow.session,
                company_id=company_id,
                document_type_code="JOURNAL_ENTRY",
            )
            journal_repo.save(journal_entry)

            for jl in journal_lines:
                jl.journal_entry_id = journal_entry.id
            uow.session.add_all(journal_lines)

            # --- Assign invoice number and update status ---
            invoice.invoice_number = self._numbering_service.issue_next_number(
                uow.session,
                company_id=company_id,
                document_type_code=self.DOCUMENT_TYPE_CODE,
            )
            invoice.status_code = "posted"
            invoice.payment_status_code = "unpaid"
            invoice.posted_journal_entry_id = journal_entry.id
            invoice.posted_at = datetime.utcnow()
            invoice.posted_by_user_id = actor_id
            invoice_repo.save(invoice)

            # Derive open balance for the result
            allocated_totals = alloc_repo.get_allocated_totals_for_invoice_ids(
                company_id, [invoice.id], posted_only=True
            )
            allocated = allocated_totals.get(invoice.id, Decimal("0.00"))
            open_balance = invoice.total_amount - allocated
            if open_balance < Decimal("0.00"):
                open_balance = Decimal("0.00")

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_posting_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import SALES_INVOICE_POSTED
            self._record_audit(company_id, SALES_INVOICE_POSTED, "SalesInvoice", invoice.id, "Posted sales invoice")
            return SalesPostingResultDTO(
                company_id=company_id,
                sales_invoice_id=invoice.id,
                invoice_number=invoice.invoice_number,
                journal_entry_id=journal_entry.id,
                journal_entry_number=journal_entry.entry_number or "",
                posted_at=invoice.posted_at or datetime.utcnow(),
                posted_by_user_id=invoice.posted_by_user_id,
                payment_status_code=invoice.payment_status_code,
                open_balance_amount=open_balance,
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

    def _require_tax_mapping_repository(self, session: Session | None) -> TaxCodeAccountMappingRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._tax_code_account_mapping_repository_factory(session)

    def _require_allocation_repository(self, session: Session | None) -> CustomerReceiptAllocationRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._customer_receipt_allocation_repository_factory(session)

    def _translate_posting_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "invoice_number" in message:
            return ConflictError("A sales invoice with this number already exists.")
        if "unique" in message and "entry_number" in message:
            return ConflictError("Journal entry numbering conflicts with an existing posted entry.")
        return ValidationError("Sales invoice could not be posted.")

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
