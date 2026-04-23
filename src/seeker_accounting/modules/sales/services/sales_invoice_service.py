from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Callable
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import AccountRepository
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.accounting.reference_data.models.tax_code import TaxCode
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository
from seeker_accounting.modules.accounting.reference_data.repositories.tax_code_repository import TaxCodeRepository
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.customers.models.customer import Customer
from seeker_accounting.modules.customers.repositories.customer_repository import CustomerRepository
from seeker_accounting.modules.job_costing.services.project_dimension_validation_service import (
    ProjectDimensionValidationService,
)
from seeker_accounting.modules.sales.dto.customer_receipt_dto import CustomerOpenInvoiceDTO
from seeker_accounting.modules.sales.dto.sales_invoice_commands import (
    CreateSalesInvoiceCommand,
    SalesInvoiceLineCommand,
    UpdateSalesInvoiceCommand,
)
from seeker_accounting.modules.sales.dto.sales_invoice_dto import (
    SalesInvoiceDetailDTO,
    SalesInvoiceLineDTO,
    SalesInvoiceListItemDTO,
    SalesInvoiceTotalsDTO,
)
from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice
from seeker_accounting.modules.sales.models.sales_invoice_line import SalesInvoiceLine
from seeker_accounting.modules.sales.repositories.customer_receipt_allocation_repository import (
    CustomerReceiptAllocationRepository,
)
from seeker_accounting.modules.sales.repositories.sales_invoice_line_repository import SalesInvoiceLineRepository
from seeker_accounting.modules.sales.repositories.sales_invoice_repository import SalesInvoiceRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CustomerRepositoryFactory = Callable[[Session], CustomerRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
TaxCodeRepositoryFactory = Callable[[Session], TaxCodeRepository]
SalesInvoiceRepositoryFactory = Callable[[Session], SalesInvoiceRepository]
SalesInvoiceLineRepositoryFactory = Callable[[Session], SalesInvoiceLineRepository]
CustomerReceiptAllocationRepositoryFactory = Callable[[Session], CustomerReceiptAllocationRepository]

_DRAFT_NUMBER_PREFIX = "SI-DRAFT-"
_ALLOWED_STATUS_CODES = {"draft", "posted", "cancelled"}
_ALLOWED_PAYMENT_STATUS_CODES = {"unpaid", "partial", "paid"}


class SalesInvoiceService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        customer_repository_factory: CustomerRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        tax_code_repository_factory: TaxCodeRepositoryFactory,
        sales_invoice_repository_factory: SalesInvoiceRepositoryFactory,
        sales_invoice_line_repository_factory: SalesInvoiceLineRepositoryFactory,
        customer_receipt_allocation_repository_factory: CustomerReceiptAllocationRepositoryFactory,
        project_dimension_validation_service: ProjectDimensionValidationService,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._customer_repository_factory = customer_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._account_repository_factory = account_repository_factory
        self._tax_code_repository_factory = tax_code_repository_factory
        self._sales_invoice_repository_factory = sales_invoice_repository_factory
        self._sales_invoice_line_repository_factory = sales_invoice_line_repository_factory
        self._customer_receipt_allocation_repository_factory = customer_receipt_allocation_repository_factory
        self._project_dimension_validation_service = project_dimension_validation_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_sales_invoices(
        self,
        company_id: int,
        status_code: str | None = None,
        payment_status_code: str | None = None,
    ) -> list[SalesInvoiceListItemDTO]:
        self._permission_service.require_permission("sales.invoices.view")
        normalized_status = self._normalize_optional_choice(status_code, _ALLOWED_STATUS_CODES, "Status code")
        normalized_payment_status = self._normalize_optional_choice(
            payment_status_code,
            _ALLOWED_PAYMENT_STATUS_CODES,
            "Payment status code",
        )

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            repository = self._require_sales_invoice_repository(uow.session)
            allocation_repository = self._require_allocation_repository(uow.session)

            invoices = repository.list_by_company(
                company_id,
                status_code=normalized_status,
                payment_status_code=normalized_payment_status,
            )
            allocated_totals = allocation_repository.get_allocated_totals_for_invoice_ids(
                company_id,
                [invoice.id for invoice in invoices if invoice.status_code == "posted"],
                posted_only=True,
            )
            return [
                self._to_list_item_dto(
                    invoice=invoice,
                    company_base_currency_code=company.base_currency_code,
                    allocated_amount=allocated_totals.get(invoice.id, Decimal("0.00")),
                    open_balance_amount=self._calculate_open_balance(
                        invoice,
                        allocated_totals.get(invoice.id, Decimal("0.00")),
                    ),
                )
                for invoice in invoices
            ]

    def list_sales_invoices_page(
        self,
        company_id: int,
        status_code: str | None = None,
        payment_status_code: str | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> "PaginatedResult[SalesInvoiceListItemDTO]":
        """Paginated + searchable sales invoice listing.

        Allocations are fetched only for the current page's posted invoices,
        which keeps register paging cheap even on large AR books.
        """
        from seeker_accounting.shared.dto.paginated_result import (
            PaginatedResult,
            normalize_page,
            normalize_page_size,
        )

        self._permission_service.require_permission("sales.invoices.view")
        normalized_status = self._normalize_optional_choice(status_code, _ALLOWED_STATUS_CODES, "Status code")
        normalized_payment_status = self._normalize_optional_choice(
            payment_status_code,
            _ALLOWED_PAYMENT_STATUS_CODES,
            "Payment status code",
        )
        safe_page = normalize_page(page)
        safe_size = normalize_page_size(page_size)
        offset = (safe_page - 1) * safe_size

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            repository = self._require_sales_invoice_repository(uow.session)
            allocation_repository = self._require_allocation_repository(uow.session)

            total = repository.count_filtered(
                company_id,
                status_code=normalized_status,
                payment_status_code=normalized_payment_status,
                query=query,
            )
            invoices = repository.list_filtered_page(
                company_id,
                status_code=normalized_status,
                payment_status_code=normalized_payment_status,
                query=query,
                limit=safe_size,
                offset=offset,
            )
            allocated_totals = allocation_repository.get_allocated_totals_for_invoice_ids(
                company_id,
                [invoice.id for invoice in invoices if invoice.status_code == "posted"],
                posted_only=True,
            )
            items = tuple(
                self._to_list_item_dto(
                    invoice=invoice,
                    company_base_currency_code=company.base_currency_code,
                    allocated_amount=allocated_totals.get(invoice.id, Decimal("0.00")),
                    open_balance_amount=self._calculate_open_balance(
                        invoice,
                        allocated_totals.get(invoice.id, Decimal("0.00")),
                    ),
                )
                for invoice in invoices
            )

        return PaginatedResult(
            items=items,
            total_count=total,
            page=safe_page,
            page_size=safe_size,
        )

    def get_sales_invoice(self, company_id: int, invoice_id: int) -> SalesInvoiceDetailDTO:
        self._permission_service.require_permission("sales.invoices.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_sales_invoice_repository(uow.session)
            allocation_repository = self._require_allocation_repository(uow.session)

            invoice = repository.get_detail(company_id, invoice_id)
            if invoice is None:
                raise NotFoundError(f"Sales invoice with id {invoice_id} was not found.")
            allocated_amount = allocation_repository.get_allocated_totals_for_invoice_ids(
                company_id,
                [invoice.id],
                posted_only=True,
            ).get(invoice.id, Decimal("0.00"))
            return self._to_detail_dto(
                invoice=invoice,
                allocated_amount=allocated_amount,
                open_balance_amount=self._calculate_open_balance(invoice, allocated_amount),
            )

    def create_draft_invoice(
        self,
        company_id: int,
        command: CreateSalesInvoiceCommand,
    ) -> SalesInvoiceDetailDTO:
        self._permission_service.require_permission("sales.invoices.create")
        normalized_command = self._normalize_command(command)

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            customer_repository = self._require_customer_repository(uow.session)
            currency_repository = self._require_currency_repository(uow.session)
            account_repository = self._require_account_repository(uow.session)
            tax_code_repository = self._require_tax_code_repository(uow.session)
            invoice_repository = self._require_sales_invoice_repository(uow.session)
            line_repository = self._require_sales_invoice_line_repository(uow.session)

            customer = self._require_customer(customer_repository, company_id, normalized_command.customer_id)
            self._require_currency(currency_repository, company, normalized_command.currency_code)
            exchange_rate = self._normalize_exchange_rate(
                company_base_currency_code=company.base_currency_code,
                currency_code=normalized_command.currency_code,
                exchange_rate=normalized_command.exchange_rate,
            )
            self._project_dimension_validation_service.validate_header_dimensions(
                session=uow.session,
                company_id=company_id,
                contract_id=normalized_command.contract_id,
                project_id=normalized_command.project_id,
            )
            invoice_lines = self._build_invoice_lines(
                session=uow.session,
                company_id=company_id,
                invoice_date=normalized_command.invoice_date,
                header_contract_id=normalized_command.contract_id,
                header_project_id=normalized_command.project_id,
                lines=normalized_command.lines,
                account_repository=account_repository,
                tax_code_repository=tax_code_repository,
            )
            subtotal_amount, tax_amount, total_amount = self._calculate_header_totals(invoice_lines)
            self._require_positive_invoice_total(total_amount)

            invoice = SalesInvoice(
                company_id=company_id,
                invoice_number=f"{_DRAFT_NUMBER_PREFIX}{uuid4().hex[:12].upper()}",
                customer_id=customer.id,
                invoice_date=normalized_command.invoice_date,
                due_date=normalized_command.due_date,
                currency_code=normalized_command.currency_code,
                exchange_rate=exchange_rate,
                status_code="draft",
                payment_status_code="unpaid",
                reference_number=normalized_command.reference_number,
                notes=normalized_command.notes,
                contract_id=normalized_command.contract_id,
                project_id=normalized_command.project_id,
                subtotal_amount=subtotal_amount,
                tax_amount=tax_amount,
                total_amount=total_amount,
            )
            invoice_repository.add(invoice)
            uow.session.flush()
            invoice.invoice_number = self._format_draft_number(invoice.id)
            invoice_repository.save(invoice)
            line_repository.replace_lines(company_id, invoice.id, invoice_lines)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import SALES_INVOICE_CREATED
            self._record_audit(company_id, SALES_INVOICE_CREATED, "SalesInvoice", invoice.id, "Created sales invoice")
            return self.get_sales_invoice(company_id, invoice.id)

    def update_draft_invoice(
        self,
        company_id: int,
        invoice_id: int,
        command: UpdateSalesInvoiceCommand,
    ) -> SalesInvoiceDetailDTO:
        self._permission_service.require_permission("sales.invoices.edit")
        normalized_command = self._normalize_update_command(command)

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            customer_repository = self._require_customer_repository(uow.session)
            currency_repository = self._require_currency_repository(uow.session)
            account_repository = self._require_account_repository(uow.session)
            tax_code_repository = self._require_tax_code_repository(uow.session)
            invoice_repository = self._require_sales_invoice_repository(uow.session)
            line_repository = self._require_sales_invoice_line_repository(uow.session)

            invoice = invoice_repository.get_by_id(company_id, invoice_id)
            if invoice is None:
                raise NotFoundError(f"Sales invoice with id {invoice_id} was not found.")
            if invoice.status_code != "draft":
                raise ValidationError("Posted invoices cannot be edited through the draft workflow.")

            customer = self._require_customer(customer_repository, company_id, normalized_command.customer_id)
            self._require_currency(currency_repository, company, normalized_command.currency_code)
            exchange_rate = self._normalize_exchange_rate(
                company_base_currency_code=company.base_currency_code,
                currency_code=normalized_command.currency_code,
                exchange_rate=normalized_command.exchange_rate,
            )
            self._project_dimension_validation_service.validate_header_dimensions(
                session=uow.session,
                company_id=company_id,
                contract_id=normalized_command.contract_id,
                project_id=normalized_command.project_id,
            )
            invoice_lines = self._build_invoice_lines(
                session=uow.session,
                company_id=company_id,
                invoice_date=normalized_command.invoice_date,
                header_contract_id=normalized_command.contract_id,
                header_project_id=normalized_command.project_id,
                lines=normalized_command.lines,
                account_repository=account_repository,
                tax_code_repository=tax_code_repository,
            )
            subtotal_amount, tax_amount, total_amount = self._calculate_header_totals(invoice_lines)
            self._require_positive_invoice_total(total_amount)

            invoice.customer_id = customer.id
            invoice.invoice_date = normalized_command.invoice_date
            invoice.due_date = normalized_command.due_date
            invoice.currency_code = normalized_command.currency_code
            invoice.exchange_rate = exchange_rate
            invoice.reference_number = normalized_command.reference_number
            invoice.notes = normalized_command.notes
            invoice.contract_id = normalized_command.contract_id
            invoice.project_id = normalized_command.project_id
            invoice.subtotal_amount = subtotal_amount
            invoice.tax_amount = tax_amount
            invoice.total_amount = total_amount
            invoice.payment_status_code = "unpaid"
            invoice_repository.save(invoice)
            line_repository.replace_lines(company_id, invoice.id, invoice_lines)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import SALES_INVOICE_UPDATED
            self._record_audit(company_id, SALES_INVOICE_UPDATED, "SalesInvoice", invoice.id, "Updated sales invoice")
            return self.get_sales_invoice(company_id, invoice.id)

    def cancel_draft_invoice(self, company_id: int, invoice_id: int) -> None:
        self._permission_service.require_permission("sales.invoices.cancel")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_sales_invoice_repository(uow.session)
            invoice = repository.get_by_id(company_id, invoice_id)
            if invoice is None:
                raise NotFoundError(f"Sales invoice with id {invoice_id} was not found.")
            if invoice.status_code != "draft":
                raise ValidationError("Posted invoices cannot be cancelled through the draft workflow.")

            invoice.status_code = "cancelled"
            invoice.payment_status_code = "unpaid"
            repository.save(invoice)
            uow.commit()

    def list_open_invoices_for_customer(self, company_id: int, customer_id: int) -> list[CustomerOpenInvoiceDTO]:
        self._permission_service.require_permission("sales.invoices.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            customer_repository = self._require_customer_repository(uow.session)
            invoice_repository = self._require_sales_invoice_repository(uow.session)
            allocation_repository = self._require_allocation_repository(uow.session)

            self._require_customer(customer_repository, company_id, customer_id)
            invoices = [
                invoice
                for invoice in invoice_repository.list_by_company(company_id, status_code="posted")
                if invoice.customer_id == customer_id
            ]
            allocated_totals = allocation_repository.get_allocated_totals_for_invoice_ids(
                company_id,
                [invoice.id for invoice in invoices],
                posted_only=True,
            )

            open_invoices: list[CustomerOpenInvoiceDTO] = []
            for invoice in invoices:
                allocated_amount = allocated_totals.get(invoice.id, Decimal("0.00"))
                open_balance_amount = self._calculate_open_balance(invoice, allocated_amount)
                if open_balance_amount <= Decimal("0.00"):
                    continue
                open_invoices.append(
                    CustomerOpenInvoiceDTO(
                        id=invoice.id,
                        invoice_number=invoice.invoice_number,
                        invoice_date=invoice.invoice_date,
                        due_date=invoice.due_date,
                        currency_code=invoice.currency_code,
                        total_amount=invoice.total_amount,
                        allocated_amount=allocated_amount,
                        open_balance_amount=open_balance_amount,
                        payment_status_code=invoice.payment_status_code,
                    )
                )
            return open_invoices

    def _normalize_command(self, command: CreateSalesInvoiceCommand) -> CreateSalesInvoiceCommand:
        return CreateSalesInvoiceCommand(
            customer_id=self._require_positive_id(command.customer_id, "Customer"),
            invoice_date=self._require_date(command.invoice_date, "Invoice date"),
            due_date=self._require_date(command.due_date, "Due date"),
            currency_code=self._normalize_currency_code(command.currency_code),
            exchange_rate=self._normalize_optional_decimal(command.exchange_rate),
            reference_number=self._normalize_optional_text(command.reference_number),
            notes=self._normalize_optional_text(command.notes),
            contract_id=self._normalize_optional_id(command.contract_id),
            project_id=self._normalize_optional_id(command.project_id),
            lines=self._normalize_line_commands(command.lines),
        )

    def _normalize_update_command(self, command: UpdateSalesInvoiceCommand) -> UpdateSalesInvoiceCommand:
        return UpdateSalesInvoiceCommand(
            customer_id=self._require_positive_id(command.customer_id, "Customer"),
            invoice_date=self._require_date(command.invoice_date, "Invoice date"),
            due_date=self._require_date(command.due_date, "Due date"),
            currency_code=self._normalize_currency_code(command.currency_code),
            exchange_rate=self._normalize_optional_decimal(command.exchange_rate),
            reference_number=self._normalize_optional_text(command.reference_number),
            notes=self._normalize_optional_text(command.notes),
            contract_id=self._normalize_optional_id(command.contract_id),
            project_id=self._normalize_optional_id(command.project_id),
            lines=self._normalize_line_commands(command.lines),
        )

    def _normalize_line_commands(self, lines: tuple[SalesInvoiceLineCommand, ...]) -> tuple[SalesInvoiceLineCommand, ...]:
        if len(lines) == 0:
            raise ValidationError("At least one invoice line is required.")

        normalized_lines: list[SalesInvoiceLineCommand] = []
        for line in lines:
            description = self._require_text(line.description, "Line description")
            quantity = self._normalize_quantity(line.quantity)
            unit_price = self._normalize_money(line.unit_price, "Unit price")
            discount_percent = self._normalize_optional_percent(line.discount_percent)
            discount_amount = self._normalize_optional_money(line.discount_amount, "Discount amount")
            if discount_percent is not None and discount_amount is not None:
                raise ValidationError("Only one discount method may be supplied per invoice line.")

            normalized_lines.append(
                SalesInvoiceLineCommand(
                    description=description,
                    quantity=quantity,
                    unit_price=unit_price,
                    discount_percent=discount_percent,
                    discount_amount=discount_amount,
                    tax_code_id=line.tax_code_id if line.tax_code_id and line.tax_code_id > 0 else None,
                    revenue_account_id=self._require_positive_id(line.revenue_account_id, "Revenue account"),
                    contract_id=self._normalize_optional_id(line.contract_id),
                    project_id=self._normalize_optional_id(line.project_id),
                    project_job_id=self._normalize_optional_id(line.project_job_id),
                    project_cost_code_id=self._normalize_optional_id(line.project_cost_code_id),
                )
            )
        return tuple(normalized_lines)

    def _build_invoice_lines(
        self,
        *,
        session: Session,
        company_id: int,
        invoice_date: date,
        header_contract_id: int | None,
        header_project_id: int | None,
        lines: tuple[SalesInvoiceLineCommand, ...],
        account_repository: AccountRepository,
        tax_code_repository: TaxCodeRepository,
    ) -> list[SalesInvoiceLine]:
        built_lines: list[SalesInvoiceLine] = []
        for line_number, command in enumerate(lines, start=1):
            revenue_account = self._require_revenue_account(account_repository, company_id, command.revenue_account_id)
            tax_code = self._require_tax_code_for_date(tax_code_repository, company_id, command.tax_code_id, invoice_date)
            resolved_dimensions = self._project_dimension_validation_service.resolve_line_dimensions(
                header_contract_id=header_contract_id,
                header_project_id=header_project_id,
                line_contract_id=command.contract_id,
                line_project_id=command.project_id,
                line_project_job_id=command.project_job_id,
                line_project_cost_code_id=command.project_cost_code_id,
            )
            self._project_dimension_validation_service.validate_line_dimensions(
                session=session,
                company_id=company_id,
                contract_id=resolved_dimensions.contract_id,
                project_id=resolved_dimensions.project_id,
                project_job_id=resolved_dimensions.project_job_id,
                project_cost_code_id=resolved_dimensions.project_cost_code_id,
                line_number=line_number,
            )
            subtotal_amount, tax_amount, total_amount = self._calculate_line_totals(command, tax_code)
            built_lines.append(
                SalesInvoiceLine(
                    sales_invoice_id=0,
                    line_number=line_number,
                    description=command.description,
                    quantity=command.quantity,
                    unit_price=command.unit_price,
                    discount_percent=command.discount_percent,
                    discount_amount=command.discount_amount,
                    tax_code_id=tax_code.id if tax_code is not None else None,
                    revenue_account_id=revenue_account.id,
                    line_subtotal_amount=subtotal_amount,
                    line_tax_amount=tax_amount,
                    line_total_amount=total_amount,
                    contract_id=resolved_dimensions.contract_id,
                    project_id=resolved_dimensions.project_id,
                    project_job_id=resolved_dimensions.project_job_id,
                    project_cost_code_id=resolved_dimensions.project_cost_code_id,
                )
            )
        return built_lines

    def _calculate_line_totals(
        self,
        command: SalesInvoiceLineCommand,
        tax_code: TaxCode | None,
    ) -> tuple[Decimal, Decimal, Decimal]:
        base_amount = self._quantize_money(command.quantity * command.unit_price)
        if command.discount_amount is not None:
            discount_amount = command.discount_amount
        elif command.discount_percent is not None:
            discount_amount = self._quantize_money(base_amount * command.discount_percent / Decimal("100"))
        else:
            discount_amount = Decimal("0.00")
        if discount_amount > base_amount:
            raise ValidationError("Discount amount cannot exceed the line amount.")

        line_subtotal_amount = self._quantize_money(base_amount - discount_amount)
        line_tax_amount = self._calculate_tax_amount(line_subtotal_amount, tax_code)
        line_total_amount = self._quantize_money(line_subtotal_amount + line_tax_amount)
        return line_subtotal_amount, line_tax_amount, line_total_amount

    def _calculate_tax_amount(self, line_subtotal_amount: Decimal, tax_code: TaxCode | None) -> Decimal:
        if tax_code is None:
            return Decimal("0.00")
        method_code = tax_code.calculation_method_code.strip().upper()
        if method_code == "PERCENTAGE":
            if tax_code.rate_percent is None:
                raise ValidationError("Percentage tax code is missing a rate.")
            return self._quantize_money(line_subtotal_amount * Decimal(str(tax_code.rate_percent)) / Decimal("100"))
        if method_code == "FIXED_AMOUNT":
            if tax_code.rate_percent is None:
                return Decimal("0.00")
            return self._quantize_money(Decimal(str(tax_code.rate_percent)))
        return Decimal("0.00")

    def _calculate_header_totals(self, lines: list[SalesInvoiceLine]) -> tuple[Decimal, Decimal, Decimal]:
        subtotal_amount = self._quantize_money(sum((line.line_subtotal_amount for line in lines), Decimal("0.00")))
        tax_amount = self._quantize_money(sum((line.line_tax_amount for line in lines), Decimal("0.00")))
        total_amount = self._quantize_money(sum((line.line_total_amount for line in lines), Decimal("0.00")))
        return subtotal_amount, tax_amount, total_amount

    def _calculate_open_balance(self, invoice: SalesInvoice, allocated_amount: Decimal) -> Decimal:
        if invoice.status_code != "posted":
            return Decimal("0.00")
        balance = self._quantize_money(invoice.total_amount - allocated_amount)
        return balance if balance > Decimal("0.00") else Decimal("0.00")

    def _require_company_exists(self, session: Session | None, company_id: int):
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repository = self._company_repository_factory(session)
        company = repository.get_by_id(company_id)
        if company is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")
        return company

    def _require_customer_repository(self, session: Session | None) -> CustomerRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._customer_repository_factory(session)

    def _require_currency_repository(self, session: Session | None) -> CurrencyRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._currency_repository_factory(session)

    def _require_account_repository(self, session: Session | None) -> AccountRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_repository_factory(session)

    def _require_tax_code_repository(self, session: Session | None) -> TaxCodeRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._tax_code_repository_factory(session)

    def _require_sales_invoice_repository(self, session: Session | None) -> SalesInvoiceRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._sales_invoice_repository_factory(session)

    def _require_sales_invoice_line_repository(self, session: Session | None) -> SalesInvoiceLineRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._sales_invoice_line_repository_factory(session)

    def _require_allocation_repository(self, session: Session | None) -> CustomerReceiptAllocationRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._customer_receipt_allocation_repository_factory(session)

    def _require_customer(
        self,
        customer_repository: CustomerRepository,
        company_id: int,
        customer_id: int,
    ) -> Customer:
        customer = customer_repository.get_by_id(company_id, customer_id)
        if customer is None:
            raise ValidationError("Customer must belong to the active company.")
        return customer

    def _require_currency(self, currency_repository: CurrencyRepository, company: object, currency_code: str) -> Currency:
        company_base_currency_code = getattr(company, "base_currency_code", None)
        with self._unit_of_work_factory() as uow:
            session = uow.session
            if session is None:
                raise RuntimeError("Unit of work has no active session.")
            currency = session.get(Currency, currency_code)
            if currency is None:
                raise ValidationError("Currency must exist in the reference data.")
            if company_base_currency_code != currency_code and not currency.is_active:
                raise ValidationError("Currency must reference an active currency code.")
            _ = currency_repository
            return currency

    def _require_revenue_account(
        self,
        account_repository: AccountRepository,
        company_id: int,
        account_id: int,
    ):
        account = account_repository.get_by_id(company_id, account_id)
        if account is None:
            raise ValidationError("Revenue account must belong to the active company.")
        if not account.is_active:
            raise ValidationError("Revenue account must be active.")
        if not account.allow_manual_posting:
            raise ValidationError("Revenue account must allow manual posting.")
        return account

    def _require_tax_code_for_date(
        self,
        tax_code_repository: TaxCodeRepository,
        company_id: int,
        tax_code_id: int | None,
        invoice_date: date,
    ) -> TaxCode | None:
        if tax_code_id is None:
            return None
        tax_code = tax_code_repository.get_by_id(company_id, tax_code_id)
        if tax_code is None:
            raise ValidationError("Tax code must belong to the active company.")
        if invoice_date < tax_code.effective_from:
            raise ValidationError("Tax code is not yet effective for the invoice date.")
        if tax_code.effective_to is not None and invoice_date > tax_code.effective_to:
            raise ValidationError("Tax code is no longer effective for the invoice date.")
        return tax_code

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

    def _normalize_optional_percent(self, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value < Decimal("0") or value > Decimal("100"):
            raise ValidationError("Discount percent must be between 0 and 100.")
        return self._quantize_rate(value)

    def _normalize_optional_money(self, value: Decimal | None, label: str) -> Decimal | None:
        if value is None:
            return None
        if value < Decimal("0"):
            raise ValidationError(f"{label} cannot be negative.")
        return self._quantize_money(value)

    def _normalize_optional_id(self, value: int | None) -> int | None:
        if value is None:
            return None
        if value <= 0:
            raise ValidationError("Dimension identifiers must be greater than zero.")
        return value

    def _normalize_quantity(self, value: Decimal) -> Decimal:
        if value <= Decimal("0"):
            raise ValidationError("Quantity must be greater than zero.")
        return self._quantize_quantity(value)

    def _normalize_money(self, value: Decimal, label: str) -> Decimal:
        if value < Decimal("0"):
            raise ValidationError(f"{label} cannot be negative.")
        return self._quantize_money(value)

    def _require_date(self, value: date, label: str) -> date:
        if value is None:
            raise ValidationError(f"{label} is required.")
        return value

    def _require_positive_id(self, value: int, label: str) -> int:
        if value <= 0:
            raise ValidationError(f"{label} is required.")
        return value

    def _require_text(self, value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValidationError(f"{label} is required.")
        return normalized

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
                "Exchange rate is required when the invoice currency differs from the company base currency."
            )
        return self._quantize_rate(exchange_rate)

    def _normalize_optional_choice(
        self,
        value: str | None,
        allowed_values: set[str],
        label: str,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        if normalized not in allowed_values:
            raise ValidationError(f"{label} is not recognized.")
        return normalized

    def _format_draft_number(self, invoice_id: int) -> str:
        return f"{_DRAFT_NUMBER_PREFIX}{invoice_id:06d}"

    def _require_positive_invoice_total(self, total_amount: Decimal) -> None:
        if total_amount <= Decimal("0.00"):
            raise ValidationError("Invoice total must be greater than zero.")

    def _quantize_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)

    def _quantize_quantity(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0000"), rounding=ROUND_HALF_UP)

    def _quantize_rate(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0000"), rounding=ROUND_HALF_UP)

    def _translate_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "invoice_number" in message:
            return ConflictError("A sales invoice with this number already exists.")
        return ValidationError("Sales invoice data could not be saved.")

    def _to_list_item_dto(
        self,
        *,
        invoice: SalesInvoice,
        company_base_currency_code: str,
        allocated_amount: Decimal,
        open_balance_amount: Decimal,
    ) -> SalesInvoiceListItemDTO:
        customer = invoice.customer
        _ = company_base_currency_code
        return SalesInvoiceListItemDTO(
            id=invoice.id,
            company_id=invoice.company_id,
            invoice_number=invoice.invoice_number,
            customer_id=invoice.customer_id,
            customer_code=customer.customer_code if customer is not None else "",
            customer_name=customer.display_name if customer is not None else "",
            invoice_date=invoice.invoice_date,
            due_date=invoice.due_date,
            currency_code=invoice.currency_code,
            subtotal_amount=invoice.subtotal_amount,
            tax_amount=invoice.tax_amount,
            total_amount=invoice.total_amount,
            allocated_amount=allocated_amount,
            open_balance_amount=open_balance_amount,
            status_code=invoice.status_code,
            payment_status_code=invoice.payment_status_code,
            posted_at=invoice.posted_at,
            updated_at=invoice.updated_at,
        )

    def _to_detail_dto(
        self,
        *,
        invoice: SalesInvoice,
        allocated_amount: Decimal,
        open_balance_amount: Decimal,
    ) -> SalesInvoiceDetailDTO:
        customer = invoice.customer
        lines = tuple(
            SalesInvoiceLineDTO(
                id=line.id,
                sales_invoice_id=line.sales_invoice_id,
                line_number=line.line_number,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount_percent=line.discount_percent,
                discount_amount=line.discount_amount,
                tax_code_id=line.tax_code_id,
                tax_code_code=line.tax_code.code if line.tax_code is not None else None,
                tax_code_name=line.tax_code.name if line.tax_code is not None else None,
                revenue_account_id=line.revenue_account_id,
                revenue_account_code=line.revenue_account.account_code if line.revenue_account is not None else "",
                revenue_account_name=line.revenue_account.account_name if line.revenue_account is not None else "",
                line_subtotal_amount=line.line_subtotal_amount,
                line_tax_amount=line.line_tax_amount,
                line_total_amount=line.line_total_amount,
                contract_id=line.contract_id,
                project_id=line.project_id,
                project_job_id=line.project_job_id,
                project_cost_code_id=line.project_cost_code_id,
            )
            for line in sorted(invoice.lines, key=lambda row: (row.line_number, row.id))
        )
        totals = SalesInvoiceTotalsDTO(
            subtotal_amount=invoice.subtotal_amount,
            tax_amount=invoice.tax_amount,
            total_amount=invoice.total_amount,
            allocated_amount=allocated_amount,
            open_balance_amount=open_balance_amount,
        )
        return SalesInvoiceDetailDTO(
            id=invoice.id,
            company_id=invoice.company_id,
            invoice_number=invoice.invoice_number,
            customer_id=invoice.customer_id,
            customer_code=customer.customer_code if customer is not None else "",
            customer_name=customer.display_name if customer is not None else "",
            invoice_date=invoice.invoice_date,
            due_date=invoice.due_date,
            currency_code=invoice.currency_code,
            exchange_rate=invoice.exchange_rate,
            status_code=invoice.status_code,
            payment_status_code=invoice.payment_status_code,
            reference_number=invoice.reference_number,
            notes=invoice.notes,
            posted_journal_entry_id=invoice.posted_journal_entry_id,
            posted_at=invoice.posted_at,
            posted_by_user_id=invoice.posted_by_user_id,
            created_at=invoice.created_at,
            updated_at=invoice.updated_at,
            totals=totals,
            lines=lines,
            contract_id=invoice.contract_id,
            project_id=invoice.project_id,
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
