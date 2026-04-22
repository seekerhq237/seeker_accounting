from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.fixed_assets.models.asset_category import AssetCategory


class AssetCategoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[AssetCategory]:
        stmt = select(AssetCategory).where(AssetCategory.company_id == company_id)
        if active_only:
            stmt = stmt.where(AssetCategory.is_active.is_(True))
        stmt = stmt.order_by(AssetCategory.code)
        return list(self._session.execute(stmt).scalars().all())

    def get_by_id(self, company_id: int, category_id: int) -> AssetCategory | None:
        return self._session.get(AssetCategory, category_id)

    def get_by_code(self, company_id: int, code: str) -> AssetCategory | None:
        stmt = (
            select(AssetCategory)
            .where(AssetCategory.company_id == company_id)
            .where(AssetCategory.code == code)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def save(self, category: AssetCategory) -> AssetCategory:
        self._session.add(category)
        self._session.flush()
        return category
