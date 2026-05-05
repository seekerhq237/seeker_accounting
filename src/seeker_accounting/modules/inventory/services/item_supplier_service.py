"""Item Supplier Service — P2 / Slice 3.4.

Manages the item-supplier catalog: add, update, delete, and set preferred
supplier. The GoodsReceiptService calls update_last_cost() after posting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.inventory.models.item_supplier import ItemSupplier
from seeker_accounting.modules.inventory.repositories.item_supplier_repository import (
    ItemSupplierRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

ItemSupplierRepositoryFactory = Callable[[Session], ItemSupplierRepository]


@dataclass
class ItemSupplierDTO:
    id: int | None
    company_id: int
    item_id: int
    supplier_id: int
    supplier_item_code: str | None
    supplier_uom_id: int | None
    last_unit_cost: Decimal | None
    last_currency_code: str | None
    last_purchase_date: date | None
    lead_time_days: int | None
    is_preferred: bool
    minimum_order_qty: Decimal | None
    notes: str | None


class ItemSupplierService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        item_supplier_repository_factory: ItemSupplierRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._repo_factory = item_supplier_repository_factory

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_for_item(self, company_id: int, item_id: int) -> list[ItemSupplierDTO]:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            rows = repo.list_by_item(company_id, item_id)
            return [_to_dto(r) for r in rows]

    def list_for_supplier(self, company_id: int, supplier_id: int) -> list[ItemSupplierDTO]:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            rows = repo.list_by_supplier(company_id, supplier_id)
            return [_to_dto(r) for r in rows]

    # ------------------------------------------------------------------
    # Create / update
    # ------------------------------------------------------------------

    def save(self, cmd: ItemSupplierDTO) -> ItemSupplierDTO:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)

            if cmd.id is not None:
                row = repo.get(cmd.id)
                if row is None:
                    raise NotFoundError(f"Item supplier {cmd.id} not found.")
            else:
                existing = repo.get_by_item_supplier(
                    cmd.company_id, cmd.item_id, cmd.supplier_id
                )
                if existing is not None:
                    raise ConflictError(
                        "An item-supplier record already exists for this combination."
                    )
                row = ItemSupplier(company_id=cmd.company_id)
                repo.add(row)

            row.item_id = cmd.item_id
            row.supplier_id = cmd.supplier_id
            row.supplier_item_code = cmd.supplier_item_code
            row.supplier_uom_id = cmd.supplier_uom_id
            row.last_unit_cost = cmd.last_unit_cost
            row.last_currency_code = cmd.last_currency_code
            row.last_purchase_date = cmd.last_purchase_date
            row.lead_time_days = cmd.lead_time_days
            row.minimum_order_qty = cmd.minimum_order_qty
            row.notes = cmd.notes

            if cmd.is_preferred:
                self._clear_preferred(uow.session, cmd.company_id, cmd.item_id, exclude_id=row.id)
            row.is_preferred = cmd.is_preferred

            uow.session.flush()
            uow.commit()
            return _to_dto(row)

    def set_preferred(
        self, company_id: int, item_id: int, item_supplier_id: int
    ) -> None:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            target = repo.get(item_supplier_id)
            if target is None or target.company_id != company_id or target.item_id != item_id:
                raise NotFoundError(f"Item supplier {item_supplier_id} not found.")
            self._clear_preferred(uow.session, company_id, item_id, exclude_id=target.id)
            target.is_preferred = True
            uow.commit()

    def delete(self, company_id: int, item_supplier_id: int) -> None:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            row = repo.get(item_supplier_id)
            if row is None or row.company_id != company_id:
                raise NotFoundError(f"Item supplier {item_supplier_id} not found.")
            repo.delete(row)
            uow.commit()

    # ------------------------------------------------------------------
    # Called by GoodsReceiptService on GRN post
    # ------------------------------------------------------------------

    def update_last_cost(
        self,
        session: Session,
        company_id: int,
        item_id: int,
        supplier_id: int,
        unit_cost: Decimal,
        currency_code: str,
        purchase_date: date,
    ) -> None:
        """Update last-cost fields in-session (no UoW — caller owns the tx)."""
        repo = self._repo_factory(session)
        row = repo.get_by_item_supplier(company_id, item_id, supplier_id)
        if row is not None:
            row.last_unit_cost = unit_cost
            row.last_currency_code = currency_code
            row.last_purchase_date = purchase_date

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clear_preferred(
        self, session: Session, company_id: int, item_id: int, exclude_id: int | None
    ) -> None:
        repo = self._repo_factory(session)
        preferred = repo.get_preferred(company_id, item_id)
        if preferred is not None and preferred.id != exclude_id:
            preferred.is_preferred = False


def _to_dto(row: ItemSupplier) -> ItemSupplierDTO:
    return ItemSupplierDTO(
        id=row.id,
        company_id=row.company_id,
        item_id=row.item_id,
        supplier_id=row.supplier_id,
        supplier_item_code=row.supplier_item_code,
        supplier_uom_id=row.supplier_uom_id,
        last_unit_cost=row.last_unit_cost,
        last_currency_code=row.last_currency_code,
        last_purchase_date=row.last_purchase_date,
        lead_time_days=row.lead_time_days,
        is_preferred=row.is_preferred,
        minimum_order_qty=row.minimum_order_qty,
        notes=row.notes,
    )
