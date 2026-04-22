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
from seeker_accounting.modules.customers.repositories.customer_repository import CustomerRepository
from seeker_accounting.modules.job_costing.services.project_dimension_validation_service import (
    ProjectDimensionValidationService,
)
from seeker_accounting.modules.sales.dto.sales_invoice_commands import (
    CreateSalesInvoiceCommand,
    SalesInvoiceLineCommand,
)
from seeker_accounting.modules.sales.dto.sales_order_commands import (
    ConvertSalesOrderCommand,
    CreateSalesOrderCommand,
    SalesOrderLineCommand,
    UpdateSalesOrderCommand,
)
from seeker_accounting.modules.sales.dto.sales_order_dto import (
    SalesOrderConversionResultDTO,
    SalesOrderDetailDTO,
    SalesOrderLineDTO,
    SalesOrderListItemDTO,
    SalesOrderTotalsDTO,
)
from seeker_accounting.modules.sales.models.sales_order import SalesOrder
from seeker_accounting.modules.sales.models.sales_order_line import SalesOrderLine
from seeker_accounting.modules.sales.repositories.sales_invoice_repository import SalesInvoiceRepository
from seeker_accounting.modules.sales.repositories.sales_order_line_repository import SalesOrderLineRepository
from seeker_accounting.modules.sales.repositories.sales_order_repository import SalesOrderRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService
    from seeker_accounting.modules.sales.services.sales_invoice_service import SalesInvoiceService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CustomerRepositoryFactory = Callable[[Session], CustomerRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
TaxCodeRepositoryFactory = Callable[[Session], TaxCodeRepository]
SalesOrderRepositoryFactory = Callable[[Session], SalesOrderRepository]
SalesOrderLineRepositoryFactory = Callable[[Session], SalesOrderLineRepository]
SalesInvoiceRepositoryFactory = Callable[[Session], SalesInvoiceRepository]

_DRAFT_NUMBER_PREFIX = "SO-DRAFT-"
_FINALIZED_NUMBER_PREFIX = "SO-"
_ALLOWED_STATUS_FILTERS = frozenset({"draft", "confirmed", "invoiced", "cancelled"})


class SalesOrderService:
    """Manage sales orders and their lifecycle (draft → confirmed → invoiced / cancelled)."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        customer_repository_factory: CustomerRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        tax_code_repository_factory: TaxCodeRepositoryFactory,
        sales_order_repository_factory: SalesOrderRepositoryFactory,
        sales_order_line_repository_factory: SalesOrderLineRepositoryFactory,
        sales_invoice_repository_factory: SalesInvoiceRepositoryFactory,
        sales_invoice_service: "SalesInvoiceService",
        project_dimension_validation_service: ProjectDimensionValidationService,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._customer_repository_factory = customer_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._account_repository_factory = account_repository_factory
        self._tax_code_repository_factory = tax_code_repository_factory
        self._sales_order_repository_factory = sales_order_repository_factory
        self._sales_order_line_repository_factory = sales_order_line_repository_factory
        self._sales_invoice_repository_factory = sales_invoice_repository_factory
        self._sales_invoice_service = sales_invoice_service
        self._project_dimension_validation_service = project_dimension_validation_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ── Read ──────────────────────────────────────────────────────────────────
    def list_orders(
        self,
        company_id: int,
        status_code: str | None = None,
    ) -> list[SalesOrderListItemDTO]:
        self._permission_service.require_permission("sales.orders.view")
        normalized_status = self._normalize_optional_choice(status_code, _ALLOWED_STATUS_FILTERS, "Status code")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_order_repository(uow.session)
            orders = repository.list_by_company(company_id, status_code=normalized_status)
            return [self._to_list_item_dto(order) for order in orders]

    def get_order(self, company_id: int, order_id: int) -> SalesOrderDetailDTO:
        self._permission_service.require_permission("sales.orders.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_order_repository(uow.session)
            order = repository.get_detail(company_id, order_id)
            if order is None:
                raise NotFoundError(f"Sales order with id {order_id} was not found.")
            return self._to_detail_dto(order)

    # ── Create / update drafts ───────────────────────────────────────────────
    def create_draft_order(
        self,
        company_id: int,
        command: CreateSalesOrderCommand,
    ) -> SalesOrderDetailDTO:
        self._permission_service.require_permission("sales.orders.create")
        normalized_command = self._normalize_create_command(command)

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            customer_repository = self._require_customer_repository(uow.session)
            account_repository = self._require_account_repository(uow.session)
            tax_code_repository = self._require_tax_code_repository(uow.session)
            order_repository = self._require_order_repository(uow.session)
            line_repository = self._require_order_line_repository(uow.session)

            customer = self._require_customer(customer_repository, company_id, normalized_command.customer_id)
            self._require_currency(uow.session, company, normalized_command.currency_code)
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
            order_lines = self._build_order_lines(
                session=uow.session,
                company_id=company_id,
                order_date=normalized_command.order_date,
                header_contract_id=normalized_command.contract_id,
                header_project_id=normalized_command.project_id,
                lines=normalized_command.lines,
                account_repository=account_repository,
                tax_code_repository=tax_code_repository,
            )
            subtotal_amount, tax_amount, total_amount = self._calculate_header_totals(order_lines)
            self._require_positive_total(total_amount)

            order = SalesOrder(
                company_id=company_id,
                order_number=f"{_DRAFT_NUMBER_PREFIX}{uuid4().hex[:12].upper()}",
                customer_id=customer.id,
                order_date=normalized_command.order_date,
                requested_delivery_date=normalized_command.requested_delivery_date,
                currency_code=normalized_command.currency_code,
                exchange_rate=exchange_rate,
                status_code="draft",
                reference_number=normalized_command.reference_number,
                notes=normalized_command.notes,
                contract_id=normalized_command.contract_id,
                project_id=normalized_command.project_id,
                source_quote_id=normalized_command.source_quote_id,
                subtotal_amount=subtotal_amount,
                tax_amount=tax_amount,
                total_amount=total_amount,
            )
            order_repository.add(order)
            uow.session.flush()
            order.order_number = self._format_draft_number(order.id)
            order_repository.save(order)
            line_repository.replace_lines(company_id, order.id, order_lines)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

        from seeker_accounting.modules.audit.event_type_catalog import SALES_ORDER_CREATED
        self._record_audit(company_id, SALES_ORDER_CREATED, order.id, "Created sales order")
        return self.get_order(company_id, order.id)

    def update_draft_order(
        self,
        company_id: int,
        order_id: int,
        command: UpdateSalesOrderCommand,
    ) -> SalesOrderDetailDTO:
        self._permission_service.require_permission("sales.orders.edit")
        normalized_command = self._normalize_update_command(command)

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            customer_repository = self._require_customer_repository(uow.session)
            account_repository = self._require_account_repository(uow.session)
            tax_code_repository = self._require_tax_code_repository(uow.session)
            order_repository = self._require_order_repository(uow.session)
            line_repository = self._require_order_line_repository(uow.session)

            order = order_repository.get_by_id(company_id, order_id)
            if order is None:
                raise NotFoundError(f"Sales order with id {order_id} was not found.")
            if order.status_code != "draft":
                raise ValidationError("Only draft orders can be edited.")

            customer = self._require_customer(customer_repository, company_id, normalized_command.customer_id)
            self._require_currency(uow.session, company, normalized_command.currency_code)
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
            order_lines = self._build_order_lines(
                session=uow.session,
                company_id=company_id,
                order_date=normalized_command.order_date,
                header_contract_id=normalized_command.contract_id,
                header_project_id=normalized_command.project_id,
                lines=normalized_command.lines,
                account_repository=account_repository,
                tax_code_repository=tax_code_repository,
            )
            subtotal_amount, tax_amount, total_amount = self._calculate_header_totals(order_lines)
            self._require_positive_total(total_amount)

            order.customer_id = customer.id
            order.order_date = normalized_command.order_date
            order.requested_delivery_date = normalized_command.requested_delivery_date
            order.currency_code = normalized_command.currency_code
            order.exchange_rate = exchange_rate
            order.reference_number = normalized_command.reference_number
            order.notes = normalized_command.notes
            order.contract_id = normalized_command.contract_id
            order.project_id = normalized_command.project_id
            order.subtotal_amount = subtotal_amount
            order.tax_amount = tax_amount
            order.total_amount = total_amount
            order_repository.save(order)
            line_repository.replace_lines(company_id, order.id, order_lines)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

        from seeker_accounting.modules.audit.event_type_catalog import SALES_ORDER_UPDATED
        self._record_audit(company_id, SALES_ORDER_UPDATED, order.id, "Updated sales order")
        return self.get_order(company_id, order.id)

    # ── Lifecycle transitions ────────────────────────────────────────────────
    def confirm_order(self, company_id: int, order_id: int) -> SalesOrderDetailDTO:
        """Confirm the customer's commitment (draft → confirmed). Assigns final SO number."""
        self._permission_service.require_permission("sales.orders.confirm")
        return self._transition_status(
            company_id=company_id,
            order_id=order_id,
            allowed_from={"draft"},
            new_status="confirmed",
            finalize_number=True,
            audit_event_code_name="SALES_ORDER_CONFIRMED",
            audit_description="Confirmed sales order",
        )

    def cancel_order(self, company_id: int, order_id: int) -> SalesOrderDetailDTO:
        """Cancel a draft or confirmed sales order."""
        self._permission_service.require_permission("sales.orders.cancel")
        return self._transition_status(
            company_id=company_id,
            order_id=order_id,
            allowed_from={"draft", "confirmed"},
            new_status="cancelled",
            finalize_number=False,
            audit_event_code_name="SALES_ORDER_CANCELLED",
            audit_description="Cancelled sales order",
        )

    # ── Convert to sales invoice ─────────────────────────────────────────────
    def convert_to_invoice(
        self,
        company_id: int,
        order_id: int,
        command: ConvertSalesOrderCommand,
    ) -> SalesOrderConversionResultDTO:
        self._permission_service.require_permission("sales.orders.convert")
        self._permission_service.require_permission("sales.invoices.create")

        invoice_date = self._require_date(command.invoice_date, "Invoice date")
        due_date = self._require_date(command.due_date, "Due date")
        reference_number = self._normalize_optional_text(command.reference_number)
        notes = self._normalize_optional_text(command.notes)

        # Phase 1: validate order and snapshot data to build the invoice command.
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            order_repository = self._require_order_repository(uow.session)
            line_repository = self._require_order_line_repository(uow.session)

            order = order_repository.get_by_id(company_id, order_id)
            if order is None:
                raise NotFoundError(f"Sales order with id {order_id} was not found.")
            if order.status_code != "confirmed":
                raise ValidationError("Only confirmed orders can be converted to an invoice.")
            if order.converted_to_invoice_id is not None:
                raise ConflictError("This sales order has already been converted to an invoice.")

            order_lines = line_repository.list_for_order(company_id, order.id)
            if len(order_lines) == 0:
                raise ValidationError("Sales order has no lines to convert.")

            invoice_line_commands: list[SalesInvoiceLineCommand] = []
            for line in order_lines:
                invoice_line_commands.append(
                    SalesInvoiceLineCommand(
                        description=line.description,
                        quantity=line.quantity,
                        unit_price=line.unit_price,
                        tax_code_id=line.tax_code_id,
                        revenue_account_id=line.revenue_account_id if line.revenue_account_id is not None else 0,
                        contract_id=line.contract_id,
                        project_id=line.project_id,
                        project_job_id=line.project_job_id,
                        project_cost_code_id=line.project_cost_code_id,
                    )
                )

            create_invoice_command = CreateSalesInvoiceCommand(
                customer_id=order.customer_id,
                invoice_date=invoice_date,
                due_date=due_date,
                currency_code=order.currency_code,
                exchange_rate=order.exchange_rate,
                reference_number=reference_number if reference_number is not None else order.reference_number,
                notes=notes if notes is not None else order.notes,
                contract_id=order.contract_id,
                project_id=order.project_id,
                lines=tuple(invoice_line_commands),
            )

        # Phase 2: create the draft invoice through the invoice service (own transaction).
        invoice_detail = self._sales_invoice_service.create_draft_invoice(company_id, create_invoice_command)

        # Phase 3: mark the order invoiced and link it to the invoice.
        with self._unit_of_work_factory() as uow:
            order_repository = self._require_order_repository(uow.session)
            invoice_repository = self._require_invoice_repository(uow.session)
            order = order_repository.get_by_id(company_id, order_id)
            if order is None:
                raise NotFoundError(f"Sales order with id {order_id} was not found.")
            order.status_code = "invoiced"
            order.converted_to_invoice_id = invoice_detail.id
            order_repository.save(order)

            invoice = invoice_repository.get_by_id(company_id, invoice_detail.id)
            if invoice is not None:
                invoice.source_order_id = order.id
                invoice_repository.save(invoice)
            uow.commit()

        from seeker_accounting.modules.audit.event_type_catalog import SALES_ORDER_CONVERTED
        self._record_audit(
            company_id,
            SALES_ORDER_CONVERTED,
            order_id,
            f"Converted sales order to invoice {invoice_detail.invoice_number}",
        )
        return SalesOrderConversionResultDTO(
            order_id=order_id,
            order_number=self._get_order_number(company_id, order_id),
            invoice_id=invoice_detail.id,
        )

    # ── Internal helpers ─────────────────────────────────────────────────────
    def _transition_status(
        self,
        *,
        company_id: int,
        order_id: int,
        allowed_from: set[str],
        new_status: str,
        finalize_number: bool,
        audit_event_code_name: str,
        audit_description: str,
    ) -> SalesOrderDetailDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_order_repository(uow.session)
            order = repository.get_by_id(company_id, order_id)
            if order is None:
                raise NotFoundError(f"Sales order with id {order_id} was not found.")
            if order.status_code not in allowed_from:
                raise ValidationError(
                    f"Order in status '{order.status_code}' cannot transition to '{new_status}'."
                )
            order.status_code = new_status
            if finalize_number and order.order_number.startswith(_DRAFT_NUMBER_PREFIX):
                order.order_number = f"{_FINALIZED_NUMBER_PREFIX}{order.id:06d}"
            repository.save(order)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

        from seeker_accounting.modules.audit import event_type_catalog as _ec
        event_code = getattr(_ec, audit_event_code_name)
        self._record_audit(company_id, event_code, order_id, audit_description)
        return self.get_order(company_id, order_id)

    def _get_order_number(self, company_id: int, order_id: int) -> str:
        with self._unit_of_work_factory() as uow:
            repository = self._require_order_repository(uow.session)
            order = repository.get_by_id(company_id, order_id)
            return order.order_number if order is not None else ""

    def _normalize_create_command(self, command: CreateSalesOrderCommand) -> CreateSalesOrderCommand:
        return CreateSalesOrderCommand(
            customer_id=self._require_positive_id(command.customer_id, "Customer"),
            order_date=self._require_date(command.order_date, "Order date"),
            requested_delivery_date=self._normalize_optional_delivery_date(
                command.requested_delivery_date, command.order_date
            ),
            currency_code=self._normalize_currency_code(command.currency_code),
            exchange_rate=self._normalize_optional_decimal(command.exchange_rate),
            reference_number=self._normalize_optional_text(command.reference_number),
            notes=self._normalize_optional_text(command.notes),
            contract_id=self._normalize_optional_id(command.contract_id),
            project_id=self._normalize_optional_id(command.project_id),
            source_quote_id=self._normalize_optional_id(command.source_quote_id),
            lines=self._normalize_line_commands(command.lines),
        )

    def _normalize_update_command(self, command: UpdateSalesOrderCommand) -> UpdateSalesOrderCommand:
        return UpdateSalesOrderCommand(
            customer_id=self._require_positive_id(command.customer_id, "Customer"),
            order_date=self._require_date(command.order_date, "Order date"),
            requested_delivery_date=self._normalize_optional_delivery_date(
                command.requested_delivery_date, command.order_date
            ),
            currency_code=self._normalize_currency_code(command.currency_code),
            exchange_rate=self._normalize_optional_decimal(command.exchange_rate),
            reference_number=self._normalize_optional_text(command.reference_number),
            notes=self._normalize_optional_text(command.notes),
            contract_id=self._normalize_optional_id(command.contract_id),
            project_id=self._normalize_optional_id(command.project_id),
            lines=self._normalize_line_commands(command.lines),
        )

    def _normalize_line_commands(
        self,
        lines: tuple[SalesOrderLineCommand, ...],
    ) -> tuple[SalesOrderLineCommand, ...]:
        if len(lines) == 0:
            raise ValidationError("At least one order line is required.")
        normalized: list[SalesOrderLineCommand] = []
        for line in lines:
            description = self._require_text(line.description, "Line description")
            quantity = self._normalize_quantity(line.quantity)
            unit_price = self._normalize_money(line.unit_price, "Unit price")
            discount_percent = self._normalize_optional_percent(line.discount_percent)
            discount_amount = self._normalize_optional_money(line.discount_amount, "Discount amount")
            if discount_percent is not None and discount_amount is not None:
                raise ValidationError("Only one discount method may be supplied per order line.")
            normalized.append(
                SalesOrderLineCommand(
                    description=description,
                    quantity=quantity,
                    unit_price=unit_price,
                    discount_percent=discount_percent,
                    discount_amount=discount_amount,
                    tax_code_id=line.tax_code_id if line.tax_code_id and line.tax_code_id > 0 else None,
                    revenue_account_id=self._normalize_optional_id(line.revenue_account_id),
                    contract_id=self._normalize_optional_id(line.contract_id),
                    project_id=self._normalize_optional_id(line.project_id),
                    project_job_id=self._normalize_optional_id(line.project_job_id),
                    project_cost_code_id=self._normalize_optional_id(line.project_cost_code_id),
                )
            )
        return tuple(normalized)

    def _build_order_lines(
        self,
        *,
        session: Session,
        company_id: int,
        order_date: date,
        header_contract_id: int | None,
        header_project_id: int | None,
        lines: tuple[SalesOrderLineCommand, ...],
        account_repository: AccountRepository,
        tax_code_repository: TaxCodeRepository,
    ) -> list[SalesOrderLine]:
        built: list[SalesOrderLine] = []
        for line_number, command in enumerate(lines, start=1):
            revenue_account_id: int | None = None
            if command.revenue_account_id is not None:
                revenue_account = self._require_revenue_account(
                    account_repository, company_id, command.revenue_account_id
                )
                revenue_account_id = revenue_account.id
            tax_code = self._require_tax_code_for_date(
                tax_code_repository, company_id, command.tax_code_id, order_date
            )
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
            built.append(
                SalesOrderLine(
                    sales_order_id=0,
                    line_number=line_number,
                    description=command.description,
                    quantity=command.quantity,
                    unit_price=command.unit_price,
                    discount_percent=command.discount_percent,
                    discount_amount=command.discount_amount,
                    tax_code_id=tax_code.id if tax_code is not None else None,
                    revenue_account_id=revenue_account_id,
                    line_subtotal_amount=subtotal_amount,
                    line_tax_amount=tax_amount,
                    line_total_amount=total_amount,
                    contract_id=resolved_dimensions.contract_id,
                    project_id=resolved_dimensions.project_id,
                    project_job_id=resolved_dimensions.project_job_id,
                    project_cost_code_id=resolved_dimensions.project_cost_code_id,
                )
            )
        return built

    def _calculate_line_totals(
        self,
        command: SalesOrderLineCommand,
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
            return self._quantize_money(
                line_subtotal_amount * Decimal(str(tax_code.rate_percent)) / Decimal("100")
            )
        if method_code == "FIXED_AMOUNT":
            if tax_code.rate_percent is None:
                return Decimal("0.00")
            return self._quantize_money(Decimal(str(tax_code.rate_percent)))
        return Decimal("0.00")

    def _calculate_header_totals(self, lines: list[SalesOrderLine]) -> tuple[Decimal, Decimal, Decimal]:
        subtotal_amount = self._quantize_money(sum((l.line_subtotal_amount for l in lines), Decimal("0.00")))
        tax_amount = self._quantize_money(sum((l.line_tax_amount for l in lines), Decimal("0.00")))
        total_amount = self._quantize_money(sum((l.line_total_amount for l in lines), Decimal("0.00")))
        return subtotal_amount, tax_amount, total_amount

    # ── Repository getters ───────────────────────────────────────────────────
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

    def _require_account_repository(self, session: Session | None) -> AccountRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_repository_factory(session)

    def _require_tax_code_repository(self, session: Session | None) -> TaxCodeRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._tax_code_repository_factory(session)

    def _require_order_repository(self, session: Session | None) -> SalesOrderRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._sales_order_repository_factory(session)

    def _require_order_line_repository(self, session: Session | None) -> SalesOrderLineRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._sales_order_line_repository_factory(session)

    def _require_invoice_repository(self, session: Session | None) -> SalesInvoiceRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._sales_invoice_repository_factory(session)

    # ── Validation helpers ───────────────────────────────────────────────────
    def _require_customer(self, customer_repository: CustomerRepository, company_id: int, customer_id: int):
        customer = customer_repository.get_by_id(company_id, customer_id)
        if customer is None:
            raise ValidationError("Customer must belong to the active company.")
        return customer

    def _require_currency(self, session: Session | None, company: object, currency_code: str) -> Currency:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        currency = session.get(Currency, currency_code)
        if currency is None:
            raise ValidationError("Currency must exist in the reference data.")
        company_base_currency_code = getattr(company, "base_currency_code", None)
        if company_base_currency_code != currency_code and not currency.is_active:
            raise ValidationError("Currency must reference an active currency code.")
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
        reference_date: date,
    ) -> TaxCode | None:
        if tax_code_id is None:
            return None
        tax_code = tax_code_repository.get_by_id(company_id, tax_code_id)
        if tax_code is None:
            raise ValidationError("Tax code must belong to the active company.")
        if reference_date < tax_code.effective_from:
            raise ValidationError("Tax code is not yet effective for the order date.")
        if tax_code.effective_to is not None and reference_date > tax_code.effective_to:
            raise ValidationError("Tax code is no longer effective for the order date.")
        return tax_code

    # ── Normalizers ──────────────────────────────────────────────────────────
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

    def _normalize_optional_delivery_date(self, value: date | None, reference_date: date) -> date | None:
        if value is None:
            return None
        if value < reference_date:
            raise ValidationError("Requested delivery date cannot be earlier than the order date.")
        return value

    def _normalize_optional_choice(
        self,
        value: str | None,
        allowed_values: set[str] | frozenset[str],
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
                "Exchange rate is required when the order currency differs from the company base currency."
            )
        return self._quantize_rate(exchange_rate)

    def _require_positive_total(self, total_amount: Decimal) -> None:
        if total_amount <= Decimal("0.00"):
            raise ValidationError("Order total must be greater than zero.")

    def _format_draft_number(self, order_id: int) -> str:
        return f"{_DRAFT_NUMBER_PREFIX}{order_id:06d}"

    def _quantize_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)

    def _quantize_quantity(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0000"), rounding=ROUND_HALF_UP)

    def _quantize_rate(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0000"), rounding=ROUND_HALF_UP)

    def _translate_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "order_number" in message:
            return ConflictError("A sales order with this number already exists.")
        return ValidationError("Sales order data could not be saved.")

    # ── DTO mapping ───────────────────────────────────────────────────────────
    def _to_list_item_dto(self, order: SalesOrder) -> SalesOrderListItemDTO:
        customer = order.customer
        return SalesOrderListItemDTO(
            id=order.id,
            order_number=order.order_number,
            order_date=order.order_date,
            requested_delivery_date=order.requested_delivery_date,
            customer_id=order.customer_id,
            customer_name=customer.display_name if customer is not None else "",
            currency_code=order.currency_code,
            subtotal_amount=order.subtotal_amount,
            tax_amount=order.tax_amount,
            total_amount=order.total_amount,
            status_code=order.status_code,
            source_quote_id=order.source_quote_id,
            converted_to_invoice_id=order.converted_to_invoice_id,
        )

    def _to_detail_dto(self, order: SalesOrder) -> SalesOrderDetailDTO:
        customer = order.customer
        lines = tuple(
            SalesOrderLineDTO(
                id=line.id,
                line_number=line.line_number,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount_percent=line.discount_percent,
                discount_amount=line.discount_amount,
                tax_code_id=line.tax_code_id,
                tax_code_name=line.tax_code.name if line.tax_code is not None else None,
                revenue_account_id=line.revenue_account_id,
                revenue_account_code=line.revenue_account.account_code if line.revenue_account is not None else None,
                line_subtotal_amount=line.line_subtotal_amount,
                line_tax_amount=line.line_tax_amount,
                line_total_amount=line.line_total_amount,
                contract_id=line.contract_id,
                project_id=line.project_id,
                project_job_id=line.project_job_id,
                project_cost_code_id=line.project_cost_code_id,
            )
            for line in sorted(order.lines, key=lambda row: (row.line_number, row.id))
        )
        return SalesOrderDetailDTO(
            id=order.id,
            order_number=order.order_number,
            order_date=order.order_date,
            requested_delivery_date=order.requested_delivery_date,
            customer_id=order.customer_id,
            customer_name=customer.display_name if customer is not None else "",
            currency_code=order.currency_code,
            exchange_rate=order.exchange_rate,
            status_code=order.status_code,
            reference_number=order.reference_number,
            notes=order.notes,
            subtotal_amount=order.subtotal_amount,
            tax_amount=order.tax_amount,
            total_amount=order.total_amount,
            contract_id=order.contract_id,
            project_id=order.project_id,
            source_quote_id=order.source_quote_id,
            converted_to_invoice_id=order.converted_to_invoice_id,
            lines=lines,
        )

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
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
                    entity_type="SalesOrder",
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
