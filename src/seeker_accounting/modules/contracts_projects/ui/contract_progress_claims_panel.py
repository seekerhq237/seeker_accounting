"""Contract progress claims tab panel + create claim dialog + generate invoice dialog."""
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
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.contracts_projects.dto.contract_progress_billing_dto import (
    CreateProgressClaimCommand,
    GenerateProgressInvoiceCommand,
    ProgressClaimDTO,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn, apply_status_chip_to_column
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.message_boxes import show_error, show_info


def _fmt_amount(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


def _fmt_date(value: date | None) -> str:
    return "—" if value is None else value.isoformat()


def _humanize(code: str | None) -> str:
    if not code:
        return "—"
    return code.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Panel (tab widget)
# ---------------------------------------------------------------------------


class ContractProgressClaimsPanel(QWidget):
    """List panel for contract progress billing claims."""

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
        self._claims: tuple[ProgressClaimDTO, ...] = ()

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
        title_lbl = QLabel("Progress Claims", card)
        title_lbl.setObjectName("DialogSectionTitle")
        header.addWidget(title_lbl)
        header.addStretch(1)
        self._summary_label = QLabel("", card)
        self._summary_label.setObjectName("DialogSectionSummary")
        header.addWidget(self._summary_label)
        self._new_btn = QPushButton("New Claim", card)
        self._new_btn.setProperty("variant", "primary")
        self._new_btn.clicked.connect(self._create_claim)
        header.addWidget(self._new_btn)
        self._invoice_btn = QPushButton("Generate Invoice", card)
        self._invoice_btn.setEnabled(False)
        self._invoice_btn.clicked.connect(self._generate_invoice)
        header.addWidget(self._invoice_btn)
        card_layout.addLayout(header)

        self._model = QStandardItemModel(0, 8, card)
        self._table = DataTable(
            columns=(
                DataTableColumn(key="number", title="Claim #"),
                DataTableColumn(key="date", title="Date"),
                DataTableColumn(key="status", title="Status"),
                DataTableColumn(key="prev_cert", title="Prev. Certified", is_numeric=True),
                DataTableColumn(key="current", title="Current Claim", is_numeric=True),
                DataTableColumn(key="vat", title="VAT", is_numeric=True),
                DataTableColumn(key="retention", title="Retention", is_numeric=True),
                DataTableColumn(key="net", title="Net Receivable", is_numeric=True),
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
        self._table.selection_changed.connect(self._on_selection_changed)
        card_layout.addWidget(self._table, 1)
        layout.addWidget(card, 1)

    def reload(self) -> None:
        try:
            self._claims = self._service_registry.contract_progress_billing_service.list_progress_claims(
                self._company_id, self._contract_id
            )
        except Exception as exc:
            self._claims = ()
            show_error(self, "Progress Claims", f"Could not load progress claims.\n\n{exc}")
        self._populate_table()

    def _populate_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        total_certified = Decimal("0.00")
        total_net = Decimal("0.00")
        for claim in self._claims:
            self._model.appendRow([
                self._make_item(claim.claim_number, user_data=claim.id),
                self._make_item(_fmt_date(claim.claim_date)),
                self._make_item(claim.status_code),
                self._make_item(f"{claim.previous_certified_amount:,.2f}"),
                self._make_item(f"{claim.current_claim_amount:,.2f}"),
                self._make_item(f"{claim.vat_amount:,.2f}"),
                self._make_item(f"{claim.retention_amount:,.2f}"),
                self._make_item(f"{claim.net_receivable_amount:,.2f}"),
            ])
            total_certified += claim.current_claim_amount
            total_net += claim.net_receivable_amount
        count = len(self._claims)
        self._summary_label.setText(
            f"{count} claim{'s' if count != 1 else ''} | "
            f"Total Billed: {total_certified:,.2f} | Net: {total_net:,.2f}"
        )
        self._on_selection_changed([])

    def _on_selection_changed(self, _rows: list) -> None:
        selected = self._selected_claim()
        can_invoice = (
            selected is not None
            and selected.status_code == "certified"
            and selected.sales_invoice_id is None
        )
        self._invoice_btn.setEnabled(can_invoice)

    def _selected_claim(self) -> ProgressClaimDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        id_item = self._model.item(rows[0], 0)
        if id_item is None:
            return None
        claim_id = id_item.data(Qt.ItemDataRole.UserRole)
        for claim in self._claims:
            if claim.id == claim_id:
                return claim
        return None

    def _create_claim(self) -> None:
        dialog = CreateProgressClaimDialog(
            self._service_registry,
            self._company_id,
            self._contract_id,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def _generate_invoice(self) -> None:
        selected = self._selected_claim()
        if selected is None or selected.status_code != "certified" or selected.sales_invoice_id is not None:
            return
        dialog = GenerateProgressInvoiceDialog(
            self._service_registry,
            self._company_id,
            selected,
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
# Create progress claim dialog
# ---------------------------------------------------------------------------


class CreateProgressClaimDialog(QDialog):
    """Form dialog for creating a new progress claim."""

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
        self.setWindowTitle("New Progress Claim")
        self.setModal(True)
        apply_window_size(self, "modules.contracts.projects.ui.contract.progress.claims.panel.0")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        # Reference section
        ref_card = QFrame(self)
        ref_card.setObjectName("DialogSectionCard")
        ref_layout = QGridLayout(ref_card)
        ref_layout.setContentsMargins(16, 14, 16, 14)
        ref_layout.setSpacing(10)

        self._claim_number_edit = QLineEdit(self)
        self._claim_number_edit.setPlaceholderText("e.g. PC-001")

        self._claim_date_edit = QDateEdit(self)
        self._claim_date_edit.setCalendarPopup(True)
        self._claim_date_edit.setDisplayFormat("yyyy-MM-dd")
        from PySide6.QtCore import QDate
        self._claim_date_edit.setDate(QDate.currentDate())

        ref_layout.addWidget(create_field_block("Claim Number *", self._claim_number_edit), 0, 0)
        ref_layout.addWidget(create_field_block("Claim Date *", self._claim_date_edit), 0, 1)
        layout.addWidget(ref_card)

        # Amounts section
        amounts_card = QFrame(self)
        amounts_card.setObjectName("DialogSectionCard")
        amounts_layout = QGridLayout(amounts_card)
        amounts_layout.setContentsMargins(16, 14, 16, 14)
        amounts_layout.setSpacing(10)

        amounts_title = QLabel("Amounts", amounts_card)
        amounts_title.setObjectName("DialogSectionTitle")
        amounts_layout.addWidget(amounts_title, 0, 0, 1, 2)

        self._certified_amount_edit = QLineEdit(self)
        self._certified_amount_edit.setPlaceholderText("0.00  — cumulative certified to date")
        self._certified_amount_edit.textChanged.connect(self._recalc_net)

        self._vat_amount_edit = QLineEdit(self)
        self._vat_amount_edit.setPlaceholderText("0.00")
        self._vat_amount_edit.setText("0.00")
        self._vat_amount_edit.textChanged.connect(self._recalc_net)

        self._retention_pct_edit = QLineEdit(self)
        self._retention_pct_edit.setPlaceholderText("0.00  — leave blank for no retention")
        self._retention_pct_edit.textChanged.connect(self._recalc_net)

        self._advance_recovery_edit = QLineEdit(self)
        self._advance_recovery_edit.setPlaceholderText("0.00")
        self._advance_recovery_edit.setText("0.00")
        self._advance_recovery_edit.textChanged.connect(self._recalc_net)

        self._withheld_vat_edit = QLineEdit(self)
        self._withheld_vat_edit.setPlaceholderText("0.00")
        self._withheld_vat_edit.setText("0.00")
        self._withheld_vat_edit.textChanged.connect(self._recalc_net)

        self._wht_edit = QLineEdit(self)
        self._wht_edit.setPlaceholderText("0.00")
        self._wht_edit.setText("0.00")
        self._wht_edit.textChanged.connect(self._recalc_net)

        self._net_receivable_label = QLabel("—", self)
        self._net_receivable_label.setObjectName("ValueLabel")

        amounts_layout.addWidget(create_field_block("Certified Amount *", self._certified_amount_edit), 1, 0)
        amounts_layout.addWidget(create_field_block("VAT Amount", self._vat_amount_edit), 1, 1)
        amounts_layout.addWidget(create_field_block("Retention %", self._retention_pct_edit), 2, 0)
        amounts_layout.addWidget(create_field_block("Advance Recovery", self._advance_recovery_edit), 2, 1)
        amounts_layout.addWidget(create_field_block("Withheld VAT", self._withheld_vat_edit), 3, 0)
        amounts_layout.addWidget(create_field_block("Withholding Tax", self._wht_edit), 3, 1)
        amounts_layout.addWidget(
            create_field_block("Calculated Net Receivable", self._net_receivable_label), 4, 0, 1, 2
        )
        layout.addWidget(amounts_card)

        # Notes
        notes_card = QFrame(self)
        notes_card.setObjectName("DialogSectionCard")
        notes_layout = QVBoxLayout(notes_card)
        notes_layout.setContentsMargins(16, 14, 16, 14)
        notes_layout.setSpacing(8)
        notes_label = QLabel("Notes", notes_card)
        notes_label.setObjectName("DialogSectionTitle")
        notes_layout.addWidget(notes_label)
        self._notes_edit = QPlainTextEdit(notes_card)
        self._notes_edit.setMaximumHeight(80)
        notes_layout.addWidget(self._notes_edit)
        layout.addWidget(notes_card)

        layout.addStretch(1)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        save_btn = button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn is not None:
            save_btn.setText("Create Claim")
            save_btn.setProperty("variant", "primary")
        button_box.accepted.connect(self._handle_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _parse_decimal(self, text: str, default: Decimal = Decimal("0.00")) -> Decimal:
        try:
            return Decimal(text.replace(",", "").strip())
        except (InvalidOperation, ValueError):
            return default

    def _recalc_net(self) -> None:
        try:
            certified = self._parse_decimal(self._certified_amount_edit.text())
            vat = self._parse_decimal(self._vat_amount_edit.text())
            ret_pct_text = self._retention_pct_edit.text().strip()
            retention = Decimal("0.00")
            if ret_pct_text:
                ret_pct = self._parse_decimal(ret_pct_text)
                retention = (certified * ret_pct / Decimal("100")).quantize(Decimal("0.01"))
            advance_rec = self._parse_decimal(self._advance_recovery_edit.text())
            withheld_vat = self._parse_decimal(self._withheld_vat_edit.text())
            wht = self._parse_decimal(self._wht_edit.text())
            # current_claim = certified (the service will compute prev_certified from DB)
            # For display: net ≈ certified + VAT - retention - advance_rec - withheld_vat - WHT
            net = certified + vat - retention - advance_rec - withheld_vat - wht
            self._net_receivable_label.setText(f"{net:,.2f}")
        except Exception:
            self._net_receivable_label.setText("—")

    def _handle_save(self) -> None:
        self._error_label.hide()
        claim_number = self._claim_number_edit.text().strip()
        if not claim_number:
            self._show_error("Claim number is required.")
            return

        from PySide6.QtCore import QDate
        qd = self._claim_date_edit.date()
        claim_date = date(qd.year(), qd.month(), qd.day())

        certified_text = self._certified_amount_edit.text().strip()
        if not certified_text:
            self._show_error("Certified amount is required.")
            return

        try:
            certified_amount = Decimal(certified_text.replace(",", ""))
            vat_amount = self._parse_decimal(self._vat_amount_edit.text())
            ret_pct_text = self._retention_pct_edit.text().strip()
            retention_percent: Decimal | None = None
            if ret_pct_text:
                retention_percent = Decimal(ret_pct_text.replace(",", ""))
            advance_recovery = self._parse_decimal(self._advance_recovery_edit.text())
            withheld_vat = self._parse_decimal(self._withheld_vat_edit.text())
            wht = self._parse_decimal(self._wht_edit.text())
        except InvalidOperation:
            self._show_error("All amount fields must be numeric.")
            return

        notes = self._notes_edit.toPlainText().strip() or None

        command = CreateProgressClaimCommand(
            contract_id=self._contract_id,
            claim_number=claim_number,
            claim_date=claim_date,
            certified_amount=certified_amount,
            vat_amount=vat_amount,
            retention_percent=retention_percent,
            advance_recovery_amount=advance_recovery,
            withheld_vat_amount=withheld_vat,
            withholding_tax_amount=wht,
            notes=notes,
        )
        try:
            self._service_registry.contract_progress_billing_service.create_progress_claim(
                self._company_id, command
            )
        except (ValidationError, ConflictError, NotFoundError) as exc:
            self._show_error(str(exc))
            return
        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()


# ---------------------------------------------------------------------------
# Generate progress invoice dialog
# ---------------------------------------------------------------------------


class GenerateProgressInvoiceDialog(QDialog):
    """Confirm + configure generating a draft sales invoice from a certified progress claim."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        claim: ProgressClaimDTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._claim = claim
        self.setWindowTitle("Generate Progress Invoice")
        self.setModal(True)
        apply_window_size(self, "modules.contracts.projects.ui.contract.progress.claims.panel.1")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        summary_card = QFrame(self)
        summary_card.setObjectName("DialogSectionCard")
        summary_layout = QGridLayout(summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        summary_layout.setSpacing(10)
        summary_title = QLabel(f"Claim: {claim.claim_number}", summary_card)
        summary_title.setObjectName("DialogSectionTitle")
        summary_layout.addWidget(summary_title, 0, 0, 1, 2)

        specs = [
            ("Claim Date", _fmt_date(claim.claim_date)),
            ("Gross Claim", f"{claim.current_claim_amount:,.2f}"),
            ("VAT", f"{claim.vat_amount:,.2f}"),
            ("Retention Held", f"{claim.retention_amount:,.2f}"),
            ("Advance Recovery", f"{claim.advance_recovery_amount:,.2f}"),
            ("Net Receivable", f"{claim.net_receivable_amount:,.2f}"),
        ]
        for row_idx, (label, value) in enumerate(specs, start=1):
            lbl = QLabel(label + ":", summary_card)
            lbl.setObjectName("FieldLabel")
            val = QLabel(value, summary_card)
            val.setObjectName("ValueLabel")
            summary_layout.addWidget(lbl, row_idx, 0)
            summary_layout.addWidget(val, row_idx, 1)
        layout.addWidget(summary_card)

        config_card = QFrame(self)
        config_card.setObjectName("DialogSectionCard")
        config_layout = QGridLayout(config_card)
        config_layout.setContentsMargins(16, 14, 16, 14)
        config_layout.setSpacing(10)
        config_title = QLabel("Invoice Settings", config_card)
        config_title.setObjectName("DialogSectionTitle")
        config_layout.addWidget(config_title, 0, 0, 1, 2)

        self._invoice_date_edit = QDateEdit(self)
        self._invoice_date_edit.setCalendarPopup(True)
        self._invoice_date_edit.setDisplayFormat("yyyy-MM-dd")
        from PySide6.QtCore import QDate
        self._invoice_date_edit.setDate(QDate.currentDate())

        self._due_date_edit = QDateEdit(self)
        self._due_date_edit.setCalendarPopup(True)
        self._due_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._due_date_edit.setDate(QDate.currentDate())

        self._revenue_account_edit = QLineEdit(self)
        self._revenue_account_edit.setPlaceholderText("Revenue account ID (numeric)")

        config_layout.addWidget(create_field_block("Invoice Date *", self._invoice_date_edit), 1, 0)
        config_layout.addWidget(create_field_block("Due Date *", self._due_date_edit), 1, 1)
        config_layout.addWidget(
            create_field_block("Revenue Account ID *", self._revenue_account_edit), 2, 0, 1, 2
        )
        layout.addWidget(config_card)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        layout.addStretch(1)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        ok_btn = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Generate Invoice")
            ok_btn.setProperty("variant", "primary")
        button_box.accepted.connect(self._handle_generate)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _handle_generate(self) -> None:
        self._error_label.hide()
        rev_account_text = self._revenue_account_edit.text().strip()
        if not rev_account_text:
            self._show_error("Revenue account ID is required.")
            return
        try:
            revenue_account_id = int(rev_account_text)
        except ValueError:
            self._show_error("Revenue account ID must be a numeric ID.")
            return

        from PySide6.QtCore import QDate
        inv_qd = self._invoice_date_edit.date()
        due_qd = self._due_date_edit.date()
        invoice_date = date(inv_qd.year(), inv_qd.month(), inv_qd.day())
        due_date = date(due_qd.year(), due_qd.month(), due_qd.day())

        command = GenerateProgressInvoiceCommand(
            claim_id=self._claim.id,
            invoice_date=invoice_date,
            due_date=due_date,
            revenue_account_id=revenue_account_id,
        )
        try:
            result = self._service_registry.contract_progress_billing_service.generate_sales_invoice_from_claim(
                self._company_id, command
            )
        except (ValidationError, ConflictError, NotFoundError) as exc:
            self._show_error(str(exc))
            return

        show_info(
            self,
            "Invoice Generated",
            f"Draft sales invoice {result.invoice_number} created.\n"
            f"Net receivable: {result.net_receivable_amount:,.2f}",
        )
        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()
