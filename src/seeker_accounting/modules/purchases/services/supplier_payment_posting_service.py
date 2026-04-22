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
from seeker_accounting.modules.purchases.dto.supplier_payment_dto import PaymentPostingResultDTO
from seeker_accounting.modules.purchases.repositories.purchase_bill_repository import (
    PurchaseBillRepository,
)
from seeker_accounting.modules.purchases.repositories.supplier_payment_allocation_repository import (
    SupplierPaymentAllocationRepository,
)
from seeker_accounting.modules.purchases.repositories.supplier_payment_repository import (
    SupplierPaymentRepository,
)
from seeker_accounting.modules.treasury.repositories.financial_account_repository import FinancialAccountRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService
from seeker_accounting.modules.administration.services.permission_service import PermissionService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
SupplierPaymentRepositoryFactory = Callable[[Session], SupplierPaymentRepository]
SupplierPaymentAllocationRepositoryFactory = Callable[[Session], SupplierPaymentAllocationRepository]
PurchaseBillRepositoryFactory = Callable[[Session], PurchaseBillRepository]
AccountRoleMappingRepositoryFactory = Callable[[Session], AccountRoleMappingRepository]
FinancialAccountRepositoryFactory = Callable[[Session], FinancialAccountRepository]


class SupplierPaymentPostingService:
    DOCUMENT_TYPE_CODE = "SUPPLIER_PAYMENT"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        supplier_payment_repository_factory: SupplierPaymentRepositoryFactory,
        supplier_payment_allocation_repository_factory: SupplierPaymentAllocationRepositoryFactory,
        purchase_bill_repository_factory: PurchaseBillRepositoryFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        account_role_mapping_repository_factory: AccountRoleMappingRepositoryFactory,
        financial_account_repository_factory: FinancialAccountRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        numbering_service: NumberingService,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._supplier_payment_repository_factory = supplier_payment_repository_factory
        self._supplier_payment_allocation_repository_factory = supplier_payment_allocation_repository_factory
        self._purchase_bill_repository_factory = purchase_bill_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._account_role_mapping_repository_factory = account_role_mapping_repository_factory
        self._financial_account_repository_factory = financial_account_repository_factory
        self._company_repository_factory = company_repository_factory
        self._numbering_service = numbering_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def post_payment(
        self,
        company_id: int,
        payment_id: int,
        actor_user_id: int | None = None,
    ) -> PaymentPostingResultDTO:
        self._permission_service.require_permission("purchases.payments.post")
        with self._unit_of_work_factory() as uow:
            actor_id = actor_user_id if actor_user_id is not None else self._app_context.current_user_id
            self._require_company_exists(uow.session, company_id)

            payment_repo = self._require_payment_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)
            bill_repo = self._require_bill_repository(uow.session)
            journal_repo = self._require_journal_entry_repository(uow.session)
            fiscal_period_repo = self._require_fiscal_period_repository(uow.session)
            role_mapping_repo = self._require_role_mapping_repository(uow.session)
            fa_repo = self._require_financial_account_repository(uow.session)

            payment = payment_repo.get_detail(company_id, payment_id)
            if payment is None:
                raise NotFoundError(f"Supplier payment with id {payment_id} was not found.")
            if payment.status_code != "draft":
                raise ValidationError("Only draft payments can be posted.")

            # --- Period validation ---
            fiscal_period = fiscal_period_repo.get_covering_date(company_id, payment.payment_date)
            if fiscal_period is None:
                raise ValidationError("Payment date must fall within an existing fiscal period.")
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError("Payment cannot be posted into a locked fiscal period.")
            if fiscal_period.status_code != "OPEN":
                raise ValidationError("Payment can only be posted into an open fiscal period.")

            # --- AP control account ---
            ap_mapping = role_mapping_repo.get_by_role_code(company_id, "ap_control")
            if ap_mapping is None:
                raise ValidationError(
                    "An AP control account mapping must be configured before posting supplier payments."
                )
            ap_account_id = ap_mapping.account_id

            # --- Financial account GL account ---
            financial_account = fa_repo.get_by_id(company_id, payment.financial_account_id)
            if financial_account is None or not financial_account.is_active:
                raise ValidationError("Financial account must be active to post a payment.")
            gl_account_id = financial_account.gl_account_id

            # --- Build journal entry ---
            journal_lines: list[JournalEntryLine] = []

            # Debit AP control
            journal_lines.append(
                JournalEntryLine(
                    journal_entry_id=0,
                    line_number=1,
                    account_id=ap_account_id,
                    line_description=f"Payment {payment.payment_number} - AP",
                    debit_amount=payment.amount_paid,
                    credit_amount=Decimal("0.00"),
                )
            )

            # Credit bank/cash GL account
            journal_lines.append(
                JournalEntryLine(
                    journal_entry_id=0,
                    line_number=2,
                    account_id=gl_account_id,
                    line_description=f"Payment {payment.payment_number} - Bank/Cash",
                    debit_amount=Decimal("0.00"),
                    credit_amount=payment.amount_paid,
                )
            )

            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period.id,
                entry_number=None,
                entry_date=payment.payment_date,
                journal_type_code="PAYMENT",
                reference_text=payment.payment_number,
                description=f"Supplier payment {payment.payment_number}",
                source_module_code="purchases",
                source_document_type="supplier_payment",
                source_document_id=payment.id,
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

            # --- Assign payment number and update status ---
            payment.payment_number = self._numbering_service.issue_next_number(
                uow.session,
                company_id=company_id,
                document_type_code=self.DOCUMENT_TYPE_CODE,
            )
            payment.status_code = "posted"
            payment.posted_journal_entry_id = journal_entry.id
            payment.posted_at = datetime.utcnow()
            payment.posted_by_user_id = actor_id
            payment_repo.save(payment)

            # --- Refresh bill payment statuses ---
            allocations = alloc_repo.list_for_payment(company_id, payment.id)
            affected_bill_ids = list({a.purchase_bill_id for a in allocations})
            if affected_bill_ids:
                posted_alloc_totals = alloc_repo.get_allocated_totals_for_bill_ids(
                    company_id, affected_bill_ids, posted_only=True
                )
                for bill_id in affected_bill_ids:
                    bill = bill_repo.get_by_id(company_id, bill_id)
                    if bill is None or bill.status_code != "posted":
                        continue
                    allocated = posted_alloc_totals.get(bill_id, Decimal("0.00"))
                    # Include THIS payment's allocations which are now posted
                    for a in allocations:
                        if a.purchase_bill_id == bill_id:
                            allocated += a.allocated_amount
                    if allocated >= bill.total_amount:
                        bill.payment_status_code = "paid"
                    elif allocated > Decimal("0.00"):
                        bill.payment_status_code = "partial"
                    else:
                        bill.payment_status_code = "unpaid"
                    bill_repo.save(bill)

            # --- Calculate result ---
            total_allocated = sum((a.allocated_amount for a in allocations), Decimal("0.00"))
            remaining = payment.amount_paid - total_allocated
            if remaining < Decimal("0.00"):
                remaining = Decimal("0.00")

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_posting_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import SUPPLIER_PAYMENT_POSTED
            self._record_audit(company_id, SUPPLIER_PAYMENT_POSTED, "SupplierPayment", payment.id, "Posted supplier payment")
            return PaymentPostingResultDTO(
                company_id=company_id,
                supplier_payment_id=payment.id,
                payment_number=payment.payment_number,
                journal_entry_id=journal_entry.id,
                journal_entry_number=journal_entry.entry_number or "",
                posted_at=payment.posted_at or datetime.utcnow(),
                posted_by_user_id=payment.posted_by_user_id,
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

    def _require_payment_repository(self, session: Session | None) -> SupplierPaymentRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._supplier_payment_repository_factory(session)

    def _require_allocation_repository(self, session: Session | None) -> SupplierPaymentAllocationRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._supplier_payment_allocation_repository_factory(session)

    def _require_bill_repository(self, session: Session | None) -> PurchaseBillRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._purchase_bill_repository_factory(session)

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
        if "unique" in message and "payment_number" in message:
            return ConflictError("A supplier payment with this number already exists.")
        if "unique" in message and "entry_number" in message:
            return ConflictError("Journal entry numbering conflicts with an existing posted entry.")
        return ValidationError("Supplier payment could not be posted.")

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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_PURCHASES
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_PURCHASES,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
