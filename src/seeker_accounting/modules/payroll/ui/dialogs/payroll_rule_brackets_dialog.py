from __future__ import annotations

import logging

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_rule_dto import (
    DeletePayrollRuleBracketCommand,
    PayrollRuleBracketDTO,
    UpsertPayrollRuleBracketCommand,
)
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)


_COL_LINE = 0
_COL_LOWER = 1
_COL_UPPER = 2
_COL_RATE = 3
_COL_FIXED = 4
_COL_DEDUCTION = 5
_COL_CAP = 6

_HEADERS = [
    "Line #",
    "Lower Bound",
    "Upper Bound",
    "Rate %",
    "Fixed Amt",
    "Deduction Amt",
    "Cap Amt",
]


def _dec(value: Decimal | None) -> str:
    if value is None:
        return ""
    return str(value)


def _parse_dec(text: str) -> Decimal | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return Decimal(stripped)
    except InvalidOperation:
        raise ValueError(f"Invalid decimal value: {stripped!r}")


class _BracketLineDialog(QDialog):
    """Modal sub-dialog for adding or editing a single bracket line."""

    def __init__(
        self,
        line_number: int | None = None,
        bracket: PayrollRuleBracketDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        is_edit = bracket is not None
        self.setWindowTitle("Edit Bracket Line" if is_edit else "Add Bracket Line")
        self.setModal(True)
        self.resize(400, 340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        card = QFrame(self)
        card.setObjectName("PageCard")
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        hdr = QLabel("Bracket Line", card)
        hdr.setObjectName("CardTitle")
        form.addRow(hdr)

        self._line_input = QLineEdit(card)
        self._line_input.setPlaceholderText("e.g. 1")
        if is_edit:
            self._line_input.setText(str(bracket.line_number))
            self._line_input.setEnabled(False)
        elif line_number is not None:
            self._line_input.setText(str(line_number))
        form.addRow("Line Number *", self._line_input)

        self._lower_input = QLineEdit(card)
        self._lower_input.setPlaceholderText("0.00 (blank = 0)")
        form.addRow("Lower Bound", self._lower_input)

        self._upper_input = QLineEdit(card)
        self._upper_input.setPlaceholderText("blank = no ceiling")
        form.addRow("Upper Bound", self._upper_input)

        self._rate_input = QLineEdit(card)
        self._rate_input.setPlaceholderText("e.g. 10.00")
        form.addRow("Rate %", self._rate_input)

        self._fixed_input = QLineEdit(card)
        self._fixed_input.setPlaceholderText("blank = none")
        form.addRow("Fixed Amount", self._fixed_input)

        self._deduction_input = QLineEdit(card)
        self._deduction_input.setPlaceholderText("blank = none")
        form.addRow("Deduction Amount", self._deduction_input)

        self._cap_input = QLineEdit(card)
        self._cap_input.setPlaceholderText("blank = no cap")
        form.addRow("Cap Amount", self._cap_input)

        layout.addWidget(card)

        if is_edit and bracket is not None:
            self._lower_input.setText(_dec(bracket.lower_bound_amount))
            self._upper_input.setText(_dec(bracket.upper_bound_amount))
            self._rate_input.setText(_dec(bracket.rate_percent))
            self._fixed_input.setText(_dec(bracket.fixed_amount))
            self._deduction_input.setText(_dec(bracket.deduction_amount))
            self._cap_input.setText(_dec(bracket.cap_amount))

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.result_command: UpsertPayrollRuleBracketCommand | None = None

    def _validate_and_accept(self) -> None:
        self._error_label.hide()
        line_text = self._line_input.text().strip()
        if not line_text.isdigit() or int(line_text) < 1:
            self._error_label.setText("Line number must be a positive integer.")
            self._error_label.show()
            return

        try:
            lower = _parse_dec(self._lower_input.text())
            upper = _parse_dec(self._upper_input.text())
            rate = _parse_dec(self._rate_input.text())
            fixed = _parse_dec(self._fixed_input.text())
            deduction = _parse_dec(self._deduction_input.text())
            cap = _parse_dec(self._cap_input.text())
        except ValueError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return

        if upper is not None and lower is not None and upper <= lower:
            self._error_label.setText("Upper bound must be greater than lower bound.")
            self._error_label.show()
            return

        self.result_command = UpsertPayrollRuleBracketCommand(
            line_number=int(line_text),
            lower_bound_amount=lower,
            upper_bound_amount=upper,
            rate_percent=rate,
            fixed_amount=fixed,
            deduction_amount=deduction,
            cap_amount=cap,
        )
        self.accept()


class PayrollRuleBracketsDialog(QDialog):
    """Dialog for viewing and editing all bracket lines of a payroll rule set."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        rule_set_id: int,
        rule_code: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sr = service_registry
        self._company_id = company_id
        self._rule_set_id = rule_set_id

        self.setWindowTitle(f"Brackets — {rule_code}")
        self.setModal(True)
        self.resize(760, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        title_label = QLabel(f"Rule Set: <b>{rule_code}</b>", self)
        header_row.addWidget(title_label)
        header_row.addStretch()
        layout.addLayout(header_row)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        self._add_btn = QPushButton("Add Bracket", self)
        self._add_btn.setObjectName("PrimaryButton")
        self._add_btn.clicked.connect(self._on_add)
        toolbar.addWidget(self._add_btn)

        self._edit_btn = QPushButton("Edit", self)
        self._edit_btn.clicked.connect(self._on_edit)
        toolbar.addWidget(self._edit_btn)

        self._delete_btn = QPushButton("Delete", self)
        self._delete_btn.setObjectName("DangerButton")
        self._delete_btn.clicked.connect(self._on_delete)
        toolbar.addWidget(self._delete_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ── Table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget(self)
        self._table.setColumnCount(len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(lambda _: self._on_edit())
        configure_compact_table(self._table)
        layout.addWidget(self._table, 1)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        close_buttons.rejected.connect(self.accept)
        layout.addWidget(close_buttons)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payroll_rule_brackets", dialog=True)

        self._reload()

    # ── Data ──────────────────────────────────────────────────────────────────

    def _reload(self) -> None:
        self._error_label.hide()
        try:
            rs = self._sr.payroll_rule_service.get_rule_set(self._company_id, self._rule_set_id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        self._populate(rs.brackets)

    def _populate(self, brackets: tuple[PayrollRuleBracketDTO, ...]) -> None:
        self._table.setRowCount(0)
        sorted_brackets = sorted(brackets, key=lambda b: b.line_number)
        for row_idx, b in enumerate(sorted_brackets):
            self._table.insertRow(row_idx)
            self._set_cell(row_idx, _COL_LINE, str(b.line_number), b.line_number)
            self._set_cell(row_idx, _COL_LOWER, _dec(b.lower_bound_amount), align_right=True)
            self._set_cell(row_idx, _COL_UPPER, _dec(b.upper_bound_amount), align_right=True)
            self._set_cell(row_idx, _COL_RATE, _dec(b.rate_percent), align_right=True)
            self._set_cell(row_idx, _COL_FIXED, _dec(b.fixed_amount), align_right=True)
            self._set_cell(row_idx, _COL_DEDUCTION, _dec(b.deduction_amount), align_right=True)
            self._set_cell(row_idx, _COL_CAP, _dec(b.cap_amount), align_right=True)

    def _set_cell(
        self,
        row: int,
        col: int,
        text: str,
        user_data: object = None,
        align_right: bool = False,
    ) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if user_data is not None:
            item.setData(Qt.ItemDataRole.UserRole, user_data)
        if align_right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, col, item)

    def _selected_line_number(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, _COL_LINE)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return int(data) if data is not None else None

    def _selected_bracket(self) -> PayrollRuleBracketDTO | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        try:
            rs = self._sr.payroll_rule_service.get_rule_set(self._company_id, self._rule_set_id)
        except Exception:
            return None
        line_number = self._selected_line_number()
        if line_number is None:
            return None
        for b in rs.brackets:
            if b.line_number == line_number:
                return b
        return None

    def _next_line_number(self) -> int:
        max_line = 0
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_LINE)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data is not None:
                    max_line = max(max_line, int(data))
        return max_line + 1

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        self._error_label.hide()
        next_line = self._next_line_number()
        sub = _BracketLineDialog(line_number=next_line, parent=self)
        if sub.exec() != QDialog.DialogCode.Accepted or sub.result_command is None:
            return
        try:
            self._sr.payroll_rule_service.upsert_bracket(
                self._company_id, self._rule_set_id, sub.result_command
            )
        except (ValidationError, Exception) as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        self._reload()

    def _on_edit(self) -> None:
        self._error_label.hide()
        bracket = self._selected_bracket()
        if bracket is None:
            return
        sub = _BracketLineDialog(bracket=bracket, parent=self)
        if sub.exec() != QDialog.DialogCode.Accepted or sub.result_command is None:
            return
        try:
            self._sr.payroll_rule_service.upsert_bracket(
                self._company_id, self._rule_set_id, sub.result_command
            )
        except (ValidationError, Exception) as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        self._reload()

    def _on_delete(self) -> None:
        self._error_label.hide()
        line_number = self._selected_line_number()
        if line_number is None:
            return
        try:
            self._sr.payroll_rule_service.delete_bracket(
                self._company_id,
                self._rule_set_id,
                DeletePayrollRuleBracketCommand(line_number=line_number),
            )
        except (ValidationError, Exception) as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        self._reload()
