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
from seeker_accounting.modules.reporting.dto.ias_balance_sheet_dto import (
    IasBalanceSheetLineDetailDTO,
)
from seeker_accounting.modules.reporting.dto.ohada_balance_sheet_dto import (
    OhadaBalanceSheetLineDetailDTO,
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


class OhadaBalanceSheetLineDetailDialog(QDialog):
    """Read-only drilldown for OHADA balance sheet lines."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        detail_dto: OhadaBalanceSheetLineDetailDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._detail_dto = detail_dto
        self._ledger_filter = ReportingFilterDTO(
            company_id=detail_dto.company_id,
            date_from=None,
            date_to=detail_dto.statement_date,
            posted_only=True,
        )

        self.setWindowTitle(f"OHADA Balance Sheet Detail - {detail_dto.line_code}")
        self.setMinimumSize(960, 600)
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
                message="No posted balances contributed to this OHADA line at the selected statement date.",
                parent=self,
            )
        )
        return stack

    def _build_table_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(panel)
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["Account", "Source Line", "Contribution", "Debit", "Credit", "Amount"])
        configure_compact_table(self._table)
        self._table.setSortingEnabled(False)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self._table)
        return panel

    def _bind_detail(self) -> None:
        self._title_lbl.setText(f"{self._detail_dto.line_code} | {self._detail_dto.line_label}")
        statement_text = "-"
        if self._detail_dto.statement_date is not None:
            statement_text = self._detail_dto.statement_date.strftime("%Y-%m-%d")
        self._meta_lbl.setText(
            f"Statement date: {statement_text} | Net amount: {self._fmt(self._detail_dto.net_amount)}"
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
            self._table.setItem(row_index, 2, QTableWidgetItem(account.contribution_kind_code.replace("_", " ").title()))
            self._set_amount(row_index, 3, account.total_debit)
            self._set_amount(row_index, 4, account.total_credit)
            self._set_amount(row_index, 5, account.amount)
        self._stack.setCurrentIndex(0)

    def _set_amount(self, row: int, col: int, amount: Decimal | None) -> None:
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
            filter_dto=self._ledger_filter,
            parent=self,
        )

    @staticmethod
    def _fmt(amount: Decimal | None) -> str:
        value = amount or _ZERO
        if value == _ZERO:
            return "0.00"
        return f"{value:,.2f}"

    @classmethod
    def open(
        cls,
        service_registry: ServiceRegistry,
        detail_dto: OhadaBalanceSheetLineDetailDTO,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, detail_dto, parent)
        dialog.exec()


class IasBalanceSheetLineDetailDialog(QDialog):
    """Read-only drilldown for IAS balance sheet lines."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        detail_dto: IasBalanceSheetLineDetailDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._detail_dto = detail_dto
        self._ledger_filter = ReportingFilterDTO(
            company_id=detail_dto.company_id,
            date_from=None,
            date_to=detail_dto.statement_date,
            posted_only=True,
        )

        self.setWindowTitle(f"IAS Balance Sheet Detail - {detail_dto.line_code}")
        self.setMinimumSize(980, 620)
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
                message="No posted balances contributed to this IAS/IFRS line at the selected statement date.",
                parent=self,
            )
        )
        return stack

    def _build_table_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(panel)
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["Account", "Line", "Contribution", "Debit", "Credit", "Amount"])
        configure_compact_table(self._table)
        self._table.setSortingEnabled(False)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self._table)
        return panel

    def _bind_detail(self) -> None:
        self._title_lbl.setText(f"{self._detail_dto.line_code} | {self._detail_dto.line_label}")
        statement_text = "-"
        if self._detail_dto.statement_date is not None:
            statement_text = self._detail_dto.statement_date.strftime("%Y-%m-%d")
        self._meta_lbl.setText(
            f"Statement date: {statement_text} | Amount: {self._fmt(self._detail_dto.amount)}"
        )

        if self._detail_dto.warnings:
            self._warning_lbl.setText(" | ".join(issue.message for issue in self._detail_dto.warnings))
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
            self._table.setItem(row_index, 1, QTableWidgetItem(account.line_label))
            self._table.setItem(row_index, 2, QTableWidgetItem(account.contribution_kind_code.replace("_", " ").title()))
            self._set_amount(row_index, 3, account.total_debit)
            self._set_amount(row_index, 4, account.total_credit)
            self._set_amount(row_index, 5, account.amount)
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
            filter_dto=self._ledger_filter,
            parent=self,
        )

    @staticmethod
    def _fmt(amount: Decimal | None) -> str:
        value = amount or _ZERO
        if value == _ZERO:
            return "0.00"
        return f"{value:,.2f}"

    @classmethod
    def open(
        cls,
        service_registry: ServiceRegistry,
        detail_dto: IasBalanceSheetLineDetailDTO,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, detail_dto, parent)
        dialog.exec()
