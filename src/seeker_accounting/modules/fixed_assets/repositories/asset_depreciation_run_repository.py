from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run import AssetDepreciationRun
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run_line import AssetDepreciationRunLine


class AssetDepreciationRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self, company_id: int, status_code: str | None = None
    ) -> list[AssetDepreciationRun]:
        stmt = (
            select(AssetDepreciationRun)
            .where(AssetDepreciationRun.company_id == company_id)
        )
        if status_code:
            stmt = stmt.where(AssetDepreciationRun.status_code == status_code)
        stmt = stmt.order_by(AssetDepreciationRun.run_date.desc())
        return list(self._session.execute(stmt).scalars().all())

    def get_by_id(self, company_id: int, run_id: int) -> AssetDepreciationRun | None:
        stmt = (
            select(AssetDepreciationRun)
            .where(AssetDepreciationRun.company_id == company_id)
            .where(AssetDepreciationRun.id == run_id)
            .options(
                selectinload(AssetDepreciationRun.lines).selectinload(
                    AssetDepreciationRunLine.asset
                )
            )
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_total_depreciation_for_asset(self, asset_id: int) -> "Decimal":
        """Returns the total posted depreciation accumulated for the asset so far."""
        from decimal import Decimal
        from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run_line import AssetDepreciationRunLine

        stmt = (
            select(func.coalesce(func.sum(AssetDepreciationRunLine.depreciation_amount), 0))
            .join(
                AssetDepreciationRun,
                AssetDepreciationRunLine.asset_depreciation_run_id == AssetDepreciationRun.id,
            )
            .where(AssetDepreciationRunLine.asset_id == asset_id)
            .where(AssetDepreciationRun.status_code == "posted")
        )
        result = self._session.execute(stmt).scalar()
        return Decimal(str(result)) if result is not None else Decimal("0")

    def save(self, run: AssetDepreciationRun) -> AssetDepreciationRun:
        self._session.add(run)
        self._session.flush()
        return run
