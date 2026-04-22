from __future__ import annotations

import logging

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from PySide6.QtCore import QEvent, QModelIndex, QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_dto import AccountLookupDTO
from seeker_accounting.modules.accounting.journals.dto.journal_commands import JournalLineCommand
from seeker_accounting.modules.accounting.journals.dto.journal_dto import JournalLineDTO
from seeker_accounting.modules.accounting.journals.ui.account_cell_widget import AccountCellWidget
from seeker_accounting.shared.ui.table_delegates import (
    NumericDelegate,
    RowNumberDelegate,
    _format_number,
)
from seeker_accounting.shared.ui.table_helpers import configure_compact_editable_table

_log = logging.getLogger(__name__)

# Column indices
_COL_SELECT = 0
_COL_ROW_NUM = 1
_COL_ACCOUNT_CODE = 2   # compound widget: [pick-btn][code-edit]
_COL_ACCOUNT_NAME = 3   # read-only display label
_COL_DESCRIPTION = 4
_COL_DEBIT = 5
_COL_CREDIT = 6
_COL_COUNT = 7

_HEADERS = ("", "#", "Acc #", "Account Name", "Description", "Debit", "Credit")

# Ordered list of editable columns for arrow-key navigation
_EDITABLE_COLS = (_COL_ACCOUNT_CODE, _COL_DESCRIPTION, _COL_DEBIT, _COL_CREDIT)


class JournalEntryLinesGrid(QFrame):
    """Editable line-items grid for Journal Entries.

    Public API:
        set_lines(lines)
        get_line_commands() -> list[JournalLineCommand]
        calculate_totals() -> (total_debit, total_credit, imbalance, line_count)
        set_header_description(text) — default description for new rows
        get_selected_indices() -> list[int]
        set_allocation(indices, allocation)
        get_allocation(row) -> dict
        set_read_only(read_only)
        lines_changed  — signal
    """

    lines_changed = Signal()

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._account_options: list[AccountLookupDTO] = []
        self._accounts_by_code: dict[str, tuple[int, str]] = {}   # code -> (id, name)
        self._accounts_by_id: dict[int, tuple[str, str]] = {}     # id -> (code, name)
        self._updating = False
        self._header_description: str = ""
        self._read_only = False

        # Per-row allocation data: contract_id, project_id, project_job_id, project_cost_code_id
        self._allocation_data: list[dict] = []

        self.setObjectName("PageCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # ── Header row ───────────────────────────────────────────────
        header_row = QWidget(self)
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        title = QLabel("Entry Lines", header_row)
        title.setObjectName("CardTitle")
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        layout.addWidget(header_row)

        # ── Model + View ─────────────────────────────────────────────
        self._model = QStandardItemModel(0, _COL_COUNT, self)
        self._model.setHorizontalHeaderLabels(_HEADERS)

        self._table = QTableView(self)
        self._table.setModel(self._model)
        configure_compact_editable_table(self._table)

        self._table.setMouseTracking(True)
        self._table.viewport().setMouseTracking(True)

        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        # ── Delegates ────────────────────────────────────────────────
        self._row_num_delegate = RowNumberDelegate(self._table)
        self._debit_delegate = NumericDelegate(decimals=2, parent=self._table)
        self._credit_delegate = NumericDelegate(decimals=2, parent=self._table)

        self._table.setItemDelegateForColumn(_COL_ROW_NUM, self._row_num_delegate)
        self._table.setItemDelegateForColumn(_COL_DEBIT, self._debit_delegate)
        self._table.setItemDelegateForColumn(_COL_CREDIT, self._credit_delegate)

        # ── Column widths ────────────────────────────────────────────
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)

        header.setSectionResizeMode(_COL_SELECT, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_SELECT, 28)

        header.setSectionResizeMode(_COL_ROW_NUM, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_ROW_NUM, 32)

        header.setSectionResizeMode(_COL_ACCOUNT_CODE, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_ACCOUNT_CODE, 130)

        header.setSectionResizeMode(_COL_ACCOUNT_NAME, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_ACCOUNT_NAME, 190)

        header.setSectionResizeMode(_COL_DESCRIPTION, QHeaderView.ResizeMode.Stretch)

        header.setSectionResizeMode(_COL_DEBIT, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_DEBIT, 110)

        header.setSectionResizeMode(_COL_CREDIT, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_CREDIT, 110)

        layout.addWidget(self._table, 1)

        # ── Empty state overlay ──────────────────────────────────────
        self._empty_label = QLabel("No journal lines yet. Click Add Line to begin.", self._table)
        self._empty_label.setObjectName("LinesEmptyState")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._empty_label.hide()

        # ── Bottom action bar ────────────────────────────────────────
        self._action_row = QWidget(self)
        action_layout = QHBoxLayout(self._action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(10)

        add_button = QPushButton("+ Add Line", self._action_row)
        add_button.setProperty("variant", "secondary")
        add_button.clicked.connect(self._add_empty_row)
        action_layout.addWidget(add_button)

        remove_button = QPushButton("Remove", self._action_row)
        remove_button.setProperty("variant", "ghost")
        remove_button.clicked.connect(self._remove_selected_row)
        action_layout.addWidget(remove_button)

        action_layout.addStretch(1)
        layout.addWidget(self._action_row)

        # ── Keyboard shortcuts ───────────────────────────────────────
        add_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        add_shortcut.activated.connect(self._add_empty_row)

        del_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self._table)
        del_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        del_shortcut.activated.connect(self._remove_selected_row)

        # ── Signals ──────────────────────────────────────────────────
        self._model.dataChanged.connect(self._on_data_changed)

        # ── Load reference data ──────────────────────────────────────
        self._load_reference_data()
        self._refresh_empty_state()

    # ------------------------------------------------------------------
    # Reference data
    # ------------------------------------------------------------------

    def _load_reference_data(self) -> None:
        try:
            self._account_options = (
                self._service_registry.chart_of_accounts_service.list_account_lookup_options(
                    self._company_id, active_only=False,
                )
            )
        except Exception:
            _log.warning("Failed to load accounts", exc_info=True)
            self._account_options = []

        # O(1) lookup maps — used by AccountCellWidget and _append_row.
        # by-code: active accounts only (can't post to inactive).
        # by-id: all accounts so existing lines with inactive accounts still display.
        self._accounts_by_code = {
            a.account_code: (a.id, a.account_name)
            for a in self._account_options
            if a.is_active
        }
        self._accounts_by_id = {
            a.id: (a.account_code, a.account_name)
            for a in self._account_options
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_header_description(self, text: str) -> None:
        """Store the header description used as default for new lines."""
        self._header_description = text.strip()

    def set_lines(self, lines: tuple[JournalLineDTO, ...]) -> None:
        self._updating = True
        try:
            self._model.removeRows(0, self._model.rowCount())
            self._allocation_data.clear()
            for line in lines:
                alloc = {
                    "contract_id": line.contract_id,
                    "project_id": line.project_id,
                    "project_job_id": line.project_job_id,
                    "project_cost_code_id": line.project_cost_code_id,
                }
                self._append_row(
                    account_id=line.account_id,
                    account_code=line.account_code,
                    account_name=line.account_name,
                    description=line.line_description or "",
                    debit=line.debit_amount,
                    credit=line.credit_amount,
                    allocation=alloc,
                )
        finally:
            self._updating = False
        self._refresh_empty_state()
        self.lines_changed.emit()

    def get_line_commands(self) -> list[JournalLineCommand]:
        commands: list[JournalLineCommand] = []
        for row in range(self._model.rowCount()):
            account_id = self._model.data(
                self._model.index(row, _COL_ACCOUNT_CODE), Qt.ItemDataRole.UserRole
            )
            if not isinstance(account_id, int) or account_id <= 0:
                continue

            debit = self._get_decimal(row, _COL_DEBIT) or Decimal("0.00")
            credit = self._get_decimal(row, _COL_CREDIT) or Decimal("0.00")

            if debit <= 0 and credit <= 0:
                continue

            description = (self._model.data(self._model.index(row, _COL_DESCRIPTION)) or "").strip()
            alloc = self._get_row_allocation(row)

            commands.append(
                JournalLineCommand(
                    account_id=account_id,
                    line_description=description or None,
                    debit_amount=debit,
                    credit_amount=credit,
                    contract_id=alloc.get("contract_id"),
                    project_id=alloc.get("project_id"),
                    project_job_id=alloc.get("project_job_id"),
                    project_cost_code_id=alloc.get("project_cost_code_id"),
                )
            )
        return commands

    def calculate_totals(self) -> tuple[Decimal, Decimal, Decimal, int]:
        """Return (total_debit, total_credit, imbalance, line_count)."""
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        line_count = 0

        for row in range(self._model.rowCount()):
            account_id = self._model.data(
                self._model.index(row, _COL_ACCOUNT_CODE), Qt.ItemDataRole.UserRole
            )
            if not isinstance(account_id, int) or account_id <= 0:
                continue

            debit = self._get_decimal(row, _COL_DEBIT) or Decimal("0.00")
            credit = self._get_decimal(row, _COL_CREDIT) or Decimal("0.00")

            if debit <= 0 and credit <= 0:
                continue

            total_debit += debit
            total_credit += credit
            line_count += 1

        imbalance = (total_debit - total_credit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return (
            total_debit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            total_credit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            imbalance,
            line_count,
        )

    def get_selected_indices(self) -> list[int]:
        """Return row indices where the selection checkbox is checked."""
        indices: list[int] = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row, _COL_SELECT)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                indices.append(row)
        return indices

    def set_all_checked(self, checked: bool) -> None:
        """Check or uncheck all row selection checkboxes."""
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._updating = True
        try:
            for row in range(self._model.rowCount()):
                item = self._model.item(row, _COL_SELECT)
                if item is not None:
                    item.setCheckState(state)
        finally:
            self._updating = False

    def set_allocation(self, indices: list[int], allocation: dict) -> None:
        """Apply allocation data to the specified rows."""
        for idx in indices:
            if 0 <= idx < len(self._allocation_data):
                self._allocation_data[idx] = dict(allocation)

    def get_allocation(self, row: int) -> dict:
        """Return allocation data for a specific row."""
        return self._get_row_allocation(row)

    def set_read_only(self, read_only: bool = True) -> None:
        """Enable or disable editing of the grid."""
        self._read_only = read_only
        self._action_row.setVisible(not read_only)
        for row in range(self._model.rowCount()):
            # Disable / enable checkboxes
            item = self._model.item(row, _COL_SELECT)
            if item is not None:
                flags = item.flags()
                if read_only:
                    flags &= ~Qt.ItemFlag.ItemIsUserCheckable
                else:
                    flags |= Qt.ItemFlag.ItemIsUserCheckable
                item.setFlags(flags)
            # Account cell widget
            acct_widget = self._table.indexWidget(self._model.index(row, _COL_ACCOUNT_CODE))
            if isinstance(acct_widget, AccountCellWidget):
                acct_widget.set_read_only(read_only)
            # Other persistent editors (description, debit, credit)
            for col in (_COL_DESCRIPTION, _COL_DEBIT, _COL_CREDIT):
                widget = self._table.indexWidget(self._model.index(row, col))
                if widget is not None:
                    widget.setEnabled(not read_only)

    # ------------------------------------------------------------------
    # Row manipulation
    # ------------------------------------------------------------------

    def _add_empty_row(self) -> None:
        self._append_row(
            account_id=None,
            description=self._header_description,
            debit=None,
            credit=None,
            allocation=None,
        )
        self._refresh_empty_state()
        # Focus the account-code cell of the new row
        new_row = self._model.rowCount() - 1
        self._focus_cell(new_row, _COL_ACCOUNT_CODE)

    def _append_row(
        self,
        account_id: int | None,
        description: str,
        debit: Decimal | None,
        credit: Decimal | None,
        allocation: dict | None,
        *,
        account_code: str = "",
        account_name: str = "",
    ) -> None:
        was_updating = self._updating
        self._updating = True
        try:
            row_items: list[QStandardItem] = []

            # Col 0: selection checkbox
            check_item = QStandardItem()
            check_item.setCheckable(True)
            check_item.setCheckState(Qt.CheckState.Unchecked)
            check_item.setEditable(False)
            row_items.append(check_item)

            # Col 1: row number (painted by delegate)
            num_item = QStandardItem()
            num_item.setEditable(False)
            row_items.append(num_item)

            # Resolve code / name from id when not fully supplied
            resolved_code = account_code
            resolved_name = account_name
            if account_id is not None and account_id > 0:
                if not resolved_code or not resolved_name:
                    lookup = self._accounts_by_id.get(account_id)
                    if lookup:
                        if not resolved_code:
                            resolved_code = lookup[0]
                        if not resolved_name:
                            resolved_name = lookup[1]

            # Col 2: account code (UserRole = account_id, DisplayRole = code)
            acct_code_item = QStandardItem()
            acct_code_item.setEditable(False)  # widget handles editing via setIndexWidget
            if account_id is not None and account_id > 0:
                acct_code_item.setData(resolved_code, Qt.ItemDataRole.DisplayRole)
                acct_code_item.setData(account_id, Qt.ItemDataRole.UserRole)
            row_items.append(acct_code_item)

            # Col 3: account name (read-only display)
            acct_name_item = QStandardItem(resolved_name)
            acct_name_item.setEditable(False)
            row_items.append(acct_name_item)

            # Col 4: description
            desc_item = QStandardItem(description)
            row_items.append(desc_item)

            # Col 5: debit
            debit_item = QStandardItem()
            if debit is not None and debit > 0:
                debit_item.setData(_format_number(debit), Qt.ItemDataRole.DisplayRole)
                debit_item.setData(debit, Qt.ItemDataRole.UserRole)
            row_items.append(debit_item)

            # Col 6: credit
            credit_item = QStandardItem()
            if credit is not None and credit > 0:
                credit_item.setData(_format_number(credit), Qt.ItemDataRole.DisplayRole)
                credit_item.setData(credit, Qt.ItemDataRole.UserRole)
            row_items.append(credit_item)

            self._model.appendRow(row_items)

            # Store allocation data
            alloc = allocation if allocation is not None else {
                "contract_id": None,
                "project_id": None,
                "project_job_id": None,
                "project_cost_code_id": None,
            }
            self._allocation_data.append(dict(alloc))

            # Open editors for this row
            row_idx = self._model.rowCount() - 1
            self._open_row_editors(row_idx)
        finally:
            self._updating = was_updating

        if not was_updating:
            self.lines_changed.emit()

    def _open_row_editors(self, row: int) -> None:
        """Open editors for all editable columns in *row*.

        The account column is populated via ``setIndexWidget`` with a compound
        ``AccountCellWidget``.  The remaining editable columns use persistent
        editors created through their respective delegates.
        """
        # ── Account column: compound widget ───────────────────────────
        acct_widget = AccountCellWidget(
            accounts_by_code=self._accounts_by_code,
            account_options=self._account_options,
            parent=None,
        )
        acct_widget.account_confirmed.connect(self._on_account_widget_confirmed)

        # Seed the widget from the model data already set by _append_row
        acct_code_item = self._model.item(row, _COL_ACCOUNT_CODE)
        if acct_code_item:
            account_id = acct_code_item.data(Qt.ItemDataRole.UserRole)
            code = acct_code_item.data(Qt.ItemDataRole.DisplayRole) or ""
            acct_name_item = self._model.item(row, _COL_ACCOUNT_NAME)
            name = (
                (acct_name_item.data(Qt.ItemDataRole.DisplayRole) or "")
                if acct_name_item
                else ""
            )
            if isinstance(account_id, int) and account_id > 0:
                acct_widget.set_account(account_id, code, name, emit=False)

        self._table.setIndexWidget(self._model.index(row, _COL_ACCOUNT_CODE), acct_widget)
        # Install the event filter on the inner code field so arrow-key
        # navigation between cells works (see _find_editor_cell).
        acct_widget.code_edit.installEventFilter(self)

        # ── Other editable columns: persistent editors ────────────────
        for col in (_COL_DESCRIPTION, _COL_DEBIT, _COL_CREDIT):
            idx = self._model.index(row, col)
            self._table.openPersistentEditor(idx)
            widget = self._table.indexWidget(idx)
            if widget is not None:
                widget.installEventFilter(self)

    def _close_row_editors(self, row: int) -> None:
        """Close editors for all editable columns in *row*."""
        # Account column was placed via setIndexWidget — clear it the same way.
        self._table.setIndexWidget(self._model.index(row, _COL_ACCOUNT_CODE), None)
        # Other editable columns use persistent editors.
        for col in (_COL_DESCRIPTION, _COL_DEBIT, _COL_CREDIT):
            self._table.closePersistentEditor(self._model.index(row, col))

    def _remove_selected_row(self) -> None:
        if self._read_only:
            return
        index = self._table.currentIndex()
        if not index.isValid():
            return
        row = index.row()
        self._close_row_editors(row)
        self._model.removeRow(row)
        if 0 <= row < len(self._allocation_data):
            self._allocation_data.pop(row)
        self._refresh_empty_state()
        self.lines_changed.emit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_decimal(self, row: int, col: int) -> Decimal | None:
        raw = self._model.data(self._model.index(row, col), Qt.ItemDataRole.UserRole)
        if raw is None:
            return None
        if isinstance(raw, Decimal):
            return raw
        try:
            return Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return None

    def _get_row_allocation(self, row: int) -> dict:
        if 0 <= row < len(self._allocation_data):
            return dict(self._allocation_data[row])
        return {
            "contract_id": None,
            "project_id": None,
            "project_job_id": None,
            "project_cost_code_id": None,
        }

    # ------------------------------------------------------------------
    # Account widget callback
    # ------------------------------------------------------------------

    def _on_account_widget_confirmed(self, account_id: int, code: str, name: str) -> None:
        """Called by AccountCellWidget when the user confirms an account."""
        sender_widget = self.sender()
        for row in range(self._model.rowCount()):
            w = self._table.indexWidget(self._model.index(row, _COL_ACCOUNT_CODE))
            if w is sender_widget:
                self._updating = True
                try:
                    self._model.setData(
                        self._model.index(row, _COL_ACCOUNT_CODE),
                        code,
                        Qt.ItemDataRole.DisplayRole,
                    )
                    self._model.setData(
                        self._model.index(row, _COL_ACCOUNT_CODE),
                        account_id if account_id > 0 else None,
                        Qt.ItemDataRole.UserRole,
                    )
                    self._model.setData(
                        self._model.index(row, _COL_ACCOUNT_NAME),
                        name,
                        Qt.ItemDataRole.DisplayRole,
                    )
                finally:
                    self._updating = False
                self.lines_changed.emit()
                return

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_data_changed(
        self,
        top_left: QModelIndex,
        bottom_right: QModelIndex,
        _roles: list[int] | None = None,
    ) -> None:
        if self._updating:
            return

        for row in range(top_left.row(), bottom_right.row() + 1):
            col = top_left.column()

            # Debit/credit mutual exclusivity
            if col == _COL_DEBIT:
                debit = self._get_decimal(row, _COL_DEBIT)
                if debit is not None and debit > 0:
                    self._updating = True
                    try:
                        idx = self._model.index(row, _COL_CREDIT)
                        self._model.setData(idx, "", Qt.ItemDataRole.DisplayRole)
                        self._model.setData(idx, None, Qt.ItemDataRole.UserRole)
                        widget = self._table.indexWidget(idx)
                        if isinstance(widget, QLineEdit):
                            widget.setText("")
                    finally:
                        self._updating = False

            elif col == _COL_CREDIT:
                credit = self._get_decimal(row, _COL_CREDIT)
                if credit is not None and credit > 0:
                    self._updating = True
                    try:
                        idx = self._model.index(row, _COL_DEBIT)
                        self._model.setData(idx, "", Qt.ItemDataRole.DisplayRole)
                        self._model.setData(idx, None, Qt.ItemDataRole.UserRole)
                        widget = self._table.indexWidget(idx)
                        if isinstance(widget, QLineEdit):
                            widget.setText("")
                    finally:
                        self._updating = False

        self.lines_changed.emit()

    def _refresh_empty_state(self) -> None:
        has_rows = self._model.rowCount() > 0
        self._empty_label.setVisible(not has_rows)
        if not has_rows:
            vp = self._table.viewport()
            self._empty_label.setGeometry(0, 0, vp.width(), vp.height())

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        if self._empty_label.isVisible():
            vp = self._table.viewport()
            self._empty_label.setGeometry(0, 0, vp.width(), vp.height())

    # ------------------------------------------------------------------
    # Arrow-key navigation between persistent editors
    # ------------------------------------------------------------------

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, event)

        key_event: QKeyEvent = event  # type: ignore[assignment]
        key = key_event.key()

        if key not in (
            Qt.Key.Key_Left, Qt.Key.Key_Right,
            Qt.Key.Key_Up, Qt.Key.Key_Down,
            Qt.Key.Key_Tab, Qt.Key.Key_Backtab,
        ):
            return super().eventFilter(obj, event)

        row, col = self._find_editor_cell(obj)
        if row < 0:
            return super().eventFilter(obj, event)

        # If a combo dropdown list is open, let Up/Down navigate the
        # popup list instead of moving to another grid row.
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down) and hasattr(obj, 'view') and obj.view().isVisible():
            return super().eventFilter(obj, event)

        # For QLineEdit: Left/Right only navigate away at text boundaries
        if isinstance(obj, QLineEdit) and key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            cursor_pos = obj.cursorPosition()
            text_len = len(obj.text())
            if key == Qt.Key.Key_Left and cursor_pos > 0:
                return super().eventFilter(obj, event)
            if key == Qt.Key.Key_Right and cursor_pos < text_len:
                return super().eventFilter(obj, event)

        target_row, target_col = row, col
        col_idx = _EDITABLE_COLS.index(col) if col in _EDITABLE_COLS else -1

        if key in (Qt.Key.Key_Left, Qt.Key.Key_Backtab):
            if col_idx > 0:
                target_col = _EDITABLE_COLS[col_idx - 1]
            elif row > 0:
                target_row = row - 1
                target_col = _EDITABLE_COLS[-1]
            else:
                return super().eventFilter(obj, event)

        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Tab):
            if col_idx < len(_EDITABLE_COLS) - 1:
                target_col = _EDITABLE_COLS[col_idx + 1]
            elif row < self._model.rowCount() - 1:
                target_row = row + 1
                target_col = _EDITABLE_COLS[0]
            else:
                return super().eventFilter(obj, event)

        elif key == Qt.Key.Key_Up:
            if row > 0:
                target_row = row - 1
            else:
                return super().eventFilter(obj, event)

        elif key == Qt.Key.Key_Down:
            if row < self._model.rowCount() - 1:
                target_row = row + 1
            else:
                return super().eventFilter(obj, event)

        if target_row != row or target_col != col:
            self._focus_cell(target_row, target_col)
            return True

        return super().eventFilter(obj, event)

    def _find_editor_cell(self, widget: QObject) -> tuple[int, int]:
        for row in range(self._model.rowCount()):
            for col in _EDITABLE_COLS:
                idx = self._model.index(row, col)
                w = self._table.indexWidget(idx)
                if w is widget or (w is not None and widget.parent() is w):
                    return row, col
        return -1, -1

    def _focus_cell(self, row: int, col: int) -> None:
        idx = self._model.index(row, col)
        self._table.setCurrentIndex(idx)
        widget = self._table.indexWidget(idx)
        if widget is not None:
            if isinstance(widget, AccountCellWidget):
                widget.code_edit.setFocus()
                widget.code_edit.selectAll()
            elif isinstance(widget, QLineEdit):
                widget.setFocus()
                widget.selectAll()
            else:
                widget.setFocus()
