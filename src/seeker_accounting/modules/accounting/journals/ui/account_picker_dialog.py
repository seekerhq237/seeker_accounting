"""AccountPickerDialog — browse and select a non-control account.

Used by AccountCellWidget in the journal entry lines grid.  Filters to
active, non-control accounts only (control accounts are managed by subledger
posting services and must not be targeted by manual journal lines).
"""
from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_dto import AccountLookupDTO
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_COL_CODE = 0
_COL_NAME = 1
_COL_COUNT = 2


class AccountPickerDialog(QDialog):
    """Account picker dialog for journal-entry line items.

    Shows active, non-control accounts in a searchable table.
    Supports double-click selection and a Select button.

    Usage::
        result = AccountPickerDialog.pick_account(account_options, parent=self)
        if result:
            account_id, code, name = result
    """

    def __init__(
        self,
        account_options: list[AccountLookupDTO],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Account")
        self.setObjectName("AccountPickerDialog")
        self.setModal(True)
        self.resize(640, 480)

        # Active, non-control accounts only
        self._accounts = [
            a for a in account_options
            if not a.is_control_account and a.is_active
        ]
        self._selected: AccountLookupDTO | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # ── Title ────────────────────────────────────────────────────
        title = QLabel("Select Account", self)
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        # ── Search bar ───────────────────────────────────────────────
        search_row = QWidget(self)
        search_layout = QHBoxLayout(search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)

        search_label = QLabel("Search:", search_row)
        search_layout.addWidget(search_label)

        self._search_edit = QLineEdit(search_row)
        self._search_edit.setPlaceholderText("Filter by code or name…")
        self._search_edit.setClearButtonEnabled(True)
        search_layout.addWidget(self._search_edit, 1)

        layout.addWidget(search_row)

        # ── Table ────────────────────────────────────────────────────
        self._source_model = QStandardItemModel(0, _COL_COUNT, self)
        self._source_model.setHorizontalHeaderLabels(["Code", "Account Name"])

        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._source_model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)  # match across all columns

        self._table = QTableView(self)
        self._table.setModel(self._proxy)
        configure_compact_table(self._table)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(_COL_CODE, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_CODE, 110)
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(True)

        self._populate_table()
        layout.addWidget(self._table, 1)

        # ── Buttons ──────────────────────────────────────────────────
        btn_box = QDialogButtonBox(self)

        self._select_btn = QPushButton("Select", self)
        self._select_btn.setProperty("variant", "primary")
        self._select_btn.setEnabled(False)
        btn_box.addButton(self._select_btn, QDialogButtonBox.ButtonRole.AcceptRole)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setProperty("variant", "secondary")
        btn_box.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)

        btn_box.accepted.connect(self._on_select)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        # ── Connections ──────────────────────────────────────────────
        self._search_edit.textChanged.connect(self._on_search_changed)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._table.doubleClicked.connect(self._on_double_clicked)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selected_account(self) -> tuple[int, str, str] | None:
        """Return (account_id, account_code, account_name) or None."""
        if self._selected is None:
            return None
        return (self._selected.id, self._selected.account_code, self._selected.account_name)

    @classmethod
    def pick_account(
        cls,
        account_options: list[AccountLookupDTO],
        parent: QWidget | None = None,
    ) -> tuple[int, str, str] | None:
        """Open the picker and return the selected account or None if cancelled."""
        dialog = cls(account_options, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selected_account()
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _populate_table(self) -> None:
        for acc in self._accounts:
            code_item = QStandardItem(acc.account_code)
            code_item.setData(acc.id, Qt.ItemDataRole.UserRole)
            code_item.setEditable(False)

            name_item = QStandardItem(acc.account_name)
            name_item.setEditable(False)

            self._source_model.appendRow([code_item, name_item])

        self._proxy.sort(_COL_CODE, Qt.SortOrder.AscendingOrder)

    def _resolve_selected_account(self) -> AccountLookupDTO | None:
        proxy_idx = self._table.currentIndex()
        if not proxy_idx.isValid():
            return None
        source_idx = self._proxy.mapToSource(self._proxy.index(proxy_idx.row(), _COL_CODE))
        item = self._source_model.itemFromIndex(source_idx)
        if item is None:
            return None
        account_id: int = item.data(Qt.ItemDataRole.UserRole)
        for acc in self._accounts:
            if acc.id == account_id:
                return acc
        return None

    def showEvent(self, event: object) -> None:
        super().showEvent(event)  # type: ignore[arg-type]
        self._search_edit.setFocus()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        self._proxy.setFilterFixedString(text)

    def _on_selection_changed(self) -> None:
        self._select_btn.setEnabled(self._table.selectionModel().hasSelection())

    def _on_double_clicked(self, _index: object) -> None:
        if self._table.selectionModel().hasSelection():
            self._on_select()

    def _on_select(self) -> None:
        acc = self._resolve_selected_account()
        if acc is None:
            return
        self._selected = acc
        self.accept()
