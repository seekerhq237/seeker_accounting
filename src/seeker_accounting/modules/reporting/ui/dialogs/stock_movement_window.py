from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.dto.stock_movement_report_dto import (
    StockMovementItemDetailDTO,
    StockMovementReportDTO,
    StockMovementReportFilterDTO,
)
from seeker_accounting.modules.reporting.services.reporting_context_service import (
    ReportingContextService,
)
from seeker_accounting.modules.reporting.ui.dialogs.journal_source_detail_dialog import (
    JournalSourceDetailDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.report_print_preview_dialog import (
    ReportPrintPreviewDialog,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_context_strip import (
    ReportingContextStrip,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_empty_state import (
    ReportingEmptyState,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_filter_bar import (
    ReportingFilterBar,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_ZERO_QTY = Decimal("0.0000")
_WINDOWS: list["StockMovementWindow"] = []


class StockMovementDetailDialog(QDialog):
    """Movement ledger for a single stock item inside the selected report context."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        detail_dto: StockMovementItemDetailDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._detail_dto = detail_dto

        self.setWindowTitle(f"Stock Movement Detail | {detail_dto.item_code}")
        self.setMinimumSize(1100, 620)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 12)
        root.setSpacing(10)

        root.addWidget(self._build_header())

        self._table = QTableWidget(self)
        self._table.setColumnCount(10)
        self._table.setHorizontalHeaderLabels(
            [
                "Date",
                "Document #",
                "Type",
                "Reference",
                "Location",
                "Inward",
                "Outward",
                "Running Qty",
                "Unit Cost",
                "Amount",
            ]
        )
        configure_compact_table(self._table)
        self._table.setSortingEnabled(False)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        root.addWidget(self._table, 1)

        footer = QLabel(
            "Double-click a posted movement row to open the journal detail when that link exists.",
            self,
        )
        footer.setProperty("role", "caption")
        root.addWidget(footer)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._bind_rows()

    def _build_header(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(6)

        title = QLabel(
            f"{self._detail_dto.item_code} | {self._detail_dto.item_name}",
            card,
        )
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            f"Movement ledger for {self._period_label(self._detail_dto.date_from, self._detail_dto.date_to)}",
            card,
        )
        subtitle.setObjectName("PageSummary")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        meta_row = QWidget(card)
        meta_layout = QHBoxLayout(meta_row)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(18)
        self._add_pair(meta_layout, "UOM:", self._detail_dto.unit_of_measure_code)
        self._add_pair(meta_layout, "Opening:", self._fmt_qty(self._detail_dto.opening_quantity))
        self._add_pair(meta_layout, "Inward:", self._fmt_qty(self._detail_dto.inward_quantity))
        self._add_pair(meta_layout, "Outward:", self._fmt_qty(self._detail_dto.outward_quantity))
        self._add_pair(meta_layout, "Closing:", self._fmt_qty(self._detail_dto.closing_quantity))
        meta_layout.addStretch(1)
        layout.addWidget(meta_row)
        return card

    def _bind_rows(self) -> None:
        rows = self._detail_dto.rows
        self._table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self._set_text(row_index, 0, row.document_date.strftime("%Y-%m-%d"))
            document_item = QTableWidgetItem(row.document_number)
            if row.posted_journal_entry_id is not None:
                document_item.setData(Qt.ItemDataRole.UserRole, row.posted_journal_entry_id)
            self._table.setItem(row_index, 1, document_item)
            self._set_text(row_index, 2, row.document_type_code.replace("_", " ").title())
            self._set_text(row_index, 3, row.reference_number or "-")
            location_label = " | ".join(
                part for part in (row.location_code, row.location_name) if part
            ) or "-"
            self._set_text(row_index, 4, location_label)
            self._set_amount(row_index, 5, self._fmt_qty(row.inward_quantity))
            self._set_amount(row_index, 6, self._fmt_qty(row.outward_quantity))
            self._set_amount(row_index, 7, self._fmt_qty(row.running_quantity))
            self._set_amount(row_index, 8, self._fmt_unit_cost(row.unit_cost))
            self._set_amount(row_index, 9, self._fmt_amount(row.line_amount))

    def _set_text(self, row: int, column: int, value: str) -> None:
        self._table.setItem(row, column, QTableWidgetItem(value))

    def _set_amount(self, row: int, column: int, value: str) -> None:
        item = QTableWidgetItem(value)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, column, item)

    def _on_row_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        item = self._table.item(row, 1)
        if item is None:
            return
        journal_entry_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(journal_entry_id, int):
            return
        JournalSourceDetailDialog.open(
            self._service_registry,
            self._detail_dto.company_id,
            journal_entry_id,
            parent=self,
        )

    def _add_pair(self, layout: QHBoxLayout, label: str, value: str) -> None:
        pair = QWidget(self)
        pair_layout = QHBoxLayout(pair)
        pair_layout.setContentsMargins(0, 0, 0, 0)
        pair_layout.setSpacing(6)
        caption = QLabel(label, pair)
        caption.setProperty("role", "caption")
        pair_layout.addWidget(caption)
        text = QLabel(value, pair)
        text.setObjectName("TopBarValue")
        pair_layout.addWidget(text)
        layout.addWidget(pair)

    @staticmethod
    def _fmt_qty(value: Decimal | None) -> str:
        quantity = value or _ZERO_QTY
        text = f"{quantity:,.4f}"
        return text.rstrip("0").rstrip(".") if "." in text else text

    @staticmethod
    def _fmt_unit_cost(value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"{value:,.4f}"

    @staticmethod
    def _fmt_amount(value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"{value:,.2f}"

    @staticmethod
    def _period_label(date_from, date_to) -> str:
        if date_from is None and date_to is None:
            return "all posted movement"
        if date_from is None:
            return f"up to {date_to.strftime('%d %b %Y')}" if date_to else "all posted movement"
        if date_to is None:
            return f"from {date_from.strftime('%d %b %Y')}"
        return f"{date_from.strftime('%d %b %Y')} - {date_to.strftime('%d %b %Y')}"

    @classmethod
    def open(
        cls,
        service_registry: ServiceRegistry,
        detail_dto: StockMovementItemDetailDTO,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, detail_dto, parent)
        dialog.exec()


class StockMovementWindow(QFrame):
    """Focused operational report window for posted stock movement analysis."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int | None,
        initial_filter: ReportingFilterDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._active_company_context = service_registry.active_company_context
        self._report_service = service_registry.stock_movement_report_service
        self._item_service = service_registry.item_service
        self._location_service = service_registry.inventory_location_service
        self._context_service = ReportingContextService(
            fiscal_calendar_service=service_registry.fiscal_calendar_service,
            active_company_context=service_registry.active_company_context,
        )

        resolved_company_id = company_id or self._active_company_context.company_id
        self._current_filter = StockMovementReportFilterDTO(
            company_id=resolved_company_id or 0,
            date_from=initial_filter.date_from if initial_filter else None,
            date_to=initial_filter.date_to if initial_filter else None,
        )
        self._current_report: StockMovementReportDTO | None = None

        self.setObjectName("StockMovementWindow")
        self.setWindowTitle("Stock Movement Report")
        self.setMinimumSize(960, 620)
        self.setWindowFlag(Qt.WindowType.Window, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(ReportingContextStrip(self._context_service, service_registry, self))
        root.addWidget(self._build_filter_bar())
        root.addWidget(self._build_warning_band())
        root.addWidget(self._build_summary_strip())
        root.addWidget(self._build_content_stack(), 1)

        self._active_company_context.active_company_changed.connect(self._on_company_changed)
        self._sync_filter_context()
        self._load_aux_filters()
        self._load_report()

    def _build_header(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(18)

        title_block = QWidget(card)
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)

        eyebrow = QLabel("Operational Report | Inventory", title_block)
        eyebrow.setProperty("role", "caption")
        title_layout.addWidget(eyebrow)

        title = QLabel("Stock Movement Report", title_block)
        title.setObjectName("PageTitle")
        title_layout.addWidget(title)

        summary = QLabel(
            "Posted stock movement by item, with opening, inward, outward, and closing quantities ready for review and print preview.",
            title_block,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        title_layout.addWidget(summary)
        layout.addWidget(title_block, 1)

        filters = QWidget(card)
        filters_layout = QVBoxLayout(filters)
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.setSpacing(8)

        self._item_combo = QComboBox(filters)
        self._item_combo.setMinimumWidth(260)
        self._item_combo.currentIndexChanged.connect(self._on_aux_filter_changed)
        filters_layout.addWidget(self._labeled_field("Stock Item", self._item_combo, filters))

        self._location_combo = QComboBox(filters)
        self._location_combo.setMinimumWidth(260)
        self._location_combo.currentIndexChanged.connect(self._on_aux_filter_changed)
        filters_layout.addWidget(self._labeled_field("Location", self._location_combo, filters))

        layout.addWidget(filters)
        return card

    def _build_filter_bar(self) -> QWidget:
        self._filter_bar = ReportingFilterBar(self)
        self._filter_bar.refresh_requested.connect(self._on_refresh_requested)
        self._filter_bar.print_preview_requested.connect(self._on_print_preview_requested)
        self._filter_bar.template_preview_requested.connect(lambda meta: None)
        self._filter_bar._posted_only.setChecked(True)
        self._filter_bar._posted_only.setEnabled(False)
        self._filter_bar._template_btn.hide()

        fl = self._filter_bar.layout()

        self._location_combo = QComboBox(self._filter_bar)
        self._location_combo.setMinimumWidth(180)
        self._location_combo.currentIndexChanged.connect(self._on_aux_filter_changed)
        fl.insertWidget(0, self._location_combo)

        loc_lbl = QLabel("Location:", self._filter_bar)
        loc_lbl.setProperty("role", "caption")
        fl.insertWidget(0, loc_lbl)

        sep = QFrame(self._filter_bar)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        fl.insertWidget(0, sep)

        self._item_combo = QComboBox(self._filter_bar)
        self._item_combo.setMinimumWidth(200)
        self._item_combo.currentIndexChanged.connect(self._on_aux_filter_changed)
        fl.insertWidget(0, self._item_combo)

        item_lbl = QLabel("Item:", self._filter_bar)
        item_lbl.setProperty("role", "caption")
        fl.insertWidget(0, item_lbl)

        return self._filter_bar

    def _build_warning_band(self) -> QWidget:
        self._warning_band = QFrame(self)
        self._warning_band.setObjectName("PageCard")
        layout = QHBoxLayout(self._warning_band)
        layout.setContentsMargins(16, 10, 16, 10)
        self._warning_label = QLabel(self._warning_band)
        self._warning_label.setObjectName("PageSummary")
        self._warning_label.setWordWrap(True)
        layout.addWidget(self._warning_label, 1)
        self._warning_band.hide()
        return self._warning_band

    def _build_summary_strip(self) -> QWidget:
        strip = QWidget(self)
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(20, 6, 20, 6)
        layout.setSpacing(8)
        self._summary_labels: dict[str, QLabel] = {}
        for key, title in (
            ("opening", "Opening Qty"),
            ("inward", "Inward Qty"),
            ("outward", "Outward Qty"),
            ("closing", "Closing Qty"),
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
            value = QLabel("0", card)
            value.setObjectName("InfoCardTitle")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            card_layout.addWidget(value)
            layout.addWidget(card, 1)
            self._summary_labels[key] = value
        return strip

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_table_panel())
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Active Company",
                message="Select an active company before opening the stock movement report.",
                parent=self,
            )
        )
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Posted Stock Movement",
                message="No posted stock movement matched the selected date range and filters.",
                parent=self,
            )
        )
        return self._stack

    def _build_table_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 0, 20, 20)

        self._table = QTableWidget(panel)
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            [
                "Item Code",
                "Item Name",
                "UOM",
                "Opening",
                "Inward",
                "Outward",
                "Closing",
                "Moves",
            ]
        )
        configure_compact_table(self._table)
        self._table.setSortingEnabled(False)
        self._table.cellDoubleClicked.connect(self._on_table_double_clicked)
        layout.addWidget(self._table, 1)
        return panel

    def _load_aux_filters(self) -> None:
        company_id = self._current_filter.company_id
        self._item_combo.blockSignals(True)
        self._location_combo.blockSignals(True)
        try:
            self._item_combo.clear()
            self._location_combo.clear()
            self._item_combo.addItem("All stock items", None)
            self._location_combo.addItem("All locations", None)
            if company_id <= 0:
                return
            for item in self._item_service.list_items(company_id, active_only=False, item_type_code="stock"):
                self._item_combo.addItem(f"{item.item_code} | {item.item_name}", item.id)
            for location in self._location_service.list_inventory_locations(company_id, active_only=False):
                self._location_combo.addItem(f"{location.code} | {location.name}", location.id)
            self._set_combo_value(self._item_combo, self._current_filter.item_id)
            self._set_combo_value(self._location_combo, self._current_filter.location_id)
        finally:
            self._item_combo.blockSignals(False)
            self._location_combo.blockSignals(False)

    def _sync_filter_context(self) -> None:
        company_name = self._active_company_context.company_name or ""
        self._filter_bar.set_company_context(self._current_filter.company_id, company_name)
        self._filter_bar.set_filter(
            ReportingFilterDTO(
                company_id=self._current_filter.company_id,
                date_from=self._current_filter.date_from,
                date_to=self._current_filter.date_to,
                posted_only=True,
            )
        )
        self._filter_bar._posted_only.setChecked(True)

    def _load_report(self) -> None:
        if self._current_filter.company_id <= 0:
            self._current_report = None
            self._update_warning_band(())
            self._update_summary(None)
            self._stack.setCurrentIndex(1)
            return

        try:
            report = self._report_service.get_report(self._current_filter)
        except ValidationError as exc:
            show_error(self, "Stock Movement Report", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "Stock Movement Report", str(exc))
            return

        self._current_report = report
        self._update_warning_band(report.warnings)
        self._update_summary(report)
        if not report.rows:
            self._stack.setCurrentIndex(2)
            return
        self._bind_report(report)
        self._stack.setCurrentIndex(0)

    def _bind_report(self, report: StockMovementReportDTO) -> None:
        self._table.setRowCount(len(report.rows))
        for row_index, row in enumerate(report.rows):
            code_item = QTableWidgetItem(row.item_code)
            code_item.setData(Qt.ItemDataRole.UserRole, row.item_id)
            self._table.setItem(row_index, 0, code_item)
            self._table.setItem(row_index, 1, QTableWidgetItem(row.item_name))
            self._table.setItem(row_index, 2, QTableWidgetItem(row.unit_of_measure_code))
            self._set_amount_item(row_index, 3, self._fmt_qty(row.opening_quantity))
            self._set_amount_item(row_index, 4, self._fmt_qty(row.inward_quantity))
            self._set_amount_item(row_index, 5, self._fmt_qty(row.outward_quantity))
            self._set_amount_item(row_index, 6, self._fmt_qty(row.closing_quantity))
            self._set_amount_item(row_index, 7, str(row.movement_count), align_right=False)

    def _set_amount_item(
        self,
        row: int,
        column: int,
        text: str,
        *,
        align_right: bool = True,
    ) -> None:
        item = QTableWidgetItem(text)
        if align_right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, column, item)

    def _update_warning_band(self, warnings) -> None:
        messages = [warning.message for warning in warnings]
        if self._current_filter.location_id is not None and self._current_report and self._current_report.location_label:
            messages.append(f"Location filter: {self._current_report.location_label}")
        if not messages:
            self._warning_band.hide()
            return
        self._warning_label.setText(" | ".join(messages))
        self._warning_band.show()

    def _update_summary(self, report: StockMovementReportDTO | None) -> None:
        opening = report.total_opening_quantity if report else _ZERO_QTY
        inward = report.total_inward_quantity if report else _ZERO_QTY
        outward = report.total_outward_quantity if report else _ZERO_QTY
        closing = report.total_closing_quantity if report else _ZERO_QTY
        self._summary_labels["opening"].setText(self._fmt_qty(opening))
        self._summary_labels["inward"].setText(self._fmt_qty(inward))
        self._summary_labels["outward"].setText(self._fmt_qty(outward))
        self._summary_labels["closing"].setText(self._fmt_qty(closing))

    def _build_filter_from_ui(self, filter_dto: ReportingFilterDTO) -> StockMovementReportFilterDTO:
        return StockMovementReportFilterDTO(
            company_id=filter_dto.company_id or self._active_company_context.company_id or 0,
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
            item_id=self._selected_id(self._item_combo),
            location_id=self._selected_id(self._location_combo),
        )

    def _on_company_changed(self, company_id: object, company_name: object) -> None:  # noqa: ARG002
        if not isinstance(company_id, int):
            return
        self._current_filter = StockMovementReportFilterDTO(
            company_id=company_id,
            date_from=self._current_filter.date_from,
            date_to=self._current_filter.date_to,
            item_id=None,
            location_id=None,
        )
        self._sync_filter_context()
        self._load_aux_filters()
        self._load_report()

    def _on_refresh_requested(self, filter_dto: object) -> None:
        if not isinstance(filter_dto, ReportingFilterDTO):
            return
        self._current_filter = self._build_filter_from_ui(filter_dto)
        self._sync_filter_context()
        self._load_report()

    def _on_aux_filter_changed(self, index: int) -> None:  # noqa: ARG002
        self._current_filter = self._build_filter_from_ui(self._filter_bar.get_filter())
        self._load_report()

    def _on_print_preview_requested(self, meta: object) -> None:  # noqa: ARG002
        if self._current_report is None:
            return
        company_name = self._active_company_context.company_name or "Unknown Company"
        preview_meta = self._report_service.build_print_preview_meta(self._current_report, company_name)
        ReportPrintPreviewDialog.show_preview(preview_meta, parent=self)

    def _on_table_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        if self._current_report is None:
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        item_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(item_id, int):
            return
        try:
            detail = self._report_service.get_item_detail(self._current_filter, item_id)
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Stock Movement Report", str(exc))
            return
        StockMovementDetailDialog.open(self._service_registry, detail, parent=self)

    def _labeled_field(self, caption: str, field: QWidget, parent: QWidget) -> QWidget:
        wrapper = QWidget(parent)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(caption, wrapper)
        label.setProperty("role", "caption")
        layout.addWidget(label)
        layout.addWidget(field)
        return wrapper

    @staticmethod
    def _selected_id(combo: QComboBox) -> int | None:
        value = combo.currentData()
        return value if isinstance(value, int) and value > 0 else None

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: int | None) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return
        combo.setCurrentIndex(0)

    @staticmethod
    def _fmt_qty(value: Decimal | None) -> str:
        quantity = value or _ZERO_QTY
        text = f"{quantity:,.4f}"
        return text.rstrip("0").rstrip(".") if "." in text else text

    @classmethod
    def open(
        cls,
        service_registry: ServiceRegistry,
        company_id: int | None,
        initial_filter: ReportingFilterDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        window = cls(service_registry, company_id, initial_filter=initial_filter, parent=parent)
        window.show()
        _WINDOWS.append(window)
        window.destroyed.connect(lambda: _WINDOWS.remove(window) if window in _WINDOWS else None)
