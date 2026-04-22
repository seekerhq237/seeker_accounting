from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.fixed_assets.models.depreciation_method import DepreciationMethod


class DepreciationMethodRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self, active_only: bool = True) -> list[DepreciationMethod]:
        stmt = select(DepreciationMethod).order_by(DepreciationMethod.sort_order)
        if active_only:
            stmt = stmt.where(DepreciationMethod.is_active == True)  # noqa: E712
        return list(self._session.execute(stmt).scalars().all())

    def get_by_code(self, code: str) -> DepreciationMethod | None:
        stmt = select(DepreciationMethod).where(DepreciationMethod.code == code)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_id(self, method_id: int) -> DepreciationMethod | None:
        stmt = select(DepreciationMethod).where(DepreciationMethod.id == method_id)
        return self._session.execute(stmt).scalar_one_or_none()
