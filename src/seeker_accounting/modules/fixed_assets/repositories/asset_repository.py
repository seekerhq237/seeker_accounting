from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.fixed_assets.models.asset import Asset


class AssetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        active_only: bool = False,
        query: str | None = None,
        status_code: str | None = None,
    ) -> list[Asset]:
        stmt = (
            select(Asset)
            .where(Asset.company_id == company_id)
            .options(selectinload(Asset.category))
        )
        if active_only:
            stmt = stmt.where(Asset.status_code == "active")
        if status_code:
            stmt = stmt.where(Asset.status_code == status_code)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                (Asset.asset_number.ilike(like)) | (Asset.asset_name.ilike(like))
            )
        stmt = stmt.order_by(Asset.asset_number)
        return list(self._session.execute(stmt).scalars().all())

    def get_by_id(self, company_id: int, asset_id: int) -> Asset | None:
        stmt = (
            select(Asset)
            .where(Asset.company_id == company_id)
            .where(Asset.id == asset_id)
            .options(selectinload(Asset.category))
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_number(self, company_id: int, asset_number: str) -> Asset | None:
        stmt = (
            select(Asset)
            .where(Asset.company_id == company_id)
            .where(Asset.asset_number == asset_number)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_eligible_for_run(self, company_id: int) -> list[Asset]:
        """Assets eligible for depreciation: active status only."""
        stmt = (
            select(Asset)
            .where(Asset.company_id == company_id)
            .where(Asset.status_code == "active")
            .options(selectinload(Asset.category))
            .order_by(Asset.asset_number)
        )
        return list(self._session.execute(stmt).scalars().all())

    def save(self, asset: Asset) -> Asset:
        self._session.add(asset)
        self._session.flush()
        return asset
