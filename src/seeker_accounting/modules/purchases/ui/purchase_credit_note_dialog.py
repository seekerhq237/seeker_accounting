from __future__ import annotations

import logging
from datetime import date

from PySide6.QtCore import Qt
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
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.purchases.dto.purchase_credit_note_commands import (
    CreatePurchaseCreditNoteCommand,
    UpdatePurchaseCreditNoteCommand,
)
from seeker_accounting.modules.purchases.dto.purchase_credit_note_dto import PurchaseCreditNoteDetailDTO
from seeker_accounting.modules.purchases.ui.purchase_credit_note_lines_grid import PurchaseCreditNoteLinesGrid
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

_log = logging.getLogger(__name__)


class PurchaseCreditNoteDialog(QDialog):
    """Create or edit a draft purchase credit note."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        credit_note_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._credit_note_id = credit_note_id
        self._saved: PurchaseCreditNoteDetailDTO | None = None

        is_edit = credit_note_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Purchase Credit Note — {company_name}")
        self.setModal(True)
        self.resize(920, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        layout.addWidget(self._build_header_section())
        layout.addWidget(self._build_lines_section(), 1)
        layout.addWidget(self._build_totals_panel())

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        self._button_box.accepted.connect(self._handle_submit)
        self._button_box.rejected.connect(self.reject)
        save_btn = self._button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn:
            save_btn.setText("Save Changes" if is_edit else "Create Credit Note")
            save_btn.setProperty("variant", "primary")
        cancel_btn = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn:
            cancel_btn.setProperty("variant", "secondary")
        layout.addWidget(self._button_box)

        self._load_reference_data()
        if is_edit:
            self._load_credit_note()

    @property
    def saved(self) -> PurchaseCreditNoteDetailDTO | None:
        return self._saved

    @classmethod
    def create_credit_note(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> PurchaseCreditNoteDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved
        return None

    @classmethod
    def edit_credit_note(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        credit_note_id: int,
        parent: QWidget | None = None,
    ) -> PurchaseCreditNoteDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, credit_note_id=credit_note_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved
        return None

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_header_section(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("PageCard")
        grid = QGridLayout(frame)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setSpacing(12)

        # Row 0: Supplier | Credit Note Date
        self._supplier_combo = SearchableComboBox(frame)
        grid.addLayout(create_field_block("Supplier *", self._supplier_combo), 0, 0)

        self._credit_date_edit = QDateEdit(frame)
        self._credit_date_edit.setCalendarPopup(True)
        self._credit_date_edit.setDate(date.today())
        grid.addLayout(create_field_block("Credit Note Date *", self._credit_date_edit), 0, 1)

        # Row 1: Currency | Supplier Credit Reference
        self._currency_combo = SearchableComboBox(frame)
        grid.addLayout(create_field_block("Currency *", self._currency_combo), 1, 0)

        self._supplier_ref_edit = QLineEdit(frame)
        self._supplier_ref_edit.setPlaceholderText("Supplier's credit note reference (optional)")
        grid.addLayout(create_field_block("Supplier Credit Ref.", self._supplier_ref_edit), 1, 1)

        # Row 2: Source Bill # | Reason
        self._source_bill_edit = QLineEdit(frame)
        self._source_bill_edit.setPlaceholderText("Source bill number (optional)")
        grid.addLayout(create_field_block("Source Bill", self._source_bill_edit), 2, 0)

        self._reason_edit = QPlainTextEdit(frame)
        self._reason_edit.setPlaceholderText("Reason for credit note (optional)")
        self._reason_edit.setFixedHeight(60)
        grid.addLayout(create_field_block("Reason", self._reason_edit), 2, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return frame

    def _build_lines_section(self) -> PurchaseCreditNoteLinesGrid:
        self._lines_grid = PurchaseCreditNoteLinesGrid(
            self._service_registry, self._company_id, parent=self
        )
        self._lines_grid.lines_changed.connect(self._update_totals)
        return self._lines_grid

    def _build_totals_panel(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("PageCard")
        hl = QHBoxLayout(frame)
        hl.setContentsMargins(12, 8, 12, 8)
        hl.setSpacing(20)
        hl.addStretch(1)

        self._subtotal_label = QLabel("Subtotal: 0.00", frame)
        self._subtotal_label.setObjectName("TotalLabel")
        hl.addWidget(self._subtotal_label)

        self._tax_label = QLabel("Tax: 0.00", frame)
        self._tax_label.setObjectName("TotalLabel")
        hl.addWidget(self._tax_label)

        self._total_label = QLabel("Total: 0.00", frame)
        self._total_label.setObjectName("TotalLabelBold")
        hl.addWidget(self._total_label)

        return frame

    # ------------------------------------------------------------------
    # Reference data
    # ------------------------------------------------------------------

    def _load_reference_data(self) -> None:
        try:
            suppliers = self._service_registry.supplier_service.list_suppliers(self._company_id)
            self._supplier_combo.clear()
            for s in suppliers:
                self._supplier_combo.addItem(s.name, s.id)
        except Exception:
            _log.warning("PCN dialog: failed to load suppliers", exc_info=True)

        try:
            currencies = self._service_registry.reference_data_service.list_currencies()
            self._currency_combo.clear()
            for cur in currencies:
                self._currency_combo.addItem(f"{cur.code} — {cur.name}", cur.code)
        except Exception:
            _log.warning("PCN dialog: failed to load currencies", exc_info=True)

    # ------------------------------------------------------------------
    # Load existing
    # ------------------------------------------------------------------

    def _load_credit_note(self) -> None:
        if self._credit_note_id is None:
            return
        try:
            cn = self._service_registry.purchase_credit_note_service.get_credit_note(
                self._company_id, self._credit_note_id
            )
        except Exception:
            _log.warning("PCN dialog: failed to load credit note", exc_info=True)
            return

        idx = self._supplier_combo.findData(cn.supplier_id)
        if idx >= 0:
            self._supplier_combo.setCurrentIndex(idx)

        self._credit_date_edit.setDate(cn.credit_date)

        cur_idx = self._currency_combo.findData(cn.currency_code)
        if cur_idx >= 0:
            self._currency_combo.setCurrentIndex(cur_idx)

        self._supplier_ref_edit.setText(cn.supplier_credit_reference or "")
        self._source_bill_edit.setText(cn.source_bill_number or "")
        self._reason_edit.setPlainText(cn.reason_text or "")

        self._lines_grid.set_lines(cn.lines)
        self._update_totals()

    # ------------------------------------------------------------------
    # Totals
    # ------------------------------------------------------------------

    def _update_totals(self) -> None:
        subtotal, tax, total, _ = self._lines_grid.calculate_totals()
        self._subtotal_label.setText(f"Subtotal: {subtotal:,.2f}")
        self._tax_label.setText(f"Tax: {tax:,.2f}")
        self._total_label.setText(f"Total: {total:,.2f}")

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._error_label.hide()
        try:
            supplier_id = self._supplier_combo.currentData()
            if not isinstance(supplier_id, int) or supplier_id <= 0:
                raise ValidationError("A supplier is required.")

            credit_date = self._credit_date_edit.date().toPython()
            currency_code = self._currency_combo.currentData()
            if not currency_code:
                raise ValidationError("A currency is required.")

            line_cmds = self._lines_grid.get_line_commands()
            if not line_cmds:
                raise ValidationError("At least one credit note line is required.")

            for i, lc in enumerate(line_cmds, start=1):
                if lc.line_subtotal_amount <= 0:
                    raise ValidationError(f"Line {i}: amount must be greater than zero.")

            supplier_ref = self._supplier_ref_edit.text().strip() or None
            source_bill_ref = self._source_bill_edit.text().strip() or None
            source_bill_id: int | None = None
            if source_bill_ref:
                try:
                    bill = self._service_registry.purchase_bill_service.get_bill_by_number(
                        self._company_id, source_bill_ref
                    )
                    if bill is not None:
                        source_bill_id = bill.id
                except Exception:
                    pass  # Best-effort link only

            reason_text = self._reason_edit.toPlainText().strip() or None

            if self._credit_note_id is None:
                cmd = CreatePurchaseCreditNoteCommand(
                    company_id=self._company_id,
                    supplier_id=supplier_id,
                    credit_date=credit_date,
                    currency_code=currency_code,
                    exchange_rate=None,
                    reason_text=reason_text,
                    supplier_credit_reference=supplier_ref,
                    source_bill_id=source_bill_id,
                    contract_id=None,
                    project_id=None,
                    lines=line_cmds,
                )
                self._saved = self._service_registry.purchase_credit_note_service.create_draft_credit_note(cmd)
            else:
                cmd = UpdatePurchaseCreditNoteCommand(
                    credit_note_id=self._credit_note_id,
                    company_id=self._company_id,
                    supplier_id=supplier_id,
                    credit_date=credit_date,
                    currency_code=currency_code,
                    exchange_rate=None,
                    reason_text=reason_text,
                    supplier_credit_reference=supplier_ref,
                    source_bill_id=source_bill_id,
                    contract_id=None,
                    project_id=None,
                    lines=line_cmds,
                )
                self._saved = self._service_registry.purchase_credit_note_service.update_draft_credit_note(cmd)

            self.accept()

        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
        except Exception as exc:
            _log.error("PCN dialog submit error", exc_info=True)
            self._error_label.setText(f"Unexpected error: {exc}")
            self._error_label.show()
