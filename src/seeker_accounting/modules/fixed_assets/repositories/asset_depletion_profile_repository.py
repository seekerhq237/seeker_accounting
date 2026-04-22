from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.fixed_assets.models.asset_depletion_profile import AssetDepletionProfile


class AssetDepletionProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_asset(self, company_id: int, asset_id: int) -> AssetDepletionProfile | None:
        stmt = (
            select(AssetDepletionProfile)
            .where(AssetDepletionProfile.company_id == company_id)
            .where(AssetDepletionProfile.asset_id == asset_id)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def save(self, profile: AssetDepletionProfile) -> AssetDepletionProfile:
        self._session.add(profile)
        self._session.flush()
        return profile

    def delete(self, profile: AssetDepletionProfile) -> None:
        self._session.delete(profile)
        self._session.flush()
