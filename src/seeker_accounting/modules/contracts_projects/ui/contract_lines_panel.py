"""Contract lines (schedule of values) tab panel + batch editor dialog."""
from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.contracts_projects.dto.contract_commercial_dto import (
    ContractLineCommand,
    ContractLineDTO,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn
from seeker_accounting.shared.ui.message_boxes import show_error

_BILLING_BASIS_OPTIONS: list[tuple[str, str]] = [
    ("milestone", "Milestone"),
    ("progress", "Progress %"),
    ("time_and_material", "Time & Material"),
    ("fixed_schedule", "Fixed Schedule"),
    ("manual", "Manual"),
]


def _humanize(code: str | None) -> str:
    if not code:
        return "—"
    return code.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Panel (tab widget)
# ---------------------------------------------------------------------------


class ContractLinesPanel(QWidget):
    """Read-only list panel for contract schedule-of-values lines."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        contract_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._contract_id = contract_id
        self._lines: tuple[ContractLineDTO, ...] = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(10)

        header = QHBoxLayout()
        title_lbl = QLabel("Schedule of Values", card)
        title_lbl.setObjectName("DialogSectionTitle")
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._summary_label = QLabel("", card)
        self._summary_label.setObjectName("DialogSectionSummary")
        header.addWidget(self._summary_label)
        self._edit_btn = QPushButton("Edit Lines", card)
        self._edit_btn.setProperty("variant", "primary")
        self._edit_btn.clicked.connect(self._open_editor)
        header.addWidget(self._edit_btn)
        card_layout.addLayout(header)

        self._model = QStandardItemModel(0, 6, card)
        self._table = DataTable(
            columns=(
                DataTableColumn(key="num", title="#"),
                DataTableColumn(key="description", title="Description"),
                DataTableColumn(key="qty", title="Qty", is_numeric=True),
                DataTableColumn(key="rate", title="Unit Rate", is_numeric=True),
                DataTableColumn(key="amount", title="Amount", is_numeric=True),
                DataTableColumn(key="basis", title="Billing Basis"),
            ),
            show_search=False,
            show_count=True,
            show_density_toggle=False,
            show_column_chooser=False,
            selection_mode="single",
            parent=card,
        )
        self._table.set_model(self._model)
        card_layout.addWidget(self._table, 1)
        layout.addWidget(card, 1)

    def reload(self) -> None:
        try:
            self._lines = self._service_registry.contract_commercial_service.list_contract_lines(
                self._company_id, self._contract_id
            )
        except Exception as exc:
            self._lines = ()
            show_error(self, "Contract Lines", f"Could not load contract lines.\n\n{exc}")
        self._populate_table()

    def _populate_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        total = Decimal("0.00")
        for line in self._lines:
            self._model.appendRow([
                self._make_item(str(line.line_number), user_data=line.id),
                self._make_item(line.description),
                self._make_item(f"{line.quantity:,.4f}"),
                self._make_item(f"{line.unit_rate:,.2f}"),
                self._make_item(f"{line.line_amount:,.2f}"),
                self._make_item(_humanize(line.billing_basis_code)),
            ])
            total += line.line_amount
        count = len(self._lines)
        self._summary_label.setText(
            f"{count} line{'s' if count != 1 else ''} | Total: {total:,.2f}"
        )

    def _open_editor(self) -> None:
        dialog = ContractLinesEditorDialog(
            self._service_registry,
            self._company_id,
            self._contract_id,
            self._lines,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    @staticmethod
    def _make_item(text: object, *, user_data: object = None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item


# ---------------------------------------------------------------------------
# Batch editor dialog
# ---------------------------------------------------------------------------


class ContractLinesEditorDialog(QDialog):
    """Inline table editor for creating/replacing all contract lines."""

    _COL_DESCRIPTION = 0
    _COL_QTY = 1
    _COL_RATE = 2
    _COL_AMOUNT = 3
    _COL_BASIS = 4
    _COL_NOTES = 5
    _COLS = 6

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        contract_id: int,
        current_lines: tuple[ContractLineDTO, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._contract_id = contract_id
        self.setWindowTitle("Edit Contract Lines")
        self.setModal(True)
        apply_window_size(self, "modules.contracts.projects.ui.contract.lines.panel.0")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        intro = QLabel(
            "Add, remove, or edit lines. All changes are applied together when you save.",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._table = QTableWidget(0, self._COLS, self)
        self._table.setHorizontalHeaderLabels(
            ["Description *", "Qty *", "Unit Rate *", "Amount", "Billing Basis", "Notes"]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            self._COL_DESCRIPTION, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            self._COL_NOTES, QHeaderView.ResizeMode.Stretch
        )
        for col in (self._COL_QTY, self._COL_RATE, self._COL_AMOUNT, self._COL_BASIS):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.itemChanged.connect(self._recalc_row_amount)
        layout.addWidget(self._table, 1)

        toolbar = QHBoxLayout()
        add_btn = QPushButton("Add Line", self)
        add_btn.clicked.connect(self._add_row)
        toolbar.addWidget(add_btn)
        remove_btn = QPushButton("Remove Selected", self)
        remove_btn.clicked.connect(self._remove_selected)
        toolbar.addWidget(remove_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        save_btn = button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn is not None:
            save_btn.setProperty("variant", "primary")
        button_box.accepted.connect(self._handle_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._table.blockSignals(True)
        for line in current_lines:
            self._append_row(
                description=line.description,
                qty=str(line.quantity),
                rate=str(line.unit_rate),
                basis_code=line.billing_basis_code,
                notes=line.notes or "",
            )
        self._table.blockSignals(False)
        if not current_lines:
            self._add_row()

    def _append_row(
        self,
        description: str = "",
        qty: str = "1.0000",
        rate: str = "0.00",
        basis_code: str = "milestone",
        notes: str = "",
    ) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, self._COL_DESCRIPTION, QTableWidgetItem(description))
        self._table.setItem(row, self._COL_QTY, QTableWidgetItem(qty))
        self._table.setItem(row, self._COL_RATE, QTableWidgetItem(rate))

        amount_item = QTableWidgetItem(self._calc_amount(qty, rate))
        amount_item.setFlags(amount_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(row, self._COL_AMOUNT, amount_item)

        combo = QComboBox(self._table)
        for code, label in _BILLING_BASIS_OPTIONS:
            combo.addItem(label, code)
        idx = next((i for i, (c, _) in enumerate(_BILLING_BASIS_OPTIONS) if c == basis_code), 0)
        combo.setCurrentIndex(idx)
        self._table.setCellWidget(row, self._COL_BASIS, combo)

        self._table.setItem(row, self._COL_NOTES, QTableWidgetItem(notes))

    def _add_row(self) -> None:
        self._append_row()

    def _remove_selected(self) -> None:
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()}, reverse=True)
        for row in rows:
            self._table.removeRow(row)

    def _recalc_row_amount(self, item: QTableWidgetItem) -> None:
        if item.column() not in (self._COL_QTY, self._COL_RATE):
            return
        row = item.row()
        qty_item = self._table.item(row, self._COL_QTY)
        rate_item = self._table.item(row, self._COL_RATE)
        amount_item = self._table.item(row, self._COL_AMOUNT)
        if qty_item is None or rate_item is None or amount_item is None:
            return
        self._table.blockSignals(True)
        amount_item.setText(self._calc_amount(qty_item.text(), rate_item.text()))
        self._table.blockSignals(False)

    @staticmethod
    def _calc_amount(qty_str: str, rate_str: str) -> str:
        try:
            qty = Decimal(qty_str.replace(",", ""))
            rate = Decimal(rate_str.replace(",", ""))
            return f"{(qty * rate).quantize(Decimal('0.00')):,.2f}"
        except (InvalidOperation, ValueError):
            return "0.00"

    def _build_commands(self) -> tuple[ContractLineCommand, ...] | None:
        commands: list[ContractLineCommand] = []
        for row in range(self._table.rowCount()):
            desc_item = self._table.item(row, self._COL_DESCRIPTION)
            qty_item = self._table.item(row, self._COL_QTY)
            rate_item = self._table.item(row, self._COL_RATE)
            notes_item = self._table.item(row, self._COL_NOTES)
            combo: QComboBox | None = self._table.cellWidget(row, self._COL_BASIS)  # type: ignore[assignment]

            description = (desc_item.text() if desc_item else "").strip()
            qty_str = (qty_item.text() if qty_item else "1").strip()
            rate_str = (rate_item.text() if rate_item else "0").strip()
            notes = (notes_item.text() if notes_item else "").strip()
            basis_code = combo.currentData() if combo else "milestone"

            if not description:
                self._show_error(f"Row {row + 1}: Description is required.")
                return None
            try:
                qty = Decimal(qty_str.replace(",", ""))
                rate = Decimal(rate_str.replace(",", ""))
            except InvalidOperation:
                self._show_error(f"Row {row + 1}: Quantity and Unit Rate must be numeric.")
                return None
            if qty <= 0:
                self._show_error(f"Row {row + 1}: Quantity must be greater than zero.")
                return None

            commands.append(
                ContractLineCommand(
                    description=description,
                    quantity=qty,
                    unit_rate=rate,
                    billing_basis_code=basis_code,
                    notes=notes or None,
                )
            )
        return tuple(commands)

    def _handle_save(self) -> None:
        self._error_label.hide()
        commands = self._build_commands()
        if commands is None:
            return
        try:
            self._service_registry.contract_commercial_service.replace_contract_lines(
                self._company_id, self._contract_id, commands
            )
        except (ValidationError, NotFoundError) as exc:
            self._show_error(str(exc))
            return
        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()
