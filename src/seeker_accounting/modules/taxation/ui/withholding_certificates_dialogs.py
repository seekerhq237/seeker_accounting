"""Dialogs for the withholding-tax certificate register.

Slice T13. Three thin form dialogs that build the matching command DTO
and dispatch to ``WithholdingTaxCertificateService``:

* ``RecordWithholdingCertificateDialog`` — capture a new certificate
* ``EditWithholdingCertificateDialog`` — edit an existing (non-voided)
  certificate; direction is immutable post-creation
* ``VoidWithholdingCertificateDialog`` — capture a void reason and
  confirm
"""

from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.taxation.constants import (
    WHT_COUNTERPARTY_CUSTOMER,
    WHT_COUNTERPARTY_OTHER,
    WHT_COUNTERPARTY_SUPPLIER,
    WHT_DIRECTION_INBOUND,
    WHT_DIRECTION_OUTBOUND,
)
from seeker_accounting.modules.taxation.dto.withholding_tax_certificate_dto import (
    LinkWithholdingCertificateToJournalEntryCommand,
    RecordWithholdingTaxCertificateCommand,
    UpdateWithholdingTaxCertificateCommand,
    VoidWithholdingTaxCertificateCommand,
    WithholdingTaxCertificateDTO,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.message_boxes import show_error


_DIRECTION_OPTIONS: tuple[tuple[str, str], ...] = (
    (WHT_DIRECTION_INBOUND, "Inbound — received from customer"),
    (WHT_DIRECTION_OUTBOUND, "Outbound — issued to supplier"),
)

_COUNTERPARTY_KIND_OPTIONS: tuple[tuple[str, str], ...] = (
    (WHT_COUNTERPARTY_CUSTOMER, "Customer"),
    (WHT_COUNTERPARTY_SUPPLIER, "Supplier"),
    (WHT_COUNTERPARTY_OTHER, "Other"),
)


def _section_frame(parent: QWidget, title: str) -> QFrame:
    frame = QFrame(parent)
    frame.setObjectName("DialogSection")
    frame.setProperty("card", True)
    grid = QGridLayout(frame)
    grid.setContentsMargins(16, 12, 16, 12)
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(8)
    header = QLabel(title, frame)
    header.setStyleSheet("font-weight: 600; color: #111827;")
    grid.addWidget(header, 0, 0, 1, 2)
    grid.setColumnStretch(1, 1)
    return frame


def _to_qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def _from_qdate(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def _set_combo_to_data(combo: QComboBox, value: str) -> None:
    for index in range(combo.count()):
        if combo.itemData(index) == value:
            combo.setCurrentIndex(index)
            return


# ─────────────────────────── Form base ────────────────────────────────


class _CertificateFormFields:
    """Shared field-construction logic for record/edit dialogs."""

    def __init__(self, owner: BaseDialog, service_registry: ServiceRegistry, company_id: int) -> None:
        self._owner = owner
        self._registry = service_registry
        self._company_id = company_id
        self._tax_codes: list = []

        self._error_label = QLabel(owner)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        owner.body_layout.addWidget(self._error_label)

        # ── Direction + counterparty ──
        cp_frame = _section_frame(owner, "Counterparty")
        grid: QGridLayout = cp_frame.layout()  # type: ignore[assignment]

        self.direction_combo = QComboBox(cp_frame)
        for code, label in _DIRECTION_OPTIONS:
            self.direction_combo.addItem(label, code)
        grid.addWidget(QLabel("Direction"), 1, 0)
        grid.addWidget(self.direction_combo, 1, 1)

        self.kind_combo = QComboBox(cp_frame)
        for code, label in _COUNTERPARTY_KIND_OPTIONS:
            self.kind_combo.addItem(label, code)
        grid.addWidget(QLabel("Counterparty kind"), 2, 0)
        grid.addWidget(self.kind_combo, 2, 1)

        self.name_edit = QLineEdit(cp_frame)
        self.name_edit.setMaxLength(200)
        self.name_edit.setPlaceholderText("Legal name as it appears on the certificate")
        grid.addWidget(QLabel("Counterparty name"), 3, 0)
        grid.addWidget(self.name_edit, 3, 1)

        self.niu_edit = QLineEdit(cp_frame)
        self.niu_edit.setMaxLength(50)
        self.niu_edit.setPlaceholderText("Tax identifier (NIU) — optional")
        grid.addWidget(QLabel("Counterparty NIU"), 4, 0)
        grid.addWidget(self.niu_edit, 4, 1)

        owner.body_layout.addWidget(cp_frame)

        # ── Certificate ──
        cert_frame = _section_frame(owner, "Certificate")
        grid = cert_frame.layout()  # type: ignore[assignment]

        self.number_edit = QLineEdit(cert_frame)
        self.number_edit.setMaxLength(80)
        self.number_edit.setPlaceholderText("Unique within the same direction")
        grid.addWidget(QLabel("Certificate number"), 1, 0)
        grid.addWidget(self.number_edit, 1, 1)

        self.date_edit = QDateEdit(cert_frame)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(_to_qdate(date.today()))
        grid.addWidget(QLabel("Certificate date"), 2, 0)
        grid.addWidget(self.date_edit, 2, 1)

        self.tax_code_combo = QComboBox(cert_frame)
        self._populate_tax_codes()
        grid.addWidget(QLabel("Tax code"), 3, 0)
        grid.addWidget(self.tax_code_combo, 3, 1)

        self.base_edit = QLineEdit(cert_frame)
        self.base_edit.setPlaceholderText("e.g. 1000000.00")
        grid.addWidget(QLabel("Taxable base"), 4, 0)
        grid.addWidget(self.base_edit, 4, 1)

        self.tax_edit = QLineEdit(cert_frame)
        self.tax_edit.setPlaceholderText("e.g. 22000.00")
        grid.addWidget(QLabel("Tax amount"), 5, 0)
        grid.addWidget(self.tax_edit, 5, 1)

        self.notes_edit = QPlainTextEdit(cert_frame)
        self.notes_edit.setPlaceholderText("Optional notes (max 2000 characters)")
        self.notes_edit.setFixedHeight(64)
        grid.addWidget(QLabel("Notes"), 6, 0, alignment=Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.notes_edit, 6, 1)

        owner.body_layout.addWidget(cert_frame)

    def _populate_tax_codes(self) -> None:
        try:
            self._tax_codes = self._registry.tax_setup_service.list_tax_codes(
                self._company_id, active_only=True
            )
        except Exception:
            self._tax_codes = []
        self.tax_code_combo.clear()
        if not self._tax_codes:
            self.tax_code_combo.addItem("— No active tax codes —", None)
            self.tax_code_combo.setEnabled(False)
            return
        for tc in self._tax_codes:
            label = f"{tc.code} — {tc.name}"
            self.tax_code_combo.addItem(label, tc.id)

    def show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    def hide_error(self) -> None:
        self._error_label.hide()

    # ----- read helpers -----

    def read_amounts(self) -> tuple[Decimal, Decimal] | None:
        try:
            base = Decimal((self.base_edit.text() or "").strip())
            amount = Decimal((self.tax_edit.text() or "").strip())
        except (InvalidOperation, ValueError):
            self.show_error("Taxable base and tax amount must be valid numbers.")
            return None
        return base, amount

    def selected_tax_code_id(self) -> int | None:
        data = self.tax_code_combo.currentData()
        if data is None:
            return None
        return int(data)


# ─────────────────────────── Record dialog ────────────────────────────


class RecordWithholdingCertificateDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._recorded: WithholdingTaxCertificateDTO | None = None

        super().__init__(
            "Record Withholding-Tax Certificate",
            parent,
            help_key="dialog.tax.record_withholding_certificate",
        )
        self.setObjectName("RecordWithholdingCertificateDialog")
        apply_window_size(self, "modules.taxation.ui.withholding.certificates.dialogs.0")

        intro = QLabel(
            "Record an inbound (received from customer) or outbound "
            "(issued to supplier) withholding-tax certificate. The "
            "certificate number must be unique within its direction.",
            self,
        )
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        self._fields = _CertificateFormFields(self, service_registry, company_id)

        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Record")
            ok_btn.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_submit)

    def _handle_submit(self) -> None:
        self._fields.hide_error()

        amounts = self._fields.read_amounts()
        if amounts is None:
            return
        base, tax = amounts

        tax_code_id = self._fields.selected_tax_code_id()
        if tax_code_id is None:
            self._fields.show_error("Select a tax code.")
            return

        command = RecordWithholdingTaxCertificateCommand(
            direction=str(self._fields.direction_combo.currentData()),
            counterparty_kind=str(self._fields.kind_combo.currentData()),
            counterparty_id=None,
            counterparty_name=self._fields.name_edit.text().strip(),
            counterparty_niu=(self._fields.niu_edit.text().strip() or None),
            tax_code_id=tax_code_id,
            certificate_number=self._fields.number_edit.text().strip(),
            certificate_date=_from_qdate(self._fields.date_edit.date()),
            taxable_base=base,
            tax_amount=tax,
            fiscal_period_id=None,
            source_document_type=None,
            source_document_id=None,
            evidence_attachment_path=None,
            notes=(self._fields.notes_edit.toPlainText().strip() or None),
        )
        try:
            self._recorded = (
                self._service_registry.withholding_tax_certificate_service
                .record_certificate(self._company_id, command)
            )
        except ValidationError as exc:
            self._fields.show_error(str(exc))
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Record Withholding Certificate", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Record Withholding Certificate",
                f"Could not record the certificate.\n\n{exc}",
            )
            return

        self.accept()

    def recorded_certificate(self) -> WithholdingTaxCertificateDTO | None:
        return self._recorded


# ─────────────────────────── Edit dialog ──────────────────────────────


class EditWithholdingCertificateDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        certificate: WithholdingTaxCertificateDTO,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._original = certificate
        self._updated: WithholdingTaxCertificateDTO | None = None

        super().__init__(
            "Edit Withholding-Tax Certificate",
            parent,
            help_key="dialog.tax.edit_withholding_certificate",
        )
        self.setObjectName("EditWithholdingCertificateDialog")
        apply_window_size(self, "modules.taxation.ui.withholding.certificates.dialogs.1")

        intro = QLabel(
            f"Editing certificate <b>{certificate.certificate_number}</b> "
            f"({certificate.direction.lower()}). Direction is immutable — "
            "to change direction, void this certificate and record a new one.",
            self,
        )
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        self._fields = _CertificateFormFields(self, service_registry, company_id)

        # Lock direction
        _set_combo_to_data(self._fields.direction_combo, certificate.direction)
        self._fields.direction_combo.setEnabled(False)

        # Pre-fill remaining fields
        _set_combo_to_data(self._fields.kind_combo, certificate.counterparty_kind)
        self._fields.name_edit.setText(certificate.counterparty_name)
        self._fields.niu_edit.setText(certificate.counterparty_niu or "")
        self._fields.number_edit.setText(certificate.certificate_number)
        self._fields.date_edit.setDate(_to_qdate(certificate.certificate_date))
        _set_combo_to_data(self._fields.tax_code_combo, certificate.tax_code_id)
        self._fields.base_edit.setText(str(certificate.taxable_base))
        self._fields.tax_edit.setText(str(certificate.tax_amount))
        self._fields.notes_edit.setPlainText(certificate.notes or "")

        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Save")
            ok_btn.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_submit)

    def _handle_submit(self) -> None:
        self._fields.hide_error()

        amounts = self._fields.read_amounts()
        if amounts is None:
            return
        base, tax = amounts

        tax_code_id = self._fields.selected_tax_code_id()
        if tax_code_id is None:
            self._fields.show_error("Select a tax code.")
            return

        command = UpdateWithholdingTaxCertificateCommand(
            certificate_id=self._original.id,
            counterparty_kind=str(self._fields.kind_combo.currentData()),
            counterparty_id=self._original.counterparty_id,
            counterparty_name=self._fields.name_edit.text().strip(),
            counterparty_niu=(self._fields.niu_edit.text().strip() or None),
            tax_code_id=tax_code_id,
            certificate_number=self._fields.number_edit.text().strip(),
            certificate_date=_from_qdate(self._fields.date_edit.date()),
            taxable_base=base,
            tax_amount=tax,
            fiscal_period_id=self._original.fiscal_period_id,
            source_document_type=self._original.source_document_type,
            source_document_id=self._original.source_document_id,
            evidence_attachment_path=self._original.evidence_attachment_path,
            notes=(self._fields.notes_edit.toPlainText().strip() or None),
        )
        try:
            self._updated = (
                self._service_registry.withholding_tax_certificate_service
                .update_certificate(self._company_id, command)
            )
        except ValidationError as exc:
            self._fields.show_error(str(exc))
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Edit Withholding Certificate", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Edit Withholding Certificate",
                f"Could not save the certificate.\n\n{exc}",
            )
            return

        self.accept()

    def updated_certificate(self) -> WithholdingTaxCertificateDTO | None:
        return self._updated


# ─────────────────────────── Void dialog ──────────────────────────────


class VoidWithholdingCertificateDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        certificate: WithholdingTaxCertificateDTO,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._certificate = certificate
        self._voided: WithholdingTaxCertificateDTO | None = None

        super().__init__(
            "Void Withholding-Tax Certificate",
            parent,
            help_key="dialog.tax.void_withholding_certificate",
        )
        self.setObjectName("VoidWithholdingCertificateDialog")
        apply_window_size(self, "modules.taxation.ui.withholding.certificates.dialogs.2")

        intro = QLabel(
            f"Void certificate <b>{certificate.certificate_number}</b> "
            f"({certificate.direction.lower()}). Voided certificates remain "
            "in the register for audit but are excluded from totals.",
            self,
        )
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        frame = _section_frame(self, "Reason")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._reason_edit = QPlainTextEdit(frame)
        self._reason_edit.setPlaceholderText("Reason for voiding (recommended, max 500 characters)")
        self._reason_edit.setFixedHeight(80)
        grid.addWidget(QLabel("Reason"), 1, 0, alignment=Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self._reason_edit, 1, 1)

        self.body_layout.addWidget(frame)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Void")
            ok_btn.setProperty("variant", "danger")
        self.button_box.accepted.connect(self._handle_submit)

    def _handle_submit(self) -> None:
        self._error_label.hide()
        reason = self._reason_edit.toPlainText().strip()
        command = VoidWithholdingTaxCertificateCommand(
            certificate_id=self._certificate.id,
            reason=(reason or None),
        )
        try:
            self._voided = (
                self._service_registry.withholding_tax_certificate_service
                .void_certificate(self._company_id, command)
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Void Withholding Certificate", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Void Withholding Certificate",
                f"Could not void the certificate.\n\n{exc}",
            )
            return

        self.accept()

    def voided_certificate(self) -> WithholdingTaxCertificateDTO | None:
        return self._voided


# ─────────────────────────── Link dialog ──────────────────────────────


class LinkWithholdingCertificateDialog(BaseDialog):
    """Attach (or clear) a posted journal entry on a certificate.

    Lists posted journal entries for the active company within a
    bounded date window so the user can pick the supplier-payment
    JE that recorded the withholding deduction. The dialog is
    deliberately minimal — it does not create or edit accounting
    facts; it only sets the ``source_document_*`` link fields.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        certificate: WithholdingTaxCertificateDTO,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._certificate = certificate
        self._linked: WithholdingTaxCertificateDTO | None = None
        self._candidate_entries: list = []

        super().__init__(
            "Link Certificate to Journal Entry",
            parent,
            help_key="dialog.tax.link_withholding_certificate",
        )
        self.setObjectName("LinkWithholdingCertificateDialog")
        apply_window_size(self, "modules.taxation.ui.withholding.certificates.dialogs.3")

        intro = QLabel(
            f"Attach a posted journal entry to certificate "
            f"<b>{certificate.certificate_number}</b> "
            f"({certificate.direction.lower()}). For outbound "
            "certificates this is typically the supplier-payment journal "
            "entry that recorded the withholding deduction.",
            self,
        )
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        # ── Window selector ──
        window_frame = _section_frame(self, "Search window")
        grid: QGridLayout = window_frame.layout()  # type: ignore[assignment]

        # Default window: ±60 days around the certificate date.
        cert_date = certificate.certificate_date
        default_from = QDate(cert_date.year, cert_date.month, cert_date.day).addDays(-60)
        default_to = QDate(cert_date.year, cert_date.month, cert_date.day).addDays(60)

        from PySide6.QtWidgets import QDateEdit  # local to keep imports tidy

        self._from_edit = QDateEdit(window_frame)
        self._from_edit.setCalendarPopup(True)
        self._from_edit.setDisplayFormat("yyyy-MM-dd")
        self._from_edit.setDate(default_from)
        grid.addWidget(QLabel("From"), 1, 0)
        grid.addWidget(self._from_edit, 1, 1)

        self._to_edit = QDateEdit(window_frame)
        self._to_edit.setCalendarPopup(True)
        self._to_edit.setDisplayFormat("yyyy-MM-dd")
        self._to_edit.setDate(default_to)
        grid.addWidget(QLabel("To"), 2, 0)
        grid.addWidget(self._to_edit, 2, 1)

        from PySide6.QtWidgets import QPushButton

        self._refresh_btn = QPushButton("Search posted entries", window_frame)
        self._refresh_btn.clicked.connect(self._reload_entries)
        grid.addWidget(self._refresh_btn, 3, 1)

        self.body_layout.addWidget(window_frame)

        # ── Entry combo ──
        from PySide6.QtWidgets import QComboBox

        chooser_frame = _section_frame(self, "Journal entry")
        cgrid: QGridLayout = chooser_frame.layout()  # type: ignore[assignment]

        self._entry_combo = QComboBox(chooser_frame)
        self._entry_combo.setMinimumWidth(360)
        cgrid.addWidget(QLabel("Posted entry"), 1, 0)
        cgrid.addWidget(self._entry_combo, 1, 1)

        # Show currently linked JE, if any.
        current_text = "— none —"
        if certificate.source_document_id and certificate.source_document_type:
            current_text = (
                f"{certificate.source_document_type} #"
                f"{certificate.source_document_id}"
            )
        cgrid.addWidget(QLabel("Currently linked"), 2, 0)
        current_label = QLabel(current_text, chooser_frame)
        current_label.setStyleSheet("color: #6B7280;")
        cgrid.addWidget(current_label, 2, 1)

        self.body_layout.addWidget(chooser_frame)
        self.body_layout.addStretch(1)

        # ── Buttons (Cancel, Clear link, Save) ──
        from PySide6.QtWidgets import QPushButton as _PB

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        self._clear_btn = _PB("Clear link", self)
        self._clear_btn.setProperty("variant", "secondary")
        self._clear_btn.clicked.connect(self._handle_clear)
        self.button_box.addButton(self._clear_btn, QDialogButtonBox.ButtonRole.ResetRole)
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Link")
            ok_btn.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_link)

        # Initial population
        self._reload_entries()

    # ── Internals ─────────────────────────────────────────────────────

    def _reload_entries(self) -> None:
        self._error_label.hide()
        self._entry_combo.clear()

        d_from = _from_qdate(self._from_edit.date())
        d_to = _from_qdate(self._to_edit.date())
        if d_from > d_to:
            self._show_error("'From' date is after 'To' date.")
            self._candidate_entries = []
            self._entry_combo.addItem("— invalid date range —", None)
            return

        registry = self._service_registry
        # Pull POSTED entries via JournalService and clip to the date
        # window locally. JournalService is the supported public surface
        # for cross-module reads.
        try:
            entries = registry.journal_service.list_journal_entries(
                self._company_id, status_code="POSTED"
            )
        except (AttributeError, PermissionDeniedError):
            entries = []
            self._show_error(
                "Posted journal entries are not available for this company.",
            )
            self._candidate_entries = []
            self._entry_combo.addItem("— unavailable —", None)
            self._entry_combo.setEnabled(False)
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._candidate_entries = []
            self._show_error(f"Could not load journal entries.\n\n{exc}")
            self._entry_combo.addItem("— unavailable —", None)
            self._entry_combo.setEnabled(False)
            return

        self._candidate_entries = [
            e for e in entries if d_from <= e.entry_date <= d_to
        ]
        if not self._candidate_entries:
            self._entry_combo.addItem("— no posted entries in this window —", None)
            self._entry_combo.setEnabled(False)
            return

        self._entry_combo.setEnabled(True)
        for e in self._candidate_entries:
            label = (
                f"{getattr(e, 'entry_number', '?')} \u00b7 "
                f"{e.entry_date.isoformat()} \u00b7 "
                f"{(getattr(e, 'description', '') or '')[:60]}"
            )
            self._entry_combo.addItem(label, e.id)

        # Pre-select currently linked entry, if visible
        if self._certificate.source_document_id is not None:
            for i in range(self._entry_combo.count()):
                if self._entry_combo.itemData(i) == self._certificate.source_document_id:
                    self._entry_combo.setCurrentIndex(i)
                    break

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    # ── Handlers ──────────────────────────────────────────────────────

    def _handle_link(self) -> None:
        self._error_label.hide()
        je_id = self._entry_combo.currentData()
        if je_id is None:
            self._show_error("Select a posted journal entry to link.")
            return
        self._dispatch_link(int(je_id))

    def _handle_clear(self) -> None:
        self._error_label.hide()
        self._dispatch_link(None)

    def _dispatch_link(self, journal_entry_id: int | None) -> None:
        command = LinkWithholdingCertificateToJournalEntryCommand(
            certificate_id=self._certificate.id,
            journal_entry_id=journal_entry_id,
        )
        try:
            self._linked = (
                self._service_registry.withholding_tax_certificate_service
                .link_to_journal_entry(self._company_id, command)
            )
        except ValidationError as exc:
            self._show_error(str(exc))
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Link Withholding Certificate", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Link Withholding Certificate",
                f"Could not save the link.\n\n{exc}",
            )
            return
        self.accept()

    def linked_certificate(self) -> WithholdingTaxCertificateDTO | None:
        return self._linked

