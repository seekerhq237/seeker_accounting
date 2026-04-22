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
from seeker_accounting.modules.inventory.dto.inventory_document_commands import (
    InventoryDocumentLineCommand,
)
from seeker_accounting.modules.inventory.dto.inventory_document_dto import (
    InventoryDocumentLineDTO,
)
from seeker_accounting.shared.ui.table_delegates import (
    ComboBoxDelegate,
    NumericDelegate,
    RowNumberDelegate,
    _format_number,
)
from seeker_accounting.shared.ui.table_helpers import configure_compact_editable_table

_log = logging.getLogger(__name__)

# Column indices
_COL_ROW_NUM = 0
_COL_ITEM = 1
_COL_UOM = 2
_COL_QTY = 3
_COL_UNIT_COST = 4
_COL_ACCOUNT = 5
_COL_DESCRIPTION = 6
_COL_LINE_AMOUNT = 7
_COL_COUNT = 8

_HEADERS = ("#", "Item", "UoM", "Qty", "Unit Cost", "Account", "Description", "Amount")

# Ordered list of editable columns for arrow-key navigation
_EDITABLE_COLS = (
    _COL_ITEM,
    _COL_UOM,
    _COL_QTY,
    _COL_UNIT_COST,
    _COL_ACCOUNT,
    _COL_DESCRIPTION,
)


class InventoryDocumentLinesGrid(QFrame):
    """Editable line-items grid for Inventory Documents.

    Public API:
        set_lines(lines)
        get_line_commands() -> list[InventoryDocumentLineCommand]
        calculate_totals() -> (total, Decimal(0), total, line_count)
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
        self._items: list[tuple[int, str, str]] = []
        self._items_uom: dict[int, int | None] = {}
        self._uoms: list[tuple[int, str, str]] = []
        self._accounts: list[tuple[int, str, str]] = []
        self._updating = False

        self.setObjectName("PageCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # ── Header row ───────────────────────────────────────────────
        header_row = QWidget(self)
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        title = QLabel("Document Lines", header_row)
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
        self._item_delegate = ComboBoxDelegate(
            placeholder="-- Select item --", parent=self._table
        )
        self._uom_delegate = ComboBoxDelegate(
            placeholder="-- UoM --", parent=self._table
        )
        self._qty_delegate = NumericDelegate(decimals=2, parent=self._table)
        self._cost_delegate = NumericDelegate(decimals=2, parent=self._table)
        self._account_delegate = ComboBoxDelegate(
            placeholder="-- Account --", parent=self._table
        )
        self._amount_delegate = NumericDelegate(
            decimals=2, read_only=True, parent=self._table
        )

        self._table.setItemDelegateForColumn(_COL_ROW_NUM, self._row_num_delegate)
        self._table.setItemDelegateForColumn(_COL_ITEM, self._item_delegate)
        self._table.setItemDelegateForColumn(_COL_UOM, self._uom_delegate)
        self._table.setItemDelegateForColumn(_COL_QTY, self._qty_delegate)
        self._table.setItemDelegateForColumn(_COL_UNIT_COST, self._cost_delegate)
        self._table.setItemDelegateForColumn(_COL_ACCOUNT, self._account_delegate)
        self._table.setItemDelegateForColumn(_COL_LINE_AMOUNT, self._amount_delegate)

        # ── Column widths ────────────────────────────────────────────
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)

        header.setSectionResizeMode(_COL_ROW_NUM, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_ROW_NUM, 32)

        header.setSectionResizeMode(_COL_ITEM, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_ITEM, 200)

        header.setSectionResizeMode(_COL_UOM, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_UOM, 100)

        header.setSectionResizeMode(_COL_QTY, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_QTY, 70)

        header.setSectionResizeMode(_COL_UNIT_COST, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_UNIT_COST, 100)

        header.setSectionResizeMode(_COL_ACCOUNT, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_ACCOUNT, 180)

        header.setSectionResizeMode(_COL_DESCRIPTION, QHeaderView.ResizeMode.Stretch)

        header.setSectionResizeMode(_COL_LINE_AMOUNT, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_LINE_AMOUNT, 110)

        layout.addWidget(self._table, 1)

        # ── Empty state overlay ──────────────────────────────────────
        self._empty_label = QLabel(
            "No line items yet. Click Add Line to begin.", self._table
        )
        self._empty_label.setObjectName("LinesEmptyState")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self._empty_label.hide()

        # ── Bottom action bar ────────────────────────────────────────
        action_row = QWidget(self)
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(10)

        add_button = QPushButton("+ Add Line", action_row)
        add_button.setProperty("variant", "secondary")
        add_button.clicked.connect(self._add_empty_row)
        action_layout.addWidget(add_button)

        remove_button = QPushButton("Remove", action_row)
        remove_button.setProperty("variant", "ghost")
        remove_button.clicked.connect(self._remove_selected_row)
        action_layout.addWidget(remove_button)

        action_layout.addStretch(1)
        layout.addWidget(action_row)

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
            items = self._service_registry.item_service.list_items(
                self._company_id, active_only=True, item_type_code="stock"
            )
            self._items = [(i.id, i.item_code, i.item_name) for i in items]
            self._items_uom = {
                i.id: i.unit_of_measure_id for i in items
            }
        except Exception:
            _log.warning("Failed to load items", exc_info=True)
            self._items = []
            self._items_uom = {}

        try:
            uoms = self._service_registry.unit_of_measure_service.list_units_of_measure(
                self._company_id, active_only=True
            )
            self._uoms = [(u.id, u.code, u.name) for u in uoms]
        except Exception:
            _log.warning("Failed to load UoMs", exc_info=True)
            self._uoms = []

        try:
            accounts = self._service_registry.chart_of_accounts_service.list_accounts(
                self._company_id, active_only=True
            )
            self._accounts = [
                (a.id, a.account_code, a.account_name)
                for a in accounts
                if a.allow_manual_posting
            ]
        except Exception:
            _log.warning("Failed to load accounts", exc_info=True)
            self._accounts = []

        self._item_delegate.set_items(
            [(f"{code} - {name}", iid) for iid, code, name in self._items]
        )
        self._uom_delegate.set_items(
            [(f"{code} - {name}", uid) for uid, code, name in self._uoms]
        )
        self._account_delegate.set_items(
            [(f"{code} - {name}", aid) for aid, code, name in self._accounts]
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_lines(self, lines: tuple[InventoryDocumentLineDTO, ...]) -> None:
        self._updating = True
        try:
            self._model.removeRows(0, self._model.rowCount())
            for line in lines:
                self._append_row(
                    item_id=line.item_id,
                    uom_id=line.transaction_uom_id,
                    quantity=line.quantity,
                    unit_cost=line.unit_cost,
                    account_id=line.counterparty_account_id,
                    description=line.line_description or "",
                    line_amount=line.line_amount,
                )
        finally:
            self._updating = False
        self._recalculate_all_totals()
        self._refresh_empty_state()

    def get_line_commands(self) -> list[InventoryDocumentLineCommand]:
        commands: list[InventoryDocumentLineCommand] = []
        for row in range(self._model.rowCount()):
            item_id = self._model.data(
                self._model.index(row, _COL_ITEM), Qt.ItemDataRole.UserRole
            )
            if not isinstance(item_id, int) or item_id <= 0:
                continue

            uom_id = self._model.data(
                self._model.index(row, _COL_UOM), Qt.ItemDataRole.UserRole
            )
            if not isinstance(uom_id, int) or uom_id <= 0:
                uom_id = None

            quantity = self._get_decimal(row, _COL_QTY)
            unit_cost = self._get_decimal(row, _COL_UNIT_COST)

            account_id = self._model.data(
                self._model.index(row, _COL_ACCOUNT), Qt.ItemDataRole.UserRole
            )
            if not isinstance(account_id, int) or account_id <= 0:
                account_id = None

            description = (
                self._model.data(self._model.index(row, _COL_DESCRIPTION)) or ""
            ).strip()

            commands.append(
                InventoryDocumentLineCommand(
                    item_id=item_id,
                    quantity=quantity if quantity is not None else Decimal("0"),
                    unit_cost=unit_cost,
                    counterparty_account_id=account_id,
                    line_description=description or None,
                    transaction_uom_id=uom_id,
                )
            )
        return commands

    def calculate_totals(self) -> tuple[Decimal, Decimal, Decimal, int]:
        total = Decimal("0.00")
        for row in range(self._model.rowCount()):
            amount = self._calculate_row_amount(row)
            if amount is not None:
                total += abs(amount)
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return (total, Decimal("0.00"), total, self._model.rowCount())

    # ------------------------------------------------------------------
    # Row manipulation
    # ------------------------------------------------------------------

    def _add_empty_row(self) -> None:
        self._append_row(
            item_id=None,
            uom_id=None,
            quantity=None,
            unit_cost=None,
            account_id=None,
            description="",
            line_amount=None,
        )
        self._refresh_empty_state()
        new_row = self._model.rowCount() - 1
        item_index = self._model.index(new_row, _COL_ITEM)
        self._table.setCurrentIndex(item_index)
        widget = self._table.indexWidget(item_index)
        if widget is not None:
            widget.setFocus()

    def _append_row(
        self,
        item_id: int | None,
        uom_id: int | None,
        quantity: Decimal | None,
        unit_cost: Decimal | None,
        account_id: int | None,
        description: str,
        line_amount: Decimal | None,
    ) -> None:
        was_updating = self._updating
        self._updating = True
        try:
            row_items: list[QStandardItem] = []

            # Col 0: row number (painted by delegate)
            num_item = QStandardItem()
            num_item.setEditable(False)
            row_items.append(num_item)

            # Col 1: item
            item_item = QStandardItem()
            if item_id is not None and item_id > 0:
                item_item.setData(
                    self._item_display(item_id), Qt.ItemDataRole.DisplayRole
                )
                item_item.setData(item_id, Qt.ItemDataRole.UserRole)
            row_items.append(item_item)

            # Col 2: UoM
            uom_item = QStandardItem()
            if uom_id is not None and uom_id > 0:
                uom_item.setData(
                    self._uom_display(uom_id), Qt.ItemDataRole.DisplayRole
                )
                uom_item.setData(uom_id, Qt.ItemDataRole.UserRole)
            row_items.append(uom_item)

            # Col 3: qty
            qty_item = QStandardItem()
            if quantity is not None:
                qty_item.setData(
                    _format_number(quantity), Qt.ItemDataRole.DisplayRole
                )
                qty_item.setData(quantity, Qt.ItemDataRole.UserRole)
            row_items.append(qty_item)

            # Col 4: unit cost
            cost_item = QStandardItem()
            if unit_cost is not None:
                cost_item.setData(
                    _format_number(unit_cost), Qt.ItemDataRole.DisplayRole
                )
                cost_item.setData(unit_cost, Qt.ItemDataRole.UserRole)
            row_items.append(cost_item)

            # Col 5: account
            acct_item = QStandardItem()
            if account_id is not None and account_id > 0:
                acct_item.setData(
                    self._account_display(account_id), Qt.ItemDataRole.DisplayRole
                )
                acct_item.setData(account_id, Qt.ItemDataRole.UserRole)
            row_items.append(acct_item)

            # Col 6: description
            desc_item = QStandardItem(description)
            row_items.append(desc_item)

            # Col 7: line amount (read-only)
            amount_item = QStandardItem()
            amount_item.setEditable(False)
            if line_amount is not None:
                amount_item.setData(
                    _format_number(line_amount), Qt.ItemDataRole.DisplayRole
                )
                amount_item.setData(line_amount, Qt.ItemDataRole.UserRole)
            row_items.append(amount_item)

            self._model.appendRow(row_items)

            row_idx = self._model.rowCount() - 1
            self._open_row_editors(row_idx)
        finally:
            self._updating = was_updating

        if not was_updating:
            self._refresh_row_amount(self._model.rowCount() - 1)
            self.lines_changed.emit()

    def _open_row_editors(self, row: int) -> None:
        for col in _EDITABLE_COLS:
            idx = self._model.index(row, col)
            self._table.openPersistentEditor(idx)
            widget = self._table.indexWidget(idx)
            if widget is not None:
                widget.installEventFilter(self)

    def _close_row_editors(self, row: int) -> None:
        for col in _EDITABLE_COLS:
            idx = self._model.index(row, col)
            self._table.closePersistentEditor(idx)

    def _remove_selected_row(self) -> None:
        index = self._table.currentIndex()
        if not index.isValid():
            return
        row = index.row()
        self._close_row_editors(row)
        self._model.removeRow(row)
        self._recalculate_all_totals()
        self._refresh_empty_state()

    # ------------------------------------------------------------------
    # Calculation helpers
    # ------------------------------------------------------------------

    def _get_decimal(self, row: int, col: int) -> Decimal | None:
        raw = self._model.data(
            self._model.index(row, col), Qt.ItemDataRole.UserRole
        )
        if raw is None:
            return None
        if isinstance(raw, Decimal):
            return raw
        try:
            return Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return None

    def _calculate_row_amount(self, row: int) -> Decimal | None:
        quantity = self._get_decimal(row, _COL_QTY)
        unit_cost = self._get_decimal(row, _COL_UNIT_COST)
        if quantity is None or unit_cost is None:
            return None
        return (quantity * unit_cost).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def _refresh_row_amount(self, row: int) -> None:
        if row < 0 or row >= self._model.rowCount():
            return
        amount = self._calculate_row_amount(row)
        was = self._updating
        self._updating = True
        try:
            idx = self._model.index(row, _COL_LINE_AMOUNT)
            if amount is not None:
                self._model.setData(
                    idx, _format_number(amount), Qt.ItemDataRole.DisplayRole
                )
                self._model.setData(idx, amount, Qt.ItemDataRole.UserRole)
            else:
                self._model.setData(idx, "", Qt.ItemDataRole.DisplayRole)
                self._model.setData(idx, None, Qt.ItemDataRole.UserRole)
        finally:
            self._updating = was

    def _recalculate_all_totals(self) -> None:
        for row in range(self._model.rowCount()):
            self._refresh_row_amount(row)
        self.lines_changed.emit()

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _item_display(self, item_id: int) -> str:
        for iid, code, name in self._items:
            if iid == item_id:
                return f"{code} - {name}"
        return ""

    def _uom_display(self, uom_id: int) -> str:
        for uid, code, name in self._uoms:
            if uid == uom_id:
                return f"{code} - {name}"
        return ""

    def _account_display(self, account_id: int) -> str:
        for aid, code, name in self._accounts:
            if aid == account_id:
                return f"{code} - {name}"
        return ""

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
            if col == _COL_ITEM:
                self._auto_set_uom(row)
            if col in (_COL_QTY, _COL_UNIT_COST):
                self._refresh_row_amount(row)
        self.lines_changed.emit()

    def _auto_set_uom(self, row: int) -> None:
        item_id = self._model.data(
            self._model.index(row, _COL_ITEM), Qt.ItemDataRole.UserRole
        )
        if not isinstance(item_id, int) or item_id <= 0:
            return
        uom_id = self._items_uom.get(item_id)
        if uom_id is None:
            return
        was = self._updating
        self._updating = True
        try:
            idx = self._model.index(row, _COL_UOM)
            display = self._uom_display(uom_id)
            self._model.setData(idx, display, Qt.ItemDataRole.DisplayRole)
            self._model.setData(idx, uom_id, Qt.ItemDataRole.UserRole)
            widget = self._table.indexWidget(idx)
            if widget is not None and hasattr(widget, "set_current_value"):
                widget.set_current_value(uom_id)
        finally:
            self._updating = was

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
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_Tab,
            Qt.Key.Key_Backtab,
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
        if isinstance(obj, QLineEdit) and key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
        ):
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
            widget.setFocus()
            if isinstance(widget, QLineEdit):
                widget.selectAll()
