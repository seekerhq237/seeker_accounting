from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
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
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn

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

        self._model = QStandardItemModel(0, 4, self)
        self._model.setHorizontalHeaderLabels(["Account", "Name", "Note", "Amount"])
        self._table = DataTable(
            columns=(
                DataTableColumn(key="account", title="Account"),
                DataTableColumn(key="name", title="Name"),
                DataTableColumn(key="note", title="Note"),
                DataTableColumn(key="amount", title="Amount"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=self,
        )
        self._table.set_model(self._model)
        self._table.view().doubleClicked.connect(self._on_row_double_clicked)
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
        self._model.removeRows(0, self._model.rowCount())
        for row in rows:
            amount_item = self._make_item(self._fmt(row.amount))
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._model.appendRow([
                self._make_item(row.account_code, user_data=row.account_id),
                self._make_item(row.account_name),
                self._make_item(row.note or ""),
                amount_item,
            ])
        self._footer.setText(
            "Double-click an account row to open the contributing ledger lines."
        )

    def _on_row_double_clicked(self, index) -> None:
        proxy = self._table.view().model()
        if proxy is None:
            return
        src = proxy.mapToSource(index)
        row = src.row()
        id_item = self._model.item(row, 0)
        if id_item is None:
            return
        account_id = id_item.data(Qt.ItemDataRole.UserRole)
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

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

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
