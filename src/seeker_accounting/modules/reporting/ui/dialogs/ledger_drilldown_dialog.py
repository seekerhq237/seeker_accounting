from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.ui.dialogs.journal_source_detail_dialog import (
    JournalSourceDetailDialog,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_ZERO = Decimal("0.00")


class LedgerDrilldownDialog(QDialog):
    """Focused drilldown dialog showing ledger lines for a single account."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        account_id: int,
        filter_dto: ReportingFilterDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ledger Drilldown")
        self.setMinimumSize(860, 520)
        self.setModal(True)

        self._service_registry = service_registry
        self._company_id = company_id
        self._account_id = account_id
        self._filter = filter_dto
        if not isinstance(self._filter.company_id, int):
            self._filter.company_id = company_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)

        self._header = QLabel("", self)
        self._header.setObjectName("InfoCardTitle")
        layout.addWidget(self._header)

        self._table = QTableWidget(self)
        self._table.setColumnCount(8)
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
            ]
        )
        configure_compact_table(self._table)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self._table, 1)

        self._footer = QLabel("", self)
        self._footer.setProperty("role", "caption")
        layout.addWidget(self._footer)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load()

    def _load(self) -> None:
        try:
            report = self._service_registry.general_ledger_report_service.get_account_ledger(
                self._filter, self._account_id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Ledger Drilldown", str(exc))
            self.reject()
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "Ledger Drilldown", str(exc))
            self.reject()
            return

        if not report.accounts:
            self._header.setText("No lines available")
            return

        account = report.accounts[0]
        self._header.setText(f"{account.account_code} | {account.account_name}")
        self._footer.setText(
            f"Opening: {self._fmt(account.opening_balance)}    "
            f"Period: D {self._fmt(account.period_debit)} / C {self._fmt(account.period_credit)}    "
            f"Closing: {self._fmt(account.closing_balance)}"
        )

        self._table.setRowCount(len(account.lines))
        for row_index, line in enumerate(account.lines):
            self._set_text(row_index, 0, line.entry_date.strftime("%Y-%m-%d"))
            self._set_text(row_index, 1, line.entry_number or "-")
            self._set_text(row_index, 2, line.reference_text or "-")
            self._set_text(row_index, 3, line.journal_description or "-")
            self._set_text(row_index, 4, line.line_description or "-")
            self._set_amount(row_index, 5, line.debit_amount)
            self._set_amount(row_index, 6, line.credit_amount)
            self._set_amount(row_index, 7, line.running_balance, line.journal_entry_id)

    def _set_text(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        self._table.setItem(row, col, item)

    def _set_amount(self, row: int, col: int, amount: Decimal, journal_entry_id: int | None = None) -> None:
        item = QTableWidgetItem(self._fmt(amount))
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if isinstance(journal_entry_id, int):
            item.setData(Qt.ItemDataRole.UserRole, journal_entry_id)
        self._table.setItem(row, col, item)

    def _on_row_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        item = self._table.item(row, 7)
        if item is None:
            return
        journal_entry_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(journal_entry_id, int):
            return
        JournalSourceDetailDialog.open(
            service_registry=self._service_registry,
            company_id=self._company_id,
            journal_entry_id=journal_entry_id,
            parent=self,
        )

    @staticmethod
    def _fmt(amount: Decimal) -> str:
        if amount == _ZERO:
            return "0.00"
        return f"{amount:,.2f}"

    @classmethod
    def open(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        account_id: int,
        filter_dto: ReportingFilterDTO,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, company_id, account_id, filter_dto, parent)
        dialog.exec()
