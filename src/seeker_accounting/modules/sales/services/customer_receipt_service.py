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
from seeker_accounting.modules.customers.models.customer import Customer
from seeker_accounting.modules.customers.repositories.customer_repository import CustomerRepository
from seeker_accounting.modules.sales.dto.customer_receipt_commands import (
    CreateCustomerReceiptCommand,
    CustomerReceiptAllocationCommand,
    UpdateCustomerReceiptCommand,
)
from seeker_accounting.modules.sales.dto.customer_receipt_dto import (
    CustomerOpenInvoiceDTO,
    CustomerReceiptAllocationDTO,
    CustomerReceiptDetailDTO,
    CustomerReceiptListItemDTO,
    InvoiceReceiptRowDTO,
)
from seeker_accounting.modules.sales.models.customer_receipt import CustomerReceipt
from seeker_accounting.modules.sales.models.customer_receipt_allocation import CustomerReceiptAllocation
from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice
from seeker_accounting.modules.sales.repositories.customer_receipt_allocation_repository import (
    CustomerReceiptAllocationRepository,
)
from seeker_accounting.modules.sales.repositories.customer_receipt_repository import CustomerReceiptRepository
from seeker_accounting.modules.sales.repositories.sales_invoice_repository import SalesInvoiceRepository
from seeker_accounting.modules.treasury.models.financial_account import FinancialAccount
from seeker_accounting.modules.treasury.repositories.financial_account_repository import FinancialAccountRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CustomerRepositoryFactory = Callable[[Session], CustomerRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]
FinancialAccountRepositoryFactory = Callable[[Session], FinancialAccountRepository]
SalesInvoiceRepositoryFactory = Callable[[Session], SalesInvoiceRepository]
CustomerReceiptRepositoryFactory = Callable[[Session], CustomerReceiptRepository]
CustomerReceiptAllocationRepositoryFactory = Callable[[Session], CustomerReceiptAllocationRepository]

_DRAFT_NUMBER_PREFIX = "CR-DRAFT-"
_ALLOWED_STATUS_CODES = {"draft", "posted", "cancelled"}


class CustomerReceiptService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        customer_repository_factory: CustomerRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        financial_account_repository_factory: FinancialAccountRepositoryFactory,
        sales_invoice_repository_factory: SalesInvoiceRepositoryFactory,
        customer_receipt_repository_factory: CustomerReceiptRepositoryFactory,
        customer_receipt_allocation_repository_factory: CustomerReceiptAllocationRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._customer_repository_factory = customer_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._financial_account_repository_factory = financial_account_repository_factory
        self._sales_invoice_repository_factory = sales_invoice_repository_factory
        self._customer_receipt_repository_factory = customer_receipt_repository_factory
        self._customer_receipt_allocation_repository_factory = customer_receipt_allocation_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_customer_receipts(
        self, company_id: int, status_code: str | None = None
    ) -> list[CustomerReceiptListItemDTO]:
        self._permission_service.require_permission("sales.receipts.view")
        normalized_status = self._normalize_optional_choice(status_code, _ALLOWED_STATUS_CODES, "Status code")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            receipt_repo = self._require_receipt_repository(uow.session)
            receipts = receipt_repo.list_by_company(company_id, status_code=normalized_status)
            return [self._to_list_item_dto(receipt) for receipt in receipts]

    def get_customer_receipt(self, company_id: int, receipt_id: int) -> CustomerReceiptDetailDTO:
        self._permission_service.require_permission("sales.receipts.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            receipt_repo = self._require_receipt_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)

            receipt = receipt_repo.get_detail(company_id, receipt_id)
            if receipt is None:
                raise NotFoundError(f"Customer receipt with id {receipt_id} was not found.")

            allocated_amount = alloc_repo.get_total_allocated_for_receipt(company_id, receipt.id)
            return self._to_detail_dto(receipt, allocated_amount)

    def create_draft_receipt(
        self,
        company_id: int,
        command: CreateCustomerReceiptCommand,
    ) -> CustomerReceiptDetailDTO:
        self._permission_service.require_permission("sales.receipts.create")
        normalized = self._normalize_create_command(command)
        if normalized.allocations:
            self._permission_service.require_permission("sales.receipts.allocate")

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            customer_repo = self._require_customer_repository(uow.session)
            fa_repo = self._require_financial_account_repository(uow.session)
            invoice_repo = self._require_invoice_repository(uow.session)
            receipt_repo = self._require_receipt_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)

            customer = self._require_customer(customer_repo, company_id, normalized.customer_id)
            financial_account = self._require_financial_account(fa_repo, company_id, normalized.financial_account_id)
            self._validate_currency(uow.session, company, normalized.currency_code)
            exchange_rate = self._normalize_exchange_rate(
                company_base_currency_code=company.base_currency_code,
                currency_code=normalized.currency_code,
                exchange_rate=normalized.exchange_rate,
            )

            self._validate_allocations(
                invoice_repo=invoice_repo,
                alloc_repo=alloc_repo,
                company_id=company_id,
                customer_id=customer.id,
                receipt_currency_code=normalized.currency_code,
                amount_received=normalized.amount_received,
                allocations=normalized.allocations,
                exclude_receipt_id=None,
            )

            receipt = CustomerReceipt(
                company_id=company_id,
                receipt_number=f"{_DRAFT_NUMBER_PREFIX}{uuid4().hex[:12].upper()}",
                customer_id=customer.id,
                financial_account_id=financial_account.id,
                receipt_date=normalized.receipt_date,
                currency_code=normalized.currency_code,
                exchange_rate=exchange_rate,
                amount_received=normalized.amount_received,
                status_code="draft",
                reference_number=normalized.reference_number,
                notes=normalized.notes,
            )
            receipt_repo.add(receipt)
            uow.session.flush()
            receipt.receipt_number = self._format_draft_number(receipt.id)
            receipt_repo.save(receipt)

            allocation_models = self._build_allocation_models(
                company_id=company_id,
                receipt_id=receipt.id,
                receipt_date=normalized.receipt_date,
                allocations=normalized.allocations,
            )
            alloc_repo.replace_allocations_for_receipt(company_id, receipt.id, allocation_models)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import CUSTOMER_RECEIPT_CREATED
            self._record_audit(company_id, CUSTOMER_RECEIPT_CREATED, "CustomerReceipt", receipt.id, "Created customer receipt")
            return self.get_customer_receipt(company_id, receipt.id)

    def update_draft_receipt(
        self,
        company_id: int,
        receipt_id: int,
        command: UpdateCustomerReceiptCommand,
    ) -> CustomerReceiptDetailDTO:
        self._permission_service.require_permission("sales.receipts.edit")
        normalized = self._normalize_update_command(command)
        if normalized.allocations:
            self._permission_service.require_permission("sales.receipts.allocate")

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            customer_repo = self._require_customer_repository(uow.session)
            fa_repo = self._require_financial_account_repository(uow.session)
            invoice_repo = self._require_invoice_repository(uow.session)
            receipt_repo = self._require_receipt_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)

            receipt = receipt_repo.get_by_id(company_id, receipt_id)
            if receipt is None:
                raise NotFoundError(f"Customer receipt with id {receipt_id} was not found.")
            if receipt.status_code != "draft":
                raise ValidationError("Posted receipts cannot be edited through the draft workflow.")

            customer = self._require_customer(customer_repo, company_id, normalized.customer_id)
            financial_account = self._require_financial_account(fa_repo, company_id, normalized.financial_account_id)
            self._validate_currency(uow.session, company, normalized.currency_code)
            exchange_rate = self._normalize_exchange_rate(
                company_base_currency_code=company.base_currency_code,
                currency_code=normalized.currency_code,
                exchange_rate=normalized.exchange_rate,
            )

            self._validate_allocations(
                invoice_repo=invoice_repo,
                alloc_repo=alloc_repo,
                company_id=company_id,
                customer_id=customer.id,
                receipt_currency_code=normalized.currency_code,
                amount_received=normalized.amount_received,
                allocations=normalized.allocations,
                exclude_receipt_id=receipt.id,
            )

            receipt.customer_id = customer.id
            receipt.financial_account_id = financial_account.id
            receipt.receipt_date = normalized.receipt_date
            receipt.currency_code = normalized.currency_code
            receipt.exchange_rate = exchange_rate
            receipt.amount_received = normalized.amount_received
            receipt.reference_number = normalized.reference_number
            receipt.notes = normalized.notes
            receipt_repo.save(receipt)

            allocation_models = self._build_allocation_models(
                company_id=company_id,
                receipt_id=receipt.id,
                receipt_date=normalized.receipt_date,
                allocations=normalized.allocations,
            )
            alloc_repo.replace_allocations_for_receipt(company_id, receipt.id, allocation_models)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import CUSTOMER_RECEIPT_UPDATED
            self._record_audit(company_id, CUSTOMER_RECEIPT_UPDATED, "CustomerReceipt", receipt.id, "Updated customer receipt")
            return self.get_customer_receipt(company_id, receipt.id)

    def cancel_draft_receipt(self, company_id: int, receipt_id: int) -> None:
        self._permission_service.require_permission("sales.receipts.cancel")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            receipt_repo = self._require_receipt_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)

            receipt = receipt_repo.get_by_id(company_id, receipt_id)
            if receipt is None:
                raise NotFoundError(f"Customer receipt with id {receipt_id} was not found.")
            if receipt.status_code != "draft":
                raise ValidationError("Posted receipts cannot be cancelled through the draft workflow.")

            alloc_repo.replace_allocations_for_receipt(company_id, receipt.id, [])
            receipt.status_code = "cancelled"
            receipt_repo.save(receipt)
            uow.commit()

    def list_allocatable_invoices(
        self, company_id: int, customer_id: int
    ) -> list[CustomerOpenInvoiceDTO]:
        self._permission_service.require_permission("sales.receipts.allocate")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            customer_repo = self._require_customer_repository(uow.session)
            invoice_repo = self._require_invoice_repository(uow.session)
            alloc_repo = self._require_allocation_repository(uow.session)

            self._require_customer(customer_repo, company_id, customer_id)
            invoices = [
                inv
                for inv in invoice_repo.list_by_company(company_id, status_code="posted")
                if inv.customer_id == customer_id
            ]
            allocated_totals = alloc_repo.get_allocated_totals_for_invoice_ids(
                company_id, [inv.id for inv in invoices], posted_only=True
            )

            result: list[CustomerOpenInvoiceDTO] = []
            for inv in invoices:
                allocated = allocated_totals.get(inv.id, Decimal("0.00"))
                open_balance = self._quantize_money(inv.total_amount - allocated)
                if open_balance <= Decimal("0.00"):
                    continue
                result.append(
                    CustomerOpenInvoiceDTO(
                        id=inv.id,
                        invoice_number=inv.invoice_number,
                        invoice_date=inv.invoice_date,
                        due_date=inv.due_date,
                        currency_code=inv.currency_code,
                        total_amount=inv.total_amount,
                        allocated_amount=allocated,
                        open_balance_amount=open_balance,
                        payment_status_code=inv.payment_status_code,
                    )
                )
            return result

    # ------------------------------------------------------------------
    # Allocation validation
    # ------------------------------------------------------------------

    def list_receipts_for_invoice(
        self, company_id: int, invoice_id: int
    ) -> list[InvoiceReceiptRowDTO]:
        """Return all receipts that have an allocation applied to the given invoice."""
        self._permission_service.require_permission("sales.receipts.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            alloc_repo = self._require_allocation_repository(uow.session)
            allocations = alloc_repo.list_for_invoice(company_id, invoice_id)
            return [self._to_invoice_receipt_row_dto(alloc) for alloc in allocations]

    def _to_invoice_receipt_row_dto(self, alloc: CustomerReceiptAllocation) -> InvoiceReceiptRowDTO:
        r = alloc.customer_receipt
        fa = r.financial_account if r is not None else None
        return InvoiceReceiptRowDTO(
            receipt_id=r.id if r is not None else 0,
            receipt_number=r.receipt_number if r is not None else "",
            receipt_date=r.receipt_date if r is not None else alloc.allocation_date,
            financial_account_code=fa.account_code if fa is not None else "",
            financial_account_name=fa.name if fa is not None else "",
            currency_code=r.currency_code if r is not None else "",
            amount_received=r.amount_received if r is not None else Decimal("0.00"),
            allocated_to_invoice=alloc.allocated_amount,
            status_code=r.status_code if r is not None else "",
        )

    def _validate_allocations(
        self,
        *,
        invoice_repo: SalesInvoiceRepository,
        alloc_repo: CustomerReceiptAllocationRepository,
        company_id: int,
        customer_id: int,
        receipt_currency_code: str,
        amount_received: Decimal,
        allocations: tuple[CustomerReceiptAllocationCommand, ...],
        exclude_receipt_id: int | None,
    ) -> None:
        if not allocations:
            return

        total_allocated = Decimal("0.00")
        invoice_ids = [a.sales_invoice_id for a in allocations]
        if len(set(invoice_ids)) != len(invoice_ids):
            raise ValidationError("Duplicate invoice allocations are not allowed.")

        posted_alloc_totals = alloc_repo.get_allocated_totals_for_invoice_ids(
            company_id, invoice_ids, posted_only=True
        )

        for alloc_cmd in allocations:
            if alloc_cmd.allocated_amount <= Decimal("0.00"):
                raise ValidationError("Allocation amounts must be greater than zero.")

            invoice = invoice_repo.get_by_id(company_id, alloc_cmd.sales_invoice_id)
            if invoice is None:
                raise ValidationError(f"Invoice with id {alloc_cmd.sales_invoice_id} was not found.")
            if invoice.customer_id != customer_id:
                raise ValidationError("Allocated invoices must belong to the same customer.")
            if invoice.status_code != "posted":
                raise ValidationError("Only posted invoices can be allocated against.")
            if invoice.currency_code != receipt_currency_code:
                raise ValidationError(
                    "In this version, allocated invoices and the receipt must use the same currency."
                )

            already_allocated = posted_alloc_totals.get(invoice.id, Decimal("0.00"))
            open_balance = self._quantize_money(invoice.total_amount - already_allocated)
            if alloc_cmd.allocated_amount > open_balance:
                raise ValidationError(
                    f"Allocation of {alloc_cmd.allocated_amount} exceeds the open balance of {open_balance} "
                    f"on invoice {invoice.invoice_number}."
                )

            total_allocated += alloc_cmd.allocated_amount

        if total_allocated > amount_received:
            raise ValidationError("Total allocations cannot exceed the amount received.")

    def _build_allocation_models(
        self,
        *,
        company_id: int,
        receipt_id: int,
        receipt_date: date,
        allocations: tuple[CustomerReceiptAllocationCommand, ...],
    ) -> list[CustomerReceiptAllocation]:
        models: list[CustomerReceiptAllocation] = []
        for alloc in allocations:
            models.append(
                CustomerReceiptAllocation(
                    company_id=company_id,
                    customer_receipt_id=receipt_id,
                    sales_invoice_id=alloc.sales_invoice_id,
                    allocated_amount=self._quantize_money(alloc.allocated_amount),
                    allocation_date=receipt_date,
                )
            )
        return models

    # ------------------------------------------------------------------
    # Normalization helpers
    # ------------------------------------------------------------------

    def _normalize_create_command(self, cmd: CreateCustomerReceiptCommand) -> CreateCustomerReceiptCommand:
        return CreateCustomerReceiptCommand(
            customer_id=self._require_positive_id(cmd.customer_id, "Customer"),
            financial_account_id=self._require_positive_id(cmd.financial_account_id, "Financial account"),
            receipt_date=self._require_date(cmd.receipt_date, "Receipt date"),
            currency_code=self._normalize_currency_code(cmd.currency_code),
            exchange_rate=self._normalize_optional_decimal(cmd.exchange_rate),
            amount_received=self._require_positive_money(cmd.amount_received, "Amount received"),
            reference_number=self._normalize_optional_text(cmd.reference_number),
            notes=self._normalize_optional_text(cmd.notes),
            allocations=cmd.allocations,
        )

    def _normalize_update_command(self, cmd: UpdateCustomerReceiptCommand) -> UpdateCustomerReceiptCommand:
        return UpdateCustomerReceiptCommand(
            customer_id=self._require_positive_id(cmd.customer_id, "Customer"),
            financial_account_id=self._require_positive_id(cmd.financial_account_id, "Financial account"),
            receipt_date=self._require_date(cmd.receipt_date, "Receipt date"),
            currency_code=self._normalize_currency_code(cmd.currency_code),
            exchange_rate=self._normalize_optional_decimal(cmd.exchange_rate),
            amount_received=self._require_positive_money(cmd.amount_received, "Amount received"),
            reference_number=self._normalize_optional_text(cmd.reference_number),
            notes=self._normalize_optional_text(cmd.notes),
            allocations=cmd.allocations,
        )

    # ------------------------------------------------------------------
    # Entity validation helpers
    # ------------------------------------------------------------------

    def _require_company_exists(self, session: Session | None, company_id: int):
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        company = repo.get_by_id(company_id)
        if company is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")
        return company

    def _require_customer(
        self, customer_repo: CustomerRepository, company_id: int, customer_id: int
    ) -> Customer:
        customer = customer_repo.get_by_id(company_id, customer_id)
        if customer is None:
            raise ValidationError("Customer must belong to the active company.")
        return customer

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
    # Repository factory helpers
    # ------------------------------------------------------------------

    def _require_customer_repository(self, session: Session | None) -> CustomerRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._customer_repository_factory(session)

    def _require_financial_account_repository(self, session: Session | None) -> FinancialAccountRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._financial_account_repository_factory(session)

    def _require_invoice_repository(self, session: Session | None) -> SalesInvoiceRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._sales_invoice_repository_factory(session)

    def _require_receipt_repository(self, session: Session | None) -> CustomerReceiptRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._customer_receipt_repository_factory(session)

    def _require_allocation_repository(self, session: Session | None) -> CustomerReceiptAllocationRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._customer_receipt_allocation_repository_factory(session)

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
                "Exchange rate is required when the receipt currency differs from the company base currency."
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

    def _format_draft_number(self, receipt_id: int) -> str:
        return f"{_DRAFT_NUMBER_PREFIX}{receipt_id:06d}"

    def _quantize_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)

    def _quantize_rate(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0000"), rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------
    # Error translation
    # ------------------------------------------------------------------

    def _translate_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "receipt_number" in message:
            return ConflictError("A customer receipt with this number already exists.")
        return ValidationError("Customer receipt data could not be saved.")

    # ------------------------------------------------------------------
    # DTO mapping
    # ------------------------------------------------------------------

    def _to_list_item_dto(self, receipt: CustomerReceipt) -> CustomerReceiptListItemDTO:
        customer = receipt.customer
        fa = receipt.financial_account
        return CustomerReceiptListItemDTO(
            id=receipt.id,
            company_id=receipt.company_id,
            receipt_number=receipt.receipt_number,
            customer_id=receipt.customer_id,
            customer_code=customer.customer_code if customer is not None else "",
            customer_name=customer.display_name if customer is not None else "",
            financial_account_id=receipt.financial_account_id,
            financial_account_code=fa.account_code if fa is not None else "",
            financial_account_name=fa.name if fa is not None else "",
            receipt_date=receipt.receipt_date,
            currency_code=receipt.currency_code,
            amount_received=receipt.amount_received,
            status_code=receipt.status_code,
            posted_at=receipt.posted_at,
            updated_at=receipt.updated_at,
        )

    def _to_detail_dto(
        self, receipt: CustomerReceipt, allocated_amount: Decimal
    ) -> CustomerReceiptDetailDTO:
        customer = receipt.customer
        fa = receipt.financial_account
        alloc_dtos = tuple(
            CustomerReceiptAllocationDTO(
                id=a.id,
                company_id=a.company_id,
                customer_receipt_id=a.customer_receipt_id,
                sales_invoice_id=a.sales_invoice_id,
                sales_invoice_number=a.sales_invoice.invoice_number if a.sales_invoice is not None else "",
                sales_invoice_date=a.sales_invoice.invoice_date if a.sales_invoice is not None else a.allocation_date,
                sales_invoice_due_date=a.sales_invoice.due_date if a.sales_invoice is not None else a.allocation_date,
                invoice_currency_code=a.sales_invoice.currency_code if a.sales_invoice is not None else "",
                invoice_total_amount=a.sales_invoice.total_amount if a.sales_invoice is not None else Decimal("0.00"),
                allocated_amount=a.allocated_amount,
                allocation_date=a.allocation_date,
                created_at=a.created_at,
            )
            for a in sorted(receipt.allocations, key=lambda x: (x.allocation_date, x.id))
        )
        remaining = self._quantize_money(receipt.amount_received - allocated_amount)
        if remaining < Decimal("0.00"):
            remaining = Decimal("0.00")
        return CustomerReceiptDetailDTO(
            id=receipt.id,
            company_id=receipt.company_id,
            receipt_number=receipt.receipt_number,
            customer_id=receipt.customer_id,
            customer_code=customer.customer_code if customer is not None else "",
            customer_name=customer.display_name if customer is not None else "",
            financial_account_id=receipt.financial_account_id,
            financial_account_code=fa.account_code if fa is not None else "",
            financial_account_name=fa.name if fa is not None else "",
            receipt_date=receipt.receipt_date,
            currency_code=receipt.currency_code,
            exchange_rate=receipt.exchange_rate,
            amount_received=receipt.amount_received,
            status_code=receipt.status_code,
            reference_number=receipt.reference_number,
            notes=receipt.notes,
            posted_journal_entry_id=receipt.posted_journal_entry_id,
            posted_at=receipt.posted_at,
            posted_by_user_id=receipt.posted_by_user_id,
            created_at=receipt.created_at,
            updated_at=receipt.updated_at,
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
