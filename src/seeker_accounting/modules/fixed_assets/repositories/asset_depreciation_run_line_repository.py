from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from sqlalchemy import func, select
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

    def aggregate_totals_by_run(
        self, run_ids: Iterable[int]
    ) -> dict[int, tuple[int, Decimal]]:
        """Return {run_id: (line_count, sum(depreciation_amount))} in a single query.

        Used by list views to avoid per-run N+1 line fetches.
        """
        run_id_list = list(run_ids)
        if not run_id_list:
            return {}
        stmt = (
            select(
                AssetDepreciationRunLine.asset_depreciation_run_id,
                func.count(AssetDepreciationRunLine.id),
                func.coalesce(func.sum(AssetDepreciationRunLine.depreciation_amount), 0),
            )
            .where(AssetDepreciationRunLine.asset_depreciation_run_id.in_(run_id_list))
            .group_by(AssetDepreciationRunLine.asset_depreciation_run_id)
        )
        totals: dict[int, tuple[int, Decimal]] = {}
        for run_id, count, amount in self._session.execute(stmt).all():
            totals[int(run_id)] = (int(count or 0), Decimal(str(amount or 0)))
        return totals

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
