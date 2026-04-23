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
    UpdatePurchaseBillCommand,
)
from seeker_accounting.modules.purchases.dto.purchase_bill_dto import (
    PurchaseBillDetailDTO,
    PurchaseBillLineDTO,
    PurchaseBillListItemDTO,
    PurchaseBillTotalsDTO,
    SupplierOpenBillDTO,
)
from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
from seeker_accounting.modules.purchases.models.purchase_bill_line import PurchaseBillLine
from seeker_accounting.modules.purchases.repositories.purchase_bill_line_repository import (
    PurchaseBillLineRepository,
)
from seeker_accounting.modules.purchases.repositories.purchase_bill_repository import (
    PurchaseBillRepository,
)
from seeker_accounting.modules.purchases.repositories.supplier_payment_allocation_repository import (
    SupplierPaymentAllocationRepository,
)
from seeker_accounting.modules.suppliers.models.supplier import Supplier
from seeker_accounting.modules.suppliers.repositories.supplier_repository import SupplierRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
SupplierRepositoryFactory = Callable[[Session], SupplierRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
TaxCodeRepositoryFactory = Callable[[Session], TaxCodeRepository]
PurchaseBillRepositoryFactory = Callable[[Session], PurchaseBillRepository]
PurchaseBillLineRepositoryFactory = Callable[[Session], PurchaseBillLineRepository]
SupplierPaymentAllocationRepositoryFactory = Callable[[Session], SupplierPaymentAllocationRepository]

_DRAFT_NUMBER_PREFIX = "PB-DRAFT-"
_ALLOWED_STATUS_CODES = {"draft", "posted", "cancelled"}
_ALLOWED_PAYMENT_STATUS_CODES = {"unpaid", "partial", "paid"}


class PurchaseBillService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        supplier_repository_factory: SupplierRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        tax_code_repository_factory: TaxCodeRepositoryFactory,
        purchase_bill_repository_factory: PurchaseBillRepositoryFactory,
        purchase_bill_line_repository_factory: PurchaseBillLineRepositoryFactory,
        supplier_payment_allocation_repository_factory: SupplierPaymentAllocationRepositoryFactory,
        project_dimension_validation_service: ProjectDimensionValidationService,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._supplier_repository_factory = supplier_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._account_repository_factory = account_repository_factory
        self._tax_code_repository_factory = tax_code_repository_factory
        self._purchase_bill_repository_factory = purchase_bill_repository_factory
        self._purchase_bill_line_repository_factory = purchase_bill_line_repository_factory
        self._supplier_payment_allocation_repository_factory = supplier_payment_allocation_repository_factory
        self._project_dimension_validation_service = project_dimension_validation_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_purchase_bills(
        self,
        company_id: int,
        status_code: str | None = None,
        payment_status_code: str | None = None,
    ) -> list[PurchaseBillListItemDTO]:
        self._permission_service.require_permission("purchases.bills.view")
        normalized_status = self._normalize_optional_choice(status_code, _ALLOWED_STATUS_CODES, "Status code")
        normalized_payment_status = self._normalize_optional_choice(
            payment_status_code,
            _ALLOWED_PAYMENT_STATUS_CODES,
            "Payment status code",
        )

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            repository = self._require_bill_repository(uow.session)
            allocation_repository = self._require_allocation_repository(uow.session)

            bills = repository.list_by_company(
                company_id,
                status_code=normalized_status,
                payment_status_code=normalized_payment_status,
            )
            allocated_totals = allocation_repository.get_allocated_totals_for_bill_ids(
                company_id,
                [bill.id for bill in bills if bill.status_code == "posted"],
                posted_only=True,
            )
            return [
                self._to_list_item_dto(
                    bill=bill,
                    company_base_currency_code=company.base_currency_code,
                    allocated_amount=allocated_totals.get(bill.id, Decimal("0.00")),
                    open_balance_amount=self._calculate_open_balance(
                        bill,
                        allocated_totals.get(bill.id, Decimal("0.00")),
                    ),
                )
                for bill in bills
            ]

    def list_purchase_bills_page(
        self,
        company_id: int,
        status_code: str | None = None,
        payment_status_code: str | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> "PaginatedResult[PurchaseBillListItemDTO]":
        """Paginated + searchable purchase bill listing.

        Only the current page's posted bills have allocations fetched, so
        register paging stays cheap on large AP books.
        """
        from seeker_accounting.shared.dto.paginated_result import (
            PaginatedResult,
            normalize_page,
            normalize_page_size,
        )

        self._permission_service.require_permission("purchases.bills.view")
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
            repository = self._require_bill_repository(uow.session)
            allocation_repository = self._require_allocation_repository(uow.session)

            total = repository.count_filtered(
                company_id,
                status_code=normalized_status,
                payment_status_code=normalized_payment_status,
                query=query,
            )
            bills = repository.list_filtered_page(
                company_id,
                status_code=normalized_status,
                payment_status_code=normalized_payment_status,
                query=query,
                limit=safe_size,
                offset=offset,
            )
            allocated_totals = allocation_repository.get_allocated_totals_for_bill_ids(
                company_id,
                [bill.id for bill in bills if bill.status_code == "posted"],
                posted_only=True,
            )
            items = tuple(
                self._to_list_item_dto(
                    bill=bill,
                    company_base_currency_code=company.base_currency_code,
                    allocated_amount=allocated_totals.get(bill.id, Decimal("0.00")),
                    open_balance_amount=self._calculate_open_balance(
                        bill,
                        allocated_totals.get(bill.id, Decimal("0.00")),
                    ),
                )
                for bill in bills
            )

        return PaginatedResult(
            items=items,
            total_count=total,
            page=safe_page,
            page_size=safe_size,
        )

    def get_purchase_bill(self, company_id: int, bill_id: int) -> PurchaseBillDetailDTO:
        self._permission_service.require_permission("purchases.bills.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_bill_repository(uow.session)
            allocation_repository = self._require_allocation_repository(uow.session)

            bill = repository.get_detail(company_id, bill_id)
            if bill is None:
                raise NotFoundError(f"Purchase bill with id {bill_id} was not found.")
            allocated_amount = allocation_repository.get_allocated_totals_for_bill_ids(
                company_id,
                [bill.id],
                posted_only=True,
            ).get(bill.id, Decimal("0.00"))
            return self._to_detail_dto(
                bill=bill,
                allocated_amount=allocated_amount,
                open_balance_amount=self._calculate_open_balance(bill, allocated_amount),
            )

    def create_draft_bill(
        self,
        company_id: int,
        command: CreatePurchaseBillCommand,
    ) -> PurchaseBillDetailDTO:
        self._permission_service.require_permission("purchases.bills.create")
        normalized_command = self._normalize_command(command)

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            supplier_repository = self._require_supplier_repository(uow.session)
            currency_repository = self._require_currency_repository(uow.session)
            account_repository = self._require_account_repository(uow.session)
            tax_code_repository = self._require_tax_code_repository(uow.session)
            bill_repository = self._require_bill_repository(uow.session)
            line_repository = self._require_bill_line_repository(uow.session)

            supplier = self._require_supplier(supplier_repository, company_id, normalized_command.supplier_id)
            self._require_currency(currency_repository, company, normalized_command.currency_code, uow.session)
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
            bill_lines = self._build_bill_lines(
                session=uow.session,
                company_id=company_id,
                bill_date=normalized_command.bill_date,
                header_contract_id=normalized_command.contract_id,
                header_project_id=normalized_command.project_id,
                lines=normalized_command.lines,
                account_repository=account_repository,
                tax_code_repository=tax_code_repository,
            )
            subtotal_amount, tax_amount, total_amount = self._calculate_header_totals(bill_lines)
            self._require_positive_bill_total(total_amount)

            bill = PurchaseBill(
                company_id=company_id,
                bill_number=f"{_DRAFT_NUMBER_PREFIX}{uuid4().hex[:12].upper()}",
                supplier_id=supplier.id,
                bill_date=normalized_command.bill_date,
                due_date=normalized_command.due_date,
                currency_code=normalized_command.currency_code,
                exchange_rate=exchange_rate,
                status_code="draft",
                payment_status_code="unpaid",
                supplier_bill_reference=normalized_command.supplier_bill_reference,
                notes=normalized_command.notes,
                contract_id=normalized_command.contract_id,
                project_id=normalized_command.project_id,
                subtotal_amount=subtotal_amount,
                tax_amount=tax_amount,
                total_amount=total_amount,
            )
            bill_repository.add(bill)
            uow.session.flush()
            bill.bill_number = self._format_draft_number(bill.id)
            bill_repository.save(bill)
            line_repository.replace_lines(company_id, bill.id, bill_lines)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import PURCHASE_BILL_CREATED
            self._record_audit(company_id, PURCHASE_BILL_CREATED, "PurchaseBill", bill.id, "Created purchase bill")
            return self.get_purchase_bill(company_id, bill.id)

    def update_draft_bill(
        self,
        company_id: int,
        bill_id: int,
        command: UpdatePurchaseBillCommand,
    ) -> PurchaseBillDetailDTO:
        self._permission_service.require_permission("purchases.bills.edit")
        normalized_command = self._normalize_update_command(command)

        with self._unit_of_work_factory() as uow:
            company = self._require_company_exists(uow.session, company_id)
            supplier_repository = self._require_supplier_repository(uow.session)
            currency_repository = self._require_currency_repository(uow.session)
            account_repository = self._require_account_repository(uow.session)
            tax_code_repository = self._require_tax_code_repository(uow.session)
            bill_repository = self._require_bill_repository(uow.session)
            line_repository = self._require_bill_line_repository(uow.session)

            bill = bill_repository.get_by_id(company_id, bill_id)
            if bill is None:
                raise NotFoundError(f"Purchase bill with id {bill_id} was not found.")
            if bill.status_code != "draft":
                raise ValidationError("Posted bills cannot be edited through the draft workflow.")

            supplier = self._require_supplier(supplier_repository, company_id, normalized_command.supplier_id)
            self._require_currency(currency_repository, company, normalized_command.currency_code, uow.session)
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
            bill_lines = self._build_bill_lines(
                session=uow.session,
                company_id=company_id,
                bill_date=normalized_command.bill_date,
                header_contract_id=normalized_command.contract_id,
                header_project_id=normalized_command.project_id,
                lines=normalized_command.lines,
                account_repository=account_repository,
                tax_code_repository=tax_code_repository,
            )
            subtotal_amount, tax_amount, total_amount = self._calculate_header_totals(bill_lines)
            self._require_positive_bill_total(total_amount)

            bill.supplier_id = supplier.id
            bill.bill_date = normalized_command.bill_date
            bill.due_date = normalized_command.due_date
            bill.currency_code = normalized_command.currency_code
            bill.exchange_rate = exchange_rate
            bill.supplier_bill_reference = normalized_command.supplier_bill_reference
            bill.notes = normalized_command.notes
            bill.contract_id = normalized_command.contract_id
            bill.project_id = normalized_command.project_id
            bill.subtotal_amount = subtotal_amount
            bill.tax_amount = tax_amount
            bill.total_amount = total_amount
            bill.payment_status_code = "unpaid"
            bill_repository.save(bill)
            line_repository.replace_lines(company_id, bill.id, bill_lines)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import PURCHASE_BILL_UPDATED
            self._record_audit(company_id, PURCHASE_BILL_UPDATED, "PurchaseBill", bill.id, "Updated purchase bill")
            return self.get_purchase_bill(company_id, bill.id)

    def cancel_draft_bill(self, company_id: int, bill_id: int) -> None:
        self._permission_service.require_permission("purchases.bills.cancel")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_bill_repository(uow.session)
            bill = repository.get_by_id(company_id, bill_id)
            if bill is None:
                raise NotFoundError(f"Purchase bill with id {bill_id} was not found.")
            if bill.status_code != "draft":
                raise ValidationError("Posted bills cannot be cancelled through the draft workflow.")

            bill.status_code = "cancelled"
            bill.payment_status_code = "unpaid"
            repository.save(bill)
            uow.commit()

    def list_open_bills_for_supplier(self, company_id: int, supplier_id: int) -> list[SupplierOpenBillDTO]:
        self._permission_service.require_permission("purchases.bills.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            supplier_repository = self._require_supplier_repository(uow.session)
            bill_repository = self._require_bill_repository(uow.session)
            allocation_repository = self._require_allocation_repository(uow.session)

            self._require_supplier(supplier_repository, company_id, supplier_id)
            bills = [
                bill
                for bill in bill_repository.list_by_company(company_id, status_code="posted")
                if bill.supplier_id == supplier_id
            ]
            allocated_totals = allocation_repository.get_allocated_totals_for_bill_ids(
                company_id,
                [bill.id for bill in bills],
                posted_only=True,
            )

            open_bills: list[SupplierOpenBillDTO] = []
            for bill in bills:
                allocated_amount = allocated_totals.get(bill.id, Decimal("0.00"))
                open_balance_amount = self._calculate_open_balance(bill, allocated_amount)
                if open_balance_amount <= Decimal("0.00"):
                    continue
                open_bills.append(
                    SupplierOpenBillDTO(
                        id=bill.id,
                        bill_number=bill.bill_number,
                        bill_date=bill.bill_date,
                        due_date=bill.due_date,
                        currency_code=bill.currency_code,
                        total_amount=bill.total_amount,
                        allocated_amount=allocated_amount,
                        open_balance_amount=open_balance_amount,
                        payment_status_code=bill.payment_status_code,
                    )
                )
            return open_bills

    def _build_bill_lines(
        self,
        *,
        session: Session,
        company_id: int,
        bill_date: date,
        header_contract_id: int | None,
        header_project_id: int | None,
        lines: tuple[PurchaseBillLineCommand, ...],
        account_repository: AccountRepository,
        tax_code_repository: TaxCodeRepository,
    ) -> list[PurchaseBillLine]:
        if not lines:
            raise ValidationError("At least one bill line is required.")

        bill_lines: list[PurchaseBillLine] = []
        for idx, line_cmd in enumerate(lines, start=1):
            expense_account = account_repository.get_by_id(company_id, line_cmd.expense_account_id)
            if expense_account is None:
                raise ValidationError(f"Expense account on line {idx} does not exist.")
            if not expense_account.is_active:
                raise ValidationError(f"Expense account on line {idx} must be active.")

            tax_code: TaxCode | None = None
            if line_cmd.tax_code_id is not None:
                tax_code = tax_code_repository.get_by_id(company_id, line_cmd.tax_code_id)
                if tax_code is None:
                    raise ValidationError(f"Tax code on line {idx} does not exist.")

            resolved_dimensions = self._project_dimension_validation_service.resolve_line_dimensions(
                header_contract_id=header_contract_id,
                header_project_id=header_project_id,
                line_contract_id=line_cmd.contract_id,
                line_project_id=line_cmd.project_id,
                line_project_job_id=line_cmd.project_job_id,
                line_project_cost_code_id=line_cmd.project_cost_code_id,
            )
            self._project_dimension_validation_service.validate_line_dimensions(
                session=session,
                company_id=company_id,
                contract_id=resolved_dimensions.contract_id,
                project_id=resolved_dimensions.project_id,
                project_job_id=resolved_dimensions.project_job_id,
                project_cost_code_id=resolved_dimensions.project_cost_code_id,
                line_number=idx,
            )

            quantity = line_cmd.quantity if line_cmd.quantity is not None else Decimal("1.00")
            unit_cost = line_cmd.unit_cost if line_cmd.unit_cost is not None else Decimal("0.00")
            line_subtotal = self._quantize_money(quantity * unit_cost)
            line_tax = Decimal("0.00")
            if tax_code is not None:
                tax_percent = tax_code.rate_percent / Decimal("100")
                line_tax = self._quantize_money(line_subtotal * tax_percent)
            line_total = self._quantize_money(line_subtotal + line_tax)

            bill_lines.append(
                PurchaseBillLine(
                    line_number=idx,
                    description=line_cmd.description,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    expense_account_id=expense_account.id,
                    tax_code_id=tax_code.id if tax_code is not None else None,
                    line_subtotal_amount=line_subtotal,
                    line_tax_amount=line_tax,
                    line_total_amount=line_total,
                    contract_id=resolved_dimensions.contract_id,
                    project_id=resolved_dimensions.project_id,
                    project_job_id=resolved_dimensions.project_job_id,
                    project_cost_code_id=resolved_dimensions.project_cost_code_id,
                )
            )
        return bill_lines

    def _calculate_header_totals(
        self, lines: list[PurchaseBillLine]
    ) -> tuple[Decimal, Decimal, Decimal]:
        subtotal = sum((line.line_subtotal_amount for line in lines), Decimal("0.00"))
        tax = sum((line.line_tax_amount for line in lines), Decimal("0.00"))
        total = sum((line.line_total_amount for line in lines), Decimal("0.00"))
        return (
            self._quantize_money(subtotal),
            self._quantize_money(tax),
            self._quantize_money(total),
        )

    def _normalize_command(self, command: CreatePurchaseBillCommand) -> CreatePurchaseBillCommand:
        return CreatePurchaseBillCommand(
            supplier_id=self._require_positive_id(command.supplier_id, "Supplier"),
            bill_date=self._require_date(command.bill_date, "Bill date"),
            due_date=self._require_date(command.due_date, "Due date"),
            currency_code=self._normalize_currency_code(command.currency_code),
            exchange_rate=self._normalize_optional_decimal(command.exchange_rate),
            supplier_bill_reference=self._normalize_optional_text(command.supplier_bill_reference),
            notes=self._normalize_optional_text(command.notes),
            contract_id=self._normalize_optional_id(command.contract_id),
            project_id=self._normalize_optional_id(command.project_id),
            lines=self._normalize_line_commands(command.lines),
        )

    def _normalize_update_command(self, command: UpdatePurchaseBillCommand) -> UpdatePurchaseBillCommand:
        return UpdatePurchaseBillCommand(
            supplier_id=self._require_positive_id(command.supplier_id, "Supplier"),
            bill_date=self._require_date(command.bill_date, "Bill date"),
            due_date=self._require_date(command.due_date, "Due date"),
            currency_code=self._normalize_currency_code(command.currency_code),
            exchange_rate=self._normalize_optional_decimal(command.exchange_rate),
            supplier_bill_reference=self._normalize_optional_text(command.supplier_bill_reference),
            notes=self._normalize_optional_text(command.notes),
            contract_id=self._normalize_optional_id(command.contract_id),
            project_id=self._normalize_optional_id(command.project_id),
            lines=self._normalize_line_commands(command.lines),
        )

    def _normalize_line_commands(self, lines: tuple[PurchaseBillLineCommand, ...]) -> tuple[PurchaseBillLineCommand, ...]:
        if len(lines) == 0:
            raise ValidationError("At least one bill line is required.")

        normalized_lines: list[PurchaseBillLineCommand] = []
        for line in lines:
            description = self._require_text(line.description, "Line description")
            quantity = self._normalize_optional_quantity(line.quantity)
            unit_cost = self._normalize_optional_money(line.unit_cost, "Unit cost")
            normalized_lines.append(
                PurchaseBillLineCommand(
                    description=description,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    tax_code_id=self._normalize_optional_id(line.tax_code_id),
                    expense_account_id=self._require_positive_id(line.expense_account_id, "Expense account"),
                    contract_id=self._normalize_optional_id(line.contract_id),
                    project_id=self._normalize_optional_id(line.project_id),
                    project_job_id=self._normalize_optional_id(line.project_job_id),
                    project_cost_code_id=self._normalize_optional_id(line.project_cost_code_id),
                )
            )
        return tuple(normalized_lines)

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

    def _require_currency(self, currency_repo: CurrencyRepository, company: object, currency_code: str, session: Session) -> None:
        currency = session.get(Currency, currency_code)
        if currency is None:
            raise ValidationError("Currency must exist in the reference data.")
        company_base = getattr(company, "base_currency_code", None)
        if company_base != currency_code and not currency.is_active:
            raise ValidationError("Currency must reference an active currency code.")
        _ = currency_repo

    def _require_positive_bill_total(self, total: Decimal) -> None:
        if total <= Decimal("0.00"):
            raise ValidationError("Bill total must be greater than zero.")

    def _require_bill_repository(self, session: Session | None) -> PurchaseBillRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._purchase_bill_repository_factory(session)

    def _require_bill_line_repository(self, session: Session | None) -> PurchaseBillLineRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._purchase_bill_line_repository_factory(session)

    def _require_supplier_repository(self, session: Session | None) -> SupplierRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._supplier_repository_factory(session)

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

    def _require_allocation_repository(self, session: Session | None) -> SupplierPaymentAllocationRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._supplier_payment_allocation_repository_factory(session)

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

    def _normalize_optional_quantity(self, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value < Decimal("0"):
            raise ValidationError("Quantity cannot be negative.")
        return self._quantize_quantity(value)

    def _require_date(self, value: date, label: str) -> date:
        if value is None:
            raise ValidationError(f"{label} is required.")
        return value

    def _require_positive_id(self, value: int, label: str) -> int:
        if value <= 0:
            raise ValidationError(f"{label} is required.")
        return value

    def _require_text(self, value: str, label: str) -> str:
        if not value or not value.strip():
            raise ValidationError(f"{label} is required.")
        return value.strip()

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
                "Exchange rate is required when the bill currency differs from the company base currency."
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

    def _format_draft_number(self, bill_id: int) -> str:
        return f"{_DRAFT_NUMBER_PREFIX}{bill_id:06d}"

    def _calculate_open_balance(self, bill: PurchaseBill, allocated_amount: Decimal) -> Decimal:
        return self._quantize_money(bill.total_amount - allocated_amount)

    def _quantize_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)

    def _quantize_quantity(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0000"), rounding=ROUND_HALF_UP)

    def _quantize_rate(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0000"), rounding=ROUND_HALF_UP)

    def _translate_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "bill_number" in message:
            return ConflictError("A purchase bill with this number already exists.")
        return ValidationError("Purchase bill data could not be saved.")

    def _to_list_item_dto(
        self,
        bill: PurchaseBill,
        company_base_currency_code: str,
        allocated_amount: Decimal,
        open_balance_amount: Decimal,
    ) -> PurchaseBillListItemDTO:
        supplier = bill.supplier
        _ = company_base_currency_code
        return PurchaseBillListItemDTO(
            id=bill.id,
            company_id=bill.company_id,
            bill_number=bill.bill_number,
            supplier_id=bill.supplier_id,
            supplier_code=supplier.supplier_code if supplier is not None else "",
            supplier_name=supplier.display_name if supplier is not None else "",
            bill_date=bill.bill_date,
            due_date=bill.due_date,
            currency_code=bill.currency_code,
            subtotal_amount=bill.subtotal_amount,
            tax_amount=bill.tax_amount,
            total_amount=bill.total_amount,
            allocated_amount=allocated_amount,
            open_balance_amount=open_balance_amount,
            status_code=bill.status_code,
            payment_status_code=bill.payment_status_code,
            posted_at=bill.posted_at,
            updated_at=bill.updated_at,
        )

    def _to_detail_dto(
        self, bill: PurchaseBill, allocated_amount: Decimal, open_balance_amount: Decimal
    ) -> PurchaseBillDetailDTO:
        supplier = bill.supplier
        line_dtos = tuple(
            PurchaseBillLineDTO(
                id=line.id,
                purchase_bill_id=line.purchase_bill_id,
                line_number=line.line_number,
                description=line.description,
                quantity=line.quantity,
                unit_cost=line.unit_cost,
                tax_code_id=line.tax_code_id,
                tax_code_code=line.tax_code.code if line.tax_code is not None else None,
                tax_code_name=line.tax_code.name if line.tax_code is not None else None,
                expense_account_id=line.expense_account_id or 0,
                expense_account_code=line.expense_account.account_code if line.expense_account is not None else "",
                expense_account_name=line.expense_account.account_name if line.expense_account is not None else "",
                line_subtotal_amount=line.line_subtotal_amount,
                line_tax_amount=line.line_tax_amount,
                line_total_amount=line.line_total_amount,
                contract_id=line.contract_id,
                project_id=line.project_id,
                project_job_id=line.project_job_id,
                project_cost_code_id=line.project_cost_code_id,
            )
            for line in sorted(bill.lines, key=lambda x: x.line_number)
        )
        return PurchaseBillDetailDTO(
            id=bill.id,
            company_id=bill.company_id,
            bill_number=bill.bill_number,
            supplier_id=bill.supplier_id,
            supplier_code=supplier.supplier_code if supplier is not None else "",
            supplier_name=supplier.display_name if supplier is not None else "",
            bill_date=bill.bill_date,
            due_date=bill.due_date,
            currency_code=bill.currency_code,
            exchange_rate=bill.exchange_rate,
            status_code=bill.status_code,
            payment_status_code=bill.payment_status_code,
            supplier_bill_reference=bill.supplier_bill_reference,
            notes=bill.notes,
            posted_journal_entry_id=bill.posted_journal_entry_id,
            posted_at=bill.posted_at,
            posted_by_user_id=bill.posted_by_user_id,
            created_at=bill.created_at,
            updated_at=bill.updated_at,
            totals=PurchaseBillTotalsDTO(
                subtotal_amount=bill.subtotal_amount,
                tax_amount=bill.tax_amount,
                total_amount=bill.total_amount,
                allocated_amount=allocated_amount,
                open_balance_amount=open_balance_amount,
            ),
            lines=line_dtos,
            contract_id=bill.contract_id,
            project_id=bill.project_id,
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
