from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Callable
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.purchases.dto.purchase_bill_dto import SupplierOpenBillDTO
from seeker_accounting.modules.purchases.dto.supplier_payment_commands import (
    CreateSupplierPaymentCommand,
    SupplierPaymentAllocationCommand,
    UpdateSupplierPaymentCommand,
)
from seeker_accounting.modules.purchases.dto.supplier_payment_dto import (
    BillPaymentRowDTO,
    SupplierPaymentAllocationDTO,
    SupplierPaymentDetailDTO,
    SupplierPaymentListItemDTO,
)
from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
from seeker_accounting.modules.purchases.models.supplier_payment import SupplierPayment
from seeker_accounting.modules.purchases.models.supplier_payment_allocation import SupplierPaymentAllocation
from seeker_accounting.modules.purchases.repositories.purchase_bill_repository import (
    PurchaseBillRepository,
)
from seeker_accounting.modules.purchases.repositories.supplier_payment_allocation_repository import (
    SupplierPaymentAllocationRepository,
)
from seeker_accounting.modules.purchases.repositories.supplier_payment_repository import (
    SupplierPaymentRepository,
)
from seeker_accounting.modules.suppliers.models.supplier import Supplier
from seeker_accounting.modules.suppliers.repositories.supplier_repository import SupplierRepository
from seeker_accounting.modules.treasury.models.financial_account import FinancialAccount
from seeker_accounting.modules.treasury.repositories.financial_account_repository import FinancialAccountRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
SupplierRepositoryFactory = Callable[[Session], SupplierRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]
FinancialAccountRepositoryFactory = Callable[[Session], FinancialAccountRepository]
PurchaseBillRepositoryFactory = Callable[[Session], PurchaseBillRepository]
SupplierPaymentRepositoryFactory = Callable[[Session], SupplierPaymentRepository]
SupplierPaymentAllocationRepositoryFactory = Callable[[Session], SupplierPaymentAllocationRepository]

_DRAFT_NUMBER_PREFIX = "SP-DRAFT-"
_ALLOWED_STATUS_CODES = {"draft", "posted", "cancelled"}


class SupplierPaymentService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        supplier_repository_factory: SupplierRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        financial_account_repository_factory: FinancialAccountRepositoryFactory,
        purchase_bill_repository_factory: PurchaseBillRepositoryFactory,
        supplier_payment_repository_factory: SupplierPaymentRepositoryFactory,
        supplier_payment_allocation_repository_factory: SupplierPaymentAllocationRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._supplier_repository_factory = supplier_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._financial_account_repository_factory = financial_account_repository_factory
        self._purchase_bill_repository_factory = purchase_bill_repository_factory
        self._supplier_payment_repository_factory = supplier_payment_repository_factory
        self._supplier_payment_allocation_repository_factory = supplier_payment_allocation_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_supplier_payments(self, company_id: int, status_code: str | None = None) -> list[SupplierPaymentListItemDTO]:
        self._permission_service.require_permission("purchases.payments.view")
        normalized_status = self._normalize_optional_choice(status_code, _ALLOWED_STATUS_CODES, "Status code")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            payment_repo = self._require_payment_repository(uow.session)
            payments = payment_repo.list_by_company(company_id, status_code=normalized_status)
            return [self._to_list_item_dto(payment) for payment in payments]

    def list_supplier_payments_page(
        self,
        company_id: int,
        status_code: str | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> "PaginatedResult[SupplierPaymentListItemDTO]":
        """Paginated + searchable supplier-payment listing."""
        from seeker_accounting.shared.dto.paginated_result import (
            PaginatedResult,
            normalize_page,
            normalize_page_size,
        )

        self._permission_service.require_permission("purchases.payments.view")
        normalized_status = self._normalize_optional_choice(status_code, _ALLOWED_STATUS_CODES, "Status code")
        safe_page = normalize_page(page)
        safe_size = normalize_page_size(page_size)
        offset = (safe_page - 1) * safe_size

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            payment_repo = self._require_payment_repository(uow.session)
            total = payment_repo.count_filtered(
                company_id,
                status_code=normalized_status,
                query=query,
            )
            payments = payment_repo.list_filtered_page(
                company_id,
                status_code=normalized_status,
                query=query,
                limit=safe_size,
                offset=offset,
            )
            items = tuple(self._to_list_item_dto(p) for p in payments)

        return PaginatedResult(
            items=items,
            total_count=total,
            page=safe_page,
            page_size=safe_size,
        )

    def get_supplier_payment(self, company_id: int, payment_id: int) -> SupplierPaymentDetailDTO:
        self._permission_service.require_permission("purchases.payments.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            payment_repo = self._require_payment_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)

            payment = payment_repo.get_detail(company_id, payment_id)
            if payment is None:
                raise NotFoundError(f"Supplier payment with id {payment_id} was not found.")

            allocated_amount = alloc_repo.get_total_allocated_for_payment(company_id, payment.id)
            return self._to_detail_dto(payment, allocated_amount)

    def create_draft_payment(
        self,
        company_id: int,
        command: CreateSupplierPaymentCommand,
    ) -> SupplierPaymentDetailDTO:
        self._permission_service.require_permission("purchases.payments.create")
        normalized = self._normalize_create_command(command)
        if normalized.allocations:
            self._permission_service.require_permission("purchases.payments.allocate")

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            supplier_repo = self._require_supplier_repository(uow.session)
            fa_repo = self._require_financial_account_repository(uow.session)
            bill_repo = self._require_bill_repository(uow.session)
            payment_repo = self._require_payment_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)

            supplier = self._require_supplier(supplier_repo, company_id, normalized.supplier_id)
            financial_account = self._require_financial_account(fa_repo, company_id, normalized.financial_account_id)
            self._validate_currency(uow.session, company, normalized.currency_code)
            exchange_rate = self._normalize_exchange_rate(
                company_base_currency_code=company.base_currency_code,
                currency_code=normalized.currency_code,
                exchange_rate=normalized.exchange_rate,
            )

            self._validate_allocations(
                bill_repo=bill_repo,
                alloc_repo=alloc_repo,
                company_id=company_id,
                supplier_id=supplier.id,
                payment_currency_code=normalized.currency_code,
                amount_paid=normalized.amount_paid,
                allocations=normalized.allocations,
                exclude_payment_id=None,
            )

            payment = SupplierPayment(
                company_id=company_id,
                payment_number=f"{_DRAFT_NUMBER_PREFIX}{uuid4().hex[:12].upper()}",
                supplier_id=supplier.id,
                financial_account_id=financial_account.id,
                payment_date=normalized.payment_date,
                currency_code=normalized.currency_code,
                exchange_rate=exchange_rate,
                amount_paid=normalized.amount_paid,
                status_code="draft",
                reference_number=normalized.reference_number,
                notes=normalized.notes,
            )
            payment_repo.add(payment)
            uow.session.flush()
            payment.payment_number = self._format_draft_number(payment.id)
            payment_repo.save(payment)

            allocation_models = self._build_allocation_models(
                company_id=company_id,
                payment_id=payment.id,
                payment_date=normalized.payment_date,
                allocations=normalized.allocations,
            )
            alloc_repo.replace_allocations_for_payment(company_id, payment.id, allocation_models)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import SUPPLIER_PAYMENT_CREATED
            self._record_audit(company_id, SUPPLIER_PAYMENT_CREATED, "SupplierPayment", payment.id, "Created supplier payment")
            return self.get_supplier_payment(company_id, payment.id)

    def update_draft_payment(
        self,
        company_id: int,
        payment_id: int,
        command: UpdateSupplierPaymentCommand,
    ) -> SupplierPaymentDetailDTO:
        self._permission_service.require_permission("purchases.payments.edit")
        normalized = self._normalize_update_command(command)
        if normalized.allocations:
            self._permission_service.require_permission("purchases.payments.allocate")

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            supplier_repo = self._require_supplier_repository(uow.session)
            fa_repo = self._require_financial_account_repository(uow.session)
            bill_repo = self._require_bill_repository(uow.session)
            payment_repo = self._require_payment_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)

            payment = payment_repo.get_by_id(company_id, payment_id)
            if payment is None:
                raise NotFoundError(f"Supplier payment with id {payment_id} was not found.")
            if payment.status_code != "draft":
                raise ValidationError("Posted payments cannot be edited through the draft workflow.")

            supplier = self._require_supplier(supplier_repo, company_id, normalized.supplier_id)
            financial_account = self._require_financial_account(fa_repo, company_id, normalized.financial_account_id)
            self._validate_currency(uow.session, company, normalized.currency_code)
            exchange_rate = self._normalize_exchange_rate(
                company_base_currency_code=company.base_currency_code,
                currency_code=normalized.currency_code,
                exchange_rate=normalized.exchange_rate,
            )

            self._validate_allocations(
                bill_repo=bill_repo,
                alloc_repo=alloc_repo,
                company_id=company_id,
                supplier_id=supplier.id,
                payment_currency_code=normalized.currency_code,
                amount_paid=normalized.amount_paid,
                allocations=normalized.allocations,
                exclude_payment_id=payment.id,
            )

            payment.supplier_id = supplier.id
            payment.financial_account_id = financial_account.id
            payment.payment_date = normalized.payment_date
            payment.currency_code = normalized.currency_code
            payment.exchange_rate = exchange_rate
            payment.amount_paid = normalized.amount_paid
            payment.reference_number = normalized.reference_number
            payment.notes = normalized.notes
            payment_repo.save(payment)

            allocation_models = self._build_allocation_models(
                company_id=company_id,
                payment_id=payment.id,
                payment_date=normalized.payment_date,
                allocations=normalized.allocations,
            )
            alloc_repo.replace_allocations_for_payment(company_id, payment.id, allocation_models)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import SUPPLIER_PAYMENT_UPDATED
            self._record_audit(company_id, SUPPLIER_PAYMENT_UPDATED, "SupplierPayment", payment.id, "Updated supplier payment")
            return self.get_supplier_payment(company_id, payment.id)

    def cancel_draft_payment(self, company_id: int, payment_id: int) -> None:
        self._permission_service.require_permission("purchases.payments.cancel")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            payment_repo = self._require_payment_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)

            payment = payment_repo.get_by_id(company_id, payment_id)
            if payment is None:
                raise NotFoundError(f"Supplier payment with id {payment_id} was not found.")
            if payment.status_code != "draft":
                raise ValidationError("Posted payments cannot be cancelled through the draft workflow.")

            alloc_repo.replace_allocations_for_payment(company_id, payment.id, [])
            payment.status_code = "cancelled"
            payment_repo.save(payment)
            uow.commit()

    def list_allocatable_bills(
        self, company_id: int, supplier_id: int
    ) -> list[SupplierOpenBillDTO]:
        self._permission_service.require_permission("purchases.payments.allocate")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            supplier_repo = self._require_supplier_repository(uow.session)
            bill_repo = self._require_bill_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)

            self._require_supplier(supplier_repo, company_id, supplier_id)
            bills = [
                bill
                for bill in bill_repo.list_by_company(company_id, status_code="posted")
                if bill.supplier_id == supplier_id
            ]
            allocated_totals = alloc_repo.get_allocated_totals_for_bill_ids(
                company_id, [bill.id for bill in bills], posted_only=True
            )

            result: list[SupplierOpenBillDTO] = []
            for bill in bills:
                allocated = allocated_totals.get(bill.id, Decimal("0.00"))
                open_balance = self._quantize_money(bill.total_amount - allocated)
                if open_balance <= Decimal("0.00"):
                    continue
                result.append(
                    SupplierOpenBillDTO(
                        id=bill.id,
                        bill_number=bill.bill_number,
                        bill_date=bill.bill_date,
                        due_date=bill.due_date,
                        currency_code=bill.currency_code,
                        total_amount=bill.total_amount,
                        allocated_amount=allocated,
                        open_balance_amount=open_balance,
                        payment_status_code=bill.payment_status_code,
                    )
                )
            return result

    # ------------------------------------------------------------------
    # Allocation validation
    # ------------------------------------------------------------------

    def list_payments_for_bill(
        self, company_id: int, bill_id: int
    ) -> list[BillPaymentRowDTO]:
        """Return all payments that have an allocation applied to the given bill."""
        self._permission_service.require_permission("purchases.payments.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            alloc_repo = self._require_allocation_repository(uow.session)
            allocations = alloc_repo.list_for_bill(company_id, bill_id)
            return [self._to_bill_payment_row_dto(alloc) for alloc in allocations]

    def _to_bill_payment_row_dto(self, alloc: SupplierPaymentAllocation) -> BillPaymentRowDTO:
        p = alloc.supplier_payment
        fa = p.financial_account if p is not None else None
        return BillPaymentRowDTO(
            payment_id=p.id if p is not None else 0,
            payment_number=p.payment_number if p is not None else "",
            payment_date=p.payment_date if p is not None else alloc.allocation_date,
            financial_account_code=fa.account_code if fa is not None else "",
            financial_account_name=fa.name if fa is not None else "",
            currency_code=p.currency_code if p is not None else "",
            amount_paid=p.amount_paid if p is not None else Decimal("0.00"),
            allocated_to_bill=alloc.allocated_amount,
            status_code=p.status_code if p is not None else "",
        )

    def _validate_allocations(
        self,
        *,
        bill_repo: PurchaseBillRepository,
        alloc_repo: SupplierPaymentAllocationRepository,
        company_id: int,
        supplier_id: int,
        payment_currency_code: str,
        amount_paid: Decimal,
        allocations: tuple[SupplierPaymentAllocationCommand, ...],
        exclude_payment_id: int | None,
    ) -> None:
        if not allocations:
            return

        total_allocated = Decimal("0.00")
        bill_ids = [a.purchase_bill_id for a in allocations]
        if len(set(bill_ids)) != len(bill_ids):
            raise ValidationError("Duplicate bill allocations are not allowed.")

        posted_alloc_totals = alloc_repo.get_allocated_totals_for_bill_ids(
            company_id, bill_ids, posted_only=True
        )

        for alloc_cmd in allocations:
            if alloc_cmd.allocated_amount <= Decimal("0.00"):
                raise ValidationError("Allocation amounts must be greater than zero.")

            bill = bill_repo.get_by_id(company_id, alloc_cmd.purchase_bill_id)
            if bill is None:
                raise ValidationError(f"Bill with id {alloc_cmd.purchase_bill_id} was not found.")
            if bill.supplier_id != supplier_id:
                raise ValidationError("Allocated bills must belong to the same supplier.")
            if bill.status_code != "posted":
                raise ValidationError("Only posted bills can be allocated against.")
            if bill.currency_code != payment_currency_code:
                raise ValidationError(
                    "In this version, allocated bills and the payment must use the same currency."
                )

            already_allocated = posted_alloc_totals.get(bill.id, Decimal("0.00"))
            open_balance = self._quantize_money(bill.total_amount - already_allocated)
            if alloc_cmd.allocated_amount > open_balance:
                raise ValidationError(
                    f"Allocation of {alloc_cmd.allocated_amount} exceeds the open balance of {open_balance} "
                    f"on bill {bill.bill_number}."
                )

            total_allocated += alloc_cmd.allocated_amount

        if total_allocated > amount_paid:
            raise ValidationError("Total allocations cannot exceed the amount paid.")

    def _build_allocation_models(
        self,
        *,
        company_id: int,
        payment_id: int,
        payment_date: date,
        allocations: tuple[SupplierPaymentAllocationCommand, ...],
    ) -> list[SupplierPaymentAllocation]:
        models: list[SupplierPaymentAllocation] = []
        for alloc in allocations:
            models.append(
                SupplierPaymentAllocation(
                    company_id=company_id,
                    supplier_payment_id=payment_id,
                    purchase_bill_id=alloc.purchase_bill_id,
                    allocated_amount=self._quantize_money(alloc.allocated_amount),
                    allocation_date=payment_date,
                )
            )
        return models

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize_create_command(self, cmd: CreateSupplierPaymentCommand) -> CreateSupplierPaymentCommand:
        return CreateSupplierPaymentCommand(
            supplier_id=self._require_positive_id(cmd.supplier_id, "Supplier"),
            financial_account_id=self._require_positive_id(cmd.financial_account_id, "Financial account"),
            payment_date=self._require_date(cmd.payment_date, "Payment date"),
            currency_code=self._normalize_currency_code(cmd.currency_code),
            exchange_rate=self._normalize_optional_decimal(cmd.exchange_rate),
            amount_paid=self._require_positive_money(cmd.amount_paid, "Amount paid"),
            reference_number=self._normalize_optional_text(cmd.reference_number),
            notes=self._normalize_optional_text(cmd.notes),
            allocations=cmd.allocations,
        )

    def _normalize_update_command(self, cmd: UpdateSupplierPaymentCommand) -> UpdateSupplierPaymentCommand:
        return UpdateSupplierPaymentCommand(
            supplier_id=self._require_positive_id(cmd.supplier_id, "Supplier"),
            financial_account_id=self._require_positive_id(cmd.financial_account_id, "Financial account"),
            payment_date=self._require_date(cmd.payment_date, "Payment date"),
            currency_code=self._normalize_currency_code(cmd.currency_code),
            exchange_rate=self._normalize_optional_decimal(cmd.exchange_rate),
            amount_paid=self._require_positive_money(cmd.amount_paid, "Amount paid"),
            reference_number=self._normalize_optional_text(cmd.reference_number),
            notes=self._normalize_optional_text(cmd.notes),
            allocations=cmd.allocations,
        )

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _require_company_exists(self, session: Session | None, company_id: int):
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        company = repo.get_by_id(company_id)
        if company is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")
        return company

    def _require_supplier(
        self, supplier_repo: SupplierRepository, company_id: int, supplier_id: int
    ) -> Supplier:
        supplier = supplier_repo.get_by_id(company_id, supplier_id)
        if supplier is None:
            raise ValidationError("Supplier must belong to the active company.")
        return supplier

    def _require_financial_account(
        self, fa_repo: FinancialAccountRepository, company_id: int, financial_account_id: int
    ) -> FinancialAccount:
        fa = fa_repo.get_by_id(company_id, financial_account_id)
        if fa is None:
            raise ValidationError("Financial account must belong to the active company.")
        if not fa.is_active:
            raise ValidationError("Financial account must be active.")
        return fa

    def _validate_currency(self, session: Session, company: object, currency_code: str) -> None:
        currency = session.get(Currency, currency_code)
        if currency is None:
            raise ValidationError("Currency must exist in the reference data.")
        company_base = getattr(company, "base_currency_code", None)
        if company_base != currency_code and not currency.is_active:
            raise ValidationError("Currency must reference an active currency code.")

    # ------------------------------------------------------------------
    # Repository factories
    # ------------------------------------------------------------------

    def _require_supplier_repository(self, session: Session | None) -> SupplierRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._supplier_repository_factory(session)

    def _require_financial_account_repository(self, session: Session | None) -> FinancialAccountRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._financial_account_repository_factory(session)

    def _require_bill_repository(self, session: Session | None) -> PurchaseBillRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._purchase_bill_repository_factory(session)

    def _require_payment_repository(self, session: Session | None) -> SupplierPaymentRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._supplier_payment_repository_factory(session)

    def _require_allocation_repository(self, session: Session | None) -> SupplierPaymentAllocationRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._supplier_payment_allocation_repository_factory(session)

    # ------------------------------------------------------------------
    # Scalar helpers
    # ------------------------------------------------------------------

    def _normalize_currency_code(self, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValidationError("Currency code is required.")
        return normalized

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def _normalize_optional_decimal(self, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value <= Decimal("0"):
            raise ValidationError("Exchange rate must be greater than zero.")
        return self._quantize_rate(value)

    def _require_positive_money(self, value: Decimal, label: str) -> Decimal:
        if value <= Decimal("0"):
            raise ValidationError(f"{label} must be greater than zero.")
        return self._quantize_money(value)

    def _require_date(self, value: date, label: str) -> date:
        if value is None:
            raise ValidationError(f"{label} is required.")
        return value

    def _require_positive_id(self, value: int, label: str) -> int:
        if value <= 0:
            raise ValidationError(f"{label} is required.")
        return value

    def _normalize_exchange_rate(
        self,
        *,
        company_base_currency_code: str,
        currency_code: str,
        exchange_rate: Decimal | None,
    ) -> Decimal | None:
        if currency_code == company_base_currency_code:
            return None
        if exchange_rate is None or exchange_rate <= Decimal("0"):
            raise ValidationError(
                "Exchange rate is required when the payment currency differs from the company base currency."
            )
        return self._quantize_rate(exchange_rate)

    def _normalize_optional_choice(
        self, value: str | None, allowed_values: set[str], label: str
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        if normalized not in allowed_values:
            raise ValidationError(f"{label} is not recognized.")
        return normalized

    def _format_draft_number(self, payment_id: int) -> str:
        return f"{_DRAFT_NUMBER_PREFIX}{payment_id:06d}"

    def _quantize_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)

    def _quantize_rate(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0000"), rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------
    # Error translation
    # ------------------------------------------------------------------

    def _translate_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "payment_number" in message:
            return ConflictError("A supplier payment with this number already exists.")
        return ValidationError("Supplier payment data could not be saved.")

    # ------------------------------------------------------------------
    # DTO mapping
    # ------------------------------------------------------------------

    def _to_list_item_dto(self, payment: SupplierPayment) -> SupplierPaymentListItemDTO:
        supplier = payment.supplier
        fa = payment.financial_account
        return SupplierPaymentListItemDTO(
            id=payment.id,
            company_id=payment.company_id,
            payment_number=payment.payment_number,
            supplier_id=payment.supplier_id,
            supplier_code=supplier.supplier_code if supplier is not None else "",
            supplier_name=supplier.display_name if supplier is not None else "",
            financial_account_id=payment.financial_account_id,
            financial_account_code=fa.account_code if fa is not None else "",
            financial_account_name=fa.name if fa is not None else "",
            payment_date=payment.payment_date,
            currency_code=payment.currency_code,
            amount_paid=payment.amount_paid,
            status_code=payment.status_code,
            posted_at=payment.posted_at,
            updated_at=payment.updated_at,
        )

    def _to_detail_dto(
        self, payment: SupplierPayment, allocated_amount: Decimal
    ) -> SupplierPaymentDetailDTO:
        supplier = payment.supplier
        fa = payment.financial_account
        alloc_dtos = tuple(
            SupplierPaymentAllocationDTO(
                id=a.id,
                company_id=a.company_id,
                supplier_payment_id=a.supplier_payment_id,
                purchase_bill_id=a.purchase_bill_id,
                purchase_bill_number=a.purchase_bill.bill_number if a.purchase_bill is not None else "",
                purchase_bill_date=a.purchase_bill.bill_date if a.purchase_bill is not None else a.allocation_date,
                purchase_bill_due_date=a.purchase_bill.due_date if a.purchase_bill is not None else a.allocation_date,
                bill_currency_code=a.purchase_bill.currency_code if a.purchase_bill is not None else "",
                bill_total_amount=a.purchase_bill.total_amount if a.purchase_bill is not None else Decimal("0.00"),
                allocated_amount=a.allocated_amount,
                allocation_date=a.allocation_date,
                created_at=a.created_at,
            )
            for a in sorted(payment.allocations, key=lambda x: (x.allocation_date, x.id))
        )
        remaining = self._quantize_money(payment.amount_paid - allocated_amount)
        if remaining < Decimal("0.00"):
            remaining = Decimal("0.00")
        return SupplierPaymentDetailDTO(
            id=payment.id,
            company_id=payment.company_id,
            payment_number=payment.payment_number,
            supplier_id=payment.supplier_id,
            supplier_code=supplier.supplier_code if supplier is not None else "",
            supplier_name=supplier.display_name if supplier is not None else "",
            financial_account_id=payment.financial_account_id,
            financial_account_code=fa.account_code if fa is not None else "",
            financial_account_name=fa.name if fa is not None else "",
            payment_date=payment.payment_date,
            currency_code=payment.currency_code,
            exchange_rate=payment.exchange_rate,
            amount_paid=payment.amount_paid,
            status_code=payment.status_code,
            reference_number=payment.reference_number,
            notes=payment.notes,
            posted_journal_entry_id=payment.posted_journal_entry_id,
            posted_at=payment.posted_at,
            posted_by_user_id=payment.posted_by_user_id,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
            allocated_amount=allocated_amount,
            remaining_unallocated_amount=remaining,
            allocations=alloc_dtos,
        )

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
