from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.financial_analysis_chart_dto import (
    FinancialChartDetailDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.ui.dialogs.ledger_drilldown_dialog import (
    LedgerDrilldownDialog,
)
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_ZERO = Decimal("0.00")


class ChartDetailDialog(QDialog):
    """Supporting numeric detail for a financial analysis chart element."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        detail_dto: FinancialChartDetailDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._detail_dto = detail_dto

        self.setWindowTitle(detail_dto.title)
        self.setMinimumSize(860, 560)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 12)
        root.setSpacing(10)

        root.addWidget(self._build_header())
        if detail_dto.warning_message:
            root.addWidget(self._build_warning_band(detail_dto.warning_message))

        self._table = QTableWidget(self)
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Account", "Name", "Note", "Amount"])
        configure_compact_table(self._table)
        self._table.setSortingEnabled(False)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        root.addWidget(self._table, 1)

        self._footer = QLabel("", self)
        self._footer.setProperty("role", "caption")
        root.addWidget(self._footer)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._bind_detail()

    def _build_header(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(6)

        title = QLabel(self._detail_dto.title, card)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        subtitle = QLabel(self._detail_dto.subtitle, card)
        subtitle.setObjectName("PageSummary")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        meta_row = QWidget(card)
        meta_layout = QHBoxLayout(meta_row)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(20)
        self._add_pair(meta_layout, "Lines:", str(len(self._detail_dto.rows)))
        self._add_pair(meta_layout, "Total:", self._fmt(self._detail_dto.total_amount))
        meta_layout.addStretch(1)
        layout.addWidget(meta_row)
        return card

    def _build_warning_band(self, message: str) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        label = QLabel(message, card)
        label.setObjectName("PageSummary")
        label.setWordWrap(True)
        layout.addWidget(label, 1)
        return card

    def _bind_detail(self) -> None:
        rows = self._detail_dto.rows
        self._table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            account_item = QTableWidgetItem(row.account_code)
            if row.account_id is not None:
                account_item.setData(Qt.ItemDataRole.UserRole, row.account_id)
            name_item = QTableWidgetItem(row.account_name)
            note_item = QTableWidgetItem(row.note or "")
            amount_item = QTableWidgetItem(self._fmt(row.amount))
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row_index, 0, account_item)
            self._table.setItem(row_index, 1, name_item)
            self._table.setItem(row_index, 2, note_item)
            self._table.setItem(row_index, 3, amount_item)
        self._footer.setText(
            "Double-click an account row to open the contributing ledger lines."
        )

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
            filter_dto=ReportingFilterDTO(
                company_id=self._detail_dto.company_id,
                date_from=self._detail_dto.date_from,
                date_to=self._detail_dto.date_to,
                posted_only=True,
            ),
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
    def _fmt(amount: Decimal | None) -> str:
        value = amount or _ZERO
        return f"{value:,.2f}"

    @classmethod
    def open(
        cls,
        service_registry: ServiceRegistry,
        detail_dto: FinancialChartDetailDTO,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, detail_dto, parent)
        dialog.exec()
