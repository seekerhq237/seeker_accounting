from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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
from seeker_accounting.modules.reporting.dto.trial_balance_report_dto import TrialBalanceReportDTO
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_ZERO = Decimal("0.00")


class TrialBalanceTab(QWidget):
    """Trial Balance report surface."""

    drilldown_requested = Signal(int, str, str)  # account_id, account_code, account_name

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._report_service = service_registry.trial_balance_report_service
        self._active_company_context = service_registry.active_company_context
        self._current_filter: ReportingFilterDTO | None = None

        self.setObjectName("TrialBalanceTab")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        root.addWidget(self._build_header())
        root.addWidget(self._build_stack(), 1)

    # ------------------------------------------------------------------
    # UI builders
    # ------------------------------------------------------------------

    def _build_header(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel("Trial Balance", container)
        title.setObjectName("ReportTabSectionTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Posted-only summary of opening, period, and closing balances per account.",
            container,
        )
        subtitle.setObjectName("ReportTabSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        return container

    def _build_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_table_panel())
        self._stack.addWidget(self._build_empty_state("No active company. Select a company to continue."))
        self._stack.addWidget(
            self._build_empty_state(
                "No posted activity found for the selected period.",
                title="No Data",
            )
        )
        self._stack.addWidget(self._build_empty_state("Unable to load the trial balance.", title="Error"))
        return self._stack

    def _build_table_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._table = QTableWidget(panel)
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            [
                "Account",
                "Name",
                "Opening Debit",
                "Opening Credit",
                "Period Debit",
                "Period Credit",
                "Closing Debit",
                "Closing Credit",
            ]
        )
        configure_compact_table(self._table)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self._table, 1)

        self._totals_bar = self._build_totals_bar(panel)
        layout.addWidget(self._totals_bar)
        return panel

    def _build_totals_bar(self, parent: QWidget) -> QWidget:
        bar = QFrame(parent)
        bar.setObjectName("ReportTotalsBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(18)

        self._totals_labels: dict[str, dict[str, QLabel]] = {}

        def _add_block(caption: str, key: str) -> None:
            block = QWidget(bar)
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(4)

            cap = QLabel(caption, block)
            cap.setProperty("role", "caption")
            block_layout.addWidget(cap)

            row = QWidget(block)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            debit_lbl = QLabel("Debit: 0.00", row)
            debit_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            credit_lbl = QLabel("Credit: 0.00", row)
            credit_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            row_layout.addWidget(debit_lbl)
            row_layout.addWidget(credit_lbl)
            row_layout.addStretch(1)

            block_layout.addWidget(row)
            layout.addWidget(block, 1)
            self._totals_labels[key] = {"debit": debit_lbl, "credit": credit_lbl}

        _add_block("Opening Totals", "opening")
        _add_block("Period Totals", "period")
        _add_block("Closing Totals", "closing")
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

        try:
            report = self._report_service.get_trial_balance(filter_dto)
        except ValidationError as exc:
            show_error(self, "Trial Balance", str(exc))
            self._stack.setCurrentIndex(3)
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "Trial Balance", str(exc))
            self._stack.setCurrentIndex(3)
            return

        if not report.rows:
            self._table.setRowCount(0)
            self._stack.setCurrentIndex(2)
            self._update_totals(report)
            return

        self._bind_report(report)
        self._stack.setCurrentIndex(0)

    def refresh(self) -> None:
        if self._current_filter is not None:
            self.apply_filter(self._current_filter)

    # ------------------------------------------------------------------
    # Binding
    # ------------------------------------------------------------------

    def _bind_report(self, report: TrialBalanceReportDTO) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(report.rows))

        for row_idx, row in enumerate(report.rows):
            code_item = QTableWidgetItem(row.account_code)
            code_item.setData(Qt.ItemDataRole.UserRole, row.account_id)
            self._table.setItem(row_idx, 0, code_item)

            name_item = QTableWidgetItem(row.account_name)
            self._table.setItem(row_idx, 1, name_item)

            self._set_amount_item(row_idx, 2, row.opening_debit)
            self._set_amount_item(row_idx, 3, row.opening_credit)
            self._set_amount_item(row_idx, 4, row.period_debit)
            self._set_amount_item(row_idx, 5, row.period_credit)
            self._set_amount_item(row_idx, 6, row.closing_debit)
            self._set_amount_item(row_idx, 7, row.closing_credit)

        self._table.setSortingEnabled(True)
        self._update_totals(report)

    def _update_totals(self, report: TrialBalanceReportDTO) -> None:
        self._totals_labels["opening"]["debit"].setText(f"Debit: {self._fmt(report.total_opening_debit)}")
        self._totals_labels["opening"]["credit"].setText(f"Credit: {self._fmt(report.total_opening_credit)}")
        self._totals_labels["period"]["debit"].setText(f"Debit: {self._fmt(report.total_period_debit)}")
        self._totals_labels["period"]["credit"].setText(f"Credit: {self._fmt(report.total_period_credit)}")
        self._totals_labels["closing"]["debit"].setText(f"Debit: {self._fmt(report.total_closing_debit)}")
        self._totals_labels["closing"]["credit"].setText(f"Credit: {self._fmt(report.total_closing_credit)}")

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

    def _on_row_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        code_item = self._table.item(row, 0)
        name_item = self._table.item(row, 1)
        if code_item is None or name_item is None:
            return
        account_id = code_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(account_id, int):
            return
        account_code = code_item.text()
        account_name = name_item.text()
        self.drilldown_requested.emit(account_id, account_code, account_name)
