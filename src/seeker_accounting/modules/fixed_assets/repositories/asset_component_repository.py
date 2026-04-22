from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.fixed_assets.models.asset_component import AssetComponent


class AssetComponentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_asset(self, company_id: int, asset_id: int, active_only: bool = True) -> list[AssetComponent]:
        stmt = (
            select(AssetComponent)
            .where(AssetComponent.company_id == company_id)
            .where(AssetComponent.parent_asset_id == asset_id)
            .order_by(AssetComponent.id)
        )
        if active_only:
            stmt = stmt.where(AssetComponent.is_active == True)  # noqa: E712
        return list(self._session.execute(stmt).scalars().all())

    def get_by_id(self, company_id: int, component_id: int) -> AssetComponent | None:
        stmt = (
            select(AssetComponent)
            .where(AssetComponent.company_id == company_id)
            .where(AssetComponent.id == component_id)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def save(self, component: AssetComponent) -> AssetComponent:
        self._session.add(component)
        self._session.flush()
        return component
