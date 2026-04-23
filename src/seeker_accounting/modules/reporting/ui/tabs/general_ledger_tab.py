from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_dto import AccountListItemDTO
from seeker_accounting.modules.reporting.dto.general_ledger_report_dto import GeneralLedgerAccountDTO
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.ui.dialogs.journal_source_detail_dialog import JournalSourceDetailDialog
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.background_task import run_with_progress
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_ZERO = Decimal("0.00")


class GeneralLedgerTab(QWidget):
    """General Ledger report surface."""

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._report_service = service_registry.general_ledger_report_service
        self._chart_service = service_registry.chart_of_accounts_service
        self._active_company_context = service_registry.active_company_context
        self._current_filter: ReportingFilterDTO | None = None
        self._last_company_id: int | None = None

        self.setObjectName("GeneralLedgerTab")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        root.addWidget(self._build_header())
        root.addWidget(self._build_controls(), 0)
        root.addWidget(self._build_stack(), 1)

        # Keep account options in sync with company context
        self._active_company_context.active_company_changed.connect(self._on_company_changed)
        self._reload_accounts(self._active_company_context.company_id)

    # ------------------------------------------------------------------
    # UI builders
    # ------------------------------------------------------------------

    def _build_header(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel("General Ledger", container)
        title.setObjectName("ReportTabSectionTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Posted journal lines with running balance per account and drilldown to journal detail.",
            container,
        )
        subtitle.setObjectName("ReportTabSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        return container

    def _build_controls(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        caption = QLabel("Account", card)
        caption.setProperty("role", "caption")
        layout.addWidget(caption)

        self._account_combo = QComboBox(card)
        self._account_combo.setEditable(False)
        self._account_combo.currentIndexChanged.connect(self._on_account_changed)
        layout.addWidget(self._account_combo)

        self._account_hint = QLabel("Select an account to view ledger detail.", card)
        self._account_hint.setObjectName("PageSummary")
        layout.addWidget(self._account_hint)

        return card

    def _build_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_table_panel())
        self._stack.addWidget(self._build_empty_state("No active company. Select a company to continue."))
        self._stack.addWidget(self._build_empty_state("Select an account to view the ledger.", title="Select Account"))
        self._stack.addWidget(
            self._build_empty_state("No posted lines found for the selected period.", title="No Data")
        )
        self._stack.addWidget(self._build_empty_state("Unable to load the general ledger.", title="Error"))
        return self._stack

    def _build_table_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._account_header = QLabel("", panel)
        self._account_header.setObjectName("InfoCardTitle")
        layout.addWidget(self._account_header)

        self._table = QTableWidget(panel)
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels(
            [
                "Date",
                "Entry #",
                "Reference",
                "Description",
                "Line Memo",
                "Debit",
                "Credit",
                "Running Balance",
                "Source",
            ]
        )
        configure_compact_table(self._table)
        self._table.setSortingEnabled(False)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self._table, 1)

        self._totals_bar = self._build_totals_bar(panel)
        layout.addWidget(self._totals_bar)
        return panel

    def _build_totals_bar(self, parent: QWidget) -> QWidget:
        bar = QFrame(parent)
        bar.setObjectName("ReportTotalsBar")
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(4)

        self._totals_labels: dict[str, QLabel] = {}

        def _add(label: str, key: str) -> None:
            row = QWidget(bar)
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)
            cap = QLabel(label, row)
            cap.setProperty("role", "caption")
            row_layout.addWidget(cap)
            val = QLabel("0.00", row)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val.setObjectName("TopBarValue")
            row_layout.addWidget(val)
            layout.addWidget(row)
            self._totals_labels[key] = val

        _add("Opening Balance", "opening_balance")
        _add("Period Debit", "period_debit")
        _add("Period Credit", "period_credit")
        _add("Closing Balance", "closing_balance")
        return bar

    def _build_empty_state(self, message: str, title: str = "No Company") -> QWidget:
        card = QFrame(self)
        card.setObjectName("ReportCanvasPlaceholder")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)
        header = QLabel(title, card)
        header.setObjectName("CanvasPlaceholderTitle")
        layout.addWidget(header)
        body = QLabel(message, card)
        body.setObjectName("CanvasPlaceholderSub")
        body.setWordWrap(True)
        layout.addWidget(body)
        layout.addStretch(1)
        return card

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_filter(self, filter_dto: ReportingFilterDTO) -> None:
        self._current_filter = filter_dto
        company_id = filter_dto.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            self._stack.setCurrentIndex(1)
            self._table.setRowCount(0)
            return

        self._reload_accounts(company_id, preserve_selection=True)
        account_id = self._selected_account_id()
        if account_id is None:
            self._stack.setCurrentIndex(2)
            return

        try:
            task_result = run_with_progress(
                parent=self,
                title="General Ledger",
                message="Loading posted lines and running balance…",
                worker=lambda: self._report_service.get_account_ledger(filter_dto, account_id),
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "General Ledger", str(exc))
            self._stack.setCurrentIndex(4)
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "General Ledger", str(exc))
            self._stack.setCurrentIndex(4)
            return

        if task_result.cancelled:
            return
        if task_result.error is not None:
            show_error(self, "General Ledger", str(task_result.error))
            self._stack.setCurrentIndex(4)
            return

        report = task_result.value
        assert report is not None

        if not report.accounts:
            self._table.setRowCount(0)
            self._stack.setCurrentIndex(3)
            return

        self._bind_account(report.accounts[0])
        self._stack.setCurrentIndex(0)

    def refresh(self) -> None:
        if self._current_filter is not None:
            self.apply_filter(self._current_filter)

    def focus_account(self, account_id: int, account_code: str | None = None, account_name: str | None = None) -> None:
        """Programmatically select an account (used by Trial Balance drilldown)."""
        idx = self._find_account_index(account_id)
        if idx == -1:
            display = account_code or str(account_id)
            if account_name:
                display = f"{display} · {account_name}"
            self._account_combo.addItem(display, account_id)
            idx = self._account_combo.count() - 1
        self._account_combo.setCurrentIndex(idx)
        if self._current_filter is not None:
            self.apply_filter(self._current_filter)

    def current_account_label(self) -> str | None:
        idx = self._account_combo.currentIndex()
        if idx < 0:
            return None
        return self._account_combo.currentText() or None

    # ------------------------------------------------------------------
    # Binding
    # ------------------------------------------------------------------

    def _bind_account(self, account: GeneralLedgerAccountDTO) -> None:
        header_text = f"{account.account_code} · {account.account_name}"
        self._account_header.setText(header_text)

        # Bulk populate: suspend paint + sorting for large ledgers.
        self._table.setUpdatesEnabled(False)
        self._table.setSortingEnabled(False)
        try:
            self._table.setRowCount(len(account.lines))
            for row_idx, line in enumerate(account.lines):
                self._set_text_item(row_idx, 0, line.entry_date.strftime("%Y-%m-%d"))
                self._set_text_item(row_idx, 1, line.entry_number or "—")
                self._set_text_item(row_idx, 2, line.reference_text or "—")
                self._set_text_item(row_idx, 3, line.journal_description or "—")
                self._set_text_item(row_idx, 4, line.line_description or "—")
                self._set_amount_item(row_idx, 5, line.debit_amount)
                self._set_amount_item(row_idx, 6, line.credit_amount)
                self._set_amount_item(row_idx, 7, line.running_balance)

                source_parts = []
                if line.source_module_code:
                    source_parts.append(line.source_module_code)
                if line.source_document_type:
                    source_parts.append(line.source_document_type)
                source = " / ".join(source_parts) if source_parts else "—"
                item = QTableWidgetItem(source)
                item.setData(Qt.ItemDataRole.UserRole, line.journal_entry_id)
                self._table.setItem(row_idx, 8, item)
        finally:
            self._table.setUpdatesEnabled(True)

        self._update_totals(account)

    def _update_totals(self, account: GeneralLedgerAccountDTO) -> None:
        self._totals_labels["opening_balance"].setText(self._fmt(account.opening_balance))
        self._totals_labels["period_debit"].setText(self._fmt(account.period_debit))
        self._totals_labels["period_credit"].setText(self._fmt(account.period_credit))
        self._totals_labels["closing_balance"].setText(self._fmt(account.closing_balance))

    def _set_text_item(self, row_index: int, col_index: int, text: str) -> None:
        item = QTableWidgetItem(text)
        self._table.setItem(row_index, col_index, item)

    def _set_amount_item(self, row_index: int, col_index: int, amount: Decimal) -> None:
        item = QTableWidgetItem(self._fmt(amount))
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row_index, col_index, item)

    @staticmethod
    def _fmt(amount: Decimal) -> str:
        if amount == _ZERO:
            return "0.00"
        return f"{amount:,.2f}"

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_company_changed(self, company_id: object, company_name: object) -> None:  # noqa: ARG002
        if isinstance(company_id, int):
            self._reload_accounts(company_id)
        if self._current_filter is not None:
            self.apply_filter(self._current_filter)

    def _on_account_changed(self, index: int) -> None:  # noqa: ARG002
        if self._current_filter is not None:
            self.apply_filter(self._current_filter)

    def _on_row_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        entry_item = self._table.item(row, 8)
        if entry_item is None:
            return
        entry_id = entry_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry_id, int):
            return
        company_id = self._current_filter.company_id if self._current_filter else None
        if company_id is None:
            company_id = self._active_company_context.company_id
        if not isinstance(company_id, int):
            return
        JournalSourceDetailDialog.open(
            service_registry=self._service_registry,
            company_id=company_id,
            journal_entry_id=entry_id,
            parent=self,
        )

    # ------------------------------------------------------------------
    # Account helpers
    # ------------------------------------------------------------------

    def _reload_accounts(self, company_id: int | None, preserve_selection: bool = False) -> None:
        if company_id is None or company_id <= 0:
            self._account_combo.clear()
            self._last_company_id = None
            return
        if preserve_selection and company_id == self._last_company_id:
            return

        selected_id = self._selected_account_id()
        self._account_combo.blockSignals(True)
        self._account_combo.clear()
        try:
            accounts = self._chart_service.list_accounts(company_id, active_only=True)
        except Exception:
            accounts = []
        for account in accounts:
            self._account_combo.addItem(self._format_account_label(account), account.id)
        self._account_combo.blockSignals(False)
        self._last_company_id = company_id

        if preserve_selection and selected_id is not None:
            idx = self._find_account_index(selected_id)
            if idx >= 0:
                self._account_combo.setCurrentIndex(idx)
                return
        self._account_combo.setCurrentIndex(-1)

    def _selected_account_id(self) -> int | None:
        data = self._account_combo.currentData()
        return data if isinstance(data, int) else None

    def _find_account_index(self, account_id: int) -> int:
        for idx in range(self._account_combo.count()):
            if self._account_combo.itemData(idx) == account_id:
                return idx
        return -1

    @staticmethod
    def _format_account_label(account: AccountListItemDTO) -> str:
        return f"{account.account_code} · {account.account_name}"
