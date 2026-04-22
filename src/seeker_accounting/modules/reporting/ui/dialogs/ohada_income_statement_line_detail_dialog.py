from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.ohada_income_statement_dto import (
    OhadaIncomeStatementLineDetailDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.ui.dialogs.ledger_drilldown_dialog import (
    LedgerDrilldownDialog,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_empty_state import (
    ReportingEmptyState,
)
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_ZERO = Decimal("0.00")


class OhadaIncomeStatementLineDetailDialog(QDialog):
    """Read-only drilldown for OHADA statement lines."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        detail_dto: OhadaIncomeStatementLineDetailDTO,
        filter_dto: ReportingFilterDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._detail_dto = detail_dto
        self._filter_dto = ReportingFilterDTO(
            company_id=filter_dto.company_id,
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
            posted_only=filter_dto.posted_only,
        )

        self.setWindowTitle(f"OHADA Line Detail - {detail_dto.line_code}")
        self.setMinimumSize(900, 560)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)

        layout.addWidget(self._build_header())
        self._warning_card = self._build_warning_card()
        layout.addWidget(self._warning_card)
        self._stack = self._build_stack()
        layout.addWidget(self._stack, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._bind_detail()

    def _build_header(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(6)

        self._title_lbl = QLabel(card)
        self._title_lbl.setObjectName("InfoCardTitle")
        layout.addWidget(self._title_lbl)

        self._meta_lbl = QLabel(card)
        self._meta_lbl.setObjectName("PageSummary")
        self._meta_lbl.setWordWrap(True)
        layout.addWidget(self._meta_lbl)
        return card

    def _build_warning_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        self._warning_lbl = QLabel(card)
        self._warning_lbl.setObjectName("PageSummary")
        self._warning_lbl.setWordWrap(True)
        layout.addWidget(self._warning_lbl)
        card.hide()
        return card

    def _build_stack(self) -> QStackedWidget:
        stack = QStackedWidget(self)
        stack.addWidget(self._build_table_panel())
        stack.addWidget(
            ReportingEmptyState(
                title="No Contributing Accounts",
                message="No posted account movements contributed to this OHADA line in the selected period.",
                parent=self,
            )
        )
        return stack

    def _build_table_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = QTableWidget(panel)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Account", "OHADA Line", "Debit", "Credit", "Signed Amount"]
        )
        configure_compact_table(self._table)
        self._table.setSortingEnabled(False)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self._table)
        return panel

    def _bind_detail(self) -> None:
        period_text = "-"
        if self._detail_dto.date_from and self._detail_dto.date_to:
            period_text = (
                f"{self._detail_dto.date_from.strftime('%Y-%m-%d')} to "
                f"{self._detail_dto.date_to.strftime('%Y-%m-%d')}"
            )
        self._title_lbl.setText(f"{self._detail_dto.line_code} | {self._detail_dto.line_label}")
        self._meta_lbl.setText(
            f"Period: {period_text} | Signed amount: {self._fmt(self._detail_dto.signed_amount)}"
        )

        if self._detail_dto.warnings:
            self._warning_lbl.setText(" | ".join(warning.message for warning in self._detail_dto.warnings))
            self._warning_card.show()
        else:
            self._warning_card.hide()

        if not self._detail_dto.accounts:
            self._stack.setCurrentIndex(1)
            return

        self._table.setRowCount(len(self._detail_dto.accounts))
        for row_index, account in enumerate(self._detail_dto.accounts):
            account_item = QTableWidgetItem(f"{account.account_code} | {account.account_name}")
            account_item.setData(Qt.ItemDataRole.UserRole, account.account_id)
            self._table.setItem(row_index, 0, account_item)
            self._table.setItem(row_index, 1, QTableWidgetItem(account.line_code or "-"))
            self._set_amount(row_index, 2, account.debit_amount)
            self._set_amount(row_index, 3, account.credit_amount)
            self._set_amount(row_index, 4, account.signed_amount)
        self._stack.setCurrentIndex(0)

    def _set_amount(self, row: int, col: int, amount: Decimal) -> None:
        item = QTableWidgetItem(self._fmt(amount))
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, col, item)

    def _on_row_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        item = self._table.item(row, 0)
        if item is None:
            return
        account_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(account_id, int):
            return
        LedgerDrilldownDialog.open(
            service_registry=self._service_registry,
            company_id=self._detail_dto.company_id,
            account_id=account_id,
            filter_dto=self._filter_dto,
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
        detail_dto: OhadaIncomeStatementLineDetailDTO,
        filter_dto: ReportingFilterDTO,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, detail_dto, filter_dto, parent)
        dialog.exec()
