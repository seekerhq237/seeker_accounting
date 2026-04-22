from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.inventory_reference_commands import (
    CreateItemCategoryCommand,
    UpdateItemCategoryCommand,
)
from seeker_accounting.modules.inventory.dto.inventory_reference_dto import ItemCategoryDTO
from seeker_accounting.modules.inventory.models.item_category import ItemCategory
from seeker_accounting.modules.inventory.repositories.item_category_repository import ItemCategoryRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
ItemCategoryRepositoryFactory = Callable[[Session], ItemCategoryRepository]


class ItemCategoryService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        item_category_repository_factory: ItemCategoryRepositoryFactory,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._repo_factory = item_category_repository_factory
        self._audit_service = audit_service

    def list_item_categories(self, company_id: int, active_only: bool = False) -> list[ItemCategoryDTO]:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._repo_factory(uow.session)
            return [self._to_dto(r) for r in repo.list_by_company(company_id, active_only=active_only)]

    def get_item_category(self, company_id: int, category_id: int) -> ItemCategoryDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._repo_factory(uow.session)
            cat = repo.get_by_id(company_id, category_id)
            if cat is None:
                raise NotFoundError(f"Item category with id {category_id} was not found.")
            return self._to_dto(cat)

    def create_item_category(self, company_id: int, command: CreateItemCategoryCommand) -> ItemCategoryDTO:
        self._validate_fields(command.code, command.name)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._repo_factory(uow.session)
            if repo.code_exists(company_id, command.code.strip().upper()):
                raise ConflictError(f"Item category code '{command.code}' already exists for this company.")
            cat = ItemCategory(
                company_id=company_id,
                code=command.code.strip().upper(),
                name=command.name.strip(),
                description=command.description,
            )
            repo.add(cat)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError("Item category could not be saved.") from exc
            from seeker_accounting.modules.audit.event_type_catalog import ITEM_CATEGORY_CREATED
            self._record_audit(company_id, ITEM_CATEGORY_CREATED, "ItemCategory", cat.id, "Created item category")
            return self._to_dto(cat)

    def update_item_category(
        self, company_id: int, category_id: int, command: UpdateItemCategoryCommand
    ) -> ItemCategoryDTO:
        self._validate_fields(command.code, command.name)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._repo_factory(uow.session)
            cat = repo.get_by_id(company_id, category_id)
            if cat is None:
                raise NotFoundError(f"Item category with id {category_id} was not found.")
            new_code = command.code.strip().upper()
            if new_code != cat.code and repo.code_exists(company_id, new_code, exclude_id=category_id):
                raise ConflictError(f"Item category code '{command.code}' already exists for this company.")
            cat.code = new_code
            cat.name = command.name.strip()
            cat.description = command.description
            cat.is_active = command.is_active
            repo.save(cat)
            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError("Item category could not be saved.") from exc
            from seeker_accounting.modules.audit.event_type_catalog import ITEM_CATEGORY_UPDATED
            self._record_audit(company_id, ITEM_CATEGORY_UPDATED, "ItemCategory", cat.id, "Updated item category")
            return self._to_dto(cat)

    def deactivate_item_category(self, company_id: int, category_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._repo_factory(uow.session)
            cat = repo.get_by_id(company_id, category_id)
            if cat is None:
                raise NotFoundError(f"Item category with id {category_id} was not found.")
            cat.is_active = False
            repo.save(cat)
            uow.commit()

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

    def _to_dto(self, cat: ItemCategory) -> ItemCategoryDTO:
        return ItemCategoryDTO(
            id=cat.id,
            company_id=cat.company_id,
            code=cat.code,
            name=cat.name,
            description=cat.description,
            is_active=cat.is_active,
            created_at=cat.created_at,
            updated_at=cat.updated_at,
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
