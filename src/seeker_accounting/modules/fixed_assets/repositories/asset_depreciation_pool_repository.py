from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.fixed_assets.models.asset_depreciation_pool import AssetDepreciationPool
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_pool_member import AssetDepreciationPoolMember


class AssetDepreciationPoolRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[AssetDepreciationPool]:
        stmt = (
            select(AssetDepreciationPool)
            .where(AssetDepreciationPool.company_id == company_id)
            .options(selectinload(AssetDepreciationPool.members))
            .order_by(AssetDepreciationPool.code)
        )
        if active_only:
            stmt = stmt.where(AssetDepreciationPool.is_active == True)  # noqa: E712
        return list(self._session.execute(stmt).scalars().all())

    def get_by_id(self, company_id: int, pool_id: int) -> AssetDepreciationPool | None:
        stmt = (
            select(AssetDepreciationPool)
            .where(AssetDepreciationPool.company_id == company_id)
            .where(AssetDepreciationPool.id == pool_id)
            .options(selectinload(AssetDepreciationPool.members))
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_code(self, company_id: int, code: str) -> AssetDepreciationPool | None:
        stmt = (
            select(AssetDepreciationPool)
            .where(AssetDepreciationPool.company_id == company_id)
            .where(AssetDepreciationPool.code == code)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_active_member(self, asset_id: int) -> AssetDepreciationPoolMember | None:
        """Return the pool membership row where the asset is currently active (left_date is NULL)."""
        stmt = (
            select(AssetDepreciationPoolMember)
            .where(AssetDepreciationPoolMember.asset_id == asset_id)
            .where(AssetDepreciationPoolMember.left_date == None)  # noqa: E711
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def save(self, pool: AssetDepreciationPool) -> AssetDepreciationPool:
        self._session.add(pool)
        self._session.flush()
        return pool

    def save_member(self, member: AssetDepreciationPoolMember) -> AssetDepreciationPoolMember:
        self._session.add(member)
        self._session.flush()
        return member
