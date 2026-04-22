from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.reporting.dto.ap_aging_report_dto import (
    APAgingReportDTO,
    APAgingSupplierRowDTO,
)
from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportDetailRowDTO,
    OperationalReportFilterDTO,
    OperationalReportLineDetailDTO,
    OperationalReportWarningDTO,
)
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.repositories.ap_aging_report_repository import (
    APAgingDocumentRow,
    APAgingReportRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

APAgingReportRepositoryFactory = Callable[[Session], APAgingReportRepository]

_ZERO = Decimal("0.00")
_BUCKET_CODES = ("current", "1_30", "31_60", "61_90", "91_plus")


class APAgingReportService:
    """Builds AP aging outputs from posted payables truth."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        repository_factory: APAgingReportRepositoryFactory,
        permission_service: PermissionService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._repository_factory = repository_factory
        self._permission_service = permission_service

    def get_report(self, filter_dto: OperationalReportFilterDTO) -> APAgingReportDTO:
        if self._permission_service is not None:
            self._permission_service.require_permission("reports.ap_aging.view")
        company_id, as_of_date = self._normalize_filter(filter_dto)
        with self._unit_of_work_factory() as uow:
            repo = self._repository_factory(uow.session)
            rows = repo.list_open_documents(company_id, as_of_date)
            control_balance = repo.sum_control_balance(company_id, as_of_date)

        grouped: dict[int, dict[str, object]] = {}
        totals = {bucket: _ZERO for bucket in _BUCKET_CODES}

        for row in rows:
            bucket_code = self._bucket_code(row, as_of_date)
            amount = abs(row.open_amount).quantize(Decimal("0.01"))
            supplier_bucket = grouped.setdefault(
                row.supplier_id,
                {
                    "supplier_code": row.supplier_code,
                    "supplier_name": row.supplier_name,
                    "document_count": 0,
                    "current": _ZERO,
                    "1_30": _ZERO,
                    "31_60": _ZERO,
                    "61_90": _ZERO,
                    "91_plus": _ZERO,
                },
            )
            supplier_bucket[bucket_code] = self._to_decimal(supplier_bucket[bucket_code]) + amount
            supplier_bucket["document_count"] = int(supplier_bucket["document_count"]) + 1
            totals[bucket_code] += amount

        dto_rows = tuple(
            sorted(
                (
                    APAgingSupplierRowDTO(
                        supplier_id=supplier_id,
                        supplier_code=str(values["supplier_code"]),
                        supplier_name=str(values["supplier_name"]),
                        document_count=int(values["document_count"]),
                        current_amount=self._to_decimal(values["current"]),
                        bucket_1_30_amount=self._to_decimal(values["1_30"]),
                        bucket_31_60_amount=self._to_decimal(values["31_60"]),
                        bucket_61_90_amount=self._to_decimal(values["61_90"]),
                        bucket_91_plus_amount=self._to_decimal(values["91_plus"]),
                        total_amount=(
                            self._to_decimal(values["current"])
                            + self._to_decimal(values["1_30"])
                            + self._to_decimal(values["31_60"])
                            + self._to_decimal(values["61_90"])
                            + self._to_decimal(values["91_plus"])
                        ).quantize(Decimal("0.01")),
                    )
                    for supplier_id, values in grouped.items()
                ),
                key=lambda row: (row.supplier_name.lower(), row.supplier_code, row.supplier_id),
            )
        )
        grand_total = sum((row.total_amount for row in dto_rows), _ZERO).quantize(Decimal("0.01"))

        warnings: list[OperationalReportWarningDTO] = []
        if control_balance is None:
            warnings.append(
                OperationalReportWarningDTO(
                    code="ap_control_mapping_missing",
                    title="AP control reconciliation unavailable",
                    message=(
                        "AP control account mapping is not configured, so this aging report "
                        "cannot be reconciled back to the GL control account automatically."
                    ),
                )
            )
        else:
            delta = (control_balance - grand_total).quantize(Decimal("0.01"))
            if abs(delta) >= Decimal("0.01"):
                warnings.append(
                    OperationalReportWarningDTO(
                        code="ap_control_delta_detected",
                        title="AP subledger differs from control account",
                        message=(
                            "The posted AP control account balance differs from supplier-level aging "
                            f"by {self._fmt(delta)} as at {as_of_date.isoformat()}. Manual control-account "
                            "journals may exist outside supplier-attributed source documents."
                        ),
                    )
                )

        return APAgingReportDTO(
            company_id=company_id,
            as_of_date=as_of_date,
            rows=dto_rows,
            warnings=tuple(warnings),
            supplier_count=len(dto_rows),
            total_current=totals["current"].quantize(Decimal("0.01")),
            total_bucket_1_30=totals["1_30"].quantize(Decimal("0.01")),
            total_bucket_31_60=totals["31_60"].quantize(Decimal("0.01")),
            total_bucket_61_90=totals["61_90"].quantize(Decimal("0.01")),
            total_bucket_91_plus=totals["91_plus"].quantize(Decimal("0.01")),
            grand_total=grand_total,
        )

    def get_supplier_detail(
        self,
        filter_dto: OperationalReportFilterDTO,
        supplier_id: int,
        bucket_code: str | None = None,
    ) -> OperationalReportLineDetailDTO:
        company_id, as_of_date = self._normalize_filter(filter_dto)
        normalized_bucket = self._normalize_bucket(bucket_code)
        with self._unit_of_work_factory() as uow:
            repo = self._repository_factory(uow.session)
            identity = repo.get_supplier_identity(company_id, supplier_id)
            if identity is None:
                raise NotFoundError("Supplier was not found for this company.")
            rows = [
                row
                for row in repo.list_open_documents(company_id, as_of_date)
                if row.supplier_id == supplier_id
                and (normalized_bucket is None or self._bucket_code(row, as_of_date) == normalized_bucket)
            ]

        return OperationalReportLineDetailDTO(
            title=f"{identity[0]} - {identity[1]}",
            subtitle=f"As at {as_of_date.strftime('%d %b %Y')} | {self._bucket_label(normalized_bucket)}",
            columns=("Type", "Document", "Date", "Due", "Reference", "Amount"),
            rows=tuple(self._to_detail_row(row) for row in rows),
        )

    def build_print_preview_meta(
        self,
        report_dto: APAgingReportDTO,
        company_name: str,
    ) -> PrintPreviewMetaDTO:
        overdue_total = (
            report_dto.total_bucket_1_30
            + report_dto.total_bucket_31_60
            + report_dto.total_bucket_61_90
            + report_dto.total_bucket_91_plus
        ).quantize(Decimal("0.01"))
        rows = tuple(
            PrintPreviewRowDTO(
                row_type="line",
                reference_code=row.supplier_code,
                label=row.supplier_name,
                amount_text=self._fmt(row.current_amount),
                secondary_amount_text=self._fmt(
                    row.bucket_1_30_amount
                    + row.bucket_31_60_amount
                    + row.bucket_61_90_amount
                    + row.bucket_91_plus_amount
                ),
                tertiary_amount_text=self._fmt(row.total_amount),
            )
            for row in report_dto.rows
        )
        return PrintPreviewMetaDTO(
            report_title="AP Aging",
            company_name=company_name,
            period_label=f"As at {report_dto.as_of_date.strftime('%d %b %Y')}",
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=(
                f"Suppliers: {report_dto.supplier_count} | Current: {self._fmt(report_dto.total_current)} "
                f"| Overdue: {self._fmt(overdue_total)} | Outstanding: {self._fmt(report_dto.grand_total)}"
            ),
            amount_headers=("Current", "Overdue", "Total"),
            rows=rows,
        )

    def _normalize_filter(self, filter_dto: OperationalReportFilterDTO) -> tuple[int, date]:
        company_id = filter_dto.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            raise ValidationError("Select an active company to run AP aging.")
        if not filter_dto.posted_only:
            raise ValidationError("AP aging is limited to posted payables truth.")
        as_of_date = filter_dto.as_of_date or filter_dto.date_to or filter_dto.date_from or date.today()
        return company_id, as_of_date

    def _bucket_code(self, row: APAgingDocumentRow, as_of_date: date) -> str:
        if row.document_kind == "payment_credit" or row.due_date is None:
            return "current"
        overdue_days = (as_of_date - row.due_date).days
        if overdue_days <= 0:
            return "current"
        if overdue_days <= 30:
            return "1_30"
        if overdue_days <= 60:
            return "31_60"
        if overdue_days <= 90:
            return "61_90"
        return "91_plus"

    def _to_detail_row(self, row: APAgingDocumentRow) -> OperationalReportDetailRowDTO:
        return OperationalReportDetailRowDTO(
            values=(
                "Bill" if row.document_kind == "bill" else "Payment Credit",
                row.document_number,
                row.document_date.strftime("%Y-%m-%d"),
                row.due_date.strftime("%Y-%m-%d") if row.due_date else "-",
                row.reference_text or "-",
                self._fmt(abs(row.open_amount)),
            ),
            journal_entry_id=row.journal_entry_id,
            source_document_type=row.source_document_type,
            source_document_id=row.source_document_id,
        )

    @staticmethod
    def _normalize_bucket(bucket_code: str | None) -> str | None:
        if bucket_code is None:
            return None
        normalized = bucket_code.strip().lower()
        return normalized if normalized in _BUCKET_CODES else None

    @staticmethod
    def _bucket_label(bucket_code: str | None) -> str:
        return {
            None: "All Open Items",
            "current": "Current",
            "1_30": "1-30 Days",
            "31_60": "31-60 Days",
            "61_90": "61-90 Days",
            "91_plus": "91+ Days",
        }[bucket_code]

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))

    @staticmethod
    def _fmt(amount: Decimal) -> str:
        if amount == _ZERO:
            return "0.00"
        return f"{amount:,.2f}"
