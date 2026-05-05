from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.inventory.models.item_attribute_definition import ItemAttributeDefinition
from seeker_accounting.modules.inventory.models.item_variant import ItemVariant


class ItemVariantRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_attributes(self, company_id: int, active_only: bool = False) -> list[ItemAttributeDefinition]:
        stmt = select(ItemAttributeDefinition).where(ItemAttributeDefinition.company_id == company_id)
        if active_only:
            stmt = stmt.where(ItemAttributeDefinition.is_active.is_(True))
        stmt = stmt.order_by(ItemAttributeDefinition.sort_order, ItemAttributeDefinition.attribute_code)
        return list(self._session.scalars(stmt))

    def get_attribute(self, company_id: int, attribute_id: int) -> ItemAttributeDefinition | None:
        stmt = select(ItemAttributeDefinition).where(
            ItemAttributeDefinition.company_id == company_id,
            ItemAttributeDefinition.id == attribute_id,
        )
        return self._session.scalar(stmt)

    def get_attribute_by_code(
        self,
        company_id: int,
        item_category_id: int | None,
        attribute_code: str,
    ) -> ItemAttributeDefinition | None:
        stmt = select(ItemAttributeDefinition).where(
            ItemAttributeDefinition.company_id == company_id,
            ItemAttributeDefinition.attribute_code == attribute_code,
        )
        if item_category_id is None:
            stmt = stmt.where(ItemAttributeDefinition.item_category_id.is_(None))
        else:
            stmt = stmt.where(ItemAttributeDefinition.item_category_id == item_category_id)
        return self._session.scalar(stmt)

    def list_variants(self, company_id: int, parent_item_id: int | None = None) -> list[ItemVariant]:
        stmt = (
            select(ItemVariant)
            .where(ItemVariant.company_id == company_id)
            .options(selectinload(ItemVariant.child_item), selectinload(ItemVariant.parent_item))
        )
        if parent_item_id is not None:
            stmt = stmt.where(ItemVariant.parent_item_id == parent_item_id)
        stmt = stmt.order_by(ItemVariant.parent_item_id, ItemVariant.id)
        return list(self._session.scalars(stmt))

    def get_variant(self, company_id: int, variant_id: int) -> ItemVariant | None:
        stmt = (
            select(ItemVariant)
            .where(ItemVariant.company_id == company_id, ItemVariant.id == variant_id)
            .options(selectinload(ItemVariant.child_item), selectinload(ItemVariant.parent_item))
        )
        return self._session.scalar(stmt)

    def get_variant_by_child(self, company_id: int, child_item_id: int) -> ItemVariant | None:
        stmt = select(ItemVariant).where(
            ItemVariant.company_id == company_id,
            ItemVariant.child_item_id == child_item_id,
        )
        return self._session.scalar(stmt)

    def get_variant_by_hash(
        self,
        company_id: int,
        parent_item_id: int,
        attribute_value_combination_hash: str,
    ) -> ItemVariant | None:
        stmt = select(ItemVariant).where(
            ItemVariant.company_id == company_id,
            ItemVariant.parent_item_id == parent_item_id,
            ItemVariant.attribute_value_combination_hash == attribute_value_combination_hash,
        )
        return self._session.scalar(stmt)

    def add_attribute(self, entity: ItemAttributeDefinition) -> ItemAttributeDefinition:
        self._session.add(entity)
        return entity

    def save_attribute(self, entity: ItemAttributeDefinition) -> ItemAttributeDefinition:
        self._session.add(entity)
        return entity

    def add_variant(self, entity: ItemVariant) -> ItemVariant:
        self._session.add(entity)
        return entity

    def save_variant(self, entity: ItemVariant) -> ItemVariant:
        self._session.add(entity)
        return entity