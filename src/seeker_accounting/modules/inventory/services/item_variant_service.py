from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.item_commands import CreateItemCommand
from seeker_accounting.modules.inventory.dto.item_variant_dto import (
    CreateItemAttributeDefinitionCommand,
    CreateItemVariantCommand,
    ItemAttributeDefinitionDTO,
    ItemVariantDTO,
    UpdateItemAttributeDefinitionCommand,
)
from seeker_accounting.modules.inventory.models.item import Item
from seeker_accounting.modules.inventory.models.item_attribute_definition import ItemAttributeDefinition
from seeker_accounting.modules.inventory.models.item_variant import ItemVariant
from seeker_accounting.modules.inventory.repositories.item_category_repository import ItemCategoryRepository
from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.modules.inventory.repositories.item_variant_repository import ItemVariantRepository
from seeker_accounting.modules.inventory.repositories.unit_of_measure_repository import UnitOfMeasureRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService


CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
ItemRepositoryFactory = Callable[[Session], ItemRepository]
ItemVariantRepositoryFactory = Callable[[Session], ItemVariantRepository]
UnitOfMeasureRepositoryFactory = Callable[[Session], UnitOfMeasureRepository]
ItemCategoryRepositoryFactory = Callable[[Session], ItemCategoryRepository]

_ALLOWED_ITEM_TYPES = {"stock", "non_stock", "service"}
_ALLOWED_COST_METHODS = {"weighted_average", "fifo", "fefo", "standard_cost"}
_ALLOWED_TRACKING_MODES = {"none", "batch", "serial"}


class ItemVariantService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        item_repository_factory: ItemRepositoryFactory,
        item_variant_repository_factory: ItemVariantRepositoryFactory,
        unit_of_measure_repository_factory: UnitOfMeasureRepositoryFactory,
        item_category_repository_factory: ItemCategoryRepositoryFactory,
        permission_service: PermissionService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._item_repository_factory = item_repository_factory
        self._item_variant_repository_factory = item_variant_repository_factory
        self._uom_repository_factory = unit_of_measure_repository_factory
        self._category_repository_factory = item_category_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_attributes(self, company_id: int, active_only: bool = False) -> list[ItemAttributeDefinitionDTO]:
        self._require_permission("inventory.variants.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._item_variant_repository_factory(uow.session)
            return [self._attribute_to_dto(row) for row in repo.list_attributes(company_id, active_only=active_only)]

    def create_attribute(
        self,
        company_id: int,
        command: CreateItemAttributeDefinitionCommand,
    ) -> ItemAttributeDefinitionDTO:
        self._require_permission("inventory.variants.manage")
        attribute_code = self._normalize_code(command.attribute_code, "Attribute code")
        attribute_name = self._normalize_required(command.attribute_name, "Attribute name")
        self._validate_json_object_or_array(command.allowed_values_json, "Allowed values JSON")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            self._require_category_if_present(uow.session, company_id, command.item_category_id)
            repo = self._item_variant_repository_factory(uow.session)
            if repo.get_attribute_by_code(company_id, command.item_category_id, attribute_code) is not None:
                raise ConflictError("Variant attribute code already exists for this company/category scope.")
            entity = ItemAttributeDefinition(
                company_id=company_id,
                item_category_id=command.item_category_id,
                attribute_code=attribute_code,
                attribute_name=attribute_name,
                allowed_values_json=self._normalize_optional_text(command.allowed_values_json),
                sort_order=command.sort_order,
                is_active=True,
            )
            repo.add_attribute(entity)
            self._commit_or_translate(uow, "Variant attribute conflicts with an existing record.")
            self._record_audit(company_id, "ITEM_VARIANT_UPDATED", "ItemAttributeDefinition", entity.id, f"Variant attribute {entity.attribute_code} created.")
            return self._attribute_to_dto(entity)

    def update_attribute(
        self,
        company_id: int,
        command: UpdateItemAttributeDefinitionCommand,
    ) -> ItemAttributeDefinitionDTO:
        self._require_permission("inventory.variants.manage")
        attribute_code = self._normalize_code(command.attribute_code, "Attribute code")
        attribute_name = self._normalize_required(command.attribute_name, "Attribute name")
        self._validate_json_object_or_array(command.allowed_values_json, "Allowed values JSON")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            self._require_category_if_present(uow.session, company_id, command.item_category_id)
            repo = self._item_variant_repository_factory(uow.session)
            entity = repo.get_attribute(company_id, command.attribute_id)
            if entity is None:
                raise NotFoundError(f"Variant attribute with id {command.attribute_id} was not found.")
            duplicate = repo.get_attribute_by_code(company_id, command.item_category_id, attribute_code)
            if duplicate is not None and duplicate.id != entity.id:
                raise ConflictError("Variant attribute code already exists for this company/category scope.")
            entity.item_category_id = command.item_category_id
            entity.attribute_code = attribute_code
            entity.attribute_name = attribute_name
            entity.allowed_values_json = self._normalize_optional_text(command.allowed_values_json)
            entity.sort_order = command.sort_order
            entity.is_active = command.is_active
            repo.save_attribute(entity)
            self._commit_or_translate(uow, "Variant attribute conflicts with an existing record.")
            self._record_audit(company_id, "ITEM_VARIANT_UPDATED", "ItemAttributeDefinition", entity.id, f"Variant attribute {entity.attribute_code} updated.")
            return self._attribute_to_dto(entity)

    def list_variants(self, company_id: int, parent_item_id: int | None = None) -> list[ItemVariantDTO]:
        self._require_permission("inventory.variants.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._item_variant_repository_factory(uow.session)
            return [self._variant_to_dto(row) for row in repo.list_variants(company_id, parent_item_id)]

    def create_variant(self, company_id: int, command: CreateItemVariantCommand) -> ItemVariantDTO:
        self._require_permission("inventory.variants.manage")
        canonical_json, combination_hash = self._canonical_attribute_values(command.attribute_values_json)
        suffix = self._normalize_optional_text(command.variant_sku_suffix)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            item_repo = self._item_repository_factory(uow.session)
            variant_repo = self._item_variant_repository_factory(uow.session)
            parent = item_repo.get_by_id(company_id, command.parent_item_id)
            if parent is None:
                raise NotFoundError(f"Parent item with id {command.parent_item_id} was not found.")
            if parent.is_variant:
                raise ValidationError("A variant item cannot be used as a variant parent.")
            if variant_repo.get_variant_by_hash(company_id, parent.id, combination_hash) is not None:
                raise ConflictError("A variant with this attribute combination already exists for the parent item.")

            child_command = self._normalize_child_command(parent, command.child_item, canonical_json)
            self._validate_child_item(child_command)
            if item_repo.get_by_code(company_id, child_command.item_code.strip()) is not None:
                raise ConflictError(f"Item code '{child_command.item_code}' already exists for this company.")
            self._require_uom(uow.session, company_id, child_command.unit_of_measure_id)
            self._require_category_if_present(uow.session, company_id, child_command.item_category_id)

            child = Item(
                company_id=company_id,
                item_code=child_command.item_code.strip(),
                item_name=child_command.item_name.strip(),
                item_type_code=child_command.item_type_code,
                unit_of_measure_id=child_command.unit_of_measure_id,
                item_category_id=child_command.item_category_id,
                parent_item_id=parent.id,
                inventory_cost_method_code=child_command.inventory_cost_method_code,
                standard_cost=child_command.standard_cost,
                lifecycle_status_code=child_command.lifecycle_status_code,
                tracking_mode_code=child_command.tracking_mode_code,
                is_variant=True,
                attribute_values_json=canonical_json,
                is_sellable=child_command.is_sellable,
                is_purchasable=child_command.is_purchasable,
                is_stockable=child_command.is_stockable,
                ohada_stock_class_code=child_command.ohada_stock_class_code,
                inventory_account_id=child_command.inventory_account_id,
                cogs_account_id=child_command.cogs_account_id,
                expense_account_id=child_command.expense_account_id,
                revenue_account_id=child_command.revenue_account_id,
                purchase_tax_code_id=child_command.purchase_tax_code_id,
                sales_tax_code_id=child_command.sales_tax_code_id,
                reorder_level_quantity=child_command.reorder_level_quantity,
                description=child_command.description,
            )
            item_repo.add(child)
            uow.session.flush()
            variant = ItemVariant(
                company_id=company_id,
                parent_item_id=parent.id,
                child_item_id=child.id,
                attribute_value_combination_hash=combination_hash,
                attribute_values_json=canonical_json,
                variant_sku_suffix=suffix,
                status_code="active",
            )
            variant_repo.add_variant(variant)
            self._commit_or_translate(uow, "Item variant conflicts with an existing record.")
            self._record_audit(company_id, "ITEM_VARIANT_CREATED", "ItemVariant", variant.id, f"Variant {child.item_code} created.")
            return self._variant_to_dto(variant)

    def deactivate_variant(self, company_id: int, variant_id: int) -> ItemVariantDTO:
        self._require_permission("inventory.variants.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._item_variant_repository_factory(uow.session)
            variant = repo.get_variant(company_id, variant_id)
            if variant is None:
                raise NotFoundError(f"Item variant with id {variant_id} was not found.")
            variant.status_code = "inactive"
            variant.child_item.is_active = False
            repo.save_variant(variant)
            self._commit_or_translate(uow, "Item variant could not be deactivated.")
            self._record_audit(company_id, "ITEM_VARIANT_UPDATED", "ItemVariant", variant.id, f"Variant {variant.child_item.item_code} deactivated.")
            return self._variant_to_dto(variant)

    def _normalize_child_command(
        self,
        parent: Item,
        child_command: CreateItemCommand,
        canonical_json: str,
    ) -> CreateItemCommand:
        return CreateItemCommand(
            item_code=child_command.item_code,
            item_name=child_command.item_name,
            item_type_code=child_command.item_type_code or parent.item_type_code,
            unit_of_measure_id=child_command.unit_of_measure_id or parent.unit_of_measure_id,
            item_category_id=child_command.item_category_id if child_command.item_category_id is not None else parent.item_category_id,
            inventory_cost_method_code=child_command.inventory_cost_method_code or parent.inventory_cost_method_code,
            standard_cost=child_command.standard_cost if child_command.standard_cost is not None else parent.standard_cost,
            lifecycle_status_code=child_command.lifecycle_status_code,
            tracking_mode_code=child_command.tracking_mode_code or parent.tracking_mode_code,
            parent_item_id=parent.id,
            is_variant=True,
            attribute_values_json=canonical_json,
            is_sellable=child_command.is_sellable,
            is_purchasable=child_command.is_purchasable,
            is_stockable=child_command.is_stockable,
            ohada_stock_class_code=child_command.ohada_stock_class_code or parent.ohada_stock_class_code,
            inventory_account_id=child_command.inventory_account_id if child_command.inventory_account_id is not None else parent.inventory_account_id,
            cogs_account_id=child_command.cogs_account_id if child_command.cogs_account_id is not None else parent.cogs_account_id,
            expense_account_id=child_command.expense_account_id if child_command.expense_account_id is not None else parent.expense_account_id,
            revenue_account_id=child_command.revenue_account_id if child_command.revenue_account_id is not None else parent.revenue_account_id,
            purchase_tax_code_id=child_command.purchase_tax_code_id if child_command.purchase_tax_code_id is not None else parent.purchase_tax_code_id,
            sales_tax_code_id=child_command.sales_tax_code_id if child_command.sales_tax_code_id is not None else parent.sales_tax_code_id,
            reorder_level_quantity=child_command.reorder_level_quantity,
            description=child_command.description,
        )

    @staticmethod
    def _validate_child_item(command: CreateItemCommand) -> None:
        if not command.item_code.strip():
            raise ValidationError("Variant child item code is required.")
        if not command.item_name.strip():
            raise ValidationError("Variant child item name is required.")
        if command.item_type_code not in _ALLOWED_ITEM_TYPES:
            raise ValidationError("Variant child item type is invalid.")
        if command.tracking_mode_code not in _ALLOWED_TRACKING_MODES:
            raise ValidationError("Variant child tracking mode is invalid.")
        if command.tracking_mode_code != "none" and command.item_type_code != "stock":
            raise ValidationError("Only stock variant items can use batch or serial tracking.")
        if command.item_type_code == "stock":
            if command.inventory_cost_method_code not in _ALLOWED_COST_METHODS:
                raise ValidationError("Variant child stock items require a valid costing method.")
            if command.inventory_account_id is None:
                raise ValidationError("Variant child stock items require an inventory account.")
            if command.inventory_cost_method_code == "standard_cost" and command.standard_cost is None:
                raise ValidationError("Standard-cost variant child items require a standard cost.")

    def _require_permission(self, permission_code: str) -> None:
        if self._permission_service is not None:
            self._permission_service.require_permission(permission_code)

    def _require_company(self, session: Session, company_id: int) -> None:
        if self._company_repository_factory(session).get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _require_uom(self, session: Session, company_id: int, unit_of_measure_id: int) -> None:
        uom = self._uom_repository_factory(session).get_by_id(company_id, unit_of_measure_id)
        if uom is None or not uom.is_active:
            raise ValidationError("Unit of measure must exist and be active.")

    def _require_category_if_present(self, session: Session, company_id: int, item_category_id: int | None) -> None:
        if item_category_id is None:
            return
        category = self._category_repository_factory(session).get_by_id(company_id, item_category_id)
        if category is None or not category.is_active:
            raise ValidationError("Item category must exist and be active.")

    @staticmethod
    def _normalize_required(value: str, label: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValidationError(f"{label} is required.")
        return text

    @classmethod
    def _normalize_code(cls, value: str, label: str) -> str:
        return cls._normalize_required(value, label).upper()

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        text = (value or "").strip()
        return text or None

    @staticmethod
    def _validate_json_object_or_array(value: str | None, label: str) -> None:
        if not value:
            return
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{label} must be valid JSON.") from exc
        if not isinstance(parsed, (dict, list)):
            raise ValidationError(f"{label} must be a JSON object or array.")

    @classmethod
    def _canonical_attribute_values(cls, value: str) -> tuple[str, str]:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError("Variant attribute values must be valid JSON.") from exc
        if not isinstance(parsed, dict) or not parsed:
            raise ValidationError("Variant attribute values must be a non-empty JSON object.")
        normalized: dict[str, object] = {}
        for raw_key, raw_value in parsed.items():
            key = str(raw_key).strip().upper()
            if not key:
                raise ValidationError("Variant attribute values cannot contain a blank attribute code.")
            if key in normalized:
                raise ValidationError(f"Variant attribute '{key}' is repeated.")
            normalized[key] = cls._normalize_attribute_value(raw_value, key)
        canonical_json = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return canonical_json, hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_attribute_value(value: object, key: str) -> object:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValidationError(f"Variant attribute '{key}' requires a value.")
            return text
        if value is None or isinstance(value, (dict, list)):
            raise ValidationError(f"Variant attribute '{key}' must be a scalar value.")
        return value

    def _commit_or_translate(self, uow, message: str) -> None:
        try:
            uow.commit()
        except IntegrityError as exc:
            raise ConflictError(message) from exc

    def _record_audit(self, company_id: int, event_type_code: str, entity_type: str, entity_id: int | None, description: str) -> None:
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
            pass

    @staticmethod
    def _attribute_to_dto(entity: ItemAttributeDefinition) -> ItemAttributeDefinitionDTO:
        return ItemAttributeDefinitionDTO(
            id=entity.id,
            company_id=entity.company_id,
            item_category_id=entity.item_category_id,
            attribute_code=entity.attribute_code,
            attribute_name=entity.attribute_name,
            allowed_values_json=entity.allowed_values_json,
            sort_order=entity.sort_order,
            is_active=entity.is_active,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    @staticmethod
    def _variant_to_dto(entity: ItemVariant) -> ItemVariantDTO:
        return ItemVariantDTO(
            id=entity.id,
            company_id=entity.company_id,
            parent_item_id=entity.parent_item_id,
            child_item_id=entity.child_item_id,
            child_item_code=entity.child_item.item_code,
            child_item_name=entity.child_item.item_name,
            attribute_value_combination_hash=entity.attribute_value_combination_hash,
            attribute_values_json=entity.attribute_values_json,
            variant_sku_suffix=entity.variant_sku_suffix,
            status_code=entity.status_code,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )