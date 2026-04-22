from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.reporting.dto.fixed_asset_register_dto import (
    FixedAssetDepreciationHistoryRowDTO,
    FixedAssetRegisterDetailDTO,
    FixedAssetRegisterFilterDTO,
    FixedAssetRegisterReportDTO,
    FixedAssetRegisterRowDTO,
)
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.repositories.fixed_asset_register_repository import (
    FixedAssetRegisterRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
FixedAssetRegisterRepositoryFactory = Callable[[Session], FixedAssetRegisterRepository]

_ZERO_AMOUNT = Decimal("0.00")


class FixedAssetRegisterService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        fixed_asset_register_repository_factory: FixedAssetRegisterRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._fixed_asset_register_repository_factory = fixed_asset_register_repository_factory

    def get_report(self, filter_dto: FixedAssetRegisterFilterDTO) -> FixedAssetRegisterReportDTO:
        self._validate_filter(filter_dto)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, filter_dto.company_id)
            repo = self._fixed_asset_register_repository_factory(uow.session)
            raw_rows = repo.list_register_rows(filter_dto)

        rows: list[FixedAssetRegisterRowDTO] = []
        total_cost = _ZERO_AMOUNT
        total_accumulated = _ZERO_AMOUNT
        total_carrying = _ZERO_AMOUNT

        for row in raw_rows:
            carrying_amount = self._carrying_amount(
                row.acquisition_cost,
                row.accumulated_depreciation,
                row.salvage_value,
            )
            rows.append(
                FixedAssetRegisterRowDTO(
                    asset_id=row.asset_id,
                    asset_number=row.asset_number,
                    asset_name=row.asset_name,
                    category_id=row.category_id,
                    category_code=row.category_code,
                    category_name=row.category_name,
                    acquisition_date=row.acquisition_date,
                    acquisition_cost=row.acquisition_cost,
                    useful_life_months=row.useful_life_months,
                    depreciation_method_code=row.depreciation_method_code,
                    accumulated_depreciation=row.accumulated_depreciation,
                    carrying_amount=carrying_amount,
                    status_code=row.status_code,
                )
            )
            total_cost += row.acquisition_cost
            total_accumulated += row.accumulated_depreciation
            total_carrying += carrying_amount

        return FixedAssetRegisterReportDTO(
            company_id=filter_dto.company_id,
            as_of_date=filter_dto.as_of_date,
            asset_id=filter_dto.asset_id,
            category_id=filter_dto.category_id,
            status_code=filter_dto.status_code,
            rows=tuple(rows),
            total_acquisition_cost=total_cost,
            total_accumulated_depreciation=total_accumulated,
            total_carrying_amount=total_carrying,
        )

    def get_asset_detail(
        self,
        filter_dto: FixedAssetRegisterFilterDTO,
        asset_id: int,
    ) -> FixedAssetRegisterDetailDTO:
        if asset_id <= 0:
            raise ValidationError("Select an asset to view register detail.")
        self._validate_filter(filter_dto)
        detail_filter = FixedAssetRegisterFilterDTO(
            company_id=filter_dto.company_id,
            as_of_date=filter_dto.as_of_date,
            asset_id=asset_id,
            category_id=None,
            status_code=None,
        )
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, filter_dto.company_id)
            repo = self._fixed_asset_register_repository_factory(uow.session)
            rows = repo.list_register_rows(detail_filter)
            if not rows:
                raise NotFoundError("The selected asset could not be found.")
            row = rows[0]
            history_rows = repo.list_asset_history(filter_dto.company_id, asset_id, filter_dto.as_of_date)

        carrying_amount = self._carrying_amount(
            row.acquisition_cost,
            row.accumulated_depreciation,
            row.salvage_value,
        )
        detail_history = tuple(
            FixedAssetDepreciationHistoryRowDTO(
                run_id=history.run_id,
                run_number=history.run_number,
                run_date=history.run_date,
                period_end_date=history.period_end_date,
                depreciation_amount=history.depreciation_amount,
                accumulated_depreciation_after=history.accumulated_depreciation_after,
                carrying_amount_after=history.net_book_value_after,
                posted_journal_entry_id=history.posted_journal_entry_id,
            )
            for history in history_rows
        )
        return FixedAssetRegisterDetailDTO(
            company_id=filter_dto.company_id,
            asset_id=row.asset_id,
            as_of_date=filter_dto.as_of_date,
            asset_number=row.asset_number,
            asset_name=row.asset_name,
            category_name=row.category_name,
            acquisition_cost=row.acquisition_cost,
            accumulated_depreciation=row.accumulated_depreciation,
            carrying_amount=carrying_amount,
            history_rows=detail_history,
        )

    def build_print_preview_meta(
        self,
        report_dto: FixedAssetRegisterReportDTO,
        company_name: str,
    ) -> PrintPreviewMetaDTO:
        return PrintPreviewMetaDTO(
            report_title="Fixed Asset Register",
            company_name=company_name,
            period_label=self._as_of_label(report_dto.as_of_date),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=self._filter_summary(report_dto),
            amount_headers=("Acquisition Cost", "Accumulated Dep.", "Carrying Amount"),
            rows=tuple(self._preview_rows(report_dto)),
        )

    def _preview_rows(self, report_dto: FixedAssetRegisterReportDTO) -> list[PrintPreviewRowDTO]:
        rows: list[PrintPreviewRowDTO] = []
        for row in report_dto.rows:
            rows.append(
                PrintPreviewRowDTO(
                    row_type="line",
                    reference_code=row.asset_number,
                    label=f"{row.asset_name} | {row.category_name}",
                    amount_text=self._fmt_amount(row.acquisition_cost),
                    secondary_amount_text=self._fmt_amount(row.accumulated_depreciation),
                    tertiary_amount_text=self._fmt_amount(row.carrying_amount),
                )
            )
        rows.append(
            PrintPreviewRowDTO(
                row_type="subtotal",
                reference_code=None,
                label="Register totals",
                amount_text=self._fmt_amount(report_dto.total_acquisition_cost),
                secondary_amount_text=self._fmt_amount(report_dto.total_accumulated_depreciation),
                tertiary_amount_text=self._fmt_amount(report_dto.total_carrying_amount),
            )
        )
        return rows

    def _validate_filter(self, filter_dto: FixedAssetRegisterFilterDTO) -> None:
        if filter_dto.company_id <= 0:
            raise ValidationError("Select an active company before running the fixed asset register.")

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} was not found.")

    @staticmethod
    def _carrying_amount(
        acquisition_cost: Decimal,
        accumulated_depreciation: Decimal,
        salvage_value: Decimal | None,
    ) -> Decimal:
        minimum_value = salvage_value or _ZERO_AMOUNT
        return max(
            (acquisition_cost - accumulated_depreciation).quantize(Decimal("0.01")),
            minimum_value,
        )

    @staticmethod
    def _fmt_amount(value: Decimal | None) -> str:
        amount = value or _ZERO_AMOUNT
        return f"{amount:,.2f}"

    @staticmethod
    def _as_of_label(as_of_date) -> str:
        if as_of_date is None:
            return "Latest posted depreciation state"
        return f"As at {as_of_date.strftime('%d %b %Y')}"

    @staticmethod
    def _filter_summary(report_dto: FixedAssetRegisterReportDTO) -> str:
        parts = []
        if report_dto.category_id is not None:
            parts.append("Single category filter")
        if report_dto.status_code:
            parts.append(f"Status: {report_dto.status_code}")
        return " | ".join(parts) if parts else "All assets"
