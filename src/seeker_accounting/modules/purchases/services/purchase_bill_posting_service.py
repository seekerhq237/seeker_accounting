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
from seeker_accounting.modules.budgeting.services.budget_control_service import BudgetControlService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.purchases.dto.purchase_bill_dto import PurchasePostingResultDTO
from seeker_accounting.modules.purchases.repositories.purchase_bill_repository import (
    PurchaseBillRepository,
)
from seeker_accounting.modules.purchases.repositories.supplier_payment_allocation_repository import (
    SupplierPaymentAllocationRepository,
)
from seeker_accounting.modules.taxation.models.posted_tax_line import (
    DIRECTION_PURCHASE,
    SOURCE_PURCHASE_BILL,
)
from seeker_accounting.modules.taxation.services.tax_fact_service import (
    TaxFactInput,
    TaxFactService,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.numbering.numbering_service import NumberingService
from seeker_accounting.modules.administration.services.permission_service import PermissionService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

from seeker_accounting.modules.taxation.repositories.vat_period_lock_repository import (
    VatPeriodLockRepository,
)

AccountRepositoryFactory = Callable[[Session], AccountRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
JournalEntryRepositoryFactory = Callable[[Session], JournalEntryRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
PurchaseBillRepositoryFactory = Callable[[Session], PurchaseBillRepository]
AccountRoleMappingRepositoryFactory = Callable[[Session], AccountRoleMappingRepository]
TaxCodeAccountMappingRepositoryFactory = Callable[[Session], TaxCodeAccountMappingRepository]
SupplierPaymentAllocationRepositoryFactory = Callable[[Session], SupplierPaymentAllocationRepository]
VatPeriodLockRepositoryFactory = Callable[[Session], VatPeriodLockRepository]


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
        tax_fact_service: TaxFactService,
        budget_control_service: BudgetControlService | None = None,
        audit_service: AuditService | None = None,
        vat_period_lock_repository_factory: VatPeriodLockRepositoryFactory | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._tax_fact_service = tax_fact_service
        self._vat_period_lock_repository_factory = vat_period_lock_repository_factory
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
        self._budget_control_service = budget_control_service
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

            # --- T43: VAT period lock check ---
            if self._vat_period_lock_repository_factory is not None:
                tax_point = bill.tax_point_date or bill.bill_date
                vat_lock_repo = self._vat_period_lock_repository_factory(uow.session)
                if vat_lock_repo.is_locked(company_id, tax_point):
                    raise ValidationError(
                        "VAT period has been filed; backdating is prohibited. "
                        "Amend the return instead."
                    )

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
            self._enforce_budget_for_bill(bill)

            # --- Build journal lines ---
            journal_lines: list[JournalEntryLine] = []
            line_number = 1

            # Debit expense accounts from lines
            expense_debits: dict[tuple[int, int | None, int | None, int | None, int | None], Decimal] = {}
            tax_debits: dict[int, Decimal] = {}
            # T33: accumulate RC symmetric legs: Dr 4452 (asset) / Cr 4434 (liability)
            rc_asset_debits: dict[int, Decimal] = {}   # tax_asset_account_id → amount
            rc_liability_credits: dict[int, Decimal] = {}  # tax_liability_account_id → amount

            for bill_line in bill.lines:
                expense_key = self._dimensioned_account_key(
                    bill_line.expense_account_id,
                    line=bill_line,
                    header_contract_id=bill.contract_id,
                    header_project_id=bill.project_id,
                )
                expense_debits[expense_key] = (
                    expense_debits.get(expense_key, Decimal("0.00"))
                    + bill_line.line_subtotal_amount
                )
                if bill_line.tax_code_id is not None and bill_line.line_tax_amount > Decimal("0.00"):
                    # Non-recoverable input tax (blocked / non-deductible VAT) is
                    # not a recoverable asset — it is a cost of the underlying
                    # expense and must therefore be debited to the same expense
                    # account as the line, not to the tax_asset account.
                    tax_code_obj = bill_line.tax_code
                    is_recoverable = (
                        tax_code_obj is None or tax_code_obj.is_recoverable is not False
                    )

                    if not is_recoverable:
                        expense_debits[expense_key] = (
                            expense_debits.get(expense_key, Decimal("0.00"))
                            + bill_line.line_tax_amount
                        )
                        continue

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
                    # T33: reverse-charge — also accumulate the self-assessment legs.
                    if getattr(tax_code_obj, "is_reverse_charge", False):
                        if tax_mapping.tax_liability_account_id is None:
                            raise ValidationError(
                                f"Tax liability account mapping for reverse-charge tax code "
                                f"on line {bill_line.line_number} must be configured before posting."
                            )
                        rc_asset_debits[tax_mapping.tax_asset_account_id] = (
                            rc_asset_debits.get(tax_mapping.tax_asset_account_id, Decimal("0.00"))
                            + bill_line.line_tax_amount
                        )
                        rc_liability_credits[tax_mapping.tax_liability_account_id] = (
                            rc_liability_credits.get(tax_mapping.tax_liability_account_id, Decimal("0.00"))
                            + bill_line.line_tax_amount
                        )

            for expense_key, amount in expense_debits.items():
                exp_account_id, contract_id, project_id, project_job_id, project_cost_code_id = expense_key
                journal_lines.append(
                    JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=exp_account_id,
                        line_description=f"Expense - Bill {bill.bill_number}",
                        debit_amount=amount,
                        credit_amount=Decimal("0.00"),
                        contract_id=contract_id,
                        project_id=project_id,
                        project_job_id=project_job_id,
                        project_cost_code_id=project_cost_code_id,
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
            line_number += 1

            # T33: reverse-charge self-assessment legs.
            # The normal Dr to tax_asset (4452) is already in tax_debits above.
            # The RC legs add an equal Cr to tax_liability (4434) so that the
            # net effect on the asset account is zero and the liability account
            # records the output self-assessed VAT.
            for rc_liability_id, rc_amount in rc_liability_credits.items():
                journal_lines.append(
                    JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=rc_liability_id,
                        line_description=f"RC output VAT self-assessed - Bill {bill.bill_number}",
                        debit_amount=Decimal("0.00"),
                        credit_amount=rc_amount,
                    )
                )
                line_number += 1
            # Balancing Dr to the same asset account (cancels the normal input VAT
            # debit recorded in tax_debits so the asset position nets to zero for
            # a fully self-assessed RC transaction).
            for rc_asset_id, rc_amount in rc_asset_debits.items():
                journal_lines.append(
                    JournalEntryLine(
                        journal_entry_id=0,
                        line_number=line_number,
                        account_id=rc_asset_id,
                        line_description=f"RC input VAT recoverable - Bill {bill.bill_number}",
                        debit_amount=rc_amount,
                        credit_amount=Decimal("0.00"),
                    )
                )
                line_number += 1

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

            # --- Record immutable tax facts (Slice T11 / T12) ---
            # Prefer per-line tax-detail snapshot rows (Slice T3) so
            # multi-tax-per-line authoring flows naturally into
            # PostedTaxLine. Fall back to the parent line's single
            # tax_code/line_tax_amount for legacy documents.
            tax_facts: list[TaxFactInput] = []
            for bill_line in bill.lines:
                detail_rows = list(bill_line.tax_details or ())
                if detail_rows:
                    for detail in detail_rows:
                        if (
                            detail.tax_code_id is None
                            and detail.tax_amount == Decimal("0.00")
                        ):
                            continue
                        if detail.is_recoverable is not None:
                            line_is_recoverable: bool | None = detail.is_recoverable
                        elif detail.tax_code is not None:
                            line_is_recoverable = detail.tax_code.is_recoverable
                        else:
                            line_is_recoverable = None
                        _tc_rc = detail.tax_code
                        tax_facts.append(
                            TaxFactInput(
                                tax_code_id=detail.tax_code_id,
                                taxable_base=detail.taxable_base,
                                tax_amount=detail.tax_amount,
                                is_recoverable=line_is_recoverable,
                                source_line_id=bill_line.id,
                                is_reverse_charge=bool(
                                    getattr(_tc_rc, "is_reverse_charge", False)
                                ),
                            )
                        )
                    continue
                if bill_line.tax_code_id is None and bill_line.line_tax_amount == Decimal("0.00"):
                    continue
                tax_code_obj = bill_line.tax_code
                if tax_code_obj is None:
                    line_is_recoverable = None
                else:
                    line_is_recoverable = tax_code_obj.is_recoverable
                tax_facts.append(
                    TaxFactInput(
                        tax_code_id=bill_line.tax_code_id,
                        taxable_base=bill_line.line_subtotal_amount,
                        tax_amount=bill_line.line_tax_amount,
                        is_recoverable=line_is_recoverable,
                        source_line_id=bill_line.id,
                        is_reverse_charge=bool(
                            getattr(tax_code_obj, "is_reverse_charge", False)
                        ),
                    )
                )
            if tax_facts:
                posted_at_value = datetime.utcnow()
                self._tax_fact_service.record_facts_in_session(
                    uow.session,
                    company_id=company_id,
                    fiscal_period_id=fiscal_period.id,
                    direction=DIRECTION_PURCHASE,
                    source_document_type=SOURCE_PURCHASE_BILL,
                    source_document_id=bill.id,
                    journal_entry_id=journal_entry.id,
                    posted_at=posted_at_value,
                    posted_by_user_id=actor_id,
                    line_facts=tax_facts,
                    tax_point_date=bill.tax_point_date or bill.bill_date,
                )

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
    # Budget and dimension helpers
    # ------------------------------------------------------------------

    def _enforce_budget_for_bill(self, bill: object) -> None:
        if self._budget_control_service is None:
            return
        requests: dict[tuple[int, int | None, int | None], Decimal] = {}
        for bill_line in bill.lines:
            project_id = getattr(bill_line, "project_id", None) or getattr(bill, "project_id", None)
            if project_id is None:
                continue
            amount = self._bill_line_cost_amount(bill_line)
            if amount <= Decimal("0.00"):
                continue
            key = (
                project_id,
                getattr(bill_line, "project_job_id", None),
                getattr(bill_line, "project_cost_code_id", None),
            )
            requests[key] = requests.get(key, Decimal("0.00")) + amount
        for (project_id, project_job_id, project_cost_code_id), amount in requests.items():
            self._budget_control_service.enforce_budget(
                project_id,
                amount,
                project_job_id=project_job_id,
                project_cost_code_id=project_cost_code_id,
                context_label=f"Purchase bill {getattr(bill, 'bill_number', '')}".strip(),
            )

    @staticmethod
    def _bill_line_cost_amount(bill_line: object) -> Decimal:
        amount = Decimal(getattr(bill_line, "line_subtotal_amount", Decimal("0.00")))
        tax_amount = Decimal(getattr(bill_line, "line_tax_amount", Decimal("0.00")))
        tax_code = getattr(bill_line, "tax_code", None)
        if tax_amount > Decimal("0.00") and tax_code is not None and tax_code.is_recoverable is False:
            amount += tax_amount
        return amount.quantize(Decimal("0.01"))

    @staticmethod
    def _dimensioned_account_key(
        account_id: int,
        *,
        line: object,
        header_contract_id: int | None,
        header_project_id: int | None,
    ) -> tuple[int, int | None, int | None, int | None, int | None]:
        contract_id = getattr(line, "contract_id", None) or header_contract_id
        project_id = getattr(line, "project_id", None) or header_project_id
        return (
            account_id,
            contract_id,
            project_id,
            getattr(line, "project_job_id", None),
            getattr(line, "project_cost_code_id", None),
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
