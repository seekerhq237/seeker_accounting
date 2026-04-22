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
from seeker_accounting.modules.purchases.dto.purchase_bill_dto import PurchasePostingResultDTO
from seeker_accounting.modules.purchases.repositories.purchase_bill_repository import (
    PurchaseBillRepository,
)
from seeker_accounting.modules.purchases.repositories.supplier_payment_allocation_repository import (
    SupplierPaymentAllocationRepository,
)
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
PurchaseBillRepositoryFactory = Callable[[Session], PurchaseBillRepository]
AccountRoleMappingRepositoryFactory = Callable[[Session], AccountRoleMappingRepository]
TaxCodeAccountMappingRepositoryFactory = Callable[[Session], TaxCodeAccountMappingRepository]
SupplierPaymentAllocationRepositoryFactory = Callable[[Session], SupplierPaymentAllocationRepository]


class PurchaseBillPostingService:
    DOCUMENT_TYPE_CODE = "PURCHASE_BILL"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        purchase_bill_repository_factory: PurchaseBillRepositoryFactory,
        journal_entry_repository_factory: JournalEntryRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        fiscal_period_repository_factory: FiscalPeriodRepositoryFactory,
        account_role_mapping_repository_factory: AccountRoleMappingRepositoryFactory,
        tax_code_account_mapping_repository_factory: TaxCodeAccountMappingRepositoryFactory,
        supplier_payment_allocation_repository_factory: SupplierPaymentAllocationRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        numbering_service: NumberingService,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._purchase_bill_repository_factory = purchase_bill_repository_factory
        self._journal_entry_repository_factory = journal_entry_repository_factory
        self._account_repository_factory = account_repository_factory
        self._fiscal_period_repository_factory = fiscal_period_repository_factory
        self._account_role_mapping_repository_factory = account_role_mapping_repository_factory
        self._tax_code_account_mapping_repository_factory = tax_code_account_mapping_repository_factory
        self._supplier_payment_allocation_repository_factory = supplier_payment_allocation_repository_factory
        self._company_repository_factory = company_repository_factory
        self._numbering_service = numbering_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def post_bill(
        self,
        company_id: int,
        bill_id: int,
        actor_user_id: int | None = None,
    ) -> PurchasePostingResultDTO:
        self._permission_service.require_permission("purchases.bills.post")
        with self._unit_of_work_factory() as uow:
            actor_id = actor_user_id if actor_user_id is not None else self._app_context.current_user_id
            self._require_company_exists(uow.session, company_id)

            bill_repo = self._require_bill_repository(uow.session)
            journal_repo = self._require_journal_entry_repository(uow.session)
            fiscal_period_repo = self._require_fiscal_period_repository(uow.session)
            role_mapping_repo = self._require_role_mapping_repository(uow.session)
            tax_mapping_repo = self._require_tax_mapping_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)

            bill = bill_repo.get_detail(company_id, bill_id)
            if bill is None:
                raise NotFoundError(f"Purchase bill with id {bill_id} was not found.")
            if bill.status_code != "draft":
                raise ValidationError("Only draft bills can be posted.")
            if not bill.lines:
                raise ValidationError("Bill must have at least one line to be posted.")

            # --- Period validation ---
            fiscal_period = fiscal_period_repo.get_covering_date(company_id, bill.bill_date)
            if fiscal_period is None:
                raise ValidationError("Bill date must fall within an existing fiscal period.")
            if fiscal_period.status_code == "LOCKED":
                raise PeriodLockedError("Bill cannot be posted into a locked fiscal period.")
            if fiscal_period.status_code != "OPEN":
                raise ValidationError("Bill can only be posted into an open fiscal period.")

            # --- AP control account ---
            ap_mapping = role_mapping_repo.get_by_role_code(company_id, "ap_control")
            if ap_mapping is None:
                raise ValidationError(
                    "An AP control account mapping must be configured before posting purchase bills.",
                    app_error_code=AppErrorCode.MISSING_ACCOUNT_ROLE_MAPPING,
                    context={
                        "company_id": company_id,
                        "role_code": "ap_control",
                        "origin_workflow": "purchase_bill",
                    },
                )
            ap_account_id = ap_mapping.account_id

            # --- Build journal lines ---
            journal_lines: list[JournalEntryLine] = []
            line_number = 1

            # Debit expense accounts from lines
            expense_debits: dict[int, Decimal] = {}
            tax_debits: dict[int, Decimal] = {}

            for bill_line in bill.lines:
                expense_debits[bill_line.expense_account_id] = (
                    expense_debits.get(bill_line.expense_account_id, Decimal("0.00"))
                    + bill_line.line_subtotal_amount
                )
                if bill_line.tax_code_id is not None and bill_line.line_tax_amount > Decimal("0.00"):
                    tax_mapping = tax_mapping_repo.get_by_tax_code(company_id, bill_line.tax_code_id)
                    if tax_mapping is None or tax_mapping.tax_asset_account_id is None:
                        raise ValidationError(
                            f"Tax account mapping for tax code on line {bill_line.line_number} "
                            "must be configured before posting."
                        )
                    tax_account_id = tax_mapping.tax_asset_account_id
                    tax_debits[tax_account_id] = (
                        tax_debits.get(tax_account_id, Decimal("0.00"))
                        + bill_line.line_tax_amount
                    )

            for exp_account_id, amount in expense_debits.items():
                journal_lines.append(
                    JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=exp_account_id,
                        line_description=f"Expense - Bill {bill.bill_number}",
                        debit_amount=amount,
                        credit_amount=Decimal("0.00"),
                    )
                )
                line_number += 1

            for tax_account_id, amount in tax_debits.items():
                journal_lines.append(
                    JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=tax_account_id,
                        line_description=f"Tax asset - Bill {bill.bill_number}",
                        debit_amount=amount,
                        credit_amount=Decimal("0.00"),
                    )
                )
                line_number += 1

            # Credit AP control for the total
            journal_lines.append(
                JournalEntryLine(
                    journal_entry_id=0,
                    line_number=line_number,
                    account_id=ap_account_id,
                    line_description=f"AP - Bill {bill.bill_number}",
                    debit_amount=Decimal("0.00"),
                    credit_amount=bill.total_amount,
                )
            )

            # --- Create journal entry ---
            journal_entry = JournalEntry(
                company_id=company_id,
                fiscal_period_id=fiscal_period.id,
                entry_number=None,
                entry_date=bill.bill_date,
                journal_type_code="PURCHASE",
                reference_text=bill.bill_number,
                description=f"Purchase bill {bill.bill_number}",
                source_module_code="purchases",
                source_document_type="purchase_bill",
                source_document_id=bill.id,
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

            # --- Assign bill number and update status ---
            bill.bill_number = self._numbering_service.issue_next_number(
                uow.session,
                company_id=company_id,
                document_type_code=self.DOCUMENT_TYPE_CODE,
            )
            bill.status_code = "posted"
            bill.payment_status_code = "unpaid"
            bill.posted_journal_entry_id = journal_entry.id
            bill.posted_at = datetime.utcnow()
            bill.posted_by_user_id = actor_id
            bill_repo.save(bill)

            # Derive open balance for the result
            allocated_totals = alloc_repo.get_allocated_totals_for_bill_ids(
                company_id, [bill.id], posted_only=True
            )
            allocated = allocated_totals.get(bill.id, Decimal("0.00"))
            open_balance = bill.total_amount - allocated
            if open_balance < Decimal("0.00"):
                open_balance = Decimal("0.00")

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_posting_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import PURCHASE_BILL_POSTED
            self._record_audit(company_id, PURCHASE_BILL_POSTED, "PurchaseBill", bill.id, "Posted purchase bill")
            return PurchasePostingResultDTO(
                company_id=company_id,
                purchase_bill_id=bill.id,
                bill_number=bill.bill_number,
                journal_entry_id=journal_entry.id,
                journal_entry_number=journal_entry.entry_number or "",
                posted_at=bill.posted_at or datetime.utcnow(),
                posted_by_user_id=bill.posted_by_user_id,
                payment_status_code=bill.payment_status_code,
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

    def _require_tax_mapping_repository(self, session: Session | None) -> TaxCodeAccountMappingRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._tax_code_account_mapping_repository_factory(session)

    def _require_allocation_repository(self, session: Session | None) -> SupplierPaymentAllocationRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._supplier_payment_allocation_repository_factory(session)

    def _translate_posting_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "bill_number" in message:
            return ConflictError("A purchase bill with this number already exists.")
        if "unique" in message and "entry_number" in message:
            return ConflictError("Journal entry numbering conflicts with an existing posted entry.")
        return ValidationError("Purchase bill could not be posted.")

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
