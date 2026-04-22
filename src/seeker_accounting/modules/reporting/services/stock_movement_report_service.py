from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.dto.stock_movement_report_dto import (
    StockMovementDetailRowDTO,
    StockMovementItemDetailDTO,
    StockMovementReportDTO,
    StockMovementReportFilterDTO,
    StockMovementSummaryRowDTO,
)
from seeker_accounting.modules.reporting.repositories.stock_movement_report_repository import (
    StockMovementReportRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
StockMovementReportRepositoryFactory = Callable[[Session], StockMovementReportRepository]

_ZERO_QTY = Decimal("0.0000")


class StockMovementReportService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        stock_movement_report_repository_factory: StockMovementReportRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._stock_movement_report_repository_factory = stock_movement_report_repository_factory

    def get_report(self, filter_dto: StockMovementReportFilterDTO) -> StockMovementReportDTO:
        self._validate_filter(filter_dto)

        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, filter_dto.company_id)
            repo = self._stock_movement_report_repository_factory(uow.session)
            raw_rows = repo.list_summary_rows(filter_dto)
            location_label = (
                repo.get_location_label(filter_dto.company_id, filter_dto.location_id)
                if filter_dto.location_id is not None
                else None
            )

        rows: list[StockMovementSummaryRowDTO] = []
        total_opening = _ZERO_QTY
        total_inward = _ZERO_QTY
        total_outward = _ZERO_QTY
        total_closing = _ZERO_QTY

        for row in raw_rows:
            closing_quantity = (row.opening_quantity + row.inward_quantity - row.outward_quantity).quantize(
                Decimal("0.0001")
            )
            dto_row = StockMovementSummaryRowDTO(
                item_id=row.item_id,
                item_code=row.item_code,
                item_name=row.item_name,
                unit_of_measure_code=row.unit_of_measure_code,
                opening_quantity=row.opening_quantity,
                inward_quantity=row.inward_quantity,
                outward_quantity=row.outward_quantity,
                closing_quantity=closing_quantity,
                movement_count=row.movement_count,
            )
            rows.append(dto_row)
            total_opening += dto_row.opening_quantity
            total_inward += dto_row.inward_quantity
            total_outward += dto_row.outward_quantity
            total_closing += dto_row.closing_quantity

        return StockMovementReportDTO(
            company_id=filter_dto.company_id,
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
            item_id=filter_dto.item_id,
            location_id=filter_dto.location_id,
            location_label=location_label,
            rows=tuple(rows),
            total_opening_quantity=total_opening,
            total_inward_quantity=total_inward,
            total_outward_quantity=total_outward,
            total_closing_quantity=total_closing,
        )

    def get_item_detail(
        self,
        filter_dto: StockMovementReportFilterDTO,
        item_id: int,
    ) -> StockMovementItemDetailDTO:
        self._validate_filter(filter_dto)
        if item_id <= 0:
            raise ValidationError("Select an item to view stock movement detail.")

        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, filter_dto.company_id)
            repo = self._stock_movement_report_repository_factory(uow.session)
            item = repo.get_item_identity(filter_dto.company_id, item_id)
            if item is None:
                raise NotFoundError("The selected stock item could not be found.")
            opening_quantity = repo.get_opening_quantity(filter_dto, item_id)
            raw_rows = repo.list_item_detail_rows(filter_dto, item_id)

        detail_rows: list[StockMovementDetailRowDTO] = []
        running_quantity = opening_quantity
        inward_total = _ZERO_QTY
        outward_total = _ZERO_QTY

        for row in raw_rows:
            signed_quantity = self._signed_quantity(row.document_type_code, row.quantity)
            inward_quantity = signed_quantity if signed_quantity > 0 else _ZERO_QTY
            outward_quantity = abs(signed_quantity) if signed_quantity < 0 else _ZERO_QTY
            running_quantity = (running_quantity + signed_quantity).quantize(Decimal("0.0001"))
            inward_total += inward_quantity
            outward_total += outward_quantity
            detail_rows.append(
                StockMovementDetailRowDTO(
                    document_line_id=row.document_line_id,
                    inventory_document_id=row.inventory_document_id,
                    posted_journal_entry_id=row.posted_journal_entry_id,
                    item_id=row.item_id,
                    item_code=row.item_code,
                    item_name=row.item_name,
                    document_date=row.document_date,
                    document_number=row.document_number,
                    document_type_code=row.document_type_code,
                    reference_number=row.reference_number,
                    location_id=row.location_id,
                    location_code=row.location_code,
                    location_name=row.location_name,
                    inward_quantity=inward_quantity,
                    outward_quantity=outward_quantity,
                    running_quantity=running_quantity,
                    unit_cost=row.unit_cost,
                    line_amount=row.line_amount,
                )
            )

        closing_quantity = (opening_quantity + inward_total - outward_total).quantize(Decimal("0.0001"))
        return StockMovementItemDetailDTO(
            company_id=filter_dto.company_id,
            item_id=item.item_id,
            item_code=item.item_code,
            item_name=item.item_name,
            unit_of_measure_code=item.unit_of_measure_code,
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
            location_id=filter_dto.location_id,
            opening_quantity=opening_quantity,
            inward_quantity=inward_total,
            outward_quantity=outward_total,
            closing_quantity=closing_quantity,
            rows=tuple(detail_rows),
        )

    def build_print_preview_meta(
        self,
        report_dto: StockMovementReportDTO,
        company_name: str,
    ) -> PrintPreviewMetaDTO:
        return PrintPreviewMetaDTO(
            report_title="Stock Movement Report",
            company_name=company_name,
            period_label=self._period_label(report_dto.date_from, report_dto.date_to),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=self._filter_summary(report_dto),
            amount_headers=("Opening Qty", "Inward Qty", "Outward Qty", "Closing Qty"),
            rows=tuple(self._preview_rows(report_dto)),
        )

    def _preview_rows(self, report_dto: StockMovementReportDTO) -> list[PrintPreviewRowDTO]:
        rows: list[PrintPreviewRowDTO] = []
        for row in report_dto.rows:
            rows.append(
                PrintPreviewRowDTO(
                    row_type="line",
                    reference_code=row.item_code,
                    label=f"{row.item_name} ({row.unit_of_measure_code})",
                    amount_text=self._fmt_qty(row.opening_quantity),
                    secondary_amount_text=self._fmt_qty(row.inward_quantity),
                    tertiary_amount_text=self._fmt_qty(row.outward_quantity),
                    quaternary_amount_text=self._fmt_qty(row.closing_quantity),
                )
            )
        rows.append(
            PrintPreviewRowDTO(
                row_type="subtotal",
                reference_code=None,
                label="Stock movement totals",
                amount_text=self._fmt_qty(report_dto.total_opening_quantity),
                secondary_amount_text=self._fmt_qty(report_dto.total_inward_quantity),
                tertiary_amount_text=self._fmt_qty(report_dto.total_outward_quantity),
                quaternary_amount_text=self._fmt_qty(report_dto.total_closing_quantity),
            )
        )
        return rows

    def _filter_summary(self, report_dto: StockMovementReportDTO) -> str:
        parts = []
        if report_dto.location_label:
            parts.append(f"Location: {report_dto.location_label}")
        if report_dto.item_id is not None:
            parts.append("Single item filter")
        parts.append(f"Closing total: {self._fmt_qty(report_dto.total_closing_quantity)}")
        return " | ".join(parts) if parts else "All stock items"

    def _validate_filter(self, filter_dto: StockMovementReportFilterDTO) -> None:
        if filter_dto.company_id <= 0:
            raise ValidationError("Select an active company before running the stock movement report.")
        if filter_dto.date_from and filter_dto.date_to and filter_dto.date_to < filter_dto.date_from:
            raise ValidationError("The 'To' date must be on or after the 'From' date.")

    def _require_company(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} was not found.")

    @staticmethod
    def _signed_quantity(document_type_code: str, quantity: Decimal) -> Decimal:
        if document_type_code == "issue":
            return (-quantity).quantize(Decimal("0.0001"))
        return quantity.quantize(Decimal("0.0001"))

    @staticmethod
    def _fmt_qty(value: Decimal | None) -> str:
        amount = value or _ZERO_QTY
        text = f"{amount:,.4f}"
        return text.rstrip("0").rstrip(".") if "." in text else text

    @staticmethod
    def _period_label(date_from: date | None, date_to: date | None) -> str:
        if date_from is None and date_to is None:
            return "All posted stock movement"
        if date_from is None:
            return f"Up to {date_to.strftime('%d %b %Y')}" if date_to else "All posted stock movement"
        if date_to is None:
            return f"From {date_from.strftime('%d %b %Y')}"
        return f"{date_from.strftime('%d %b %Y')} - {date_to.strftime('%d %b %Y')}"
