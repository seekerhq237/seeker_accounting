from __future__ import annotations

import logging

from decimal import Decimal

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
from seeker_accounting.modules.accounting.journals.dto.journal_dto import JournalEntryDetailDTO
from seeker_accounting.platform.exceptions import NotFoundError
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn

_ZERO = Decimal("0.00")


_log = logging.getLogger(__name__)


class JournalSourceDetailDialog(QDialog):
    """Read-only view of a posted journal entry for GL drilldowns."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        journal_entry_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Journal Detail")
        self.setMinimumSize(720, 560)
        self.setModal(True)

        self._service_registry = service_registry
        self._company_id = company_id
        self._journal_entry_id = journal_entry_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)

        self._header_card = QFrame(self)
        self._header_card.setObjectName("PageCard")
        header_layout = QVBoxLayout(self._header_card)
        header_layout.setContentsMargins(16, 14, 16, 12)
        header_layout.setSpacing(6)

        self._title_lbl = QLabel("Journal Entry", self._header_card)
        self._title_lbl.setObjectName("InfoCardTitle")
        header_layout.addWidget(self._title_lbl)

        self._meta_lbl = QLabel("", self._header_card)
        self._meta_lbl.setObjectName("PageSummary")
        self._meta_lbl.setWordWrap(True)
        header_layout.addWidget(self._meta_lbl)

        layout.addWidget(self._header_card)

        self._model = QStandardItemModel(0, 5, self)
        self._model.setHorizontalHeaderLabels(
            ["Line", "Account", "Description", "Debit", "Credit"]
        )
        self._table = DataTable(
            columns=(
                DataTableColumn(key="line", title="Line"),
                DataTableColumn(key="account", title="Account"),
                DataTableColumn(key="description", title="Description"),
                DataTableColumn(key="debit", title="Debit"),
                DataTableColumn(key="credit", title="Credit"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=self,
        )
        self._table.set_model(self._model)
        layout.addWidget(self._table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load()

    # ------------------------------------------------------------------
    # Data binding
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            entry = self._service_registry.journal_service.get_journal_entry(
                self._company_id, self._journal_entry_id
            )
        except NotFoundError as exc:
            show_error(self, "Journal Detail", str(exc))
            self.reject()
            return
        except AppError as exc:
            show_error(self, "Journal Detail", str(exc))

        except Exception:
            _log.exception("Journal Detail")
            show_error(self, "Journal Detail", "An unexpected error occurred. See application log for details.")
            self.reject()
            return

        self._bind_entry(entry)

    def _bind_entry(self, entry: JournalEntryDetailDTO) -> None:
        entry_number = entry.entry_number or "Draft"
        self._title_lbl.setText(f"Journal {entry_number}")

        meta_parts: list[str] = [
            f"Date: {entry.entry_date.strftime('%Y-%m-%d')}",
            f"Status: {entry.status_code}",
        ]
        if entry.posted_at:
            meta_parts.append(f"Posted: {entry.posted_at.strftime('%Y-%m-%d %H:%M')}")
        if entry.source_module_code:
            meta_parts.append(f"Source: {entry.source_module_code}")
        if entry.reference_text:
            meta_parts.append(f"Reference: {entry.reference_text}")
        if entry.description:
            meta_parts.append(f"Description: {entry.description}")
        self._meta_lbl.setText(" · ".join(meta_parts))

        self._model.removeRows(0, self._model.rowCount())
        self._model.setRowCount(len(entry.lines))
        for idx, line in enumerate(entry.lines):
            self._set_text(idx, 0, str(line.line_number))
            account_label = f"{line.account_code} · {line.account_name}"
            self._set_text(idx, 1, account_label)
            self._set_text(idx, 2, line.line_description or "—")
            self._set_amount(idx, 3, line.debit_amount)
            self._set_amount(idx, 4, line.credit_amount)

    def _set_text(self, row: int, col: int, text: str) -> None:
        item = QStandardItem(text)
        item.setEditable(False)
        self._model.setItem(row, col, item)

    def _set_amount(self, row: int, col: int, amount: Decimal) -> None:
        item = QStandardItem(self._fmt(amount))
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._model.setItem(row, col, item)

    @staticmethod
    def _fmt(amount: Decimal) -> str:
        if amount == _ZERO:
            return "0.00"
        return f"{amount:,.2f}"

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def open(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        journal_entry_id: int,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(service_registry, company_id, journal_entry_id, parent)
        dialog.exec()
