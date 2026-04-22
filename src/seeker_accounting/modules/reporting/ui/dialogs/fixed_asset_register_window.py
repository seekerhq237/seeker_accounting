from __future__ import annotations

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
from seeker_accounting.modules.reporting.dto.fixed_asset_register_dto import (
    FixedAssetRegisterDetailDTO,
    FixedAssetRegisterFilterDTO,
    FixedAssetRegisterReportDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
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

_ZERO = Decimal("0.00")
_WINDOWS: list["FixedAssetRegisterWindow"] = []


class FixedAssetRegisterDetailDialog(QDialog):
    """Asset-level depreciation history surfaced from the register report."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        detail_dto: FixedAssetRegisterDetailDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._detail_dto = detail_dto

        self.setWindowTitle(f"Fixed Asset Detail | {detail_dto.asset_number}")
        self.setMinimumSize(980, 620)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 12)
        root.setSpacing(10)
        root.addWidget(self._build_header())

        self._table = QTableWidget(self)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            [
                "Run #",
                "Run Date",
                "Period End",
                "Depreciation",
                "Accum. After",
                "Carrying After",
                "Posted JE",
            ]
        )
        configure_compact_table(self._table)
        self._table.setSortingEnabled(False)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        root.addWidget(self._table, 1)

        footer = QLabel(
            "Double-click a posted depreciation row to open the related journal entry.",
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

        title = QLabel(f"{self._detail_dto.asset_number} | {self._detail_dto.asset_name}", card)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            f"{self._detail_dto.category_name} | Register position as at {self._as_of_label(self._detail_dto.as_of_date)}",
            card,
        )
        subtitle.setObjectName("PageSummary")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        meta_row = QWidget(card)
        meta_layout = QHBoxLayout(meta_row)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(18)
        self._add_pair(meta_layout, "Cost:", self._fmt(self._detail_dto.acquisition_cost))
        self._add_pair(meta_layout, "Accum. Dep.:", self._fmt(self._detail_dto.accumulated_depreciation))
        self._add_pair(meta_layout, "Carrying:", self._fmt(self._detail_dto.carrying_amount))
        meta_layout.addStretch(1)
        layout.addWidget(meta_row)
        return card

    def _bind_rows(self) -> None:
        self._table.setRowCount(len(self._detail_dto.history_rows))
        for row_index, row in enumerate(self._detail_dto.history_rows):
            run_item = QTableWidgetItem(row.run_number or f"Run {row.run_id}")
            if row.posted_journal_entry_id is not None:
                run_item.setData(Qt.ItemDataRole.UserRole, row.posted_journal_entry_id)
            self._table.setItem(row_index, 0, run_item)
            self._table.setItem(row_index, 1, QTableWidgetItem(row.run_date.strftime("%Y-%m-%d")))
            self._table.setItem(row_index, 2, QTableWidgetItem(row.period_end_date.strftime("%Y-%m-%d")))
            self._set_amount(row_index, 3, self._fmt(row.depreciation_amount))
            self._set_amount(row_index, 4, self._fmt(row.accumulated_depreciation_after))
            self._set_amount(row_index, 5, self._fmt(row.carrying_amount_after))
            self._table.setItem(
                row_index,
                6,
                QTableWidgetItem(str(row.posted_journal_entry_id) if row.posted_journal_entry_id else "-"),
            )

    def _set_amount(self, row: int, column: int, value: str) -> None:
        item = QTableWidgetItem(value)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, column, item)

    def _on_row_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        item = self._table.item(row, 0)
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
    def _fmt(value: Decimal | None) -> str:
        amount = value or _ZERO
        return f"{amount:,.2f}"

    @staticmethod
    def _as_of_label(as_of_date) -> str:
        if as_of_date is None:
            return "latest posted depreciation state"
        return as_of_date.strftime("%d %b %Y")

    @classmethod
    def open(
        cls,
        service_registry: ServiceRegistry,
        detail_dto: FixedAssetRegisterDetailDTO,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, detail_dto, parent)
        dialog.exec()


class FixedAssetRegisterWindow(QFrame):
    """Asset register report over fixed-asset operational truth."""

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
        self._report_service = service_registry.fixed_asset_register_service
        self._asset_service = service_registry.asset_service
        self._category_service = service_registry.asset_category_service
        self._context_service = ReportingContextService(
            fiscal_calendar_service=service_registry.fiscal_calendar_service,
            active_company_context=service_registry.active_company_context,
        )

        resolved_company_id = company_id or self._active_company_context.company_id
        self._current_filter = FixedAssetRegisterFilterDTO(
            company_id=resolved_company_id or 0,
            as_of_date=initial_filter.date_to if initial_filter else None,
        )
        self._current_report: FixedAssetRegisterReportDTO | None = None

        self.setObjectName("FixedAssetRegisterWindow")
        self.setWindowTitle("Fixed Asset Register")
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

        eyebrow = QLabel("Operational Report | Fixed Assets", title_block)
        eyebrow.setProperty("role", "caption")
        title_layout.addWidget(eyebrow)

        title = QLabel("Fixed Asset Register", title_block)
        title.setObjectName("PageTitle")
        title_layout.addWidget(title)

        summary = QLabel(
            "Asset-level register with acquisition cost, depreciation method, accumulated depreciation, and carrying amount.",
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

        self._asset_combo = QComboBox(filters)
        self._asset_combo.setMinimumWidth(260)
        self._asset_combo.currentIndexChanged.connect(self._on_aux_filter_changed)
        filters_layout.addWidget(self._labeled_field("Asset", self._asset_combo, filters))

        row = QWidget(filters)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        self._category_combo = QComboBox(row)
        self._category_combo.currentIndexChanged.connect(self._on_aux_filter_changed)
        row_layout.addWidget(self._labeled_field("Category", self._category_combo, row))

        self._status_combo = QComboBox(row)
        self._status_combo.currentIndexChanged.connect(self._on_aux_filter_changed)
        row_layout.addWidget(self._labeled_field("Status", self._status_combo, row))

        filters_layout.addWidget(row)
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

        self._status_combo = QComboBox(self._filter_bar)
        self._status_combo.setMinimumWidth(120)
        self._status_combo.currentIndexChanged.connect(self._on_aux_filter_changed)
        fl.insertWidget(0, self._status_combo)

        status_lbl = QLabel("Status:", self._filter_bar)
        status_lbl.setProperty("role", "caption")
        fl.insertWidget(0, status_lbl)

        sep2 = QFrame(self._filter_bar)
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        fl.insertWidget(0, sep2)

        self._category_combo = QComboBox(self._filter_bar)
        self._category_combo.setMinimumWidth(150)
        self._category_combo.currentIndexChanged.connect(self._on_aux_filter_changed)
        fl.insertWidget(0, self._category_combo)

        cat_lbl = QLabel("Category:", self._filter_bar)
        cat_lbl.setProperty("role", "caption")
        fl.insertWidget(0, cat_lbl)

        sep1 = QFrame(self._filter_bar)
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        fl.insertWidget(0, sep1)

        self._asset_combo = QComboBox(self._filter_bar)
        self._asset_combo.setMinimumWidth(200)
        self._asset_combo.currentIndexChanged.connect(self._on_aux_filter_changed)
        fl.insertWidget(0, self._asset_combo)

        asset_lbl = QLabel("Asset:", self._filter_bar)
        asset_lbl.setProperty("role", "caption")
        fl.insertWidget(0, asset_lbl)

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
            ("cost", "Acquisition Cost"),
            ("accumulated", "Accum. Dep."),
            ("carrying", "Carrying Amount"),
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
            self._summary_labels[key] = value
        return strip

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_table_panel())
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Active Company",
                message="Select an active company before opening the fixed asset register.",
                parent=self,
            )
        )
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Fixed Asset Data",
                message="No assets matched the selected as-of date and filters.",
                parent=self,
            )
        )
        return self._stack

    def _build_table_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 0, 20, 20)
        self._table = QTableWidget(panel)
        self._table.setColumnCount(10)
        self._table.setHorizontalHeaderLabels(
            [
                "Asset Code",
                "Asset Name",
                "Category",
                "Acquired",
                "Cost",
                "Useful Life",
                "Method",
                "Accum. Dep.",
                "Carrying",
                "Status",
            ]
        )
        configure_compact_table(self._table)
        self._table.setSortingEnabled(False)
        self._table.cellDoubleClicked.connect(self._on_table_double_clicked)
        layout.addWidget(self._table, 1)
        return panel

    def _load_aux_filters(self) -> None:
        company_id = self._current_filter.company_id
        self._asset_combo.blockSignals(True)
        self._category_combo.blockSignals(True)
        self._status_combo.blockSignals(True)
        try:
            self._asset_combo.clear()
            self._category_combo.clear()
            self._status_combo.clear()
            self._asset_combo.addItem("All assets", None)
            self._category_combo.addItem("All categories", None)
            self._status_combo.addItem("All statuses", None)
            for status_code in ("draft", "active", "fully_depreciated", "disposed"):
                self._status_combo.addItem(self._titleize(status_code), status_code)
            if company_id <= 0:
                return
            for asset in self._asset_service.list_assets(company_id, active_only=False):
                self._asset_combo.addItem(f"{asset.asset_number} | {asset.asset_name}", asset.id)
            for category in self._category_service.list_asset_categories(company_id, active_only=False):
                self._category_combo.addItem(f"{category.code} | {category.name}", category.id)
            self._set_combo_value(self._asset_combo, self._current_filter.asset_id)
            self._set_combo_value(self._category_combo, self._current_filter.category_id)
            self._set_combo_value(self._status_combo, self._current_filter.status_code)
        finally:
            self._asset_combo.blockSignals(False)
            self._category_combo.blockSignals(False)
            self._status_combo.blockSignals(False)

    def _sync_filter_context(self) -> None:
        company_name = self._active_company_context.company_name or ""
        self._filter_bar.set_company_context(self._current_filter.company_id, company_name)
        self._filter_bar.set_filter(
            ReportingFilterDTO(
                company_id=self._current_filter.company_id,
                date_from=None,
                date_to=self._current_filter.as_of_date,
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
            show_error(self, "Fixed Asset Register", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "Fixed Asset Register", str(exc))
            return

        self._current_report = report
        self._update_warning_band(report.warnings)
        self._update_summary(report)
        if not report.rows:
            self._stack.setCurrentIndex(2)
            return
        self._bind_report(report)
        self._stack.setCurrentIndex(0)

    def _bind_report(self, report: FixedAssetRegisterReportDTO) -> None:
        self._table.setRowCount(len(report.rows))
        for row_index, row in enumerate(report.rows):
            code_item = QTableWidgetItem(row.asset_number)
            code_item.setData(Qt.ItemDataRole.UserRole, row.asset_id)
            self._table.setItem(row_index, 0, code_item)
            self._table.setItem(row_index, 1, QTableWidgetItem(row.asset_name))
            self._table.setItem(row_index, 2, QTableWidgetItem(f"{row.category_code} | {row.category_name}"))
            self._table.setItem(row_index, 3, QTableWidgetItem(row.acquisition_date.strftime("%Y-%m-%d")))
            self._set_amount(row_index, 4, self._fmt(row.acquisition_cost))
            self._table.setItem(row_index, 5, QTableWidgetItem(f"{row.useful_life_months} mo"))
            self._table.setItem(row_index, 6, QTableWidgetItem(self._titleize(row.depreciation_method_code)))
            self._set_amount(row_index, 7, self._fmt(row.accumulated_depreciation))
            self._set_amount(row_index, 8, self._fmt(row.carrying_amount))
            self._table.setItem(row_index, 9, QTableWidgetItem(self._titleize(row.status_code)))

    def _set_amount(self, row: int, column: int, value: str) -> None:
        item = QTableWidgetItem(value)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, column, item)

    def _update_warning_band(self, warnings) -> None:
        messages = [warning.message for warning in warnings]
        messages.append("This as-of report uses the 'To' date from the shared filter bar.")
        self._warning_label.setText(" | ".join(messages))
        self._warning_band.setVisible(bool(messages))

    def _update_summary(self, report: FixedAssetRegisterReportDTO | None) -> None:
        self._summary_labels["cost"].setText(self._fmt(report.total_acquisition_cost if report else _ZERO))
        self._summary_labels["accumulated"].setText(
            self._fmt(report.total_accumulated_depreciation if report else _ZERO)
        )
        self._summary_labels["carrying"].setText(self._fmt(report.total_carrying_amount if report else _ZERO))

    def _build_filter_from_ui(self, filter_dto: ReportingFilterDTO) -> FixedAssetRegisterFilterDTO:
        return FixedAssetRegisterFilterDTO(
            company_id=filter_dto.company_id or self._active_company_context.company_id or 0,
            as_of_date=filter_dto.date_to,
            asset_id=self._selected_id(self._asset_combo),
            category_id=self._selected_id(self._category_combo),
            status_code=self._selected_code(self._status_combo),
        )

    def _on_company_changed(self, company_id: object, company_name: object) -> None:  # noqa: ARG002
        if not isinstance(company_id, int):
            return
        self._current_filter = FixedAssetRegisterFilterDTO(company_id=company_id, as_of_date=self._current_filter.as_of_date)
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
        item = self._table.item(row, 0)
        if item is None:
            return
        asset_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(asset_id, int):
            return
        try:
            detail = self._report_service.get_asset_detail(self._current_filter, asset_id)
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Fixed Asset Register", str(exc))
            return
        FixedAssetRegisterDetailDialog.open(self._service_registry, detail, parent=self)

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
    def _selected_code(combo: QComboBox) -> str | None:
        value = combo.currentData()
        return value if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _set_combo_value(combo: QComboBox, value) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return
        combo.setCurrentIndex(0)

    @staticmethod
    def _titleize(value: str | None) -> str:
        if not value:
            return "-"
        return value.replace("_", " ").title()

    @staticmethod
    def _fmt(value: Decimal | None) -> str:
        amount = value or _ZERO
        return f"{amount:,.2f}"

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
