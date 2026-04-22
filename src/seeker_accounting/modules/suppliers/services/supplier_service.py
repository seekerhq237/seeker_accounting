from __future__ import annotations

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
from seeker_accounting.modules.suppliers.dto.supplier_commands import (
    CreateSupplierCommand,
    CreateSupplierGroupCommand,
    UpdateSupplierCommand,
    UpdateSupplierGroupCommand,
)
from seeker_accounting.modules.suppliers.dto.supplier_dto import (
    SupplierDetailDTO,
    SupplierGroupDTO,
    SupplierGroupListItemDTO,
    SupplierListItemDTO,
)
from seeker_accounting.modules.suppliers.models.supplier import Supplier
from seeker_accounting.modules.suppliers.models.supplier_group import SupplierGroup
from seeker_accounting.modules.suppliers.repositories.supplier_group_repository import SupplierGroupRepository
from seeker_accounting.modules.suppliers.repositories.supplier_repository import SupplierRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CountryRepositoryFactory = Callable[[Session], CountryRepository]
PaymentTermRepositoryFactory = Callable[[Session], PaymentTermRepository]
SupplierGroupRepositoryFactory = Callable[[Session], SupplierGroupRepository]
SupplierRepositoryFactory = Callable[[Session], SupplierRepository]


class SupplierService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        country_repository_factory: CountryRepositoryFactory,
        payment_term_repository_factory: PaymentTermRepositoryFactory,
        supplier_group_repository_factory: SupplierGroupRepositoryFactory,
        supplier_repository_factory: SupplierRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._country_repository_factory = country_repository_factory
        self._payment_term_repository_factory = payment_term_repository_factory
        self._supplier_group_repository_factory = supplier_group_repository_factory
        self._supplier_repository_factory = supplier_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_supplier_groups(self, company_id: int, active_only: bool = False) -> list[SupplierGroupListItemDTO]:
        self._permission_service.require_permission("suppliers.groups.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_supplier_group_repository(uow.session)
            return [self._to_group_list_item_dto(row) for row in repository.list_by_company(company_id, active_only)]

    def get_supplier_group(self, company_id: int, group_id: int) -> SupplierGroupDTO:
        self._permission_service.require_permission("suppliers.groups.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_supplier_group_repository(uow.session)
            group = repository.get_by_id(company_id, group_id)
            if group is None:
                raise NotFoundError(f"Supplier group with id {group_id} was not found.")
            return self._to_group_dto(group)

    def create_supplier_group(self, company_id: int, command: CreateSupplierGroupCommand) -> SupplierGroupDTO:
        self._permission_service.require_permission("suppliers.groups.create")
        normalized_code = self._require_code(command.code, "Supplier group code")
        normalized_name = self._require_text(command.name, "Supplier group name")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_supplier_group_repository(uow.session)
            if repository.code_exists(company_id, normalized_code):
                raise ConflictError("A supplier group with this code already exists for the company.")

            group = SupplierGroup(company_id=company_id, code=normalized_code, name=normalized_name)
            repository.add(group)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_group_integrity_error(exc) from exc
            from seeker_accounting.modules.audit.event_type_catalog import SUPPLIER_GROUP_CREATED
            self._record_audit(company_id, SUPPLIER_GROUP_CREATED, "SupplierGroup", group.id, f"Created supplier group {group.code}")
            return self._to_group_dto(group)

    def update_supplier_group(
        self,
        company_id: int,
        group_id: int,
        command: UpdateSupplierGroupCommand,
    ) -> SupplierGroupDTO:
        self._permission_service.require_permission("suppliers.groups.edit")
        normalized_code = self._require_code(command.code, "Supplier group code")
        normalized_name = self._require_text(command.name, "Supplier group name")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_supplier_group_repository(uow.session)
            group = repository.get_by_id(company_id, group_id)
            if group is None:
                raise NotFoundError(f"Supplier group with id {group_id} was not found.")
            if repository.code_exists(company_id, normalized_code, exclude_group_id=group_id):
                raise ConflictError("A supplier group with this code already exists for the company.")

            group.code = normalized_code
            group.name = normalized_name
            group.is_active = bool(command.is_active)
            repository.save(group)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_group_integrity_error(exc) from exc
            from seeker_accounting.modules.audit.event_type_catalog import SUPPLIER_GROUP_UPDATED
            self._record_audit(company_id, SUPPLIER_GROUP_UPDATED, "SupplierGroup", group.id, f"Updated supplier group {group.code}")
            return self._to_group_dto(group)

    def deactivate_supplier_group(self, company_id: int, group_id: int) -> None:
        self._permission_service.require_permission("suppliers.groups.deactivate")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_supplier_group_repository(uow.session)
            group = repository.get_by_id(company_id, group_id)
            if group is None:
                raise NotFoundError(f"Supplier group with id {group_id} was not found.")
            group.is_active = False
            repository.save(group)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Supplier group could not be deactivated.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import SUPPLIER_GROUP_DEACTIVATED
            self._record_audit(company_id, SUPPLIER_GROUP_DEACTIVATED, "SupplierGroup", group.id, "Deactivated supplier group")
    def list_suppliers(
        self,
        company_id: int,
        active_only: bool = False,
        query: str | None = None,
    ) -> list[SupplierListItemDTO]:
        self._permission_service.require_permission("suppliers.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            supplier_repository = self._require_supplier_repository(uow.session)
            group_repository = self._require_supplier_group_repository(uow.session)
            payment_term_repository = self._require_payment_term_repository(uow.session)

            if query and query.strip():
                suppliers = supplier_repository.search_by_name_or_code(company_id, query, active_only=active_only)
            else:
                suppliers = supplier_repository.list_by_company(company_id, active_only=active_only)

            groups_by_id = {row.id: row for row in group_repository.list_by_company(company_id, active_only=False)}
            payment_terms_by_id = {
                row.id: row for row in payment_term_repository.list_by_company(company_id, active_only=False)
            }
            return [self._to_supplier_list_item_dto(row, groups_by_id, payment_terms_by_id) for row in suppliers]

    def get_supplier(self, company_id: int, supplier_id: int) -> SupplierDetailDTO:
        self._permission_service.require_permission("suppliers.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            supplier_repository = self._require_supplier_repository(uow.session)
            group_repository = self._require_supplier_group_repository(uow.session)
            payment_term_repository = self._require_payment_term_repository(uow.session)

            supplier = supplier_repository.get_by_id(company_id, supplier_id)
            if supplier is None:
                raise NotFoundError(f"Supplier with id {supplier_id} was not found.")

            groups_by_id = {row.id: row for row in group_repository.list_by_company(company_id, active_only=False)}
            payment_terms_by_id = {
                row.id: row for row in payment_term_repository.list_by_company(company_id, active_only=False)
            }
            return self._to_supplier_detail_dto(supplier, groups_by_id, payment_terms_by_id)

    def create_supplier(self, company_id: int, command: CreateSupplierCommand) -> SupplierDetailDTO:
        self._permission_service.require_permission("suppliers.create")
        normalized = self._normalize_create_command(command)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            supplier_repository = self._require_supplier_repository(uow.session)
            group_repository = self._require_supplier_group_repository(uow.session)
            payment_term_repository = self._require_payment_term_repository(uow.session)
            country_repository = self._require_country_repository(uow.session)

            if supplier_repository.code_exists(company_id, normalized.supplier_code):
                raise ConflictError("A supplier with this code already exists for the company.")

            self._validate_supplier_dependencies(
                company_id=company_id,
                supplier_group_id=normalized.supplier_group_id,
                payment_term_id=normalized.payment_term_id,
                country_code=normalized.country_code,
                supplier_group_repository=group_repository,
                payment_term_repository=payment_term_repository,
                country_repository=country_repository,
            )

            supplier = Supplier(
                company_id=company_id,
                supplier_code=normalized.supplier_code,
                display_name=normalized.display_name,
                legal_name=normalized.legal_name,
                supplier_group_id=normalized.supplier_group_id,
                payment_term_id=normalized.payment_term_id,
                tax_identifier=normalized.tax_identifier,
                phone=normalized.phone,
                email=normalized.email,
                address_line_1=normalized.address_line_1,
                address_line_2=normalized.address_line_2,
                city=normalized.city,
                region=normalized.region,
                country_code=normalized.country_code,
                notes=normalized.notes,
            )
            supplier_repository.add(supplier)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_supplier_integrity_error(exc) from exc

            groups_by_id = {row.id: row for row in group_repository.list_by_company(company_id, active_only=False)}
            payment_terms_by_id = {
                row.id: row for row in payment_term_repository.list_by_company(company_id, active_only=False)
            }
            from seeker_accounting.modules.audit.event_type_catalog import SUPPLIER_CREATED
            self._record_audit(company_id, SUPPLIER_CREATED, "Supplier", supplier.id, "Created supplier")
            return self._to_supplier_detail_dto(supplier, groups_by_id, payment_terms_by_id)

    def update_supplier(
        self,
        company_id: int,
        supplier_id: int,
        command: UpdateSupplierCommand,
    ) -> SupplierDetailDTO:
        self._permission_service.require_permission("suppliers.edit")
        normalized = self._normalize_update_command(command)

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            supplier_repository = self._require_supplier_repository(uow.session)
            group_repository = self._require_supplier_group_repository(uow.session)
            payment_term_repository = self._require_payment_term_repository(uow.session)
            country_repository = self._require_country_repository(uow.session)

            supplier = supplier_repository.get_by_id(company_id, supplier_id)
            if supplier is None:
                raise NotFoundError(f"Supplier with id {supplier_id} was not found.")
            if supplier_repository.code_exists(company_id, normalized.supplier_code, exclude_supplier_id=supplier_id):
                raise ConflictError("A supplier with this code already exists for the company.")

            self._validate_supplier_dependencies(
                company_id=company_id,
                supplier_group_id=normalized.supplier_group_id,
                payment_term_id=normalized.payment_term_id,
                country_code=normalized.country_code,
                supplier_group_repository=group_repository,
                payment_term_repository=payment_term_repository,
                country_repository=country_repository,
            )

            supplier.supplier_code = normalized.supplier_code
            supplier.display_name = normalized.display_name
            supplier.legal_name = normalized.legal_name
            supplier.supplier_group_id = normalized.supplier_group_id
            supplier.payment_term_id = normalized.payment_term_id
            supplier.tax_identifier = normalized.tax_identifier
            supplier.phone = normalized.phone
            supplier.email = normalized.email
            supplier.address_line_1 = normalized.address_line_1
            supplier.address_line_2 = normalized.address_line_2
            supplier.city = normalized.city
            supplier.region = normalized.region
            supplier.country_code = normalized.country_code
            supplier.is_active = normalized.is_active
            supplier.notes = normalized.notes
            supplier_repository.save(supplier)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_supplier_integrity_error(exc) from exc

            groups_by_id = {row.id: row for row in group_repository.list_by_company(company_id, active_only=False)}
            payment_terms_by_id = {
                row.id: row for row in payment_term_repository.list_by_company(company_id, active_only=False)
            }
            from seeker_accounting.modules.audit.event_type_catalog import SUPPLIER_UPDATED
            self._record_audit(company_id, SUPPLIER_UPDATED, "Supplier", supplier.id, "Updated supplier")
            return self._to_supplier_detail_dto(supplier, groups_by_id, payment_terms_by_id)

    def deactivate_supplier(self, company_id: int, supplier_id: int) -> None:
        self._permission_service.require_permission("suppliers.deactivate")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repository = self._require_supplier_repository(uow.session)
            supplier = repository.get_by_id(company_id, supplier_id)
            if supplier is None:
                raise NotFoundError(f"Supplier with id {supplier_id} was not found.")
            supplier.is_active = False
            repository.save(supplier)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Supplier could not be deactivated.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import SUPPLIER_DEACTIVATED
            self._record_audit(company_id, SUPPLIER_DEACTIVATED, "Supplier", supplier_id, "Deactivated supplier")
    def _validate_supplier_dependencies(
        self,
        *,
        company_id: int,
        supplier_group_id: int | None,
        payment_term_id: int | None,
        country_code: str | None,
        supplier_group_repository: SupplierGroupRepository,
        payment_term_repository: PaymentTermRepository,
        country_repository: CountryRepository,
    ) -> None:
        if supplier_group_id is not None and supplier_group_repository.get_by_id(company_id, supplier_group_id) is None:
            raise ValidationError("Supplier group must belong to the active company.")
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

    def _require_supplier_group_repository(self, session: Session | None) -> SupplierGroupRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._supplier_group_repository_factory(session)

    def _require_supplier_repository(self, session: Session | None) -> SupplierRepository:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        return self._supplier_repository_factory(session)

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

    def _normalize_create_command(self, command: CreateSupplierCommand) -> CreateSupplierCommand:
        return CreateSupplierCommand(
            supplier_code=self._require_code(command.supplier_code, "Supplier code"),
            display_name=self._require_text(command.display_name, "Display name"),
            legal_name=self._normalize_optional_text(command.legal_name),
            supplier_group_id=self._normalize_optional_id(command.supplier_group_id),
            payment_term_id=self._normalize_optional_id(command.payment_term_id),
            tax_identifier=self._normalize_optional_text(command.tax_identifier),
            phone=self._normalize_optional_text(command.phone),
            email=self._normalize_optional_text(command.email),
            address_line_1=self._normalize_optional_text(command.address_line_1),
            address_line_2=self._normalize_optional_text(command.address_line_2),
            city=self._normalize_optional_text(command.city),
            region=self._normalize_optional_text(command.region),
            country_code=self._normalize_optional_country_code(command.country_code),
            notes=self._normalize_optional_text(command.notes),
        )

    def _normalize_update_command(self, command: UpdateSupplierCommand) -> UpdateSupplierCommand:
        return UpdateSupplierCommand(
            supplier_code=self._require_code(command.supplier_code, "Supplier code"),
            display_name=self._require_text(command.display_name, "Display name"),
            legal_name=self._normalize_optional_text(command.legal_name),
            supplier_group_id=self._normalize_optional_id(command.supplier_group_id),
            payment_term_id=self._normalize_optional_id(command.payment_term_id),
            tax_identifier=self._normalize_optional_text(command.tax_identifier),
            phone=self._normalize_optional_text(command.phone),
            email=self._normalize_optional_text(command.email),
            address_line_1=self._normalize_optional_text(command.address_line_1),
            address_line_2=self._normalize_optional_text(command.address_line_2),
            city=self._normalize_optional_text(command.city),
            region=self._normalize_optional_text(command.region),
            country_code=self._normalize_optional_country_code(command.country_code),
            is_active=bool(command.is_active),
            notes=self._normalize_optional_text(command.notes),
        )

    def _translate_group_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message or "uq_supplier_groups" in message:
            return ConflictError("A supplier group with this code already exists for the company.")
        return ValidationError("Supplier group data could not be saved.")

    def _translate_supplier_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message or "uq_suppliers" in message:
            return ConflictError("A supplier with this code already exists for the company.")
        return ValidationError("Supplier data could not be saved.")

    def _to_group_list_item_dto(self, row: SupplierGroup) -> SupplierGroupListItemDTO:
        return SupplierGroupListItemDTO(id=row.id, code=row.code, name=row.name, is_active=row.is_active)

    def _to_group_dto(self, row: SupplierGroup) -> SupplierGroupDTO:
        return SupplierGroupDTO(
            id=row.id,
            company_id=row.company_id,
            code=row.code,
            name=row.name,
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_supplier_list_item_dto(
        self,
        row: Supplier,
        groups_by_id: dict[int, SupplierGroup],
        payment_terms_by_id: dict[int, PaymentTerm],
    ) -> SupplierListItemDTO:
        group = groups_by_id.get(row.supplier_group_id)
        payment_term = payment_terms_by_id.get(row.payment_term_id)
        return SupplierListItemDTO(
            id=row.id,
            company_id=row.company_id,
            supplier_code=row.supplier_code,
            display_name=row.display_name,
            supplier_group_id=row.supplier_group_id,
            supplier_group_name=group.name if group is not None else None,
            payment_term_id=row.payment_term_id,
            payment_term_name=payment_term.name if payment_term is not None else None,
            country_code=row.country_code,
            is_active=row.is_active,
            updated_at=row.updated_at,
        )

    def _to_supplier_detail_dto(
        self,
        row: Supplier,
        groups_by_id: dict[int, SupplierGroup],
        payment_terms_by_id: dict[int, PaymentTerm],
    ) -> SupplierDetailDTO:
        list_item = self._to_supplier_list_item_dto(row, groups_by_id, payment_terms_by_id)
        return SupplierDetailDTO(
            id=list_item.id,
            company_id=list_item.company_id,
            supplier_code=list_item.supplier_code,
            display_name=list_item.display_name,
            legal_name=row.legal_name,
            supplier_group_id=list_item.supplier_group_id,
            supplier_group_name=list_item.supplier_group_name,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_SUPPLIERS
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_SUPPLIERS,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
