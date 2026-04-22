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
from seeker_accounting.modules.job_costing.services.project_dimension_validation_service import (
    ProjectDimensionValidationService,
)
from seeker_accounting.modules.purchases.dto.purchase_bill_commands import (
    CreatePurchaseBillCommand,
    PurchaseBillLineCommand,
)
from seeker_accounting.modules.purchases.dto.purchase_order_commands import (
    ConvertPurchaseOrderCommand,
    CreatePurchaseOrderCommand,
    PurchaseOrderLineCommand,
    UpdatePurchaseOrderCommand,
)
from seeker_accounting.modules.purchases.dto.purchase_order_dto import (
    PurchaseOrderConversionResultDTO,
    PurchaseOrderDetailDTO,
    PurchaseOrderLineDTO,
    PurchaseOrderListItemDTO,
    PurchaseOrderTotalsDTO,
)
from seeker_accounting.modules.purchases.models.purchase_order import PurchaseOrder
from seeker_accounting.modules.purchases.models.purchase_order_line import PurchaseOrderLine
from seeker_accounting.modules.purchases.repositories.purchase_bill_repository import PurchaseBillRepository
from seeker_accounting.modules.purchases.repositories.purchase_order_line_repository import (
    PurchaseOrderLineRepository,
)
from seeker_accounting.modules.purchases.repositories.purchase_order_repository import PurchaseOrderRepository
from seeker_accounting.modules.suppliers.repositories.supplier_repository import SupplierRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService
    from seeker_accounting.modules.purchases.services.purchase_bill_service import PurchaseBillService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
SupplierRepositoryFactory = Callable[[Session], SupplierRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
TaxCodeRepositoryFactory = Callable[[Session], TaxCodeRepository]
PurchaseOrderRepositoryFactory = Callable[[Session], PurchaseOrderRepository]
PurchaseOrderLineRepositoryFactory = Callable[[Session], PurchaseOrderLineRepository]
PurchaseBillRepositoryFactory = Callable[[Session], PurchaseBillRepository]

_DRAFT_NUMBER_PREFIX = "PO-DRAFT-"
_FINALIZED_NUMBER_PREFIX = "PO-"
_ALLOWED_STATUS_FILTERS = frozenset({"draft", "sent", "acknowledged", "cancelled", "converted"})


class PurchaseOrderService:
    """Manage purchase orders and their lifecycle (draft → sent → acknowledged → converted/cancelled)."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        supplier_repository_factory: SupplierRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        tax_code_repository_factory: TaxCodeRepositoryFactory,
        purchase_order_repository_factory: PurchaseOrderRepositoryFactory,
        purchase_order_line_repository_factory: PurchaseOrderLineRepositoryFactory,
        purchase_bill_repository_factory: PurchaseBillRepositoryFactory,
        purchase_bill_service: "PurchaseBillService",
        project_dimension_validation_service: ProjectDimensionValidationService,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._supplier_repository_factory = supplier_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._account_repository_factory = account_repository_factory
        self._tax_code_repository_factory = tax_code_repository_factory
        self._purchase_order_repository_factory = purchase_order_repository_factory
        self._purchase_order_line_repository_factory = purchase_order_line_repository_factory
        self._purchase_bill_repository_factory = purchase_bill_repository_factory
        self._purchase_bill_service = purchase_bill_service
        self._project_dimension_validation_service = project_dimension_validation_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ── Read ──────────────────────────────────────────────────────────────────
    def list_orders(
        self,
        company_id: int,
        status_code: str | None = None,
    ) -> list[PurchaseOrderListItemDTO]:
        self._permission_service.require_permission("purchases.orders.view")
        normalized_status = self._normalize_optional_choice(status_code, _ALLOWED_STATUS_FILTERS, "Status code")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_order_repository(uow.session)
            orders = repository.list_by_company(company_id, status_code=normalized_status)
            return [self._to_list_item_dto(order) for order in orders]

    def get_order(self, company_id: int, order_id: int) -> PurchaseOrderDetailDTO:
        self._permission_service.require_permission("purchases.orders.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_order_repository(uow.session)
            order = repository.get_detail(company_id, order_id)
            if order is None:
                raise NotFoundError(f"Purchase order with id {order_id} was not found.")
            return self._to_detail_dto(order)

    # ── Create / update drafts ─────────────────────────────────────────────────
    def create_draft_order(
        self,
        company_id: int,
        command: CreatePurchaseOrderCommand,
    ) -> PurchaseOrderDetailDTO:
        self._permission_service.require_permission("purchases.orders.create")
        normalized_command = self._normalize_create_command(command)

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            supplier_repository = self._require_supplier_repository(uow.session)
            account_repository = self._require_account_repository(uow.session)
            tax_code_repository = self._require_tax_code_repository(uow.session)
            order_repository = self._require_order_repository(uow.session)
            line_repository = self._require_order_line_repository(uow.session)

            supplier = self._require_supplier(supplier_repository, company_id, normalized_command.supplier_id)
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

            order = PurchaseOrder(
                company_id=company_id,
                order_number=f"{_DRAFT_NUMBER_PREFIX}{uuid4().hex[:12].upper()}",
                supplier_id=supplier.id,
                order_date=normalized_command.order_date,
                expected_delivery_date=normalized_command.expected_delivery_date,
                currency_code=normalized_command.currency_code,
                exchange_rate=exchange_rate,
                status_code="draft",
                reference_number=normalized_command.reference_number,
                notes=normalized_command.notes,
                contract_id=normalized_command.contract_id,
                project_id=normalized_command.project_id,
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

        from seeker_accounting.modules.audit.event_type_catalog import PURCHASE_ORDER_CREATED
        self._record_audit(company_id, PURCHASE_ORDER_CREATED, order.id, "Created purchase order")
        return self.get_order(company_id, order.id)

    def update_draft_order(
        self,
        company_id: int,
        order_id: int,
        command: UpdatePurchaseOrderCommand,
    ) -> PurchaseOrderDetailDTO:
        self._permission_service.require_permission("purchases.orders.edit")
        normalized_command = self._normalize_update_command(command)

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            supplier_repository = self._require_supplier_repository(uow.session)
            account_repository = self._require_account_repository(uow.session)
            tax_code_repository = self._require_tax_code_repository(uow.session)
            order_repository = self._require_order_repository(uow.session)
            line_repository = self._require_order_line_repository(uow.session)

            order = order_repository.get_by_id(company_id, order_id)
            if order is None:
                raise NotFoundError(f"Purchase order with id {order_id} was not found.")
            if order.status_code != "draft":
                raise ValidationError("Only draft orders can be edited.")

            supplier = self._require_supplier(supplier_repository, company_id, normalized_command.supplier_id)
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

            order.supplier_id = supplier.id
            order.order_date = normalized_command.order_date
            order.expected_delivery_date = normalized_command.expected_delivery_date
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

        from seeker_accounting.modules.audit.event_type_catalog import PURCHASE_ORDER_UPDATED
        self._record_audit(company_id, PURCHASE_ORDER_UPDATED, order.id, "Updated purchase order")
        return self.get_order(company_id, order.id)

    # ── Lifecycle transitions ──────────────────────────────────────────────────
    def send_order(self, company_id: int, order_id: int) -> PurchaseOrderDetailDTO:
        """Mark order as sent to supplier (draft → sent). Assigns final PO number."""
        self._permission_service.require_permission("purchases.orders.send")
        return self._transition_status(
            company_id=company_id,
            order_id=order_id,
            allowed_from={"draft"},
            new_status="sent",
            finalize_number=True,
            audit_event_code_name="PURCHASE_ORDER_SENT",
            audit_description="Sent purchase order to supplier",
        )

    def acknowledge_order(self, company_id: int, order_id: int) -> PurchaseOrderDetailDTO:
        """Mark order as acknowledged by supplier (sent → acknowledged)."""
        self._permission_service.require_permission("purchases.orders.acknowledge")
        return self._transition_status(
            company_id=company_id,
            order_id=order_id,
            allowed_from={"sent"},
            new_status="acknowledged",
            finalize_number=False,
            audit_event_code_name="PURCHASE_ORDER_ACKNOWLEDGED",
            audit_description="Supplier acknowledged purchase order",
        )

    def cancel_order(self, company_id: int, order_id: int) -> PurchaseOrderDetailDTO:
        """Cancel a draft or sent purchase order."""
        self._permission_service.require_permission("purchases.orders.cancel")
        return self._transition_status(
            company_id=company_id,
            order_id=order_id,
            allowed_from={"draft", "sent"},
            new_status="cancelled",
            finalize_number=False,
            audit_event_code_name="PURCHASE_ORDER_CANCELLED",
            audit_description="Cancelled purchase order",
        )

    # ── Convert to purchase bill ───────────────────────────────────────────────
    def convert_to_bill(
        self,
        company_id: int,
        order_id: int,
        command: ConvertPurchaseOrderCommand,
    ) -> PurchaseOrderConversionResultDTO:
        self._permission_service.require_permission("purchases.orders.convert")
        self._permission_service.require_permission("purchases.bills.create")

        bill_date = self._require_date(command.bill_date, "Bill date")
        due_date = self._require_date(command.due_date, "Due date")
        reference_number = self._normalize_optional_text(command.reference_number)
        notes = self._normalize_optional_text(command.notes)

        # Phase 1: validate order and snapshot data to build the bill command.
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            order_repository = self._require_order_repository(uow.session)
            line_repository = self._require_order_line_repository(uow.session)

            order = order_repository.get_by_id(company_id, order_id)
            if order is None:
                raise NotFoundError(f"Purchase order with id {order_id} was not found.")
            if order.status_code != "acknowledged":
                raise ValidationError("Only acknowledged orders can be converted to a bill.")
            if order.converted_to_bill_id is not None:
                raise ConflictError("This purchase order has already been converted to a bill.")

            order_lines = line_repository.list_for_order(company_id, order.id)
            if len(order_lines) == 0:
                raise ValidationError("Purchase order has no lines to convert.")

            bill_line_commands: list[PurchaseBillLineCommand] = []
            for line in order_lines:
                bill_line_commands.append(
                    PurchaseBillLineCommand(
                        description=line.description,
                        quantity=line.quantity,
                        unit_cost=line.unit_cost,
                        tax_code_id=line.tax_code_id,
                        expense_account_id=line.expense_account_id if line.expense_account_id is not None else 0,
                        contract_id=line.contract_id,
                        project_id=line.project_id,
                        project_job_id=line.project_job_id,
                        project_cost_code_id=line.project_cost_code_id,
                    )
                )

            create_bill_command = CreatePurchaseBillCommand(
                supplier_id=order.supplier_id,
                bill_date=bill_date,
                due_date=due_date,
                currency_code=order.currency_code,
                exchange_rate=order.exchange_rate,
                supplier_bill_reference=reference_number if reference_number is not None else order.order_number,
                notes=notes if notes is not None else order.notes,
                contract_id=order.contract_id,
                project_id=order.project_id,
                lines=tuple(bill_line_commands),
            )

        # Phase 2: create the draft bill through the bill service (own transaction).
        bill_detail = self._purchase_bill_service.create_draft_bill(company_id, create_bill_command)

        # Phase 3: mark the order converted and link it to the bill.
        with self._unit_of_work_factory() as uow:
            order_repository = self._require_order_repository(uow.session)
            bill_repository = self._require_bill_repository(uow.session)
            order = order_repository.get_by_id(company_id, order_id)
            if order is None:
                raise NotFoundError(f"Purchase order with id {order_id} was not found.")
            order.status_code = "converted"
            order.converted_to_bill_id = bill_detail.id
            order_repository.save(order)

            bill = bill_repository.get_by_id(company_id, bill_detail.id)
            if bill is not None:
                bill.source_order_id = order.id
                bill_repository.save(bill)
            uow.commit()

        from seeker_accounting.modules.audit.event_type_catalog import PURCHASE_ORDER_CONVERTED
        self._record_audit(
            company_id,
            PURCHASE_ORDER_CONVERTED,
            order_id,
            f"Converted purchase order to bill {bill_detail.bill_number}",
        )
        return PurchaseOrderConversionResultDTO(
            order_id=order_id,
            order_number=self._get_order_number(company_id, order_id),
            purchase_bill_id=bill_detail.id,
            bill_number=bill_detail.bill_number,
        )

    # ── Internal helpers ───────────────────────────────────────────────────────
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
    ) -> PurchaseOrderDetailDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_order_repository(uow.session)
            order = repository.get_by_id(company_id, order_id)
            if order is None:
                raise NotFoundError(f"Purchase order with id {order_id} was not found.")
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

    def _normalize_create_command(self, command: CreatePurchaseOrderCommand) -> CreatePurchaseOrderCommand:
        return CreatePurchaseOrderCommand(
            supplier_id=self._require_positive_id(command.supplier_id, "Supplier"),
            order_date=self._require_date(command.order_date, "Order date"),
            expected_delivery_date=self._normalize_optional_delivery_date(
                command.expected_delivery_date, command.order_date
            ),
            currency_code=self._normalize_currency_code(command.currency_code),
            exchange_rate=self._normalize_optional_decimal(command.exchange_rate),
            reference_number=self._normalize_optional_text(command.reference_number),
            notes=self._normalize_optional_text(command.notes),
            contract_id=self._normalize_optional_id(command.contract_id),
            project_id=self._normalize_optional_id(command.project_id),
            lines=self._normalize_line_commands(command.lines),
        )

    def _normalize_update_command(self, command: UpdatePurchaseOrderCommand) -> UpdatePurchaseOrderCommand:
        return UpdatePurchaseOrderCommand(
            supplier_id=self._require_positive_id(command.supplier_id, "Supplier"),
            order_date=self._require_date(command.order_date, "Order date"),
            expected_delivery_date=self._normalize_optional_delivery_date(
                command.expected_delivery_date, command.order_date
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
        lines: tuple[PurchaseOrderLineCommand, ...],
    ) -> tuple[PurchaseOrderLineCommand, ...]:
        if len(lines) == 0:
            raise ValidationError("At least one order line is required.")
        normalized: list[PurchaseOrderLineCommand] = []
        for line in lines:
            description = self._require_text(line.description, "Line description")
            quantity = self._normalize_quantity(line.quantity)
            unit_cost = self._normalize_money(line.unit_cost, "Unit cost")
            discount_percent = self._normalize_optional_percent(line.discount_percent)
            discount_amount = self._normalize_optional_money(line.discount_amount, "Discount amount")
            if discount_percent is not None and discount_amount is not None:
                raise ValidationError("Only one discount method may be supplied per order line.")
            normalized.append(
                PurchaseOrderLineCommand(
                    description=description,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    discount_percent=discount_percent,
                    discount_amount=discount_amount,
                    tax_code_id=line.tax_code_id if line.tax_code_id and line.tax_code_id > 0 else None,
                    expense_account_id=self._normalize_optional_id(line.expense_account_id),
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
        lines: tuple[PurchaseOrderLineCommand, ...],
        account_repository: AccountRepository,
        tax_code_repository: TaxCodeRepository,
    ) -> list[PurchaseOrderLine]:
        built: list[PurchaseOrderLine] = []
        for line_number, command in enumerate(lines, start=1):
            expense_account_id: int | None = None
            if command.expense_account_id is not None:
                expense_account = self._require_expense_account(
                    account_repository, company_id, command.expense_account_id
                )
                expense_account_id = expense_account.id
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
                PurchaseOrderLine(
                    purchase_order_id=0,
                    line_number=line_number,
                    description=command.description,
                    quantity=command.quantity,
                    unit_cost=command.unit_cost,
                    discount_percent=command.discount_percent,
                    discount_amount=command.discount_amount,
                    tax_code_id=tax_code.id if tax_code is not None else None,
                    expense_account_id=expense_account_id,
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
        command: PurchaseOrderLineCommand,
        tax_code: TaxCode | None,
    ) -> tuple[Decimal, Decimal, Decimal]:
        base_amount = self._quantize_money(command.quantity * command.unit_cost)
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

    def _calculate_header_totals(self, lines: list[PurchaseOrderLine]) -> tuple[Decimal, Decimal, Decimal]:
        subtotal_amount = self._quantize_money(sum((l.line_subtotal_amount for l in lines), Decimal("0.00")))
        tax_amount = self._quantize_money(sum((l.line_tax_amount for l in lines), Decimal("0.00")))
        total_amount = self._quantize_money(sum((l.line_total_amount for l in lines), Decimal("0.00")))
        return subtotal_amount, tax_amount, total_amount

    # ── Repository getters ─────────────────────────────────────────────────────
    def _require_company_exists(self, session: Session | None, company_id: int):
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repository = self._company_repository_factory(session)
        company = repository.get_by_id(company_id)
        if company is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")
        return company

    def _require_supplier_repository(self, session: Session | None) -> SupplierRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._supplier_repository_factory(session)

    def _require_account_repository(self, session: Session | None) -> AccountRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._account_repository_factory(session)

    def _require_tax_code_repository(self, session: Session | None) -> TaxCodeRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._tax_code_repository_factory(session)

    def _require_order_repository(self, session: Session | None) -> PurchaseOrderRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._purchase_order_repository_factory(session)

    def _require_order_line_repository(self, session: Session | None) -> PurchaseOrderLineRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._purchase_order_line_repository_factory(session)

    def _require_bill_repository(self, session: Session | None) -> PurchaseBillRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._purchase_bill_repository_factory(session)

    # ── Validation helpers ─────────────────────────────────────────────────────
    def _require_supplier(self, supplier_repository: SupplierRepository, company_id: int, supplier_id: int):
        supplier = supplier_repository.get_by_id(company_id, supplier_id)
        if supplier is None:
            raise ValidationError("Supplier must belong to the active company.")
        return supplier

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

    def _require_expense_account(
        self,
        account_repository: AccountRepository,
        company_id: int,
        account_id: int,
    ):
        account = account_repository.get_by_id(company_id, account_id)
        if account is None:
            raise ValidationError("Expense account must belong to the active company.")
        if not account.is_active:
            raise ValidationError("Expense account must be active.")
        if not account.allow_manual_posting:
            raise ValidationError("Expense account must allow manual posting.")
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

    # ── Normalizers ────────────────────────────────────────────────────────────
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
            raise ValidationError("Expected delivery date cannot be earlier than the order date.")
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
            return ConflictError("A purchase order with this number already exists.")
        return ValidationError("Purchase order data could not be saved.")

    # ── DTO mapping ────────────────────────────────────────────────────────────
    def _to_list_item_dto(self, order: PurchaseOrder) -> PurchaseOrderListItemDTO:
        supplier = order.supplier
        return PurchaseOrderListItemDTO(
            id=order.id,
            company_id=order.company_id,
            order_number=order.order_number,
            supplier_id=order.supplier_id,
            supplier_code=supplier.supplier_code if supplier is not None else "",
            supplier_name=supplier.display_name if supplier is not None else "",
            order_date=order.order_date,
            expected_delivery_date=order.expected_delivery_date,
            currency_code=order.currency_code,
            subtotal_amount=order.subtotal_amount,
            tax_amount=order.tax_amount,
            total_amount=order.total_amount,
            status_code=order.status_code,
            converted_to_bill_id=order.converted_to_bill_id,
            updated_at=order.updated_at,
        )

    def _to_detail_dto(self, order: PurchaseOrder) -> PurchaseOrderDetailDTO:
        supplier = order.supplier
        lines = tuple(
            PurchaseOrderLineDTO(
                id=line.id,
                purchase_order_id=line.purchase_order_id,
                line_number=line.line_number,
                description=line.description,
                quantity=line.quantity,
                unit_cost=line.unit_cost,
                discount_percent=line.discount_percent,
                discount_amount=line.discount_amount,
                tax_code_id=line.tax_code_id,
                tax_code_code=line.tax_code.code if line.tax_code is not None else None,
                tax_code_name=line.tax_code.name if line.tax_code is not None else None,
                expense_account_id=line.expense_account_id,
                expense_account_code=line.expense_account.account_code if line.expense_account is not None else None,
                expense_account_name=line.expense_account.account_name if line.expense_account is not None else None,
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
        totals = PurchaseOrderTotalsDTO(
            subtotal_amount=order.subtotal_amount,
            tax_amount=order.tax_amount,
            total_amount=order.total_amount,
        )
        return PurchaseOrderDetailDTO(
            id=order.id,
            company_id=order.company_id,
            order_number=order.order_number,
            supplier_id=order.supplier_id,
            supplier_code=supplier.supplier_code if supplier is not None else "",
            supplier_name=supplier.display_name if supplier is not None else "",
            order_date=order.order_date,
            expected_delivery_date=order.expected_delivery_date,
            currency_code=order.currency_code,
            exchange_rate=order.exchange_rate,
            status_code=order.status_code,
            reference_number=order.reference_number,
            notes=order.notes,
            converted_to_bill_id=order.converted_to_bill_id,
            created_at=order.created_at,
            updated_at=order.updated_at,
            totals=totals,
            lines=lines,
            contract_id=order.contract_id,
            project_id=order.project_id,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_PURCHASES
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_PURCHASES,
                    entity_type="PurchaseOrder",
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
