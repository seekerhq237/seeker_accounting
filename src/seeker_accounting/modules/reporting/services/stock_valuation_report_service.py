from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.services.inventory_valuation_service import (
    InventoryValuationService,
)
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.dto.stock_valuation_report_dto import (
    StockValuationReportDTO,
    StockValuationReportFilterDTO,
    StockValuationRowDTO,
    StockValuationWarningDTO,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]

_ZERO_QTY = Decimal("0.0000")
_ZERO_AMOUNT = Decimal("0.00")


class StockValuationReportService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        inventory_valuation_service: InventoryValuationService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._inventory_valuation_service = inventory_valuation_service

    def get_report(self, filter_dto: StockValuationReportFilterDTO) -> StockValuationReportDTO:
        self._validate_filter(filter_dto)

        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, filter_dto.company_id)
            raw_rows = self._inventory_valuation_service.list_stock_positions(
                filter_dto.company_id,
                low_stock_only=False,
            )

        if filter_dto.item_id is not None:
            raw_rows = [row for row in raw_rows if row.item_id == filter_dto.item_id]

        rows: list[StockValuationRowDTO] = []
        warnings: list[StockValuationWarningDTO] = []
        total_quantity = _ZERO_QTY
        total_value = _ZERO_AMOUNT

        if filter_dto.location_id is not None:
            warnings.append(
                StockValuationWarningDTO(
                    code="location_filter_ignored",
                    severity_code="info",
                    message=(
                        "Warehouse/store filtering is not supported by the current inventory valuation truth "
                        "and is ignored in this report."
                    ),
                )
            )

        if filter_dto.as_of_date is not None and filter_dto.as_of_date != date.today():
            warnings.append(
                StockValuationWarningDTO(
                    code="historical_snapshot_unavailable",
                    severity_code="warning",
                    message=(
                        "Historical as-of valuation snapshots are not available in the current inventory truth. "
                        "This report shows the current cost-layer valuation snapshot instead."
                    ),
                )
            )

        for row in raw_rows:
            if row.quantity_on_hand == _ZERO_QTY and row.total_value == _ZERO_AMOUNT:
                continue

            basis_label = "Current Cost Layer Snapshot"
            unit_value = row.weighted_average_cost
            if unit_value is None and row.quantity_on_hand > _ZERO_QTY:
                unit_value = (row.total_value / row.quantity_on_hand).quantize(Decimal("0.0001"))

            rows.append(
                StockValuationRowDTO(
                    item_id=row.item_id,
                    item_code=row.item_code,
                    item_name=row.item_name,
                    unit_of_measure_code=row.unit_of_measure_code,
                    valuation_basis_label=basis_label,
                    quantity_on_hand=row.quantity_on_hand,
                    unit_value=unit_value,
                    total_value=row.total_value,
                    has_metadata_warning=False,
                )
            )
            total_quantity += row.quantity_on_hand
            total_value += row.total_value

        return StockValuationReportDTO(
            company_id=filter_dto.company_id,
            as_of_date=filter_dto.as_of_date,
            item_id=filter_dto.item_id,
            location_id=filter_dto.location_id,
            location_label=None,
            rows=tuple(rows),
            total_quantity_on_hand=total_quantity,
            total_inventory_value=total_value,
            warnings=tuple(warnings),
        )

    def build_print_preview_meta(
        self,
        report_dto: StockValuationReportDTO,
        company_name: str,
    ) -> PrintPreviewMetaDTO:
        return PrintPreviewMetaDTO(
            report_title="Stock Valuation Report",
            company_name=company_name,
            period_label=self._as_of_label(report_dto.as_of_date),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=self._filter_summary(report_dto),
            amount_headers=("Qty On Hand", "Unit Value", "Total Value"),
            rows=tuple(self._preview_rows(report_dto)),
        )

    def _preview_rows(self, report_dto: StockValuationReportDTO) -> list[PrintPreviewRowDTO]:
        rows: list[PrintPreviewRowDTO] = []
        for row in report_dto.rows:
            rows.append(
                PrintPreviewRowDTO(
                    row_type="line",
                    reference_code=row.item_code,
                    label=f"{row.item_name} | {row.valuation_basis_label}",
                    amount_text=self._fmt_qty(row.quantity_on_hand),
                    secondary_amount_text=self._fmt_unit(row.unit_value),
                    tertiary_amount_text=self._fmt_amount(row.total_value),
                )
            )
        rows.append(
            PrintPreviewRowDTO(
                row_type="subtotal",
                reference_code=None,
                label="Total inventory valuation",
                amount_text=self._fmt_qty(report_dto.total_quantity_on_hand),
                secondary_amount_text=None,
                tertiary_amount_text=self._fmt_amount(report_dto.total_inventory_value),
            )
        )
        return rows

    def _filter_summary(self, report_dto: StockValuationReportDTO) -> str:
        parts = []
        if report_dto.item_id is not None:
            parts.append("Single item filter")
        if report_dto.warnings:
            parts.append("Warnings present")
        if report_dto.as_of_date is not None:
            parts.append(f"As at {report_dto.as_of_date.strftime('%d %b %Y')}")
        return " | ".join(parts) if parts else "Current stock items"

    def _validate_filter(self, filter_dto: StockValuationReportFilterDTO) -> None:
        if filter_dto.company_id <= 0:
            raise ValidationError("Select an active company before running the stock valuation report.")

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} was not found.")

    @staticmethod
    def _fmt_qty(value: Decimal | None) -> str:
        amount = value or _ZERO_QTY
        text = f"{amount:,.4f}"
        return text.rstrip("0").rstrip(".") if "." in text else text

    @staticmethod
    def _fmt_unit(value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"{value:,.4f}"

    @staticmethod
    def _fmt_amount(value: Decimal | None) -> str:
        amount = value or _ZERO_AMOUNT
        return f"{amount:,.2f}"

    @staticmethod
    def _as_of_label(as_of_date) -> str:
        if as_of_date is None:
            return "Latest posted inventory value"
        return f"As at {as_of_date.strftime('%d %b %Y')}"
