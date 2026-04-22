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
    QSplitter,
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
from seeker_accounting.modules.reporting.dto.treasury_report_dto import TreasuryReportDTO
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


class TreasuryReportWindow(QFrame):
    """Focused child window for cash and bank operational reporting."""

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
        self._report_service = service_registry.treasury_report_service
        self._financial_account_service = service_registry.financial_account_service
        self._context_service = ReportingContextService(
            fiscal_calendar_service=service_registry.fiscal_calendar_service,
            active_company_context=service_registry.active_company_context,
        )
        self._current_filter = self._coerce_filter(company_id, initial_filter)
        self._current_report: TreasuryReportDTO | None = None

        self.setObjectName("TreasuryReportWindow")
        self.setWindowTitle("Cash / Bank Reports")
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
        self._load_accounts()
        self._apply_filter_to_controls()
        self._load_report()

    def _build_header(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(4)
        eyebrow = QLabel("Operational Reports | Treasury", card)
        eyebrow.setProperty("role", "caption")
        layout.addWidget(eyebrow)
        title = QLabel("Cash / Bank Reports", card)
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Opening, movement, and closing views over posted treasury transactions and transfers.",
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

        account_label = QLabel("Account", card)
        account_label.setProperty("role", "caption")
        layout.addWidget(account_label)

        self._account_combo = SearchableComboBox(card)
        self._account_combo.setFixedWidth(320)
        layout.addWidget(self._account_combo)

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
        for key, title in (("opening", "Opening"), ("inflow", "Inflow"), ("outflow", "Outflow"), ("closing", "Closing")):
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
        self._stack.addWidget(self._build_split_panel())
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Active Company",
                message="Select an active company before opening cash and bank reports.",
                parent=self,
            )
        )
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Treasury Activity",
                message="No posted treasury movements were found for the selected filter.",
                parent=self,
            )
        )
        return self._stack

    def _build_split_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 0, 20, 20)
        splitter = QSplitter(Qt.Orientation.Vertical, panel)
        splitter.addWidget(self._build_accounts_table(splitter))
        splitter.addWidget(self._build_movements_table(splitter))
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        return panel

    def _build_accounts_table(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Account Summary", panel)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)
        self._accounts_table = QTableWidget(panel)
        self._accounts_table.setColumnCount(7)
        self._accounts_table.setHorizontalHeaderLabels(["Account", "Type", "Opening", "Inflow", "Outflow", "Closing", "Moves"])
        configure_compact_table(self._accounts_table)
        self._accounts_table.cellDoubleClicked.connect(self._on_account_double_clicked)
        layout.addWidget(self._accounts_table, 1)
        return panel

    def _build_movements_table(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Movements", panel)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)
        self._movements_table = QTableWidget(panel)
        self._movements_table.setColumnCount(9)
        self._movements_table.setHorizontalHeaderLabels(
            ["Date", "Account", "Type", "Document", "Reference", "Description", "Inflow", "Outflow", "Balance"]
        )
        configure_compact_table(self._movements_table)
        self._movements_table.cellDoubleClicked.connect(self._on_movement_double_clicked)
        layout.addWidget(self._movements_table, 1)
        return panel

    def _load_accounts(self) -> None:
        company_id = self._active_company_context.company_id or self._current_filter.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            self._account_combo.set_items([], placeholder="All accounts")
            return
        accounts = self._financial_account_service.list_financial_accounts(company_id, active_only=False)
        items = [(f"{row.account_code} - {row.name}", row.id) for row in accounts]
        search_texts = [f"{row.account_code} {row.name}" for row in accounts]
        self._account_combo.set_items(items, placeholder="All accounts", search_texts=search_texts)

    def _apply_filter_to_controls(self) -> None:
        if self._current_filter.date_from is not None:
            self._from_edit.setDate(QDate(self._current_filter.date_from.year, self._current_filter.date_from.month, self._current_filter.date_from.day))
        if self._current_filter.date_to is not None:
            self._to_edit.setDate(QDate(self._current_filter.date_to.year, self._current_filter.date_to.month, self._current_filter.date_to.day))
        if self._current_filter.financial_account_id is not None:
            self._account_combo.set_current_value(self._current_filter.financial_account_id)

    def _load_report(self) -> None:
        company_id = self._current_filter.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            self._current_report = None
            self._accounts_table.setRowCount(0)
            self._movements_table.setRowCount(0)
            self._update_summary(
                TreasuryReportDTO(
                    company_id=0,
                    date_from=self._current_filter.date_from,
                    date_to=self._current_filter.date_to,
                    selected_financial_account_id=self._current_filter.financial_account_id,
                )
            )
            self._stack.setCurrentIndex(1)
            return
        try:
            report = self._report_service.get_report(self._current_filter)
        except ValidationError as exc:
            show_error(self, "Cash / Bank Reports", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "Cash / Bank Reports", str(exc))
            return
        self._current_report = report
        self._update_summary(report)
        if not report.has_activity:
            self._accounts_table.setRowCount(0)
            self._movements_table.setRowCount(0)
            self._stack.setCurrentIndex(2)
            return
        self._bind_account_rows(report)
        self._bind_movement_rows(report)
        self._stack.setCurrentIndex(0)

    def _update_summary(self, report: TreasuryReportDTO) -> None:
        self._summary_values["opening"].setText(self._fmt(report.total_opening))
        self._summary_values["inflow"].setText(self._fmt(report.total_inflow))
        self._summary_values["outflow"].setText(self._fmt(report.total_outflow))
        self._summary_values["closing"].setText(self._fmt(report.total_closing))

    def _bind_account_rows(self, report: TreasuryReportDTO) -> None:
        self._accounts_table.setRowCount(len(report.account_rows))
        for row_index, row in enumerate(report.account_rows):
            account_item = QTableWidgetItem(f"{row.account_code} - {row.account_name}")
            account_item.setData(Qt.ItemDataRole.UserRole, row.financial_account_id)
            self._accounts_table.setItem(row_index, 0, account_item)
            self._accounts_table.setItem(row_index, 1, QTableWidgetItem(row.account_type_code.replace("_", " ").title()))
            self._set_amount(self._accounts_table, row_index, 2, row.opening_balance)
            self._set_amount(self._accounts_table, row_index, 3, row.inflow_amount)
            self._set_amount(self._accounts_table, row_index, 4, row.outflow_amount)
            self._set_amount(self._accounts_table, row_index, 5, row.closing_balance)
            self._accounts_table.setItem(row_index, 6, QTableWidgetItem(str(row.movement_count)))

    def _bind_movement_rows(self, report: TreasuryReportDTO) -> None:
        self._movements_table.setRowCount(len(report.movement_rows))
        for row_index, row in enumerate(report.movement_rows):
            date_item = QTableWidgetItem(row.transaction_date.strftime("%Y-%m-%d"))
            date_item.setData(Qt.ItemDataRole.UserRole, row.journal_entry_id)
            self._movements_table.setItem(row_index, 0, date_item)
            self._movements_table.setItem(row_index, 1, QTableWidgetItem(f"{row.account_code} - {row.account_name}"))
            self._movements_table.setItem(row_index, 2, QTableWidgetItem(row.movement_type_label))
            self._movements_table.setItem(row_index, 3, QTableWidgetItem(row.document_number))
            self._movements_table.setItem(row_index, 4, QTableWidgetItem(row.reference_text or "-"))
            self._movements_table.setItem(row_index, 5, QTableWidgetItem(row.description or "-"))
            self._set_amount(self._movements_table, row_index, 6, row.inflow_amount)
            self._set_amount(self._movements_table, row_index, 7, row.outflow_amount)
            self._set_amount(self._movements_table, row_index, 8, row.running_balance)

    def _set_amount(self, table: QTableWidget, row_index: int, column_index: int, amount: Decimal) -> None:
        item = QTableWidgetItem(self._fmt(amount))
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row_index, column_index, item)

    def _on_refresh(self) -> None:
        self._current_filter = OperationalReportFilterDTO(
            company_id=self._active_company_context.company_id,
            financial_account_id=self._selected_account_id(),
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

    def _on_account_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        account_item = self._accounts_table.item(row, 0)
        if account_item is None:
            return
        account_id = account_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(account_id, int):
            self._account_combo.set_current_value(account_id)
            self._on_refresh()

    def _on_movement_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        date_item = self._movements_table.item(row, 0)
        if date_item is None:
            return
        journal_entry_id = date_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(journal_entry_id, int):
            return
        JournalSourceDetailDialog.open(
            service_registry=self._service_registry,
            company_id=self._current_filter.company_id or 0,
            journal_entry_id=journal_entry_id,
            parent=self,
        )

    def _selected_account_id(self) -> int | None:
        value = self._account_combo.current_value()
        return value if isinstance(value, int) and value > 0 else None

    def _on_company_changed(self, company_id: object, company_name: object) -> None:  # noqa: ARG002
        if isinstance(company_id, int) and company_id > 0:
            self._current_filter = OperationalReportFilterDTO(
                company_id=company_id,
                financial_account_id=None,
                date_from=self._current_filter.date_from,
                date_to=self._current_filter.date_to,
                posted_only=True,
            )
            self._load_accounts()
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
                financial_account_id=initial_filter.financial_account_id,
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
