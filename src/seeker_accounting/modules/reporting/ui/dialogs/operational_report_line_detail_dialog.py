from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
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
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


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

        self._table = QTableWidget(self)
        self._table.setColumnCount(len(detail_dto.columns))
        self._table.setHorizontalHeaderLabels(list(detail_dto.columns))
        configure_compact_table(self._table)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self._table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._bind_rows()

    def _bind_rows(self) -> None:
        self._table.setRowCount(len(self._detail_dto.rows))
        for row_index, row in enumerate(self._detail_dto.rows):
            for column_index, value in enumerate(row.values):
                item = QTableWidgetItem(value)
                if column_index == len(row.values) - 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.journal_entry_id)
                self._table.setItem(row_index, column_index, item)

    def _on_row_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        first_item = self._table.item(row, 0)
        if first_item is None:
            return
        journal_entry_id = first_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(journal_entry_id, int):
            return
        JournalSourceDetailDialog.open(
            service_registry=self._service_registry,
            company_id=self._company_id,
            journal_entry_id=journal_entry_id,
            parent=self,
        )

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
