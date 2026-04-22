from __future__ import annotations

import logging

from decimal import Decimal, ROUND_HALF_UP

from PySide6.QtCore import QEvent, QModelIndex, QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
from seeker_accounting.modules.sales.dto.customer_quote_commands import CustomerQuoteLineCommand
from seeker_accounting.modules.sales.dto.customer_quote_dto import CustomerQuoteLineDTO
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
_COL_DESCRIPTION = 1
_COL_QTY = 2
_COL_UNIT_PRICE = 3
_COL_DISCOUNT = 4
_COL_TAX_CODE = 5
_COL_ACCOUNT = 6
_COL_LINE_TOTAL = 7
_COL_COUNT = 8

_HEADERS = ("#", "Description", "Qty", "Unit Price", "Disc %", "Tax Code", "Account", "Line Total")

# Ordered list of editable columns for arrow-key navigation
_EDITABLE_COLS = (_COL_DESCRIPTION, _COL_QTY, _COL_UNIT_PRICE, _COL_DISCOUNT, _COL_TAX_CODE, _COL_ACCOUNT)


class CustomerQuoteLinesGrid(QFrame):
    """Editable line-items grid for Customer Quotes.

    Public API:
        set_lines(lines)
        get_line_commands() -> list[CustomerQuoteLineCommand]
        calculate_totals() -> (subtotal, tax, total, line_count)
        lines_changed  — signal

    The revenue_account_id column is optional on quotes; lines may be
    submitted without an account mapping.
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
        self._accounts: list[tuple[int, str, str]] = []
        self._tax_codes: list[tuple[int, str, str]] = []
        self._tax_rates_by_id: dict[int, Decimal] = {}
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

        title = QLabel("Quote Lines", header_row)
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
        self._qty_delegate = NumericDelegate(decimals=2, parent=self._table)
        self._price_delegate = NumericDelegate(decimals=2, parent=self._table)
        self._discount_delegate = NumericDelegate(decimals=2, parent=self._table)
        self._tax_delegate = ComboBoxDelegate(placeholder="-- None --", parent=self._table)
        self._account_delegate = ComboBoxDelegate(placeholder="-- None (optional) --", parent=self._table)
        self._total_delegate = NumericDelegate(decimals=2, read_only=True, parent=self._table)

        self._table.setItemDelegateForColumn(_COL_ROW_NUM, self._row_num_delegate)
        self._table.setItemDelegateForColumn(_COL_QTY, self._qty_delegate)
        self._table.setItemDelegateForColumn(_COL_UNIT_PRICE, self._price_delegate)
        self._table.setItemDelegateForColumn(_COL_DISCOUNT, self._discount_delegate)
        self._table.setItemDelegateForColumn(_COL_TAX_CODE, self._tax_delegate)
        self._table.setItemDelegateForColumn(_COL_ACCOUNT, self._account_delegate)
        self._table.setItemDelegateForColumn(_COL_LINE_TOTAL, self._total_delegate)

        # ── Column widths ────────────────────────────────────────────
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)

        header.setSectionResizeMode(_COL_ROW_NUM, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_ROW_NUM, 32)

        header.setSectionResizeMode(_COL_DESCRIPTION, QHeaderView.ResizeMode.Stretch)

        header.setSectionResizeMode(_COL_QTY, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_QTY, 60)

        header.setSectionResizeMode(_COL_UNIT_PRICE, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_UNIT_PRICE, 90)

        header.setSectionResizeMode(_COL_DISCOUNT, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_DISCOUNT, 60)

        header.setSectionResizeMode(_COL_TAX_CODE, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_TAX_CODE, 130)

        header.setSectionResizeMode(_COL_ACCOUNT, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_ACCOUNT, 170)

        header.setSectionResizeMode(_COL_LINE_TOTAL, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_LINE_TOTAL, 100)

        layout.addWidget(self._table, 1)

        # ── Empty state overlay ──────────────────────────────────────
        self._empty_label = QLabel("No line items yet. Click Add Line to begin.", self._table)
        self._empty_label.setObjectName("LinesEmptyState")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
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
            accounts = self._service_registry.chart_of_accounts_service.list_accounts(
                self._company_id, active_only=True
            )
            self._accounts = [
                (a.id, a.account_code, a.account_name) for a in accounts if a.allow_manual_posting
            ]
        except Exception:
            _log.warning("Quote lines: failed to load accounts", exc_info=True)
            self._accounts = []

        try:
            tax_codes = self._service_registry.tax_setup_service.list_tax_codes(
                self._company_id, active_only=True
            )
            self._tax_codes = [(t.id, t.code, t.name) for t in tax_codes]
            self._tax_rates_by_id = {
                t.id: (t.rate_percent or Decimal("0.00")) for t in tax_codes
            }
        except Exception:
            _log.warning("Quote lines: failed to load tax codes", exc_info=True)
            self._tax_codes = []
            self._tax_rates_by_id = {}

        self._tax_delegate.set_items(
            [(f"{code} - {name}", tid) for tid, code, name in self._tax_codes]
        )
        self._account_delegate.set_items(
            [(f"{code} - {name}", aid) for aid, code, name in self._accounts]
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_lines(self, lines: tuple[CustomerQuoteLineDTO, ...]) -> None:
        self._updating = True
        try:
            self._model.removeRows(0, self._model.rowCount())
            for line in lines:
                self._append_row(
                    description=line.description,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    discount_percent=line.discount_percent,
                    tax_code_id=line.tax_code_id,
                    revenue_account_id=line.revenue_account_id,
                    line_total=line.line_total_amount,
                )
        finally:
            self._updating = False
        self._recalculate_all_totals()
        self._refresh_empty_state()

    def get_line_commands(self) -> list[CustomerQuoteLineCommand]:
        commands: list[CustomerQuoteLineCommand] = []
        for row in range(self._model.rowCount()):
            description = (self._model.data(self._model.index(row, _COL_DESCRIPTION)) or "").strip()
            if not description:
                continue

            quantity = self._get_decimal(row, _COL_QTY)
            unit_price = self._get_decimal(row, _COL_UNIT_PRICE)
            discount_percent = self._get_decimal(row, _COL_DISCOUNT)

            tax_code_id = self._model.data(
                self._model.index(row, _COL_TAX_CODE), Qt.ItemDataRole.UserRole
            )
            if not isinstance(tax_code_id, int) or tax_code_id <= 0:
                tax_code_id = None

            revenue_account_id = self._model.data(
                self._model.index(row, _COL_ACCOUNT), Qt.ItemDataRole.UserRole
            )
            if not isinstance(revenue_account_id, int) or revenue_account_id <= 0:
                revenue_account_id = None  # optional on quotes

            commands.append(
                CustomerQuoteLineCommand(
                    description=description,
                    quantity=quantity if quantity is not None else Decimal("1"),
                    unit_price=unit_price if unit_price is not None else Decimal("0"),
                    discount_percent=discount_percent,
                    tax_code_id=tax_code_id,
                    revenue_account_id=revenue_account_id,
                )
            )
        return commands

    def calculate_totals(self) -> tuple[Decimal, Decimal, Decimal, int]:
        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")
        total = Decimal("0.00")

        for row in range(self._model.rowCount()):
            row_sub, row_tax, row_total = self._calculate_row_amounts(row)
            subtotal += row_sub
            tax_total += row_tax
            total += row_total

        return (
            subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            tax_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            self._model.rowCount(),
        )

    # ------------------------------------------------------------------
    # Row manipulation
    # ------------------------------------------------------------------

    def _add_empty_row(self) -> None:
        self._append_row(
            description="",
            quantity=None,
            unit_price=None,
            discount_percent=None,
            tax_code_id=None,
            revenue_account_id=None,
            line_total=Decimal("0.00"),
        )
        self._refresh_empty_state()
        new_row = self._model.rowCount() - 1
        desc_index = self._model.index(new_row, _COL_DESCRIPTION)
        self._table.setCurrentIndex(desc_index)
        widget = self._table.indexWidget(desc_index)
        if widget is not None:
            widget.setFocus()
            if isinstance(widget, QLineEdit):
                widget.selectAll()

    def _append_row(
        self,
        description: str,
        quantity: Decimal | None,
        unit_price: Decimal | None,
        discount_percent: Decimal | None,
        tax_code_id: int | None,
        revenue_account_id: int | None,
        line_total: Decimal,
    ) -> None:
        was_updating = self._updating
        self._updating = True
        try:
            row_items: list[QStandardItem] = []

            num_item = QStandardItem()
            num_item.setEditable(False)
            row_items.append(num_item)

            desc_item = QStandardItem(description)
            row_items.append(desc_item)

            qty_item = QStandardItem()
            if quantity is not None:
                qty_item.setData(_format_number(quantity), Qt.ItemDataRole.DisplayRole)
                qty_item.setData(quantity, Qt.ItemDataRole.UserRole)
            row_items.append(qty_item)

            price_item = QStandardItem()
            if unit_price is not None:
                price_item.setData(_format_number(unit_price), Qt.ItemDataRole.DisplayRole)
                price_item.setData(unit_price, Qt.ItemDataRole.UserRole)
            row_items.append(price_item)

            disc_item = QStandardItem()
            if discount_percent is not None:
                disc_item.setData(_format_number(discount_percent), Qt.ItemDataRole.DisplayRole)
                disc_item.setData(discount_percent, Qt.ItemDataRole.UserRole)
            row_items.append(disc_item)

            tax_item = QStandardItem()
            if tax_code_id and tax_code_id > 0:
                display = self._tax_display(tax_code_id)
                tax_item.setData(display, Qt.ItemDataRole.DisplayRole)
                tax_item.setData(tax_code_id, Qt.ItemDataRole.UserRole)
            row_items.append(tax_item)

            acct_item = QStandardItem()
            if revenue_account_id and revenue_account_id > 0:
                display = self._account_display(revenue_account_id)
                acct_item.setData(display, Qt.ItemDataRole.DisplayRole)
                acct_item.setData(revenue_account_id, Qt.ItemDataRole.UserRole)
            row_items.append(acct_item)

            total_item = QStandardItem()
            total_item.setEditable(False)
            total_item.setData(_format_number(line_total), Qt.ItemDataRole.DisplayRole)
            total_item.setData(line_total, Qt.ItemDataRole.UserRole)
            row_items.append(total_item)

            self._model.appendRow(row_items)

            row_idx = self._model.rowCount() - 1
            self._open_row_editors(row_idx)
        finally:
            self._updating = was_updating

        if not was_updating:
            self._refresh_row_total(self._model.rowCount() - 1)
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
        raw = self._model.data(self._model.index(row, col), Qt.ItemDataRole.UserRole)
        if raw is None:
            return None
        if isinstance(raw, Decimal):
            return raw
        try:
            return Decimal(str(raw))
        except Exception:
            return None

    def _calculate_row_amounts(self, row: int) -> tuple[Decimal, Decimal, Decimal]:
        qty = self._get_decimal(row, _COL_QTY) or Decimal("0")
        price = self._get_decimal(row, _COL_UNIT_PRICE) or Decimal("0")
        disc = self._get_decimal(row, _COL_DISCOUNT) or Decimal("0")

        tax_code_id = self._model.data(
            self._model.index(row, _COL_TAX_CODE), Qt.ItemDataRole.UserRole
        )
        tax_rate = Decimal("0")
        if isinstance(tax_code_id, int) and tax_code_id > 0:
            tax_rate = self._tax_rates_by_id.get(tax_code_id, Decimal("0"))

        disc_factor = (Decimal("1") - disc / Decimal("100")).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
        subtotal = (qty * price * disc_factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = subtotal + tax
        return subtotal, tax, total

    def _refresh_row_total(self, row: int) -> None:
        _, _, total = self._calculate_row_amounts(row)
        total_item = self._model.item(row, _COL_LINE_TOTAL)
        if total_item is not None:
            total_item.setData(_format_number(total), Qt.ItemDataRole.DisplayRole)
            total_item.setData(total, Qt.ItemDataRole.UserRole)

    def _recalculate_all_totals(self) -> None:
        for row in range(self._model.rowCount()):
            self._refresh_row_total(row)
        self.lines_changed.emit()

    def _tax_display(self, tax_code_id: int) -> str:
        for tid, code, name in self._tax_codes:
            if tid == tax_code_id:
                return f"{code} - {name}"
        return str(tax_code_id)

    def _account_display(self, account_id: int) -> str:
        for aid, code, name in self._accounts:
            if aid == account_id:
                return f"{code} - {name}"
        return str(account_id)

    def _refresh_empty_state(self) -> None:
        has_rows = self._model.rowCount() > 0
        self._empty_label.setVisible(not has_rows)
        if not has_rows:
            self._empty_label.resize(self._table.size())

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_data_changed(self, top_left: QModelIndex, _bottom_right: QModelIndex) -> None:
        if self._updating:
            return
        row = top_left.row()
        col = top_left.column()
        if col in (_COL_QTY, _COL_UNIT_PRICE, _COL_DISCOUNT, _COL_TAX_CODE):
            self._refresh_row_total(row)
        self.lines_changed.emit()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not isinstance(event, QKeyEvent):
            return super().eventFilter(watched, event)

        key = event.key()

        if key == Qt.Key.Key_Tab or key == Qt.Key.Key_Backtab:
            index = self._table.currentIndex()
            if not index.isValid():
                return super().eventFilter(watched, event)
            row = index.row()
            col = index.column()
            editable = list(_EDITABLE_COLS)
            if col not in editable:
                return super().eventFilter(watched, event)
            pos = editable.index(col)
            if key == Qt.Key.Key_Tab:
                next_pos = pos + 1
                if next_pos >= len(editable):
                    if row + 1 < self._model.rowCount():
                        next_row = row + 1
                        next_col = editable[0]
                    else:
                        self._add_empty_row()
                        next_row = self._model.rowCount() - 1
                        next_col = editable[0]
                else:
                    next_row = row
                    next_col = editable[next_pos]
            else:
                next_pos = pos - 1
                if next_pos < 0:
                    next_row = max(0, row - 1)
                    next_col = editable[-1]
                else:
                    next_row = row
                    next_col = editable[next_pos]
            new_index = self._model.index(next_row, next_col)
            self._table.setCurrentIndex(new_index)
            widget = self._table.indexWidget(new_index)
            if widget is not None:
                widget.setFocus()
                if isinstance(widget, QLineEdit):
                    widget.selectAll()
            return True

        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._empty_label.isVisible():
            self._empty_label.resize(self._table.size())
