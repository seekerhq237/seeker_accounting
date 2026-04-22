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
from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportFilterDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.dto.supplier_statement_dto import (
    SupplierStatementReportDTO,
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
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox
from seeker_accounting.shared.ui.table_helpers import configure_compact_table
from seeker_accounting.platform.exceptions import ValidationError

_ZERO = Decimal("0.00")


class SupplierStatementWindow(QFrame):
    """Focused child window for supplier statements."""

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
        self._report_service = service_registry.supplier_statement_service
        self._supplier_service = service_registry.supplier_service
        self._context_service = ReportingContextService(
            fiscal_calendar_service=service_registry.fiscal_calendar_service,
            active_company_context=service_registry.active_company_context,
        )
        self._current_filter = self._coerce_filter(company_id, initial_filter)
        self._current_report: SupplierStatementReportDTO | None = None

        self.setObjectName("SupplierStatementWindow")
        self.setWindowTitle("Supplier Statement")
        self.setMinimumSize(960, 620)
        self.setWindowFlag(Qt.WindowType.Window, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(ReportingContextStrip(self._context_service, service_registry, self))
        root.addWidget(self._build_controls())
        root.addWidget(self._build_summary_strip())
        root.addWidget(self._build_stack(), 1)

        self._active_company_context.active_company_changed.connect(self._on_company_changed)
        self._load_suppliers()
        self._apply_filter_to_controls()
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
        title = QLabel("Supplier Statement", card)
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Formal supplier statement with opening balance, period activity, running balance, and source drilldown.",
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

        supplier_label = QLabel("Supplier", card)
        supplier_label.setProperty("role", "caption")
        layout.addWidget(supplier_label)

        self._supplier_combo = SearchableComboBox(card)
        self._supplier_combo.setFixedWidth(320)
        layout.addWidget(self._supplier_combo)

        from_label = QLabel("From", card)
        from_label.setProperty("role", "caption")
        layout.addWidget(from_label)

        self._from_edit = QDateEdit(card)
        self._from_edit.setCalendarPopup(True)
        self._from_edit.setFixedWidth(124)
        layout.addWidget(self._from_edit)

        to_label = QLabel("To", card)
        to_label.setProperty("role", "caption")
        layout.addWidget(to_label)

        self._to_edit = QDateEdit(card)
        self._to_edit.setCalendarPopup(True)
        self._to_edit.setFixedWidth(124)
        layout.addWidget(self._to_edit)

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

    def _build_summary_strip(self) -> QWidget:
        strip = QWidget(self)
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(20, 6, 20, 6)
        layout.setSpacing(8)
        self._summary_values: dict[str, QLabel] = {}
        for key, title in (("opening", "Opening"), ("activity", "Period Activity"), ("closing", "Closing")):
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
                title="Select Supplier",
                message="Choose a supplier and reporting period to load the statement.",
                parent=self,
            )
        )
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Statement Activity",
                message="No posted supplier activity was found for the selected range.",
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
            ["Date", "Type", "Document", "Reference", "Description", "Bills", "Payments", "Balance"]
        )
        configure_compact_table(self._table)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self._table, 1)
        return panel

    def _load_suppliers(self) -> None:
        company_id = self._active_company_context.company_id or self._current_filter.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            self._supplier_combo.set_items([], placeholder="Select supplier")
            return
        suppliers = self._supplier_service.list_suppliers(company_id, active_only=False)
        items = [(f"{row.supplier_code} - {row.display_name}", row.id) for row in suppliers]
        search_texts = [f"{row.supplier_code} {row.display_name}" for row in suppliers]
        self._supplier_combo.set_items(items, placeholder="Select supplier", search_texts=search_texts)

    def _apply_filter_to_controls(self) -> None:
        if self._current_filter.date_from is not None:
            self._from_edit.setDate(QDate(self._current_filter.date_from.year, self._current_filter.date_from.month, self._current_filter.date_from.day))
        if self._current_filter.date_to is not None:
            self._to_edit.setDate(QDate(self._current_filter.date_to.year, self._current_filter.date_to.month, self._current_filter.date_to.day))
        if self._current_filter.supplier_id is not None:
            self._supplier_combo.set_current_value(self._current_filter.supplier_id)

    def _load_report(self) -> None:
        if not isinstance(self._current_filter.supplier_id, int):
            self._current_report = None
            self._table.setRowCount(0)
            self._stack.setCurrentIndex(1)
            self._update_summary(None)
            return
        try:
            report = self._report_service.get_statement(self._current_filter)
        except ValidationError as exc:
            show_error(self, "Supplier Statement", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "Supplier Statement", str(exc))
            return
        self._current_report = report
        self._update_summary(report)
        if not report.has_activity:
            self._table.setRowCount(0)
            self._stack.setCurrentIndex(2)
            return
        self._bind_rows(report)
        self._stack.setCurrentIndex(0)

    def _bind_rows(self, report: SupplierStatementReportDTO) -> None:
        self._table.setRowCount(len(report.lines))
        for row_index, line in enumerate(report.lines):
            self._table.setItem(row_index, 0, QTableWidgetItem(line.movement_date.strftime("%Y-%m-%d")))
            self._table.setItem(row_index, 1, QTableWidgetItem(line.movement_type_label))
            self._table.setItem(row_index, 2, QTableWidgetItem(line.document_number))
            self._table.setItem(row_index, 3, QTableWidgetItem(line.reference_text or "-"))
            self._table.setItem(row_index, 4, QTableWidgetItem(line.description or "-"))
            self._set_amount(row_index, 5, line.bill_amount)
            self._set_amount(row_index, 6, line.payment_amount)
            balance_item = QTableWidgetItem(self._fmt(line.running_balance))
            balance_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            balance_item.setData(Qt.ItemDataRole.UserRole, line.journal_entry_id)
            self._table.setItem(row_index, 7, balance_item)

    def _update_summary(self, report: SupplierStatementReportDTO | None) -> None:
        if report is None:
            self._summary_values["opening"].setText("0.00")
            self._summary_values["activity"].setText("0.00")
            self._summary_values["closing"].setText("0.00")
            return
        activity = (report.total_bills - report.total_payments).quantize(Decimal("0.01"))
        self._summary_values["opening"].setText(self._fmt(report.opening_balance))
        self._summary_values["activity"].setText(self._fmt(activity))
        self._summary_values["closing"].setText(self._fmt(report.closing_balance))

    def _set_amount(self, row_index: int, column_index: int, amount: Decimal) -> None:
        item = QTableWidgetItem(self._fmt(amount) if amount else "")
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row_index, column_index, item)

    def _on_refresh(self) -> None:
        self._current_filter = OperationalReportFilterDTO(
            company_id=self._active_company_context.company_id,
            supplier_id=self._selected_supplier_id(),
            date_from=self._to_python_date(self._from_edit.date()),
            date_to=self._to_python_date(self._to_edit.date()),
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

    def _on_cell_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        balance_item = self._table.item(row, 7)
        if balance_item is None:
            return
        journal_entry_id = balance_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(journal_entry_id, int):
            return
        JournalSourceDetailDialog.open(
            service_registry=self._service_registry,
            company_id=self._current_filter.company_id or 0,
            journal_entry_id=journal_entry_id,
            parent=self,
        )

    def _selected_supplier_id(self) -> int | None:
        value = self._supplier_combo.current_value()
        return value if isinstance(value, int) and value > 0 else None

    def _on_company_changed(self, company_id: object, company_name: object) -> None:  # noqa: ARG002
        if isinstance(company_id, int) and company_id > 0:
            self._current_filter = OperationalReportFilterDTO(
                company_id=company_id,
                supplier_id=None,
                date_from=self._current_filter.date_from,
                date_to=self._current_filter.date_to,
                posted_only=True,
            )
            self._load_suppliers()
            self._apply_filter_to_controls()
            self._load_report()

    @staticmethod
    def _coerce_filter(
        company_id: int | None,
        initial_filter: ReportingFilterDTO | OperationalReportFilterDTO | None,
    ) -> OperationalReportFilterDTO:
        if isinstance(initial_filter, OperationalReportFilterDTO):
            return OperationalReportFilterDTO(
                company_id=company_id or initial_filter.company_id,
                supplier_id=initial_filter.supplier_id,
                date_from=initial_filter.date_from,
                date_to=initial_filter.date_to or initial_filter.as_of_date,
                posted_only=True,
            )
        if isinstance(initial_filter, ReportingFilterDTO):
            return OperationalReportFilterDTO(
                company_id=company_id or initial_filter.company_id,
                date_from=initial_filter.date_from,
                date_to=initial_filter.date_to,
                posted_only=True,
            )
        today = date.today()
        return OperationalReportFilterDTO(company_id=company_id, date_from=today.replace(day=1), date_to=today, posted_only=True)

    @staticmethod
    def _to_python_date(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

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
