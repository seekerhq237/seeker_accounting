from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.fixed_assets.models.asset import Asset
from seeker_accounting.modules.fixed_assets.models.asset_category import AssetCategory
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run import AssetDepreciationRun
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run_line import (
    AssetDepreciationRunLine,
)
from seeker_accounting.modules.reporting.dto.fixed_asset_register_dto import (
    FixedAssetRegisterFilterDTO,
)


@dataclass(frozen=True, slots=True)
class FixedAssetRegisterQueryRow:
    asset_id: int
    asset_number: str
    asset_name: str
    category_id: int
    category_code: str
    category_name: str
    acquisition_date: date
    acquisition_cost: Decimal
    salvage_value: Decimal | None
    useful_life_months: int
    depreciation_method_code: str
    status_code: str
    accumulated_depreciation: Decimal


@dataclass(frozen=True, slots=True)
class FixedAssetHistoryQueryRow:
    run_id: int
    run_number: str | None
    run_date: date
    period_end_date: date
    depreciation_amount: Decimal
    accumulated_depreciation_after: Decimal
    net_book_value_after: Decimal
    posted_journal_entry_id: int | None


class FixedAssetRegisterRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_register_rows(
        self,
        filter_dto: FixedAssetRegisterFilterDTO,
    ) -> list[FixedAssetRegisterQueryRow]:
        depreciation_subquery = self._depreciation_total_subquery(filter_dto.as_of_date)

        stmt = (
            select(
                Asset.id.label("asset_id"),
                Asset.asset_number,
                Asset.asset_name,
                Asset.asset_category_id.label("category_id"),
                AssetCategory.code.label("category_code"),
                AssetCategory.name.label("category_name"),
                Asset.acquisition_date,
                Asset.acquisition_cost,
                Asset.salvage_value,
                Asset.useful_life_months,
                Asset.depreciation_method_code,
                Asset.status_code,
                func.coalesce(
                    depreciation_subquery.c.accumulated_depreciation,
                    0,
                ).label("accumulated_depreciation"),
            )
            .join(AssetCategory, AssetCategory.id == Asset.asset_category_id)
            .outerjoin(
                depreciation_subquery,
                depreciation_subquery.c.asset_id == Asset.id,
            )
            .where(*self._base_conditions(filter_dto))
            .order_by(Asset.asset_number.asc())
        )

        rows: list[FixedAssetRegisterQueryRow] = []
        for row in self._session.execute(stmt):
            rows.append(
                FixedAssetRegisterQueryRow(
                    asset_id=row.asset_id,
                    asset_number=row.asset_number,
                    asset_name=row.asset_name,
                    category_id=row.category_id,
                    category_code=row.category_code,
                    category_name=row.category_name,
                    acquisition_date=row.acquisition_date,
                    acquisition_cost=self._to_amount(row.acquisition_cost),
                    salvage_value=self._to_optional_amount(row.salvage_value),
                    useful_life_months=int(row.useful_life_months),
                    depreciation_method_code=row.depreciation_method_code,
                    status_code=row.status_code,
                    accumulated_depreciation=self._to_amount(row.accumulated_depreciation),
                )
            )
        return rows

    def list_asset_history(
        self,
        company_id: int,
        asset_id: int,
        as_of_date: date | None,
    ) -> list[FixedAssetHistoryQueryRow]:
        stmt = (
            select(
                AssetDepreciationRun.id.label("run_id"),
                AssetDepreciationRun.run_number,
                AssetDepreciationRun.run_date,
                AssetDepreciationRun.period_end_date,
                AssetDepreciationRunLine.depreciation_amount,
                AssetDepreciationRunLine.accumulated_depreciation_after,
                AssetDepreciationRunLine.net_book_value_after,
                AssetDepreciationRun.posted_journal_entry_id,
            )
            .join(
                AssetDepreciationRunLine,
                AssetDepreciationRunLine.asset_depreciation_run_id == AssetDepreciationRun.id,
            )
            .join(Asset, Asset.id == AssetDepreciationRunLine.asset_id)
            .where(
                Asset.company_id == company_id,
                Asset.id == asset_id,
                AssetDepreciationRun.status_code == "posted",
            )
            .order_by(
                AssetDepreciationRun.period_end_date.asc(),
                AssetDepreciationRun.id.asc(),
            )
        )
        if as_of_date is not None:
            stmt = stmt.where(AssetDepreciationRun.period_end_date <= as_of_date)

        rows: list[FixedAssetHistoryQueryRow] = []
        for row in self._session.execute(stmt):
            rows.append(
                FixedAssetHistoryQueryRow(
                    run_id=row.run_id,
                    run_number=row.run_number,
                    run_date=row.run_date,
                    period_end_date=row.period_end_date,
                    depreciation_amount=self._to_amount(row.depreciation_amount),
                    accumulated_depreciation_after=self._to_amount(row.accumulated_depreciation_after),
                    net_book_value_after=self._to_amount(row.net_book_value_after),
                    posted_journal_entry_id=row.posted_journal_entry_id,
                )
            )
        return rows

    def _depreciation_total_subquery(self, as_of_date: date | None):
        stmt = (
            select(
                AssetDepreciationRunLine.asset_id.label("asset_id"),
                func.coalesce(
                    func.sum(AssetDepreciationRunLine.depreciation_amount),
                    0,
                ).label("accumulated_depreciation"),
            )
            .join(
                AssetDepreciationRun,
                AssetDepreciationRun.id == AssetDepreciationRunLine.asset_depreciation_run_id,
            )
            .where(AssetDepreciationRun.status_code == "posted")
            .group_by(AssetDepreciationRunLine.asset_id)
        )
        if as_of_date is not None:
            stmt = stmt.where(AssetDepreciationRun.period_end_date <= as_of_date)
        return stmt.subquery()

    def _base_conditions(self, filter_dto: FixedAssetRegisterFilterDTO) -> list[object]:
        conditions: list[object] = [Asset.company_id == filter_dto.company_id]
        if filter_dto.asset_id is not None:
            conditions.append(Asset.id == filter_dto.asset_id)
        if filter_dto.category_id is not None:
            conditions.append(Asset.asset_category_id == filter_dto.category_id)
        if filter_dto.status_code:
            conditions.append(Asset.status_code == filter_dto.status_code)
        return conditions

    @staticmethod
    def _to_amount(value: object) -> Decimal:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))

    @staticmethod
    def _to_optional_amount(value: object) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value)).quantize(Decimal("0.01"))
