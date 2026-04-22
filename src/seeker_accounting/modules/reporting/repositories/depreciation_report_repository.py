from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.fixed_assets.models.asset import Asset
from seeker_accounting.modules.fixed_assets.models.asset_category import AssetCategory
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run import AssetDepreciationRun
from seeker_accounting.modules.fixed_assets.models.asset_depreciation_run_line import (
    AssetDepreciationRunLine,
)
from seeker_accounting.modules.reporting.dto.depreciation_report_dto import (
    DepreciationReportFilterDTO,
)


@dataclass(frozen=True, slots=True)
class DepreciationReportQueryRow:
    asset_id: int
    asset_number: str
    asset_name: str
    category_id: int
    category_code: str
    category_name: str
    acquisition_cost: Decimal
    salvage_value: Decimal | None
    depreciation_method_code: str
    status_code: str
    opening_accumulated_depreciation: Decimal
    current_period_depreciation: Decimal
    closing_accumulated_depreciation: Decimal


@dataclass(frozen=True, slots=True)
class DepreciationRunDetailQueryRow:
    run_id: int
    run_number: str | None
    run_date: date
    period_end_date: date
    depreciation_amount: Decimal
    accumulated_depreciation_after: Decimal
    net_book_value_after: Decimal
    posted_journal_entry_id: int | None


class DepreciationReportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_report_rows(
        self,
        filter_dto: DepreciationReportFilterDTO,
    ) -> list[DepreciationReportQueryRow]:
        if filter_dto.date_from is None:
            opening_subquery = (
                select(
                    Asset.id.label("asset_id"),
                    literal(0).label("total_depreciation"),
                )
                .where(Asset.company_id == filter_dto.company_id)
                .subquery()
            )
        else:
            opening_subquery = self._depreciation_sum_subquery(
                date_to=filter_dto.date_from - date.resolution,
            )
        period_subquery = self._depreciation_sum_subquery(
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
        )
        closing_subquery = self._depreciation_sum_subquery(
            date_to=filter_dto.date_to,
        )

        stmt = (
            select(
                Asset.id.label("asset_id"),
                Asset.asset_number,
                Asset.asset_name,
                Asset.asset_category_id.label("category_id"),
                AssetCategory.code.label("category_code"),
                AssetCategory.name.label("category_name"),
                Asset.acquisition_cost,
                Asset.salvage_value,
                Asset.depreciation_method_code,
                Asset.status_code,
                func.coalesce(opening_subquery.c.total_depreciation, 0).label("opening_accumulated_depreciation"),
                func.coalesce(period_subquery.c.total_depreciation, 0).label("current_period_depreciation"),
                func.coalesce(closing_subquery.c.total_depreciation, 0).label("closing_accumulated_depreciation"),
            )
            .join(AssetCategory, AssetCategory.id == Asset.asset_category_id)
            .outerjoin(opening_subquery, opening_subquery.c.asset_id == Asset.id)
            .outerjoin(period_subquery, period_subquery.c.asset_id == Asset.id)
            .outerjoin(closing_subquery, closing_subquery.c.asset_id == Asset.id)
            .where(*self._base_conditions(filter_dto))
            .order_by(Asset.asset_number.asc())
        )

        rows: list[DepreciationReportQueryRow] = []
        for row in self._session.execute(stmt):
            rows.append(
                DepreciationReportQueryRow(
                    asset_id=row.asset_id,
                    asset_number=row.asset_number,
                    asset_name=row.asset_name,
                    category_id=row.category_id,
                    category_code=row.category_code,
                    category_name=row.category_name,
                    acquisition_cost=self._to_amount(row.acquisition_cost),
                    salvage_value=self._to_optional_amount(row.salvage_value),
                    depreciation_method_code=row.depreciation_method_code,
                    status_code=row.status_code,
                    opening_accumulated_depreciation=self._to_amount(row.opening_accumulated_depreciation),
                    current_period_depreciation=self._to_amount(row.current_period_depreciation),
                    closing_accumulated_depreciation=self._to_amount(row.closing_accumulated_depreciation),
                )
            )
        return rows

    def list_asset_run_details(
        self,
        company_id: int,
        asset_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[DepreciationRunDetailQueryRow]:
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
        if date_from is not None:
            stmt = stmt.where(AssetDepreciationRun.period_end_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(AssetDepreciationRun.period_end_date <= date_to)

        rows: list[DepreciationRunDetailQueryRow] = []
        for row in self._session.execute(stmt):
            rows.append(
                DepreciationRunDetailQueryRow(
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

    def _depreciation_sum_subquery(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ):
        stmt = (
            select(
                AssetDepreciationRunLine.asset_id.label("asset_id"),
                func.coalesce(
                    func.sum(AssetDepreciationRunLine.depreciation_amount),
                    0,
                ).label("total_depreciation"),
            )
            .join(
                AssetDepreciationRun,
                AssetDepreciationRun.id == AssetDepreciationRunLine.asset_depreciation_run_id,
            )
            .where(AssetDepreciationRun.status_code == "posted")
            .group_by(AssetDepreciationRunLine.asset_id)
        )
        if date_from is not None:
            stmt = stmt.where(AssetDepreciationRun.period_end_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(AssetDepreciationRun.period_end_date <= date_to)
        return stmt.subquery()

    def _base_conditions(self, filter_dto: DepreciationReportFilterDTO) -> list[object]:
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
