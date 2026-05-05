"""Contract receipt allocations tab panel + record allocation dialog."""
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
    ReceiptAllocationDTO,
    RecordContractReceiptAllocationCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.message_boxes import show_error


def _fmt_date(value: date | None) -> str:
    return "—" if value is None else value.isoformat()


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------


class ContractReceiptAllocationsPanel(QWidget):
    """List panel for contract receipt allocations."""

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
        self._allocations: tuple[ReceiptAllocationDTO, ...] = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        # Summary card
        self._summary_card = QFrame(self)
        self._summary_card.setObjectName("DialogSectionCard")
        self._summary_card.setProperty("card", True)
        summary_layout = QHBoxLayout(self._summary_card)
        summary_layout.setContentsMargins(18, 12, 18, 12)
        summary_layout.setSpacing(24)
        self._collected_label = QLabel("Total Collected: —", self._summary_card)
        self._collected_label.setObjectName("MetricValue")
        summary_layout.addWidget(self._collected_label)
        summary_layout.addStretch(1)
        layout.addWidget(self._summary_card)

        # List card
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(10)

        header = QHBoxLayout()
        title_lbl = QLabel("Receipt Allocations", card)
        title_lbl.setObjectName("DialogSectionTitle")
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._count_label = QLabel("", card)
        self._count_label.setObjectName("DialogSectionSummary")
        header.addWidget(self._count_label)
        self._record_btn = QPushButton("Record Allocation", card)
        self._record_btn.setProperty("variant", "primary")
        self._record_btn.clicked.connect(self._record_allocation)
        header.addWidget(self._record_btn)
        card_layout.addLayout(header)

        self._model = QStandardItemModel(0, 8, card)
        self._table = DataTable(
            columns=(
                DataTableColumn(key="date", title="Date"),
                DataTableColumn(key="gross", title="Gross", is_numeric=True),
                DataTableColumn(key="net", title="Net Receivable", is_numeric=True),
                DataTableColumn(key="whtvat", title="WHT VAT", is_numeric=True),
                DataTableColumn(key="whttax", title="WHT Tax", is_numeric=True),
                DataTableColumn(key="retention", title="Retention", is_numeric=True),
                DataTableColumn(key="advance", title="Advance Rec.", is_numeric=True),
                DataTableColumn(key="total", title="Total Allocated", is_numeric=True),
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
            self._allocations = self._service_registry.contract_progress_billing_service.list_receipt_allocations(
                self._company_id, self._contract_id
            )
        except Exception as exc:
            self._allocations = ()
            show_error(self, "Receipt Allocations", f"Could not load receipt allocations.\n\n{exc}")
        self._populate_table()

    def _populate_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        total_collected = Decimal("0.00")
        for alloc in self._allocations:
            self._model.appendRow([
                self._make_item(_fmt_date(alloc.allocation_date), user_data=alloc.id),
                self._make_item(f"{alloc.gross_amount:,.2f}"),
                self._make_item(f"{alloc.net_receivable_amount:,.2f}"),
                self._make_item(f"{alloc.withholding_vat_amount:,.2f}"),
                self._make_item(f"{alloc.withholding_tax_amount:,.2f}"),
                self._make_item(f"{alloc.retention_amount:,.2f}"),
                self._make_item(f"{alloc.advance_recovery_amount:,.2f}"),
                self._make_item(f"{alloc.total_allocated_amount:,.2f}"),
            ])
            total_collected += alloc.total_allocated_amount
        count = len(self._allocations)
        self._count_label.setText(f"{count} allocation{'s' if count != 1 else ''}")
        self._collected_label.setText(f"Total Collected: {total_collected:,.2f}")

    def _record_allocation(self) -> None:
        dialog = RecordReceiptAllocationDialog(
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
# Record receipt allocation dialog
# ---------------------------------------------------------------------------


class RecordReceiptAllocationDialog(QDialog):
    """Form dialog for recording a contract receipt allocation breakdown."""

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
        self.setWindowTitle("Record Receipt Allocation")
        self.setModal(True)
        apply_window_size(self, "modules.contracts.projects.ui.contract.receipt.allocations.panel.0")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        header_card = QFrame(self)
        header_card.setObjectName("DialogSectionCard")
        header_layout = QGridLayout(header_card)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(10)

        self._allocation_date_edit = QDateEdit(self)
        self._allocation_date_edit.setCalendarPopup(True)
        self._allocation_date_edit.setDisplayFormat("yyyy-MM-dd")
        from PySide6.QtCore import QDate
        self._allocation_date_edit.setDate(QDate.currentDate())

        self._gross_amount_edit = QLineEdit(self)
        self._gross_amount_edit.setPlaceholderText("0.00  — total receipt gross amount")
        self._gross_amount_edit.textChanged.connect(self._recalc_total)

        header_layout.addWidget(create_field_block("Allocation Date *", self._allocation_date_edit), 0, 0)
        header_layout.addWidget(create_field_block("Gross Amount *", self._gross_amount_edit), 0, 1)
        layout.addWidget(header_card)

        breakdown_card = QFrame(self)
        breakdown_card.setObjectName("DialogSectionCard")
        breakdown_layout = QGridLayout(breakdown_card)
        breakdown_layout.setContentsMargins(16, 14, 16, 14)
        breakdown_layout.setSpacing(10)
        breakdown_title = QLabel("Deduction Breakdown", breakdown_card)
        breakdown_title.setObjectName("DialogSectionTitle")
        breakdown_layout.addWidget(breakdown_title, 0, 0, 1, 2)

        hint = QLabel(
            "Components must reconcile: Net + WHT VAT + WHT Tax + Retention + Advance Rec. = Gross",
            breakdown_card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        breakdown_layout.addWidget(hint, 1, 0, 1, 2)

        def _zero_edit(placeholder: str = "0.00") -> QLineEdit:
            e = QLineEdit(self)
            e.setPlaceholderText(placeholder)
            e.setText("0.00")
            e.textChanged.connect(self._recalc_total)
            return e

        self._net_receivable_edit = _zero_edit()
        self._whtvat_edit = _zero_edit()
        self._whttax_edit = _zero_edit()
        self._retention_edit = _zero_edit()
        self._advance_rec_edit = _zero_edit()

        breakdown_layout.addWidget(create_field_block("Net Receivable *", self._net_receivable_edit), 2, 0)
        breakdown_layout.addWidget(create_field_block("Withheld VAT", self._whtvat_edit), 2, 1)
        breakdown_layout.addWidget(create_field_block("Withholding Tax", self._whttax_edit), 3, 0)
        breakdown_layout.addWidget(create_field_block("Retention Held", self._retention_edit), 3, 1)
        breakdown_layout.addWidget(create_field_block("Advance Recovery", self._advance_rec_edit), 4, 0)

        self._total_label = QLabel("Computed Total: —", breakdown_card)
        self._total_label.setObjectName("ValueLabel")
        breakdown_layout.addWidget(
            create_field_block("Computed Total (= Gross)", self._total_label), 4, 1
        )
        layout.addWidget(breakdown_card)

        notes_card = QFrame(self)
        notes_card.setObjectName("DialogSectionCard")
        notes_layout = QVBoxLayout(notes_card)
        notes_layout.setContentsMargins(16, 14, 16, 14)
        notes_layout.setSpacing(8)
        notes_label = QLabel("Notes", notes_card)
        notes_label.setObjectName("DialogSectionTitle")
        notes_layout.addWidget(notes_label)
        self._notes_edit = QPlainTextEdit(notes_card)
        self._notes_edit.setMaximumHeight(60)
        notes_layout.addWidget(self._notes_edit)
        layout.addWidget(notes_card)

        layout.addStretch(1)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        save_btn = button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn is not None:
            save_btn.setText("Record Allocation")
            save_btn.setProperty("variant", "primary")
        button_box.accepted.connect(self._handle_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _parse(self, text: str) -> Decimal:
        try:
            return Decimal(text.replace(",", "").strip() or "0")
        except InvalidOperation:
            return Decimal("0.00")

    def _recalc_total(self) -> None:
        total = (
            self._parse(self._net_receivable_edit.text())
            + self._parse(self._whtvat_edit.text())
            + self._parse(self._whttax_edit.text())
            + self._parse(self._retention_edit.text())
            + self._parse(self._advance_rec_edit.text())
        )
        self._total_label.setText(f"{total:,.2f}")

    def _handle_save(self) -> None:
        self._error_label.hide()

        gross_text = self._gross_amount_edit.text().strip()
        if not gross_text:
            self._show_error("Gross amount is required.")
            return

        try:
            gross_amount = Decimal(gross_text.replace(",", ""))
            net_receivable = self._parse(self._net_receivable_edit.text())
            whtvat = self._parse(self._whtvat_edit.text())
            whttax = self._parse(self._whttax_edit.text())
            retention = self._parse(self._retention_edit.text())
            advance_rec = self._parse(self._advance_rec_edit.text())
        except InvalidOperation:
            self._show_error("All amount fields must be numeric.")
            return

        from PySide6.QtCore import QDate
        qd = self._allocation_date_edit.date()
        allocation_date = date(qd.year(), qd.month(), qd.day())
        notes = self._notes_edit.toPlainText().strip() or None

        command = RecordContractReceiptAllocationCommand(
            contract_id=self._contract_id,
            allocation_date=allocation_date,
            gross_amount=gross_amount,
            net_receivable_amount=net_receivable,
            withholding_vat_amount=whtvat,
            withholding_tax_amount=whttax,
            retention_amount=retention,
            advance_recovery_amount=advance_rec,
            notes=notes,
        )
        try:
            self._service_registry.contract_progress_billing_service.record_receipt_allocation(
                self._company_id, command
            )
        except (ValidationError, ConflictError, NotFoundError) as exc:
            self._show_error(str(exc))
            return
        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()
