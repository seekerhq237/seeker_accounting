from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run_line import AssetDepreciationRunLine


class AssetDepreciationRunLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_run(self, run_id: int) -> list[AssetDepreciationRunLine]:
        stmt = (
            select(AssetDepreciationRunLine)
            .where(AssetDepreciationRunLine.asset_depreciation_run_id == run_id)
            .options(selectinload(AssetDepreciationRunLine.asset))
            .order_by(AssetDepreciationRunLine.id)
        )
        return list(self._session.execute(stmt).scalars().all())

    def save(self, line: AssetDepreciationRunLine) -> AssetDepreciationRunLine:
        self._session.add(line)
        self._session.flush()
        return line

    def delete_lines_for_run(self, run_id: int) -> None:
        stmt = select(AssetDepreciationRunLine).where(
            AssetDepreciationRunLine.asset_depreciation_run_id == run_id
        )
        lines = list(self._session.execute(stmt).scalars().all())
        for line in lines:
            self._session.delete(line)
        self._session.flush()
