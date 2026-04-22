from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.reporting.dto.depreciation_report_dto import (
    DepreciationReportDTO,
    DepreciationReportDetailDTO,
    DepreciationReportFilterDTO,
    DepreciationReportRunDetailRowDTO,
    DepreciationReportRowDTO,
    DepreciationReportWarningDTO,
)
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.repositories.depreciation_report_repository import (
    DepreciationReportRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
DepreciationReportRepositoryFactory = Callable[[Session], DepreciationReportRepository]

_ZERO_AMOUNT = Decimal("0.00")


class DepreciationReportService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        depreciation_report_repository_factory: DepreciationReportRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._depreciation_report_repository_factory = depreciation_report_repository_factory

    def get_report(self, filter_dto: DepreciationReportFilterDTO) -> DepreciationReportDTO:
        self._validate_filter(filter_dto)
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, filter_dto.company_id)
            repo = self._depreciation_report_repository_factory(uow.session)
            raw_rows = repo.list_report_rows(filter_dto)

        warnings: list[DepreciationReportWarningDTO] = []
        if filter_dto.date_from is None:
            warnings.append(
                DepreciationReportWarningDTO(
                    code="opening_accumulation_not_requested",
                    severity_code="info",
                    message="Opening accumulated depreciation is zero because no period start date was supplied.",
                )
            )

        rows: list[DepreciationReportRowDTO] = []
        total_opening = _ZERO_AMOUNT
        total_current = _ZERO_AMOUNT
        total_closing = _ZERO_AMOUNT
        total_carrying = _ZERO_AMOUNT

        for row in raw_rows:
            carrying_amount = self._carrying_amount(
                row.acquisition_cost,
                row.closing_accumulated_depreciation,
                row.salvage_value,
            )
            rows.append(
                DepreciationReportRowDTO(
                    asset_id=row.asset_id,
                    asset_number=row.asset_number,
                    asset_name=row.asset_name,
                    category_id=row.category_id,
                    category_code=row.category_code,
                    category_name=row.category_name,
                    depreciation_method_code=row.depreciation_method_code,
                    opening_accumulated_depreciation=row.opening_accumulated_depreciation,
                    current_period_depreciation=row.current_period_depreciation,
                    closing_accumulated_depreciation=row.closing_accumulated_depreciation,
                    carrying_amount=carrying_amount,
                    status_code=row.status_code,
                )
            )
            total_opening += row.opening_accumulated_depreciation
            total_current += row.current_period_depreciation
            total_closing += row.closing_accumulated_depreciation
            total_carrying += carrying_amount

        return DepreciationReportDTO(
            company_id=filter_dto.company_id,
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
            asset_id=filter_dto.asset_id,
            category_id=filter_dto.category_id,
            status_code=filter_dto.status_code,
            rows=tuple(rows),
            total_opening_accumulated_depreciation=total_opening,
            total_current_period_depreciation=total_current,
            total_closing_accumulated_depreciation=total_closing,
            total_carrying_amount=total_carrying,
            warnings=tuple(warnings),
        )

    def get_asset_detail(
        self,
        filter_dto: DepreciationReportFilterDTO,
        asset_id: int,
    ) -> DepreciationReportDetailDTO:
        if asset_id <= 0:
            raise ValidationError("Select an asset to view depreciation detail.")
        self._validate_filter(filter_dto)
        detail_filter = DepreciationReportFilterDTO(
            company_id=filter_dto.company_id,
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
            asset_id=asset_id,
            category_id=None,
            status_code=None,
        )
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, filter_dto.company_id)
            repo = self._depreciation_report_repository_factory(uow.session)
            rows = repo.list_report_rows(detail_filter)
            if not rows:
                raise NotFoundError("The selected asset could not be found.")
            row = rows[0]
            detail_rows = repo.list_asset_run_details(
                filter_dto.company_id,
                asset_id,
                filter_dto.date_from,
                filter_dto.date_to,
            )

        carrying_amount = self._carrying_amount(
            row.acquisition_cost,
            row.closing_accumulated_depreciation,
            row.salvage_value,
        )
        return DepreciationReportDetailDTO(
            company_id=filter_dto.company_id,
            asset_id=row.asset_id,
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
            asset_number=row.asset_number,
            asset_name=row.asset_name,
            opening_accumulated_depreciation=row.opening_accumulated_depreciation,
            current_period_depreciation=row.current_period_depreciation,
            closing_accumulated_depreciation=row.closing_accumulated_depreciation,
            carrying_amount=carrying_amount,
            rows=tuple(
                DepreciationReportRunDetailRowDTO(
                    run_id=detail.run_id,
                    run_number=detail.run_number,
                    run_date=detail.run_date,
                    period_end_date=detail.period_end_date,
                    depreciation_amount=detail.depreciation_amount,
                    accumulated_depreciation_after=detail.accumulated_depreciation_after,
                    carrying_amount_after=detail.net_book_value_after,
                    posted_journal_entry_id=detail.posted_journal_entry_id,
                )
                for detail in detail_rows
            ),
        )

    def build_print_preview_meta(
        self,
        report_dto: DepreciationReportDTO,
        company_name: str,
    ) -> PrintPreviewMetaDTO:
        return PrintPreviewMetaDTO(
            report_title="Depreciation Report",
            company_name=company_name,
            period_label=self._period_label(report_dto.date_from, report_dto.date_to),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=self._filter_summary(report_dto),
            amount_headers=("Opening Accum.", "Period Dep.", "Closing Accum.", "Carrying Amount"),
            rows=tuple(self._preview_rows(report_dto)),
        )

    def _preview_rows(self, report_dto: DepreciationReportDTO) -> list[PrintPreviewRowDTO]:
        rows: list[PrintPreviewRowDTO] = []
        for row in report_dto.rows:
            rows.append(
                PrintPreviewRowDTO(
                    row_type="line",
                    reference_code=row.asset_number,
                    label=f"{row.asset_name} | {row.category_name}",
                    amount_text=self._fmt_amount(row.opening_accumulated_depreciation),
                    secondary_amount_text=self._fmt_amount(row.current_period_depreciation),
                    tertiary_amount_text=self._fmt_amount(row.closing_accumulated_depreciation),
                    quaternary_amount_text=self._fmt_amount(row.carrying_amount),
                )
            )
        rows.append(
            PrintPreviewRowDTO(
                row_type="subtotal",
                reference_code=None,
                label="Depreciation totals",
                amount_text=self._fmt_amount(report_dto.total_opening_accumulated_depreciation),
                secondary_amount_text=self._fmt_amount(report_dto.total_current_period_depreciation),
                tertiary_amount_text=self._fmt_amount(report_dto.total_closing_accumulated_depreciation),
                quaternary_amount_text=self._fmt_amount(report_dto.total_carrying_amount),
            )
        )
        return rows

    def _validate_filter(self, filter_dto: DepreciationReportFilterDTO) -> None:
        if filter_dto.company_id <= 0:
            raise ValidationError("Select an active company before running the depreciation report.")
        if filter_dto.date_from and filter_dto.date_to and filter_dto.date_to < filter_dto.date_from:
            raise ValidationError("The 'To' date must be on or after the 'From' date.")

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} was not found.")

    @staticmethod
    def _carrying_amount(
        acquisition_cost: Decimal,
        closing_accumulated_depreciation: Decimal,
        salvage_value: Decimal | None,
    ) -> Decimal:
        minimum_value = salvage_value or _ZERO_AMOUNT
        return max(
            (acquisition_cost - closing_accumulated_depreciation).quantize(Decimal("0.01")),
            minimum_value,
        )

    @staticmethod
    def _fmt_amount(value: Decimal | None) -> str:
        amount = value or _ZERO_AMOUNT
        return f"{amount:,.2f}"

    @staticmethod
    def _period_label(date_from: date | None, date_to: date | None) -> str:
        if date_from is None and date_to is None:
            return "All posted depreciation runs"
        if date_from is None:
            return f"Up to {date_to.strftime('%d %b %Y')}" if date_to else "All posted depreciation runs"
        if date_to is None:
            return f"From {date_from.strftime('%d %b %Y')}"
        return f"{date_from.strftime('%d %b %Y')} - {date_to.strftime('%d %b %Y')}"

    @staticmethod
    def _filter_summary(report_dto: DepreciationReportDTO) -> str:
        parts = []
        if report_dto.category_id is not None:
            parts.append("Single category filter")
        if report_dto.status_code:
            parts.append(f"Status: {report_dto.status_code}")
        if report_dto.warnings:
            parts.append("Warnings present")
        return " | ".join(parts) if parts else "All depreciable assets"
