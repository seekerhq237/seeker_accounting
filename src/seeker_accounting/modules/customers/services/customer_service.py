from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.accounting.reference_data.models.payment_term import PaymentTerm
from seeker_accounting.modules.accounting.reference_data.repositories.country_repository import CountryRepository
from seeker_accounting.modules.accounting.reference_data.repositories.payment_term_repository import (
    PaymentTermRepository,
)
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.customers.dto.customer_commands import (
    CreateCustomerCommand,
    CreateCustomerGroupCommand,
    UpdateCustomerCommand,
    UpdateCustomerGroupCommand,
)
from seeker_accounting.modules.customers.dto.customer_dto import (
    CustomerDetailDTO,
    CustomerGroupDTO,
    CustomerGroupListItemDTO,
    CustomerListItemDTO,
)
from seeker_accounting.modules.customers.models.customer import Customer
from seeker_accounting.modules.customers.models.customer_group import CustomerGroup
from seeker_accounting.modules.customers.repositories.customer_group_repository import CustomerGroupRepository
from seeker_accounting.modules.customers.repositories.customer_repository import CustomerRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CountryRepositoryFactory = Callable[[Session], CountryRepository]
PaymentTermRepositoryFactory = Callable[[Session], PaymentTermRepository]
CustomerGroupRepositoryFactory = Callable[[Session], CustomerGroupRepository]
CustomerRepositoryFactory = Callable[[Session], CustomerRepository]


class CustomerService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        country_repository_factory: CountryRepositoryFactory,
        payment_term_repository_factory: PaymentTermRepositoryFactory,
        customer_group_repository_factory: CustomerGroupRepositoryFactory,
        customer_repository_factory: CustomerRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._country_repository_factory = country_repository_factory
        self._payment_term_repository_factory = payment_term_repository_factory
        self._customer_group_repository_factory = customer_group_repository_factory
        self._customer_repository_factory = customer_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_customer_groups(self, company_id: int, active_only: bool = False) -> list[CustomerGroupListItemDTO]:
        self._permission_service.require_permission("customers.groups.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_customer_group_repository(uow.session)
            return [self._to_group_list_item_dto(row) for row in repository.list_by_company(company_id, active_only)]

    def get_customer_group(self, company_id: int, group_id: int) -> CustomerGroupDTO:
        self._permission_service.require_permission("customers.groups.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_customer_group_repository(uow.session)
            group = repository.get_by_id(company_id, group_id)
            if group is None:
                raise NotFoundError(f"Customer group with id {group_id} was not found.")
            return self._to_group_dto(group)

    def create_customer_group(self, company_id: int, command: CreateCustomerGroupCommand) -> CustomerGroupDTO:
        self._permission_service.require_permission("customers.groups.create")
        normalized_code = self._require_code(command.code, "Customer group code")
        normalized_name = self._require_text(command.name, "Customer group name")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_customer_group_repository(uow.session)
            if repository.code_exists(company_id, normalized_code):
                raise ConflictError("A customer group with this code already exists for the company.")

            group = CustomerGroup(company_id=company_id, code=normalized_code, name=normalized_name)
            repository.add(group)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_group_integrity_error(exc) from exc
            from seeker_accounting.modules.audit.event_type_catalog import CUSTOMER_GROUP_CREATED
            self._record_audit(company_id, CUSTOMER_GROUP_CREATED, "CustomerGroup", group.id, f"Created customer group {group.code}")
            return self._to_group_dto(group)

    def update_customer_group(
        self,
        company_id: int,
        group_id: int,
        command: UpdateCustomerGroupCommand,
    ) -> CustomerGroupDTO:
        self._permission_service.require_permission("customers.groups.edit")
        normalized_code = self._require_code(command.code, "Customer group code")
        normalized_name = self._require_text(command.name, "Customer group name")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_customer_group_repository(uow.session)
            group = repository.get_by_id(company_id, group_id)
            if group is None:
                raise NotFoundError(f"Customer group with id {group_id} was not found.")
            if repository.code_exists(company_id, normalized_code, exclude_group_id=group_id):
                raise ConflictError("A customer group with this code already exists for the company.")

            group.code = normalized_code
            group.name = normalized_name
            group.is_active = bool(command.is_active)
            repository.save(group)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_group_integrity_error(exc) from exc
            from seeker_accounting.modules.audit.event_type_catalog import CUSTOMER_GROUP_UPDATED
            self._record_audit(company_id, CUSTOMER_GROUP_UPDATED, "CustomerGroup", group.id, f"Updated customer group {group.code}")
            return self._to_group_dto(group)

    def deactivate_customer_group(self, company_id: int, group_id: int) -> None:
        self._permission_service.require_permission("customers.groups.deactivate")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_customer_group_repository(uow.session)
            group = repository.get_by_id(company_id, group_id)
            if group is None:
                raise NotFoundError(f"Customer group with id {group_id} was not found.")
            group.is_active = False
            repository.save(group)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Customer group could not be deactivated.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import CUSTOMER_GROUP_DEACTIVATED
            self._record_audit(company_id, CUSTOMER_GROUP_DEACTIVATED, "CustomerGroup", group.id, "Deactivated customer group")
    def list_customers(
        self,
        company_id: int,
        active_only: bool = False,
        query: str | None = None,
    ) -> list[CustomerListItemDTO]:
        self._permission_service.require_permission("customers.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            customer_repository = self._require_customer_repository(uow.session)
            group_repository = self._require_customer_group_repository(uow.session)
            payment_term_repository = self._require_payment_term_repository(uow.session)

            if query and query.strip():
                customers = customer_repository.search_by_name_or_code(company_id, query, active_only=active_only)
            else:
                customers = customer_repository.list_by_company(company_id, active_only=active_only)

            groups_by_id = {row.id: row for row in group_repository.list_by_company(company_id, active_only=False)}
            payment_terms_by_id = {
                row.id: row for row in payment_term_repository.list_by_company(company_id, active_only=False)
            }
            return [self._to_customer_list_item_dto(row, groups_by_id, payment_terms_by_id) for row in customers]

    def list_customers_page(
        self,
        company_id: int,
        active_only: bool = False,
        query: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> "PaginatedResult[CustomerListItemDTO]":
        """Paginated + searchable customer listing.

        Preferred over :meth:`list_customers` for register UIs so filtering
        and pagination happen in SQL rather than after the full table has
        been hydrated into Python.
        """
        from seeker_accounting.shared.dto.paginated_result import (
            PaginatedResult,
            normalize_page,
            normalize_page_size,
        )

        self._permission_service.require_permission("customers.view")
        safe_page = normalize_page(page)
        safe_size = normalize_page_size(page_size)
        offset = (safe_page - 1) * safe_size

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            customer_repository = self._require_customer_repository(uow.session)
            group_repository = self._require_customer_group_repository(uow.session)
            payment_term_repository = self._require_payment_term_repository(uow.session)

            total = customer_repository.count_filtered(
                company_id, query=query, active_only=active_only
            )
            customers = customer_repository.list_filtered_page(
                company_id,
                query=query,
                active_only=active_only,
                limit=safe_size,
                offset=offset,
            )
            groups_by_id = {row.id: row for row in group_repository.list_by_company(company_id, active_only=False)}
            payment_terms_by_id = {
                row.id: row for row in payment_term_repository.list_by_company(company_id, active_only=False)
            }
            items = [
                self._to_customer_list_item_dto(row, groups_by_id, payment_terms_by_id)
                for row in customers
            ]

        return PaginatedResult(
            items=tuple(items),
            total_count=total,
            page=safe_page,
            page_size=safe_size,
        )

    def get_customer(self, company_id: int, customer_id: int) -> CustomerDetailDTO:
        self._permission_service.require_permission("customers.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            customer_repository = self._require_customer_repository(uow.session)
            group_repository = self._require_customer_group_repository(uow.session)
            payment_term_repository = self._require_payment_term_repository(uow.session)

            customer = customer_repository.get_by_id(company_id, customer_id)
            if customer is None:
                raise NotFoundError(f"Customer with id {customer_id} was not found.")

            groups_by_id = {row.id: row for row in group_repository.list_by_company(company_id, active_only=False)}
            payment_terms_by_id = {
                row.id: row for row in payment_term_repository.list_by_company(company_id, active_only=False)
            }
            return self._to_customer_detail_dto(customer, groups_by_id, payment_terms_by_id)

    def create_customer(self, company_id: int, command: CreateCustomerCommand) -> CustomerDetailDTO:
        self._permission_service.require_permission("customers.create")
        normalized = self._normalize_create_command(command)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            customer_repository = self._require_customer_repository(uow.session)
            group_repository = self._require_customer_group_repository(uow.session)
            payment_term_repository = self._require_payment_term_repository(uow.session)
            country_repository = self._require_country_repository(uow.session)

            if customer_repository.code_exists(company_id, normalized.customer_code):
                raise ConflictError("A customer with this code already exists for the company.")

            self._validate_customer_dependencies(
                company_id=company_id,
                customer_group_id=normalized.customer_group_id,
                payment_term_id=normalized.payment_term_id,
                country_code=normalized.country_code,
                customer_group_repository=group_repository,
                payment_term_repository=payment_term_repository,
                country_repository=country_repository,
            )

            customer = Customer(
                company_id=company_id,
                customer_code=normalized.customer_code,
                display_name=normalized.display_name,
                legal_name=normalized.legal_name,
                customer_group_id=normalized.customer_group_id,
                payment_term_id=normalized.payment_term_id,
                tax_identifier=normalized.tax_identifier,
                phone=normalized.phone,
                email=normalized.email,
                address_line_1=normalized.address_line_1,
                address_line_2=normalized.address_line_2,
                city=normalized.city,
                region=normalized.region,
                country_code=normalized.country_code,
                credit_limit_amount=normalized.credit_limit_amount,
                notes=normalized.notes,
            )
            customer_repository.add(customer)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_customer_integrity_error(exc) from exc

            groups_by_id = {row.id: row for row in group_repository.list_by_company(company_id, active_only=False)}
            payment_terms_by_id = {
                row.id: row for row in payment_term_repository.list_by_company(company_id, active_only=False)
            }
            from seeker_accounting.modules.audit.event_type_catalog import CUSTOMER_CREATED
            self._record_audit(company_id, CUSTOMER_CREATED, "Customer", customer.id, f"Created customer")
            return self._to_customer_detail_dto(customer, groups_by_id, payment_terms_by_id)

    def update_customer(
        self,
        company_id: int,
        customer_id: int,
        command: UpdateCustomerCommand,
    ) -> CustomerDetailDTO:
        self._permission_service.require_permission("customers.edit")
        normalized = self._normalize_update_command(command)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            customer_repository = self._require_customer_repository(uow.session)
            group_repository = self._require_customer_group_repository(uow.session)
            payment_term_repository = self._require_payment_term_repository(uow.session)
            country_repository = self._require_country_repository(uow.session)

            customer = customer_repository.get_by_id(company_id, customer_id)
            if customer is None:
                raise NotFoundError(f"Customer with id {customer_id} was not found.")
            if customer_repository.code_exists(company_id, normalized.customer_code, exclude_customer_id=customer_id):
                raise ConflictError("A customer with this code already exists for the company.")

            self._validate_customer_dependencies(
                company_id=company_id,
                customer_group_id=normalized.customer_group_id,
                payment_term_id=normalized.payment_term_id,
                country_code=normalized.country_code,
                customer_group_repository=group_repository,
                payment_term_repository=payment_term_repository,
                country_repository=country_repository,
            )

            customer.customer_code = normalized.customer_code
            customer.display_name = normalized.display_name
            customer.legal_name = normalized.legal_name
            customer.customer_group_id = normalized.customer_group_id
            customer.payment_term_id = normalized.payment_term_id
            customer.tax_identifier = normalized.tax_identifier
            customer.phone = normalized.phone
            customer.email = normalized.email
            customer.address_line_1 = normalized.address_line_1
            customer.address_line_2 = normalized.address_line_2
            customer.city = normalized.city
            customer.region = normalized.region
            customer.country_code = normalized.country_code
            customer.credit_limit_amount = normalized.credit_limit_amount
            customer.is_active = normalized.is_active
            customer.notes = normalized.notes
            customer_repository.save(customer)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_customer_integrity_error(exc) from exc

            groups_by_id = {row.id: row for row in group_repository.list_by_company(company_id, active_only=False)}
            payment_terms_by_id = {
                row.id: row for row in payment_term_repository.list_by_company(company_id, active_only=False)
            }
            from seeker_accounting.modules.audit.event_type_catalog import CUSTOMER_UPDATED
            self._record_audit(company_id, CUSTOMER_UPDATED, "Customer", customer.id, "Updated customer")
            return self._to_customer_detail_dto(customer, groups_by_id, payment_terms_by_id)

    def deactivate_customer(self, company_id: int, customer_id: int) -> None:
        self._permission_service.require_permission("customers.deactivate")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_customer_repository(uow.session)
            customer = repository.get_by_id(company_id, customer_id)
            if customer is None:
                raise NotFoundError(f"Customer with id {customer_id} was not found.")
            customer.is_active = False
            repository.save(customer)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Customer could not be deactivated.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import CUSTOMER_DEACTIVATED
            self._record_audit(company_id, CUSTOMER_DEACTIVATED, "Customer", customer_id, "Deactivated customer")
    def _validate_customer_dependencies(
        self,
        *,
        company_id: int,
        customer_group_id: int | None,
        payment_term_id: int | None,
        country_code: str | None,
        customer_group_repository: CustomerGroupRepository,
        payment_term_repository: PaymentTermRepository,
        country_repository: CountryRepository,
    ) -> None:
        if customer_group_id is not None and customer_group_repository.get_by_id(company_id, customer_group_id) is None:
            raise ValidationError("Customer group must belong to the active company.")
        if payment_term_id is not None and payment_term_repository.get_by_id(company_id, payment_term_id) is None:
            raise ValidationError("Payment term must belong to the active company.")
        if country_code is not None and not country_repository.exists_active(country_code):
            raise ValidationError("Country must reference an active country code.")

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repository = self._company_repository_factory(session)
        if repository.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _require_country_repository(self, session: Session | None) -> CountryRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._country_repository_factory(session)

    def _require_payment_term_repository(self, session: Session | None) -> PaymentTermRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._payment_term_repository_factory(session)

    def _require_customer_group_repository(self, session: Session | None) -> CustomerGroupRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._customer_group_repository_factory(session)

    def _require_customer_repository(self, session: Session | None) -> CustomerRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._customer_repository_factory(session)

    def _require_text(self, value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValidationError(f"{label} is required.")
        return normalized

    def _require_code(self, value: str, label: str) -> str:
        normalized = self._require_text(value, label).upper()
        return normalized.replace(" ", "")

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def _normalize_optional_country_code(self, value: str | None) -> str | None:
        normalized = self._normalize_optional_text(value)
        return normalized.upper() if normalized is not None else None

    def _normalize_optional_id(self, value: int | None) -> int | None:
        if value is None or value <= 0:
            return None
        return value

    def _normalize_optional_decimal(self, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value < 0:
            raise ValidationError("Credit limit amount cannot be negative.")
        return value.quantize(Decimal("0.01"))

    def _normalize_create_command(self, command: CreateCustomerCommand) -> CreateCustomerCommand:
        return CreateCustomerCommand(
            customer_code=self._require_code(command.customer_code, "Customer code"),
            display_name=self._require_text(command.display_name, "Display name"),
            legal_name=self._normalize_optional_text(command.legal_name),
            customer_group_id=self._normalize_optional_id(command.customer_group_id),
            payment_term_id=self._normalize_optional_id(command.payment_term_id),
            tax_identifier=self._normalize_optional_text(command.tax_identifier),
            phone=self._normalize_optional_text(command.phone),
            email=self._normalize_optional_text(command.email),
            address_line_1=self._normalize_optional_text(command.address_line_1),
            address_line_2=self._normalize_optional_text(command.address_line_2),
            city=self._normalize_optional_text(command.city),
            region=self._normalize_optional_text(command.region),
            country_code=self._normalize_optional_country_code(command.country_code),
            credit_limit_amount=self._normalize_optional_decimal(command.credit_limit_amount),
            notes=self._normalize_optional_text(command.notes),
        )

    def _normalize_update_command(self, command: UpdateCustomerCommand) -> UpdateCustomerCommand:
        return UpdateCustomerCommand(
            customer_code=self._require_code(command.customer_code, "Customer code"),
            display_name=self._require_text(command.display_name, "Display name"),
            legal_name=self._normalize_optional_text(command.legal_name),
            customer_group_id=self._normalize_optional_id(command.customer_group_id),
            payment_term_id=self._normalize_optional_id(command.payment_term_id),
            tax_identifier=self._normalize_optional_text(command.tax_identifier),
            phone=self._normalize_optional_text(command.phone),
            email=self._normalize_optional_text(command.email),
            address_line_1=self._normalize_optional_text(command.address_line_1),
            address_line_2=self._normalize_optional_text(command.address_line_2),
            city=self._normalize_optional_text(command.city),
            region=self._normalize_optional_text(command.region),
            country_code=self._normalize_optional_country_code(command.country_code),
            credit_limit_amount=self._normalize_optional_decimal(command.credit_limit_amount),
            is_active=bool(command.is_active),
            notes=self._normalize_optional_text(command.notes),
        )

    def _translate_group_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message or "uq_customer_groups" in message:
            return ConflictError("A customer group with this code already exists for the company.")
        return ValidationError("Customer group data could not be saved.")

    def _translate_customer_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message or "uq_customers" in message:
            return ConflictError("A customer with this code already exists for the company.")
        return ValidationError("Customer data could not be saved.")

    def _to_group_list_item_dto(self, row: CustomerGroup) -> CustomerGroupListItemDTO:
        return CustomerGroupListItemDTO(id=row.id, code=row.code, name=row.name, is_active=row.is_active)

    def _to_group_dto(self, row: CustomerGroup) -> CustomerGroupDTO:
        return CustomerGroupDTO(
            id=row.id,
            company_id=row.company_id,
            code=row.code,
            name=row.name,
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_customer_list_item_dto(
        self,
        row: Customer,
        groups_by_id: dict[int, CustomerGroup],
        payment_terms_by_id: dict[int, PaymentTerm],
    ) -> CustomerListItemDTO:
        group = groups_by_id.get(row.customer_group_id)
        payment_term = payment_terms_by_id.get(row.payment_term_id)
        return CustomerListItemDTO(
            id=row.id,
            company_id=row.company_id,
            customer_code=row.customer_code,
            display_name=row.display_name,
            customer_group_id=row.customer_group_id,
            customer_group_name=group.name if group is not None else None,
            payment_term_id=row.payment_term_id,
            payment_term_name=payment_term.name if payment_term is not None else None,
            country_code=row.country_code,
            credit_limit_amount=row.credit_limit_amount,
            is_active=row.is_active,
            updated_at=row.updated_at,
        )

    def _to_customer_detail_dto(
        self,
        row: Customer,
        groups_by_id: dict[int, CustomerGroup],
        payment_terms_by_id: dict[int, PaymentTerm],
    ) -> CustomerDetailDTO:
        list_item = self._to_customer_list_item_dto(row, groups_by_id, payment_terms_by_id)
        return CustomerDetailDTO(
            id=list_item.id,
            company_id=list_item.company_id,
            customer_code=list_item.customer_code,
            display_name=list_item.display_name,
            legal_name=row.legal_name,
            customer_group_id=list_item.customer_group_id,
            customer_group_name=list_item.customer_group_name,
            payment_term_id=list_item.payment_term_id,
            payment_term_name=list_item.payment_term_name,
            tax_identifier=row.tax_identifier,
            phone=row.phone,
            email=row.email,
            address_line_1=row.address_line_1,
            address_line_2=row.address_line_2,
            city=row.city,
            region=row.region,
            country_code=row.country_code,
            credit_limit_amount=row.credit_limit_amount,
            is_active=row.is_active,
            notes=row.notes,
            created_at=row.created_at,
            updated_at=row.updated_at,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_CUSTOMERS
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_CUSTOMERS,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
