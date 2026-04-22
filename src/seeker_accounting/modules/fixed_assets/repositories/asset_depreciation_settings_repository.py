from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.fixed_assets.models.asset_depreciation_settings import AssetDepreciationSettings


class AssetDepreciationSettingsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_asset(self, company_id: int, asset_id: int) -> AssetDepreciationSettings | None:
        stmt = (
            select(AssetDepreciationSettings)
            .where(AssetDepreciationSettings.company_id == company_id)
            .where(AssetDepreciationSettings.asset_id == asset_id)
            .options(selectinload(AssetDepreciationSettings.macrs_profile))
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def save(self, settings: AssetDepreciationSettings) -> AssetDepreciationSettings:
        self._session.add(settings)
        self._session.flush()
        return settings

    def delete(self, settings: AssetDepreciationSettings) -> None:
        self._session.delete(settings)
        self._session.flush()
