from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.item_commands import CreateItemCommand, UpdateItemCommand
from seeker_accounting.modules.inventory.dto.item_dto import ItemDetailDTO, ItemListItemDTO
from seeker_accounting.modules.inventory.models.item import Item
from seeker_accounting.modules.inventory.repositories.item_category_repository import ItemCategoryRepository
from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.modules.inventory.repositories.unit_of_measure_repository import UnitOfMeasureRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
ItemRepositoryFactory = Callable[[Session], ItemRepository]
UnitOfMeasureRepositoryFactory = Callable[[Session], UnitOfMeasureRepository]
ItemCategoryRepositoryFactory = Callable[[Session], ItemCategoryRepository]

_ALLOWED_ITEM_TYPES = {"stock", "non_stock", "service"}
_ALLOWED_COST_METHODS = {"weighted_average"}


class ItemService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        item_repository_factory: ItemRepositoryFactory,
        unit_of_measure_repository_factory: UnitOfMeasureRepositoryFactory,
        item_category_repository_factory: ItemCategoryRepositoryFactory,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._item_repository_factory = item_repository_factory
        self._uom_repository_factory = unit_of_measure_repository_factory
        self._category_repository_factory = item_category_repository_factory
        self._audit_service = audit_service

    def list_items(
        self,
        company_id: int,
        active_only: bool = False,
        item_type_code: str | None = None,
    ) -> list[ItemListItemDTO]:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._item_repository_factory(uow.session)
            rows = repo.list_by_company(company_id, active_only=active_only, item_type_code=item_type_code)
            return [self._to_list_item_dto(r) for r in rows]

    def get_item(self, company_id: int, item_id: int) -> ItemDetailDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._item_repository_factory(uow.session)
            item = repo.get_by_id(company_id, item_id)
            if item is None:
                raise NotFoundError(f"Item with id {item_id} was not found.")
            return self._to_detail_dto(item)

    def create_item(self, company_id: int, command: CreateItemCommand) -> ItemDetailDTO:
        self._validate_item_fields(command.item_code, command.item_name, command.item_type_code)
        self._validate_stock_config(
            command.item_type_code,
            command.inventory_cost_method_code,
            command.inventory_account_id,
            command.cogs_account_id,
        )

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)

            uom_repo = self._uom_repository_factory(uow.session)
            uom = uom_repo.get_by_id(company_id, command.unit_of_measure_id)
            if uom is None or not uom.is_active:
                raise ValidationError("Unit of measure must exist and be active.")

            if command.item_category_id is not None:
                cat_repo = self._category_repository_factory(uow.session)
                cat = cat_repo.get_by_id(company_id, command.item_category_id)
                if cat is None or not cat.is_active:
                    raise ValidationError("Item category must exist and be active.")

            repo = self._item_repository_factory(uow.session)
            existing = repo.get_by_code(company_id, command.item_code)
            if existing is not None:
                raise ConflictError(f"Item code '{command.item_code}' already exists for this company.")

            item = Item(
                company_id=company_id,
                item_code=command.item_code.strip(),
                item_name=command.item_name.strip(),
                item_type_code=command.item_type_code,
                unit_of_measure_id=command.unit_of_measure_id,
                unit_of_measure_code=uom.code,
                item_category_id=command.item_category_id,
                inventory_cost_method_code=command.inventory_cost_method_code,
                inventory_account_id=command.inventory_account_id,
                cogs_account_id=command.cogs_account_id,
                expense_account_id=command.expense_account_id,
                revenue_account_id=command.revenue_account_id,
                purchase_tax_code_id=command.purchase_tax_code_id,
                sales_tax_code_id=command.sales_tax_code_id,
                reorder_level_quantity=command.reorder_level_quantity,
                description=command.description,
            )
            repo.add(item)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import ITEM_CREATED
            self._record_audit(company_id, ITEM_CREATED, "Item", item.id, "Created inventory item")
            return self._to_detail_dto(item)

    def update_item(self, company_id: int, item_id: int, command: UpdateItemCommand) -> ItemDetailDTO:
        self._validate_item_fields(command.item_code, command.item_name, command.item_type_code)
        self._validate_stock_config(
            command.item_type_code,
            command.inventory_cost_method_code,
            command.inventory_account_id,
            command.cogs_account_id,
        )

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)

            uom_repo = self._uom_repository_factory(uow.session)
            uom = uom_repo.get_by_id(company_id, command.unit_of_measure_id)
            if uom is None or not uom.is_active:
                raise ValidationError("Unit of measure must exist and be active.")

            if command.item_category_id is not None:
                cat_repo = self._category_repository_factory(uow.session)
                cat = cat_repo.get_by_id(company_id, command.item_category_id)
                if cat is None or not cat.is_active:
                    raise ValidationError("Item category must exist and be active.")

            repo = self._item_repository_factory(uow.session)
            item = repo.get_by_id(company_id, item_id)
            if item is None:
                raise NotFoundError(f"Item with id {item_id} was not found.")

            if command.item_code.strip() != item.item_code:
                existing = repo.get_by_code(company_id, command.item_code.strip())
                if existing is not None:
                    raise ConflictError(f"Item code '{command.item_code}' already exists for this company.")

            item.item_code = command.item_code.strip()
            item.item_name = command.item_name.strip()
            item.item_type_code = command.item_type_code
            item.unit_of_measure_id = command.unit_of_measure_id
            item.unit_of_measure_code = uom.code
            item.item_category_id = command.item_category_id
            item.inventory_cost_method_code = command.inventory_cost_method_code
            item.inventory_account_id = command.inventory_account_id
            item.cogs_account_id = command.cogs_account_id
            item.expense_account_id = command.expense_account_id
            item.revenue_account_id = command.revenue_account_id
            item.purchase_tax_code_id = command.purchase_tax_code_id
            item.sales_tax_code_id = command.sales_tax_code_id
            item.reorder_level_quantity = command.reorder_level_quantity
            item.description = command.description
            item.is_active = command.is_active
            repo.save(item)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import ITEM_UPDATED
            self._record_audit(company_id, ITEM_UPDATED, "Item", item.id, "Updated inventory item")
            return self._to_detail_dto(item)

    def deactivate_item(self, company_id: int, item_id: int) -> None:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._item_repository_factory(uow.session)
            item = repo.get_by_id(company_id, item_id)
            if item is None:
                raise NotFoundError(f"Item with id {item_id} was not found.")
            item.is_active = False
            repo.save(item)
            uow.commit()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_item_fields(self, item_code: str, item_name: str, item_type_code: str) -> None:
        if not item_code or not item_code.strip():
            raise ValidationError("Item code is required.")
        if not item_name or not item_name.strip():
            raise ValidationError("Item name is required.")
        if item_type_code not in _ALLOWED_ITEM_TYPES:
            raise ValidationError(f"Item type must be one of: {', '.join(sorted(_ALLOWED_ITEM_TYPES))}")

    def _validate_stock_config(
        self,
        item_type_code: str,
        cost_method: str | None,
        inventory_account_id: int | None,
        cogs_account_id: int | None,
    ) -> None:
        if item_type_code == "stock":
            if not cost_method:
                raise ValidationError("Costing method is required for stock items.")
            if cost_method not in _ALLOWED_COST_METHODS:
                raise ValidationError(
                    f"Costing method must be one of: {', '.join(sorted(_ALLOWED_COST_METHODS))}"
                )
            if inventory_account_id is None:
                raise ValidationError("Inventory account is required for stock items.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _translate_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        msg = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in msg and "item_code" in msg:
            return ConflictError("An item with this code already exists for the company.")
        return ValidationError("Item could not be saved.")

    def _to_list_item_dto(self, item: Item) -> ItemListItemDTO:
        return ItemListItemDTO(
            id=item.id,
            company_id=item.company_id,
            item_code=item.item_code,
            item_name=item.item_name,
            item_type_code=item.item_type_code,
            unit_of_measure_code=item.unit_of_measure_code,
            unit_of_measure_id=item.unit_of_measure_id,
            item_category_id=item.item_category_id,
            inventory_cost_method_code=item.inventory_cost_method_code,
            reorder_level_quantity=item.reorder_level_quantity,
            is_active=item.is_active,
            updated_at=item.updated_at,
        )

    def _to_detail_dto(self, item: Item) -> ItemDetailDTO:
        return ItemDetailDTO(
            id=item.id,
            company_id=item.company_id,
            item_code=item.item_code,
            item_name=item.item_name,
            item_type_code=item.item_type_code,
            unit_of_measure_code=item.unit_of_measure_code,
            unit_of_measure_id=item.unit_of_measure_id,
            item_category_id=item.item_category_id,
            inventory_cost_method_code=item.inventory_cost_method_code,
            inventory_account_id=item.inventory_account_id,
            cogs_account_id=item.cogs_account_id,
            expense_account_id=item.expense_account_id,
            revenue_account_id=item.revenue_account_id,
            purchase_tax_code_id=item.purchase_tax_code_id,
            sales_tax_code_id=item.sales_tax_code_id,
            reorder_level_quantity=item.reorder_level_quantity,
            description=item.description,
            is_active=item.is_active,
            created_at=item.created_at,
            updated_at=item.updated_at,
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
