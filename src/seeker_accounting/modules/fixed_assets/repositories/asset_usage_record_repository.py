from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.fixed_assets.models.asset_usage_record import AssetUsageRecord


class AssetUsageRecordRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_asset(
        self,
        company_id: int,
        asset_id: int,
        up_to_date: date | None = None,
    ) -> list[AssetUsageRecord]:
        stmt = (
            select(AssetUsageRecord)
            .where(AssetUsageRecord.company_id == company_id)
            .where(AssetUsageRecord.asset_id == asset_id)
            .order_by(AssetUsageRecord.usage_date)
        )
        if up_to_date is not None:
            stmt = stmt.where(AssetUsageRecord.usage_date <= up_to_date)
        return list(self._session.execute(stmt).scalars().all())

    def get_by_id(self, company_id: int, record_id: int) -> AssetUsageRecord | None:
        stmt = (
            select(AssetUsageRecord)
            .where(AssetUsageRecord.company_id == company_id)
            .where(AssetUsageRecord.id == record_id)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def save(self, record: AssetUsageRecord) -> AssetUsageRecord:
        self._session.add(record)
        self._session.flush()
        return record
