from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.operational_report_filter_dto import (
    OperationalReportLineDetailDTO,
)
from seeker_accounting.modules.reporting.ui.dialogs.journal_source_detail_dialog import (
    JournalSourceDetailDialog,
)
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn


class OperationalReportLineDetailDialog(QDialog):
    """Reusable detail dialog for operational report drilldowns."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        detail_dto: OperationalReportLineDetailDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._detail_dto = detail_dto

        self.setWindowTitle(detail_dto.title)
        self.setMinimumSize(860, 520)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)

        header = QFrame(self)
        header.setObjectName("PageCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 14, 16, 12)
        header_layout.setSpacing(6)

        title = QLabel(detail_dto.title, header)
        title.setObjectName("InfoCardTitle")
        header_layout.addWidget(title)

        subtitle = QLabel(detail_dto.subtitle, header)
        subtitle.setObjectName("PageSummary")
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        if detail_dto.warnings:
            warning = QFrame(self)
            warning.setObjectName("PageCard")
            warning_layout = QVBoxLayout(warning)
            warning_layout.setContentsMargins(14, 10, 14, 10)
            warning_layout.setSpacing(4)
            for message in detail_dto.warnings:
                label = QLabel(message, warning)
                label.setObjectName("PageSummary")
                label.setWordWrap(True)
                warning_layout.addWidget(label)
            layout.addWidget(warning)

        columns = tuple(DataTableColumn(key=str(i), title=col) for i, col in enumerate(detail_dto.columns))
        self._table = DataTable(
            columns=columns,
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=self,
        )
        self._model = QStandardItemModel(0, len(detail_dto.columns), self)
        self._model.setHorizontalHeaderLabels(list(detail_dto.columns))
        self._table.set_model(self._model)
        self._table.view().doubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self._table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._bind_rows()

    def _bind_rows(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        for row in self._detail_dto.rows:
            items = []
            for column_index, value in enumerate(row.values):
                item = self._make_item(value)
                if column_index == len(row.values) - 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if column_index == 0:
                    item.setData(row.journal_entry_id, Qt.ItemDataRole.UserRole)
                items.append(item)
            self._model.appendRow(items)

    def _on_row_double_clicked(self, index) -> None:
        proxy = self._table.view().model()
        if proxy is None:
            return
        src = proxy.mapToSource(index)
        row = src.row()
        id_item = self._model.item(row, 0)
        if id_item is None:
            return
        journal_entry_id = id_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(journal_entry_id, int):
            return
        JournalSourceDetailDialog.open(
            service_registry=self._service_registry,
            company_id=self._company_id,
            journal_entry_id=journal_entry_id,
            parent=self,
        )

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    @classmethod
    def open(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        detail_dto: OperationalReportLineDetailDTO,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, company_id, detail_dto, parent)
        dialog.exec()
