from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.ap_aging_report_dto import APAgingReportDTO
from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportFilterDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.services.reporting_context_service import (
    ReportingContextService,
)
from seeker_accounting.modules.reporting.ui.dialogs.operational_report_line_detail_dialog import (
    OperationalReportLineDetailDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.report_print_preview_dialog import (
    ReportPrintPreviewDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.supplier_statement_window import (
    SupplierStatementWindow,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_context_strip import (
    ReportingContextStrip,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_empty_state import (
    ReportingEmptyState,
)
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table
from seeker_accounting.platform.exceptions import ValidationError

_ZERO = Decimal("0.00")


class APAgingWindow(QFrame):
    """Focused child window for AP aging."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int | None,
        initial_filter: ReportingFilterDTO | OperationalReportFilterDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._active_company_context = service_registry.active_company_context
        self._report_service = service_registry.ap_aging_report_service
        self._context_service = ReportingContextService(
            fiscal_calendar_service=service_registry.fiscal_calendar_service,
            active_company_context=service_registry.active_company_context,
        )
        self._current_filter = self._coerce_filter(company_id, initial_filter)
        self._current_report: APAgingReportDTO | None = None

        self.setObjectName("APAgingWindow")
        self.setWindowTitle("AP Aging")
        self.setMinimumSize(960, 620)
        self.setWindowFlag(Qt.WindowType.Window, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(ReportingContextStrip(self._context_service, service_registry, self))
        root.addWidget(self._build_controls())
        root.addWidget(self._build_warning_band())
        root.addWidget(self._build_summary_strip())
        root.addWidget(self._build_stack(), 1)

        self._active_company_context.active_company_changed.connect(self._on_company_changed)
        self._load_report()

    def _build_header(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(4)
        eyebrow = QLabel("Operational Reports | Payables", card)
        eyebrow.setProperty("role", "caption")
        layout.addWidget(eyebrow)
        title = QLabel("Accounts Payable Aging", card)
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Posted supplier balances grouped into aging buckets with direct drilldown to statement and document detail.",
            card,
        )
        subtitle.setObjectName("PageSummary")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        return card

    def _build_controls(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        label = QLabel("As Of", card)
        label.setProperty("role", "caption")
        layout.addWidget(label)

        self._as_of_edit = QDateEdit(card)
        self._as_of_edit.setCalendarPopup(True)
        self._as_of_edit.setFixedWidth(130)
        self._as_of_edit.setDate(QDate(self._current_filter.as_of_date.year, self._current_filter.as_of_date.month, self._current_filter.as_of_date.day))
        layout.addWidget(self._as_of_edit)

        layout.addStretch(1)

        refresh = QPushButton("Refresh", card)
        refresh.setProperty("variant", "primary")
        refresh.clicked.connect(self._on_refresh)
        layout.addWidget(refresh)

        print_btn = QPushButton("Print Preview", card)
        print_btn.setProperty("variant", "secondary")
        print_btn.clicked.connect(self._on_print_preview)
        layout.addWidget(print_btn)
        return card

    def _build_warning_band(self) -> QWidget:
        self._warning_band = QFrame(self)
        self._warning_band.setObjectName("PageCard")
        layout = QVBoxLayout(self._warning_band)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)
        self._warning_label = QLabel(self._warning_band)
        self._warning_label.setObjectName("PageSummary")
        self._warning_label.setWordWrap(True)
        layout.addWidget(self._warning_label)
        self._warning_band.hide()
        return self._warning_band

    def _build_summary_strip(self) -> QWidget:
        strip = QWidget(self)
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(20, 6, 20, 6)
        layout.setSpacing(8)
        self._summary_values: dict[str, QLabel] = {}
        for key, title in (
            ("outstanding", "Outstanding"),
            ("current", "Current"),
            ("overdue", "Overdue"),
            ("suppliers", "Suppliers"),
        ):
            card = QFrame(strip)
            card.setObjectName("InfoCard")
            card.setProperty("card", True)
            card.setFixedHeight(34)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(10, 0, 10, 0)
            card_layout.setSpacing(8)
            caption = QLabel(title, card)
            caption.setProperty("role", "caption")
            card_layout.addWidget(caption)
            card_layout.addStretch(1)
            value = QLabel("0.00", card)
            value.setObjectName("InfoCardTitle")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            card_layout.addWidget(value)
            layout.addWidget(card, 1)
            self._summary_values[key] = value
        return strip

    def _build_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_table_panel())
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Active Company",
                message="Select an active company before opening AP aging.",
                parent=self,
            )
        )
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Payables Activity",
                message="No posted payable balances were found for the selected as-of date.",
                parent=self,
            )
        )
        return self._stack

    def _build_table_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 0, 20, 20)
        self._table = QTableWidget(panel)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(["Supplier", "Current", "1-30", "31-60", "61-90", "91+", "Total"])
        configure_compact_table(self._table)
        self._table.setSortingEnabled(False)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self._table, 1)
        return panel

    def _load_report(self) -> None:
        company_id = self._current_filter.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            self._current_report = None
            self._stack.setCurrentIndex(1)
            return
        try:
            report = self._report_service.get_report(self._current_filter)
        except ValidationError as exc:
            show_error(self, "AP Aging", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "AP Aging", str(exc))
            return

        self._current_report = report
        self._update_warning_band(report)
        self._update_summary(report)
        if not report.rows:
            self._table.setRowCount(0)
            self._stack.setCurrentIndex(2)
            return
        self._bind_rows(report)
        self._stack.setCurrentIndex(0)

    def _update_warning_band(self, report: APAgingReportDTO) -> None:
        if not report.warnings:
            self._warning_band.hide()
            return
        self._warning_label.setText(" | ".join(w.message for w in report.warnings))
        self._warning_band.show()

    def _update_summary(self, report: APAgingReportDTO) -> None:
        overdue = (
            report.total_bucket_1_30
            + report.total_bucket_31_60
            + report.total_bucket_61_90
            + report.total_bucket_91_plus
        ).quantize(Decimal("0.01"))
        self._summary_values["outstanding"].setText(self._fmt(report.grand_total))
        self._summary_values["current"].setText(self._fmt(report.total_current))
        self._summary_values["overdue"].setText(self._fmt(overdue))
        self._summary_values["suppliers"].setText(str(report.supplier_count))

    def _bind_rows(self, report: APAgingReportDTO) -> None:
        self._table.setRowCount(len(report.rows))
        for row_index, row in enumerate(report.rows):
            supplier_item = QTableWidgetItem(f"{row.supplier_code} - {row.supplier_name}")
            supplier_item.setData(Qt.ItemDataRole.UserRole, row.supplier_id)
            self._table.setItem(row_index, 0, supplier_item)
            self._set_amount(row_index, 1, row.current_amount)
            self._set_amount(row_index, 2, row.bucket_1_30_amount)
            self._set_amount(row_index, 3, row.bucket_31_60_amount)
            self._set_amount(row_index, 4, row.bucket_61_90_amount)
            self._set_amount(row_index, 5, row.bucket_91_plus_amount)
            self._set_amount(row_index, 6, row.total_amount)

    def _set_amount(self, row_index: int, column_index: int, amount: Decimal) -> None:
        item = QTableWidgetItem(self._fmt(amount))
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row_index, column_index, item)

    def _on_refresh(self) -> None:
        qdate = self._as_of_edit.date()
        self._current_filter = OperationalReportFilterDTO(
            company_id=self._active_company_context.company_id,
            as_of_date=date(qdate.year(), qdate.month(), qdate.day()),
            posted_only=True,
        )
        self._load_report()

    def _on_print_preview(self) -> None:
        if self._current_report is None:
            return
        preview = self._report_service.build_print_preview_meta(
            self._current_report,
            self._active_company_context.company_name or "Unknown Company",
        )
        ReportPrintPreviewDialog.show_preview(preview, parent=self)

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        supplier_item = self._table.item(row, 0)
        if supplier_item is None:
            return
        supplier_id = supplier_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(supplier_id, int):
            return
        if column == 0:
            as_of = self._current_filter.as_of_date
            SupplierStatementWindow.open(
                self._service_registry,
                self._current_filter.company_id,
                initial_filter=OperationalReportFilterDTO(
                    company_id=self._current_filter.company_id,
                    supplier_id=supplier_id,
                    date_from=as_of.replace(day=1),
                    date_to=as_of,
                    posted_only=True,
                ),
                parent=self,
            )
            return

        bucket_map = {1: "current", 2: "1_30", 3: "31_60", 4: "61_90", 5: "91_plus", 6: None}
        detail = self._report_service.get_supplier_detail(self._current_filter, supplier_id, bucket_map.get(column))
        OperationalReportLineDetailDialog.open(
            self._service_registry,
            self._current_filter.company_id or 0,
            detail,
            parent=self,
        )

    def _on_company_changed(self, company_id: object, company_name: object) -> None:  # noqa: ARG002
        if isinstance(company_id, int) and company_id > 0:
            self._current_filter = OperationalReportFilterDTO(
                company_id=company_id,
                as_of_date=self._current_filter.as_of_date,
                posted_only=True,
            )
            self._load_report()

    @staticmethod
    def _coerce_filter(
        company_id: int | None,
        initial_filter: ReportingFilterDTO | OperationalReportFilterDTO | None,
    ) -> OperationalReportFilterDTO:
        resolved_company_id = company_id
        if isinstance(initial_filter, OperationalReportFilterDTO):
            return OperationalReportFilterDTO(
                company_id=resolved_company_id or initial_filter.company_id,
                as_of_date=initial_filter.as_of_date or initial_filter.date_to or initial_filter.date_from or date.today(),
                posted_only=True,
            )
        if isinstance(initial_filter, ReportingFilterDTO):
            return OperationalReportFilterDTO(
                company_id=resolved_company_id or initial_filter.company_id,
                as_of_date=initial_filter.date_to or initial_filter.date_from or date.today(),
                posted_only=True,
            )
        return OperationalReportFilterDTO(company_id=resolved_company_id, as_of_date=date.today(), posted_only=True)

    @staticmethod
    def _fmt(amount: Decimal) -> str:
        if amount == _ZERO:
            return "0.00"
        return f"{amount:,.2f}"

    @classmethod
    def open(
        cls,
        service_registry: ServiceRegistry,
        company_id: int | None,
        initial_filter: ReportingFilterDTO | OperationalReportFilterDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        window = cls(service_registry, company_id, initial_filter=initial_filter, parent=parent)
        window.show()
