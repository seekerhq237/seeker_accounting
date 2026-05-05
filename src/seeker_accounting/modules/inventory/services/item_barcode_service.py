"""Item Barcode Service — P6 / Slice 7.5.

CRUD for item barcodes and resolver for scanner-based item lookup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.inventory.models.item_barcode import ItemBarcode
from seeker_accounting.modules.inventory.repositories.item_barcode_repository import (
    ItemBarcodeRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

ItemBarcodeRepositoryFactory = Callable[[Session], ItemBarcodeRepository]


@dataclass
class ItemBarcodeDTO:
    id: int | None
    item_id: int
    company_id: int
    barcode: str
    barcode_type_code: str
    is_primary: bool


class ItemBarcodeService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        item_barcode_repository_factory: ItemBarcodeRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._repo_factory = item_barcode_repository_factory

    # ------------------------------------------------------------------
    # Resolve barcode for scanner entry
    # ------------------------------------------------------------------

    def resolve_item_by_barcode(
        self, company_id: int, barcode: str
    ) -> int | None:
        """Return item_id for the given barcode, or None if not found."""
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            row = repo.find_by_barcode(company_id, barcode.strip())
            return row.item_id if row else None

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_for_item(self, item_id: int) -> list[ItemBarcodeDTO]:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            rows = repo.list_for_item(item_id)
            return [_to_dto(r) for r in rows]

    def save(self, cmd: ItemBarcodeDTO) -> int:
        if not cmd.barcode.strip():
            raise ValidationError("Barcode value must not be empty.")

        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)

            if cmd.id is not None:
                row = repo.get(cmd.id)
                if row is None:
                    raise NotFoundError(f"Barcode {cmd.id} not found.")
            else:
                existing = repo.find_by_barcode(cmd.company_id, cmd.barcode)
                if existing is not None:
                    raise ConflictError(
                        f"Barcode '{cmd.barcode}' is already assigned to item {existing.item_id}."
                    )
                row = ItemBarcode(company_id=cmd.company_id)
                repo.add(row)

            row.item_id = cmd.item_id
            row.barcode = cmd.barcode.strip()
            row.barcode_type_code = cmd.barcode_type_code
            row.is_primary = cmd.is_primary

            if cmd.is_primary:
                self._clear_primary(uow.session, cmd.item_id, exclude_id=row.id if row.id else None)

            uow.session.flush()
            uow.commit()
            return row.id

    def delete(self, barcode_id: int) -> None:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            row = repo.get(barcode_id)
            if row is None:
                raise NotFoundError(f"Barcode {barcode_id} not found.")
            repo.delete(row)
            uow.commit()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _clear_primary(
        self, session: Session, item_id: int, exclude_id: int | None
    ) -> None:
        repo = self._repo_factory(session)
        current = repo.get_primary(item_id)
        if current is not None and (exclude_id is None or current.id != exclude_id):
            current.is_primary = False


def _to_dto(row: ItemBarcode) -> ItemBarcodeDTO:
    return ItemBarcodeDTO(
        id=row.id,
        item_id=row.item_id,
        company_id=row.company_id,
        barcode=row.barcode,
        barcode_type_code=row.barcode_type_code,
        is_primary=row.is_primary,
    )
