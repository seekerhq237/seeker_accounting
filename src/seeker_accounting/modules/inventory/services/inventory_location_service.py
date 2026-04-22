from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.inventory_reference_commands import (
    CreateInventoryLocationCommand,
    UpdateInventoryLocationCommand,
)
from seeker_accounting.modules.inventory.dto.inventory_reference_dto import InventoryLocationDTO
from seeker_accounting.modules.inventory.models.inventory_location import InventoryLocation
from seeker_accounting.modules.inventory.repositories.inventory_location_repository import InventoryLocationRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
InventoryLocationRepositoryFactory = Callable[[Session], InventoryLocationRepository]


class InventoryLocationService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        inventory_location_repository_factory: InventoryLocationRepositoryFactory,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._repo_factory = inventory_location_repository_factory
        self._audit_service = audit_service

    def list_inventory_locations(self, company_id: int, active_only: bool = False) -> list[InventoryLocationDTO]:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._repo_factory(uow.session)
            return [self._to_dto(r) for r in repo.list_by_company(company_id, active_only=active_only)]

    def get_inventory_location(self, company_id: int, location_id: int) -> InventoryLocationDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._repo_factory(uow.session)
            loc = repo.get_by_id(company_id, location_id)
            if loc is None:
                raise NotFoundError(f"Inventory location with id {location_id} was not found.")
            return self._to_dto(loc)

    def create_inventory_location(
        self, company_id: int, command: CreateInventoryLocationCommand
    ) -> InventoryLocationDTO:
        self._validate_fields(command.code, command.name)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._repo_factory(uow.session)
            if repo.code_exists(company_id, command.code.strip().upper()):
                raise ConflictError(f"Inventory location code '{command.code}' already exists for this company.")
            loc = InventoryLocation(
                company_id=company_id,
                code=command.code.strip().upper(),
                name=command.name.strip(),
                description=command.description,
            )
            repo.add(loc)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError("Inventory location could not be saved.") from exc
            from seeker_accounting.modules.audit.event_type_catalog import INVENTORY_LOCATION_CREATED
            self._record_audit(company_id, INVENTORY_LOCATION_CREATED, "InventoryLocation", loc.id, "Created inventory location")
            return self._to_dto(loc)

    def update_inventory_location(
        self, company_id: int, location_id: int, command: UpdateInventoryLocationCommand
    ) -> InventoryLocationDTO:
        self._validate_fields(command.code, command.name)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._repo_factory(uow.session)
            loc = repo.get_by_id(company_id, location_id)
            if loc is None:
                raise NotFoundError(f"Inventory location with id {location_id} was not found.")
            new_code = command.code.strip().upper()
            if new_code != loc.code and repo.code_exists(company_id, new_code, exclude_id=location_id):
                raise ConflictError(f"Inventory location code '{command.code}' already exists for this company.")
            loc.code = new_code
            loc.name = command.name.strip()
            loc.description = command.description
            loc.is_active = command.is_active
            repo.save(loc)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError("Inventory location could not be saved.") from exc
            from seeker_accounting.modules.audit.event_type_catalog import INVENTORY_LOCATION_UPDATED
            self._record_audit(company_id, INVENTORY_LOCATION_UPDATED, "InventoryLocation", loc.id, "Updated inventory location")
            return self._to_dto(loc)

    def deactivate_inventory_location(self, company_id: int, location_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._repo_factory(uow.session)
            loc = repo.get_by_id(company_id, location_id)
            if loc is None:
                raise NotFoundError(f"Inventory location with id {location_id} was not found.")
            loc.is_active = False
            repo.save(loc)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import INVENTORY_LOCATION_DEACTIVATED
            self._record_audit(company_id, INVENTORY_LOCATION_DEACTIVATED, "InventoryLocation", location_id, "Deactivated inventory location")

    def _validate_fields(self, code: str, name: str) -> None:
        if not code or not code.strip():
            raise ValidationError("Code is required.")
        if not name or not name.strip():
            raise ValidationError("Name is required.")

    def _require_company(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _to_dto(self, loc: InventoryLocation) -> InventoryLocationDTO:
        return InventoryLocationDTO(
            id=loc.id,
            company_id=loc.company_id,
            code=loc.code,
            name=loc.name,
            description=loc.description,
            is_active=loc.is_active,
            created_at=loc.created_at,
            updated_at=loc.updated_at,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_INVENTORY
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_INVENTORY,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
