"""Contract retention movements tab panel + release retention dialog."""
from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.contracts_projects.dto.contract_progress_billing_dto import (
    ReleaseRetentionCommand,
    RetentionMovementDTO,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn, apply_status_chip_to_column
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.message_boxes import show_error

_RELEASE_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("partial_release", "Partial Release"),
    ("final_release", "Final Release"),
    ("write_off", "Write-Off"),
]


def _fmt_date(value: date | None) -> str:
    return "—" if value is None else value.isoformat()


def _humanize(code: str | None) -> str:
    if not code:
        return "—"
    return code.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------


class ContractRetentionPanel(QWidget):
    """List panel for contract retention movements."""

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
        self._movements: tuple[RetentionMovementDTO, ...] = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        # Balance card
        self._balance_card = QFrame(self)
        self._balance_card.setObjectName("DialogSectionCard")
        self._balance_card.setProperty("card", True)
        balance_layout = QHBoxLayout(self._balance_card)
        balance_layout.setContentsMargins(18, 12, 18, 12)
        balance_layout.setSpacing(24)
        self._balance_label = QLabel("Open Retention Balance: —", self._balance_card)
        self._balance_label.setObjectName("MetricValue")
        balance_layout.addWidget(self._balance_label)
        balance_layout.addStretch(1)
        layout.addWidget(self._balance_card)

        # Movements list card
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(10)

        header = QHBoxLayout()
        title_lbl = QLabel("Retention Movements", card)
        title_lbl.setObjectName("DialogSectionTitle")
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._summary_label = QLabel("", card)
        self._summary_label.setObjectName("DialogSectionSummary")
        header.addWidget(self._summary_label)
        self._release_btn = QPushButton("Release Retention", card)
        self._release_btn.setProperty("variant", "primary")
        self._release_btn.clicked.connect(self._release_retention)
        header.addWidget(self._release_btn)
        card_layout.addLayout(header)

        self._model = QStandardItemModel(0, 6, card)
        self._table = DataTable(
            columns=(
                DataTableColumn(key="date", title="Date"),
                DataTableColumn(key="type", title="Type"),
                DataTableColumn(key="status", title="Status"),
                DataTableColumn(key="amount", title="Amount", is_numeric=True),
                DataTableColumn(key="due_date", title="Due Date"),
                DataTableColumn(key="notes", title="Notes"),
            ),
            show_search=False,
            show_count=True,
            show_density_toggle=False,
            show_column_chooser=False,
            selection_mode="single",
            parent=card,
        )
        self._table.set_model(self._model)
        self._status_delegate = apply_status_chip_to_column(self._table.view(), 2)
        card_layout.addWidget(self._table, 1)
        layout.addWidget(card, 1)

    def reload(self) -> None:
        try:
            self._movements = self._service_registry.contract_progress_billing_service.list_retention_movements(
                self._company_id, self._contract_id
            )
        except Exception as exc:
            self._movements = ()
            show_error(self, "Retention Movements", f"Could not load retention movements.\n\n{exc}")
        self._populate_table()
        self._refresh_balance()

    def _populate_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        held = Decimal("0.00")
        released = Decimal("0.00")
        for mv in self._movements:
            self._model.appendRow([
                self._make_item(_fmt_date(mv.movement_date), user_data=mv.id),
                self._make_item(_humanize(mv.movement_type_code)),
                self._make_item(mv.status_code),
                self._make_item(f"{mv.amount:,.2f}"),
                self._make_item(_fmt_date(mv.due_date)),
                self._make_item(mv.notes or ""),
            ])
            if mv.movement_type_code in {"partial_release", "final_release", "write_off"}:
                released += mv.amount
            else:
                held += mv.amount
        count = len(self._movements)
        self._summary_label.setText(
            f"{count} movement{'s' if count != 1 else ''} | "
            f"Held: {held:,.2f} | Released: {released:,.2f}"
        )

    def _refresh_balance(self) -> None:
        try:
            balance = self._service_registry.contract_progress_billing_service.get_retention_balance(
                self._company_id, self._contract_id
            )
            self._balance_label.setText(
                f"Open Retention Balance: {balance.open_retention_amount:,.2f}"
            )
        except Exception:
            self._balance_label.setText("Open Retention Balance: —")

    def _release_retention(self) -> None:
        dialog = ReleaseRetentionDialog(
            self._service_registry,
            self._company_id,
            self._contract_id,
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
# Release retention dialog
# ---------------------------------------------------------------------------


class ReleaseRetentionDialog(QDialog):
    """Form dialog for recording a retention release."""

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
        self.setWindowTitle("Release Retention")
        self.setModal(True)
        apply_window_size(self, "modules.contracts.projects.ui.contract.retention.panel.0")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        form_card = QFrame(self)
        form_card.setObjectName("DialogSectionCard")
        form_layout = QGridLayout(form_card)
        form_layout.setContentsMargins(16, 14, 16, 14)
        form_layout.setSpacing(10)

        self._movement_date_edit = QDateEdit(self)
        self._movement_date_edit.setCalendarPopup(True)
        self._movement_date_edit.setDisplayFormat("yyyy-MM-dd")
        from PySide6.QtCore import QDate
        self._movement_date_edit.setDate(QDate.currentDate())

        self._type_combo = QComboBox(self)
        for code, label in _RELEASE_TYPE_OPTIONS:
            self._type_combo.addItem(label, code)

        self._amount_edit = QLineEdit(self)
        self._amount_edit.setPlaceholderText("0.00")

        form_layout.addWidget(create_field_block("Release Date *", self._movement_date_edit), 0, 0)
        form_layout.addWidget(create_field_block("Release Type *", self._type_combo), 0, 1)
        form_layout.addWidget(create_field_block("Amount *", self._amount_edit), 1, 0)
        layout.addWidget(form_card)

        notes_card = QFrame(self)
        notes_card.setObjectName("DialogSectionCard")
        notes_layout = QVBoxLayout(notes_card)
        notes_layout.setContentsMargins(16, 14, 16, 14)
        notes_layout.setSpacing(8)
        notes_label = QLabel("Notes", notes_card)
        notes_label.setObjectName("DialogSectionTitle")
        notes_layout.addWidget(notes_label)
        self._notes_edit = QPlainTextEdit(notes_card)
        self._notes_edit.setMaximumHeight(70)
        notes_layout.addWidget(self._notes_edit)
        layout.addWidget(notes_card)

        layout.addStretch(1)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        save_btn = button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn is not None:
            save_btn.setText("Release")
            save_btn.setProperty("variant", "primary")
        button_box.accepted.connect(self._handle_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _handle_save(self) -> None:
        self._error_label.hide()
        from PySide6.QtCore import QDate
        qd = self._movement_date_edit.date()
        movement_date = date(qd.year(), qd.month(), qd.day())

        amount_text = self._amount_edit.text().strip()
        if not amount_text:
            self._show_error("Amount is required.")
            return
        try:
            amount = Decimal(amount_text.replace(",", ""))
        except InvalidOperation:
            self._show_error("Amount must be numeric.")
            return

        movement_type_code = self._type_combo.currentData()
        notes = self._notes_edit.toPlainText().strip() or None

        command = ReleaseRetentionCommand(
            contract_id=self._contract_id,
            movement_date=movement_date,
            amount=amount,
            movement_type_code=movement_type_code,
            notes=notes,
        )
        try:
            self._service_registry.contract_progress_billing_service.release_retention(
                self._company_id, command
            )
        except (ValidationError, ConflictError, NotFoundError) as exc:
            self._show_error(str(exc))
            return
        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()
