"""Contract customer advances tab panel + record advance dialog."""
from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
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
    CustomerAdvanceDTO,
    RecordCustomerAdvanceCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn, apply_status_chip_to_column
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.message_boxes import show_error


def _fmt_date(value: date | None) -> str:
    return "—" if value is None else value.isoformat()


def _humanize(code: str | None) -> str:
    if not code:
        return "—"
    return code.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------


class ContractCustomerAdvancesPanel(QWidget):
    """List panel for contract customer advances."""

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
        self._advances: tuple[CustomerAdvanceDTO, ...] = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        # Balance summary card
        self._balance_card = QFrame(self)
        self._balance_card.setObjectName("DialogSectionCard")
        self._balance_card.setProperty("card", True)
        balance_layout = QHBoxLayout(self._balance_card)
        balance_layout.setContentsMargins(18, 12, 18, 12)
        balance_layout.setSpacing(24)

        self._received_label = QLabel("Received: —", self._balance_card)
        self._received_label.setObjectName("MetricValue")
        self._unrecovered_label = QLabel("Unrecovered: —", self._balance_card)
        self._unrecovered_label.setObjectName("MetricValue")
        balance_layout.addWidget(self._received_label)
        balance_layout.addWidget(self._unrecovered_label)
        balance_layout.addStretch(1)
        layout.addWidget(self._balance_card)

        # List card
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(10)

        header = QHBoxLayout()
        title_lbl = QLabel("Customer Advances", card)
        title_lbl.setObjectName("DialogSectionTitle")
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._summary_label = QLabel("", card)
        self._summary_label.setObjectName("DialogSectionSummary")
        header.addWidget(self._summary_label)
        self._record_btn = QPushButton("Record Advance", card)
        self._record_btn.setProperty("variant", "primary")
        self._record_btn.clicked.connect(self._record_advance)
        header.addWidget(self._record_btn)
        card_layout.addLayout(header)

        self._model = QStandardItemModel(0, 6, card)
        self._table = DataTable(
            columns=(
                DataTableColumn(key="number", title="Advance #"),
                DataTableColumn(key="date", title="Date"),
                DataTableColumn(key="status", title="Status"),
                DataTableColumn(key="amount", title="Advance Amount", is_numeric=True),
                DataTableColumn(key="received", title="Received", is_numeric=True),
                DataTableColumn(key="recovery_pct", title="Recovery %", is_numeric=True),
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
            self._advances = self._service_registry.contract_progress_billing_service.list_customer_advances(
                self._company_id, self._contract_id
            )
        except Exception as exc:
            self._advances = ()
            show_error(self, "Customer Advances", f"Could not load customer advances.\n\n{exc}")
        self._populate_table()
        self._refresh_balance()

    def _populate_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        total_amount = Decimal("0.00")
        total_received = Decimal("0.00")
        for adv in self._advances:
            pct_str = "—" if adv.recovery_percent is None else f"{adv.recovery_percent:.2f}%"
            self._model.appendRow([
                self._make_item(adv.advance_number, user_data=adv.id),
                self._make_item(_fmt_date(adv.advance_date)),
                self._make_item(adv.status_code),
                self._make_item(f"{adv.advance_amount:,.2f}"),
                self._make_item(f"{adv.received_amount:,.2f}"),
                self._make_item(pct_str),
            ])
            total_amount += adv.advance_amount
            total_received += adv.received_amount
        count = len(self._advances)
        self._summary_label.setText(
            f"{count} advance{'s' if count != 1 else ''} | Total: {total_amount:,.2f}"
        )

    def _refresh_balance(self) -> None:
        try:
            balance = self._service_registry.contract_progress_billing_service.get_advance_balance(
                self._company_id, self._contract_id
            )
            self._received_label.setText(f"Received: {balance.received_advance_amount:,.2f}")
            self._unrecovered_label.setText(f"Unrecovered: {balance.unrecovered_advance_amount:,.2f}")
        except Exception:
            self._received_label.setText("Received: —")
            self._unrecovered_label.setText("Unrecovered: —")

    def _record_advance(self) -> None:
        dialog = RecordCustomerAdvanceDialog(
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
# Record customer advance dialog
# ---------------------------------------------------------------------------


class RecordCustomerAdvanceDialog(QDialog):
    """Form dialog for recording a customer advance payment."""

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
        self.setWindowTitle("Record Customer Advance")
        self.setModal(True)
        apply_window_size(self, "modules.contracts.projects.ui.contract.customer.advances.panel.0")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        ref_card = QFrame(self)
        ref_card.setObjectName("DialogSectionCard")
        ref_layout = QGridLayout(ref_card)
        ref_layout.setContentsMargins(16, 14, 16, 14)
        ref_layout.setSpacing(10)

        self._advance_number_edit = QLineEdit(self)
        self._advance_number_edit.setPlaceholderText("e.g. ADV-001")

        self._advance_date_edit = QDateEdit(self)
        self._advance_date_edit.setCalendarPopup(True)
        self._advance_date_edit.setDisplayFormat("yyyy-MM-dd")
        from PySide6.QtCore import QDate
        self._advance_date_edit.setDate(QDate.currentDate())

        ref_layout.addWidget(create_field_block("Advance Number *", self._advance_number_edit), 0, 0)
        ref_layout.addWidget(create_field_block("Advance Date *", self._advance_date_edit), 0, 1)
        layout.addWidget(ref_card)

        amounts_card = QFrame(self)
        amounts_card.setObjectName("DialogSectionCard")
        amounts_layout = QGridLayout(amounts_card)
        amounts_layout.setContentsMargins(16, 14, 16, 14)
        amounts_layout.setSpacing(10)

        amounts_title = QLabel("Amounts & Recovery", amounts_card)
        amounts_title.setObjectName("DialogSectionTitle")
        amounts_layout.addWidget(amounts_title, 0, 0, 1, 2)

        self._advance_amount_edit = QLineEdit(self)
        self._advance_amount_edit.setPlaceholderText("0.00")

        self._received_amount_edit = QLineEdit(self)
        self._received_amount_edit.setPlaceholderText("0.00  — amount actually received")

        self._recovery_basis_edit = QLineEdit(self)
        self._recovery_basis_edit.setPlaceholderText("e.g. per_claim  (optional)")

        self._recovery_pct_edit = QLineEdit(self)
        self._recovery_pct_edit.setPlaceholderText("0.00  (optional)")

        amounts_layout.addWidget(create_field_block("Advance Amount *", self._advance_amount_edit), 1, 0)
        amounts_layout.addWidget(create_field_block("Received Amount *", self._received_amount_edit), 1, 1)
        amounts_layout.addWidget(create_field_block("Recovery Basis", self._recovery_basis_edit), 2, 0)
        amounts_layout.addWidget(create_field_block("Recovery %", self._recovery_pct_edit), 2, 1)
        layout.addWidget(amounts_card)

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
            save_btn.setText("Record Advance")
            save_btn.setProperty("variant", "primary")
        button_box.accepted.connect(self._handle_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _handle_save(self) -> None:
        self._error_label.hide()
        advance_number = self._advance_number_edit.text().strip()
        if not advance_number:
            self._show_error("Advance number is required.")
            return

        from PySide6.QtCore import QDate
        qd = self._advance_date_edit.date()
        advance_date = date(qd.year(), qd.month(), qd.day())

        try:
            advance_amount = Decimal(self._advance_amount_edit.text().replace(",", "").strip())
            received_amount = Decimal(self._received_amount_edit.text().replace(",", "").strip())
        except (InvalidOperation, ValueError):
            self._show_error("Advance amount and received amount must be numeric.")
            return

        recovery_basis = self._recovery_basis_edit.text().strip() or None
        recovery_pct: Decimal | None = None
        pct_text = self._recovery_pct_edit.text().strip()
        if pct_text:
            try:
                recovery_pct = Decimal(pct_text.replace(",", ""))
            except InvalidOperation:
                self._show_error("Recovery % must be numeric.")
                return

        notes = self._notes_edit.toPlainText().strip() or None

        command = RecordCustomerAdvanceCommand(
            contract_id=self._contract_id,
            advance_number=advance_number,
            advance_date=advance_date,
            advance_amount=advance_amount,
            received_amount=received_amount,
            recovery_basis_code=recovery_basis,
            recovery_percent=recovery_pct,
            notes=notes,
        )
        try:
            self._service_registry.contract_progress_billing_service.record_customer_advance(
                self._company_id, command
            )
        except (ValidationError, ConflictError, NotFoundError) as exc:
            self._show_error(str(exc))
            return
        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()
