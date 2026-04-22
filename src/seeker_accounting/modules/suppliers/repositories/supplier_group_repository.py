from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.suppliers.models.supplier_group import SupplierGroup


class SupplierGroupRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[SupplierGroup]:
        statement = select(SupplierGroup).where(SupplierGroup.company_id == company_id)
        if active_only:
            statement = statement.where(SupplierGroup.is_active.is_(True))
        statement = statement.order_by(SupplierGroup.name.asc(), SupplierGroup.code.asc(), SupplierGroup.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, group_id: int) -> SupplierGroup | None:
        statement = select(SupplierGroup).where(
            SupplierGroup.company_id == company_id,
            SupplierGroup.id == group_id,
        )
        return self._session.scalar(statement)

    def get_by_code(self, company_id: int, code: str) -> SupplierGroup | None:
        statement = select(SupplierGroup).where(
            SupplierGroup.company_id == company_id,
            SupplierGroup.code == code,
        )
        return self._session.scalar(statement)

    def add(self, supplier_group: SupplierGroup) -> SupplierGroup:
        self._session.add(supplier_group)
        return supplier_group

    def save(self, supplier_group: SupplierGroup) -> SupplierGroup:
        self._session.add(supplier_group)
        return supplier_group

    def code_exists(self, company_id: int, code: str, exclude_group_id: int | None = None) -> bool:
        predicate = (SupplierGroup.company_id == company_id) & (SupplierGroup.code == code)
        if exclude_group_id is not None:
            predicate = predicate & (SupplierGroup.id != exclude_group_id)
        return bool(self._session.scalar(select(exists().where(predicate))))
