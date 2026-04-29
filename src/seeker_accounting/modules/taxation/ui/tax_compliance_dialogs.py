"""Action dialogs for the Tax Compliance workspace.

Each dialog is a thin, focused form that builds the relevant command
DTO and dispatches to the matching service. They follow the same
``BaseDialog``-derived shape as ``CompanyTaxProfileDialog`` so the page
stays calm and consistent.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.taxation.constants import (
    ALL_ASSESSED_RETURN_TAX_TYPES,
    TAX_PAYMENT_METHOD_BANK_TRANSFER,
    TAX_PAYMENT_METHOD_CASH,
    TAX_PAYMENT_METHOD_CHEQUE,
    TAX_PAYMENT_METHOD_OTHER,
    TAX_PAYMENT_METHOD_OTP,
    TAX_TYPE_VAT,
)
from seeker_accounting.modules.taxation.dto.dsf_export_dto import (
    DSFExportResultDTO,
    DSFReadinessIssue,
    GenerateDSFExportCommand,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    CreateCustomsDutyObligationCommand,
    ExportTaxReturnPDFCommand,
    ExportTaxReturnPDFResultDTO,
    FileAssessedTaxReturnCommand,
    FileTaxReturnCommand,
    GenerateAnnualPatenteObligationCommand,
    GenerateMonthlyTSRObligationsCommand,
    GenerateMonthlyVATObligationsCommand,
    GenerateMonthlyWithholdingObligationsCommand,
    GenerateQuarterlyCITInstallmentsCommand,
    RecordTaxPaymentCommand,
    SettleTaxReturnCommand,
    TaxObligationDTO,
    TaxPaymentDTO,
    TaxReturnDTO,
    TaxSettlementPreviewDTO,
    TaxSettlementResultDTO,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.message_boxes import show_error


_PAYMENT_METHOD_OPTIONS: tuple[tuple[str, str], ...] = (
    (TAX_PAYMENT_METHOD_BANK_TRANSFER, "Bank transfer"),
    (TAX_PAYMENT_METHOD_OTP, "OTP"),
    (TAX_PAYMENT_METHOD_CHEQUE, "Cheque"),
    (TAX_PAYMENT_METHOD_CASH, "Cash"),
    (TAX_PAYMENT_METHOD_OTHER, "Other"),
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


# ─────────────────────── Generate VAT obligations ───────────────────────


class GenerateMonthlyVATObligationsDialog(BaseDialog):
    """Pick a year and (optionally) due-day-of-next-month, then generate."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._generated: list[TaxObligationDTO] = []

        super().__init__(
            "Generate Monthly VAT Obligations",
            parent,
            help_key="dialog.tax.generate_vat_obligations",
        )
        self.setObjectName("GenerateMonthlyVATObligationsDialog")
        self.resize(520, 320)

        intro = QLabel(
            "Generate the 12 monthly VAT obligations for the selected calendar "
            "year. Existing obligations are preserved (idempotent).",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        frame = _section_frame(self, "Calendar")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._year_spin = QSpinBox(frame)
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(date.today().year)
        grid.addWidget(QLabel("Year"), 1, 0)
        grid.addWidget(self._year_spin, 1, 1)

        self._due_day_spin = QSpinBox(frame)
        self._due_day_spin.setRange(1, 28)
        self._due_day_spin.setValue(15)
        grid.addWidget(QLabel("Due day of next month"), 2, 0)
        grid.addWidget(self._due_day_spin, 2, 1)

        self.body_layout.addWidget(frame)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Generate")
            ok_btn.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_submit)

    def _handle_submit(self) -> None:
        self._error_label.hide()
        command = GenerateMonthlyVATObligationsCommand(
            year=int(self._year_spin.value()),
            due_day_of_next_month=int(self._due_day_spin.value()),
        )
        try:
            self._generated = (
                self._service_registry.tax_obligation_service.generate_monthly_vat_obligations(
                    self._company_id, command
                )
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Generate VAT Obligations", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Generate VAT Obligations",
                f"Could not generate obligations.\n\n{exc}",
            )
            return

        self.accept()

    def generated_obligations(self) -> list[TaxObligationDTO]:
        return list(self._generated)


# ───────────────────── Generate quarterly CIT installments ─────────────


class GenerateQuarterlyCITInstallmentsDialog(BaseDialog):
    """Pick a year and (optionally) due-day, then generate the four CIT quarters."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._generated: list[TaxObligationDTO] = []

        super().__init__(
            "Generate Quarterly CIT Installments",
            parent,
            help_key="dialog.tax.generate_cit_installments",
        )
        self.setObjectName("GenerateQuarterlyCITInstallmentsDialog")
        self.resize(520, 320)

        intro = QLabel(
            "Generate the four quarterly Corporate Income Tax installment "
            "obligations for the selected calendar year. Each quarter is due "
            "in the month following the quarter end. Existing obligations "
            "are preserved (idempotent).",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        frame = _section_frame(self, "Calendar")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._year_spin = QSpinBox(frame)
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(date.today().year)
        grid.addWidget(QLabel("Year"), 1, 0)
        grid.addWidget(self._year_spin, 1, 1)

        self._due_day_spin = QSpinBox(frame)
        self._due_day_spin.setRange(1, 28)
        self._due_day_spin.setValue(15)
        grid.addWidget(QLabel("Due day of next month"), 2, 0)
        grid.addWidget(self._due_day_spin, 2, 1)

        self.body_layout.addWidget(frame)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Generate")
            ok_btn.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_submit)

    def _handle_submit(self) -> None:
        self._error_label.hide()
        command = GenerateQuarterlyCITInstallmentsCommand(
            year=int(self._year_spin.value()),
            due_day_of_next_month=int(self._due_day_spin.value()),
        )
        try:
            self._generated = (
                self._service_registry.tax_obligation_service.generate_quarterly_cit_installments(
                    self._company_id, command
                )
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Generate CIT Installments", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Generate CIT Installments",
                f"Could not generate installments.\n\n{exc}",
            )
            return

        self.accept()

    def generated_obligations(self) -> list[TaxObligationDTO]:
        return list(self._generated)


# ─────────────────────────── File return ────────────────────────────────


class FileTaxReturnDialog(BaseDialog):
    """Capture OTP / external reference and transition the return to FILED."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        tax_return: TaxReturnDTO,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._return = tax_return
        self._filed_return: TaxReturnDTO | None = None

        super().__init__(
            "File Tax Return",
            parent,
            help_key="dialog.tax.file_return",
        )
        self.setObjectName("FileTaxReturnDialog")
        self.resize(560, 360)

        intro = QLabel(
            f"File the draft <b>{tax_return.tax_type_code}</b> return for "
            f"period <b>{tax_return.period_start} \u2192 {tax_return.period_end}</b>. "
            "Once filed, the return becomes immutable.",
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

        frame = _section_frame(self, "Filing References")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._otp_edit = QLineEdit(frame)
        self._otp_edit.setMaxLength(120)
        self._otp_edit.setPlaceholderText("OTP confirmation reference (optional)")
        if tax_return.otp_reference:
            self._otp_edit.setText(tax_return.otp_reference)
        grid.addWidget(QLabel("OTP reference"), 1, 0)
        grid.addWidget(self._otp_edit, 1, 1)

        self._ext_edit = QLineEdit(frame)
        self._ext_edit.setMaxLength(120)
        self._ext_edit.setPlaceholderText("DGI receipt / external filing reference")
        if tax_return.external_reference:
            self._ext_edit.setText(tax_return.external_reference)
        grid.addWidget(QLabel("External reference"), 2, 0)
        grid.addWidget(self._ext_edit, 2, 1)

        self.body_layout.addWidget(frame)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("File Return")
            ok_btn.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_submit)

    def _handle_submit(self) -> None:
        self._error_label.hide()
        command = FileTaxReturnCommand(
            return_id=self._return.id,
            otp_reference=(self._otp_edit.text().strip() or None),
            external_reference=(self._ext_edit.text().strip() or None),
        )
        try:
            self._filed_return = (
                self._service_registry.tax_return_service.file_return(
                    self._company_id, command
                )
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "File Tax Return", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "File Tax Return",
                f"Could not file the return.\n\n{exc}",
            )
            return

        self.accept()

    def filed_return(self) -> TaxReturnDTO | None:
        return self._filed_return


# ───────────────────────── File assessed return (T27) ────────────────────


class FileAssessedTaxReturnDialog(BaseDialog):
    """One-shot file an assessed-amount return (Patente / TSR / Customs).

    These tax types do not aggregate posted accounting facts, so the
    user enters the assessed amount directly.  The service creates a
    return that is already in the FILED state — there is no draft.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        obligation: TaxObligationDTO,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._obligation = obligation
        self._filed_return: TaxReturnDTO | None = None

        super().__init__(
            "File Assessed Tax Return",
            parent,
            help_key="dialog.tax.file_assessed_return",
        )
        self.setObjectName("FileAssessedTaxReturnDialog")
        self.resize(560, 420)

        intro = QLabel(
            f"File the <b>{obligation.tax_type_code}</b> return for period "
            f"<b>{obligation.period_start} \u2192 {obligation.period_end}</b>. "
            "Enter the assessed amount as shown on the official notice / "
            "declaration.  The return is created already in the FILED state.",
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

        frame = _section_frame(self, "Assessed Filing")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._amount_edit = QLineEdit(frame)
        self._amount_edit.setPlaceholderText("e.g. 250000.00")
        grid.addWidget(QLabel("Assessed amount  *"), 1, 0)
        grid.addWidget(self._amount_edit, 1, 1)

        self._date_edit = QDateEdit(frame)
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setDate(_to_qdate(date.today()))
        grid.addWidget(QLabel("Filing date"), 2, 0)
        grid.addWidget(self._date_edit, 2, 1)

        self._otp_edit = QLineEdit(frame)
        self._otp_edit.setMaxLength(120)
        self._otp_edit.setPlaceholderText("OTP confirmation reference (optional)")
        grid.addWidget(QLabel("OTP reference"), 3, 0)
        grid.addWidget(self._otp_edit, 3, 1)

        self._ext_edit = QLineEdit(frame)
        self._ext_edit.setMaxLength(120)
        self._ext_edit.setPlaceholderText("DGI / customs receipt reference")
        grid.addWidget(QLabel("External reference"), 4, 0)
        grid.addWidget(self._ext_edit, 4, 1)

        self._notes_edit = QLineEdit(frame)
        self._notes_edit.setMaxLength(500)
        self._notes_edit.setPlaceholderText("Optional notes")
        grid.addWidget(QLabel("Notes"), 5, 0)
        grid.addWidget(self._notes_edit, 5, 1)

        self.body_layout.addWidget(frame)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("File Return")
            ok_btn.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_submit)

    def _handle_submit(self) -> None:
        self._error_label.hide()
        try:
            amount = Decimal((self._amount_edit.text() or "").strip())
        except (InvalidOperation, ValueError):
            self._error_label.setText("Assessed amount must be a valid number.")
            self._error_label.show()
            return

        command = FileAssessedTaxReturnCommand(
            obligation_id=self._obligation.id,
            total_due_amount=amount,
            filing_date=_from_qdate(self._date_edit.date()),
            otp_reference=(self._otp_edit.text().strip() or None),
            external_reference=(self._ext_edit.text().strip() or None),
            notes=(self._notes_edit.text().strip() or None),
        )
        try:
            self._filed_return = (
                self._service_registry.tax_return_service.file_assessed_return(
                    self._company_id, command
                )
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "File Assessed Tax Return", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "File Assessed Tax Return",
                f"Could not file the return.\n\n{exc}",
            )
            return

        self.accept()

    def filed_return(self) -> TaxReturnDTO | None:
        return self._filed_return


# ───────────────────────── Record payment ───────────────────────────────


class RecordTaxPaymentDialog(BaseDialog):
    """Capture a payment row against a filed return."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        tax_return: TaxReturnDTO,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._return = tax_return
        self._payment: TaxPaymentDTO | None = None

        super().__init__(
            "Record Tax Payment",
            parent,
            help_key="dialog.tax.record_payment",
        )
        self.setObjectName("RecordTaxPaymentDialog")
        self.resize(560, 460)

        outstanding = (
            Decimal(tax_return.total_due_amount or 0)
            - Decimal(tax_return.total_paid_amount or 0)
        )
        intro = QLabel(
            f"Recording a payment against return for "
            f"<b>{tax_return.period_start} \u2192 {tax_return.period_end}</b>. "
            f"Outstanding: <b>{outstanding}</b>.",
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

        frame = _section_frame(self, "Payment")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._date_edit = QDateEdit(frame)
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setDate(_to_qdate(date.today()))
        grid.addWidget(QLabel("Payment date"), 1, 0)
        grid.addWidget(self._date_edit, 1, 1)

        self._amount_edit = QLineEdit(frame)
        self._amount_edit.setPlaceholderText("e.g. 150000.00")
        if outstanding > 0:
            self._amount_edit.setText(str(outstanding))
        grid.addWidget(QLabel("Amount"), 2, 0)
        grid.addWidget(self._amount_edit, 2, 1)

        self._method_combo = QComboBox(frame)
        for code, label in _PAYMENT_METHOD_OPTIONS:
            self._method_combo.addItem(label, code)
        grid.addWidget(QLabel("Payment method"), 3, 0)
        grid.addWidget(self._method_combo, 3, 1)

        # T16: Treasury (cash/bank) account credited by the payment.
        # Required for VAT returns so the bank-side JE can be posted.
        self._treasury_combo = QComboBox(frame)
        self._treasury_combo.addItem("— select treasury account —", None)
        try:
            accounts = (
                self._service_registry.chart_of_accounts_service.list_accounts(
                    self._company_id, active_only=True
                )
            )
            for acct in accounts:
                # Class 5 = treasury (cash, banks).  Restrict to
                # postable accounts so users cannot pick headers.
                if (
                    acct.account_class_code == "5"
                    and acct.allow_manual_posting
                    and not acct.is_control_account
                ):
                    self._treasury_combo.addItem(
                        f"{acct.account_code} — {acct.account_name}", acct.id
                    )
        except Exception:  # pragma: no cover - defensive for chart wiring
            pass
        treasury_label_text = "Treasury account"
        if (
            tax_return.tax_type_code == TAX_TYPE_VAT
            or tax_return.tax_type_code in ALL_ASSESSED_RETURN_TAX_TYPES
        ):
            treasury_label_text += "  *"
        treasury_label = QLabel(treasury_label_text)
        grid.addWidget(treasury_label, 4, 0)
        grid.addWidget(self._treasury_combo, 4, 1)

        self._reference_edit = QLineEdit(frame)
        self._reference_edit.setMaxLength(120)
        self._reference_edit.setPlaceholderText("Bank / OTP reference (optional)")
        grid.addWidget(QLabel("Reference"), 5, 0)
        grid.addWidget(self._reference_edit, 5, 1)

        self._notes_edit = QLineEdit(frame)
        self._notes_edit.setMaxLength(500)
        self._notes_edit.setPlaceholderText("Optional notes")
        grid.addWidget(QLabel("Notes"), 6, 0)
        grid.addWidget(self._notes_edit, 6, 1)

        self.body_layout.addWidget(frame)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Record Payment")
            ok_btn.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_submit)

    def _handle_submit(self) -> None:
        self._error_label.hide()
        try:
            amount = Decimal((self._amount_edit.text() or "").strip())
        except (InvalidOperation, ValueError):
            self._error_label.setText("Amount must be a valid number.")
            self._error_label.show()
            return

        treasury_account_id = self._treasury_combo.currentData()
        if (
            self._return.tax_type_code == TAX_TYPE_VAT
            or self._return.tax_type_code in ALL_ASSESSED_RETURN_TAX_TYPES
        ) and treasury_account_id is None:
            self._error_label.setText(
                "A treasury account is required so the bank-side "
                "journal entry can be posted."
            )
            self._error_label.show()
            return

        command = RecordTaxPaymentCommand(
            tax_return_id=self._return.id,
            payment_date=_from_qdate(self._date_edit.date()),
            amount=amount,
            payment_method_code=str(self._method_combo.currentData()),
            reference=(self._reference_edit.text().strip() or None),
            notes=(self._notes_edit.text().strip() or None),
            treasury_account_id=treasury_account_id,
        )
        try:
            self._payment = self._service_registry.tax_payment_service.record_payment(
                self._company_id, command
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Record Tax Payment", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Record Tax Payment",
                f"Could not record the payment.\n\n{exc}",
            )
            return

        self.accept()

    def recorded_payment(self) -> TaxPaymentDTO | None:
        return self._payment


# ───────────────────────────── DSF export ───────────────────────────────


class DSFExportDialog(BaseDialog):
    """Pick a fiscal year and output path; preview readiness; generate."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._company_name = company_name
        self._result: DSFExportResultDTO | None = None

        super().__init__(
            "Export DSF",
            parent,
            help_key="dialog.tax.dsf_export",
        )
        self.setObjectName("DSFExportDialog")
        self.resize(640, 540)

        intro = QLabel(
            f"Generate the DSF working file (Excel) for <b>{company_name}</b> "
            "for the selected fiscal year. The export reads from posted "
            "accounting truth and the tax profile.",
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

        # Year + path section
        frame = _section_frame(self, "Export")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._year_spin = QSpinBox(frame)
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(date.today().year - 1)
        grid.addWidget(QLabel("Fiscal year"), 1, 0)
        grid.addWidget(self._year_spin, 1, 1)

        path_row = QHBoxLayout()
        self._path_edit = QLineEdit(frame)
        self._path_edit.setPlaceholderText("Choose a destination .xlsx file")
        path_row.addWidget(self._path_edit, 1)
        browse = QPushButton("Browse\u2026", frame)
        browse.setProperty("variant", "secondary")
        browse.clicked.connect(self._pick_output_path)
        path_row.addWidget(browse)
        grid.addWidget(QLabel("Output file"), 2, 0)
        grid.addLayout(path_row, 2, 1)

        self.body_layout.addWidget(frame)

        # Readiness section
        readiness_frame = _section_frame(self, "Readiness")
        readiness_grid: QGridLayout = readiness_frame.layout()  # type: ignore[assignment]

        self._readiness_summary = QLabel("No readiness check run yet.", readiness_frame)
        self._readiness_summary.setWordWrap(True)
        self._readiness_summary.setStyleSheet("color: #6B7280;")
        readiness_grid.addWidget(self._readiness_summary, 1, 0, 1, 2)

        self._readiness_list = QListWidget(readiness_frame)
        self._readiness_list.setMinimumHeight(140)
        readiness_grid.addWidget(self._readiness_list, 2, 0, 1, 2)

        check_btn = QPushButton("Check Readiness", readiness_frame)
        check_btn.setProperty("variant", "ghost")
        check_btn.clicked.connect(self._handle_check_readiness)
        readiness_grid.addWidget(check_btn, 3, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)

        self.body_layout.addWidget(readiness_frame)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Generate")
            ok_btn.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_submit)

    def _pick_output_path(self) -> None:
        default_name = f"DSF_{self._company_name}_{int(self._year_spin.value())}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Choose DSF output file",
            default_name,
            "Excel files (*.xlsx)",
        )
        if path:
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            self._path_edit.setText(path)

    def _render_readiness(self, issues: tuple[DSFReadinessIssue, ...]) -> None:
        self._readiness_list.clear()
        if not issues:
            self._readiness_summary.setText("No readiness issues found.")
            self._readiness_summary.setStyleSheet("color: #047857;")
            return

        errors = sum(1 for i in issues if i.severity == "error")
        warns = sum(1 for i in issues if i.severity == "warning")
        self._readiness_summary.setText(
            f"{errors} blocking issue(s), {warns} warning(s)."
        )
        self._readiness_summary.setStyleSheet(
            "color: #B91C1C;" if errors else "color: #92400E;"
        )

        for issue in issues:
            prefix = "[ERROR] " if issue.severity == "error" else "[WARN]  "
            item = QListWidgetItem(f"{prefix}{issue.code}: {issue.message}")
            self._readiness_list.addItem(item)

    def _handle_check_readiness(self) -> None:
        try:
            issues = self._service_registry.dsf_export_service.check_readiness(
                self._company_id, int(self._year_spin.value())
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            show_error(self, "DSF Readiness", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self, "DSF Readiness", f"Could not run readiness check.\n\n{exc}"
            )
            return
        self._render_readiness(issues)

    def _handle_submit(self) -> None:
        self._error_label.hide()
        path_text = (self._path_edit.text() or "").strip()
        if not path_text:
            self._error_label.setText("Please choose an output .xlsx file.")
            self._error_label.show()
            return

        # Ensure parent dir exists (service also handles this defensively).
        try:
            Path(path_text).parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._error_label.setText(f"Could not prepare output directory: {exc}")
            self._error_label.show()
            return

        command = GenerateDSFExportCommand(
            fiscal_year=int(self._year_spin.value()),
            output_path=path_text,
        )
        try:
            self._result = self._service_registry.dsf_export_service.generate(
                self._company_id, command
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "DSF Export", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "DSF Export", f"Could not generate DSF.\n\n{exc}")
            return

        self.accept()

    def export_result(self) -> DSFExportResultDTO | None:
        return self._result


# ─────────────────────────── Settle VAT return ──────────────────────────


class SettleVATReturnDialog(BaseDialog):
    """Preview and post the VAT settlement journal for a filed return.

    The dialog calls ``tax_settlement_service.preview_settlement`` on
    open and renders:

    - a totals header (output VAT / input VAT recoverable / net plug),
    - a read-only table of the projected JE lines,
    - an optional list of blocking issues.

    The user can edit the settlement date.  The "Post Settlement" button
    is disabled while blocking issues are present.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        tax_return: TaxReturnDTO,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._return = tax_return
        self._preview: TaxSettlementPreviewDTO | None = None
        self._result: TaxSettlementResultDTO | None = None

        super().__init__(
            "Settle VAT Return",
            parent,
            help_key="dialog.tax.settle_return",
        )
        self.setObjectName("SettleVATReturnDialog")
        self.resize(720, 560)

        intro = QLabel(
            f"Posting the settlement journal for return covering "
            f"<b>{tax_return.period_start} \u2192 {tax_return.period_end}</b>. "
            "The journal aggregates posted output and input VAT and "
            "plugs the difference to the VAT payable or credit "
            "carry-forward account.",
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

        # ── Settings card ──
        settings_frame = _section_frame(self, "Settlement")
        grid: QGridLayout = settings_frame.layout()  # type: ignore[assignment]

        self._date_edit = QDateEdit(settings_frame)
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setDate(_to_qdate(tax_return.period_end))
        self._date_edit.dateChanged.connect(self._reload_preview)
        grid.addWidget(QLabel("Settlement date"), 1, 0)
        grid.addWidget(self._date_edit, 1, 1)

        self.body_layout.addWidget(settings_frame)

        # ── Totals card ──
        totals_frame = _section_frame(self, "Totals")
        totals_grid: QGridLayout = totals_frame.layout()  # type: ignore[assignment]
        self._output_label = QLabel("—", totals_frame)
        self._input_label = QLabel("—", totals_frame)
        self._payable_label = QLabel("—", totals_frame)
        self._credit_label = QLabel("—", totals_frame)
        for lbl in (
            self._output_label,
            self._input_label,
            self._payable_label,
            self._credit_label,
        ):
            lbl.setStyleSheet("font-weight: 600;")
            lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        totals_grid.addWidget(QLabel("Output VAT"), 1, 0)
        totals_grid.addWidget(self._output_label, 1, 1)
        totals_grid.addWidget(QLabel("Input VAT (recoverable)"), 2, 0)
        totals_grid.addWidget(self._input_label, 2, 1)
        totals_grid.addWidget(QLabel("Net VAT payable"), 3, 0)
        totals_grid.addWidget(self._payable_label, 3, 1)
        totals_grid.addWidget(QLabel("Net VAT credit carry-forward"), 4, 0)
        totals_grid.addWidget(self._credit_label, 4, 1)
        self.body_layout.addWidget(totals_frame)

        # ── Lines table ──
        self._lines_table = QTableWidget(0, 4, self)
        self._lines_table.setHorizontalHeaderLabels(
            ["Account", "Description", "Debit", "Credit"]
        )
        self._lines_table.verticalHeader().setVisible(False)
        self._lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._lines_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        header = self._lines_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._lines_table.setMinimumHeight(180)
        self.body_layout.addWidget(self._lines_table)

        # ── Blocking issues list ──
        self._issues_label = QLabel("Blocking issues", self)
        self._issues_label.setStyleSheet("font-weight: 600; color: #b91c1c;")
        self._issues_list = QListWidget(self)
        self._issues_list.setMaximumHeight(110)
        self._issues_label.hide()
        self._issues_list.hide()
        self.body_layout.addWidget(self._issues_label)
        self.body_layout.addWidget(self._issues_list)

        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        self._post_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if self._post_button is not None:
            self._post_button.setText("Post Settlement")
            self._post_button.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_post)

        # Initial preview load.
        self._reload_preview()

    # ── Preview ──────────────────────────────────────────────────────

    def _reload_preview(self) -> None:
        self._error_label.hide()
        try:
            self._preview = (
                self._service_registry.tax_settlement_service.preview_settlement(
                    self._company_id, self._return.id
                )
            )
        except ValidationError as exc:
            self._preview = None
            self._error_label.setText(str(exc))
            self._error_label.show()
            self._render_preview(None)
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            self._preview = None
            show_error(self, "Settle VAT Return", str(exc))
            self.reject()
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._preview = None
            show_error(
                self,
                "Settle VAT Return",
                f"Could not load settlement preview.\n\n{exc}",
            )
            self.reject()
            return

        self._render_preview(self._preview)

    def _render_preview(self, preview: TaxSettlementPreviewDTO | None) -> None:
        if preview is None:
            self._output_label.setText("—")
            self._input_label.setText("—")
            self._payable_label.setText("—")
            self._credit_label.setText("—")
            self._lines_table.setRowCount(0)
            self._issues_label.hide()
            self._issues_list.hide()
            if self._post_button is not None:
                self._post_button.setEnabled(False)
            return

        self._output_label.setText(f"{preview.total_output_vat:,.2f}")
        self._input_label.setText(f"{preview.total_input_vat_recoverable:,.2f}")
        self._payable_label.setText(f"{preview.net_payable_amount:,.2f}")
        self._credit_label.setText(
            f"{preview.net_credit_carryforward_amount:,.2f}"
        )

        self._lines_table.setRowCount(len(preview.journal_lines))
        for row, line in enumerate(preview.journal_lines):
            account_item = QTableWidgetItem(
                f"{line.account_code} — {line.account_name}"
            )
            description_item = QTableWidgetItem(line.description)
            debit_item = QTableWidgetItem(
                f"{line.debit_amount:,.2f}" if line.debit_amount else ""
            )
            credit_item = QTableWidgetItem(
                f"{line.credit_amount:,.2f}" if line.credit_amount else ""
            )
            debit_item.setTextAlignment(
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            )
            credit_item.setTextAlignment(
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            )
            self._lines_table.setItem(row, 0, account_item)
            self._lines_table.setItem(row, 1, description_item)
            self._lines_table.setItem(row, 2, debit_item)
            self._lines_table.setItem(row, 3, credit_item)

        self._issues_list.clear()
        if preview.blocking_issues:
            for issue in preview.blocking_issues:
                self._issues_list.addItem(QListWidgetItem(issue))
            self._issues_label.show()
            self._issues_list.show()
            if self._post_button is not None:
                self._post_button.setEnabled(False)
        else:
            self._issues_label.hide()
            self._issues_list.hide()
            if self._post_button is not None:
                self._post_button.setEnabled(len(preview.journal_lines) > 0)

    # ── Post ─────────────────────────────────────────────────────────

    def _handle_post(self) -> None:
        if self._preview is None or self._preview.blocking_issues:
            return

        command = SettleTaxReturnCommand(
            return_id=self._return.id,
            settlement_date=_from_qdate(self._date_edit.date()),
        )
        try:
            self._result = (
                self._service_registry.tax_settlement_service.settle_return(
                    self._company_id, command
                )
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Settle VAT Return", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Settle VAT Return",
                f"Could not post the settlement.\n\n{exc}",
            )
            return

        self.accept()

    def settlement_result(self) -> TaxSettlementResultDTO | None:
        return self._result


# ─────────────── Generate withholding-tax obligations (T18) ──────────────


class GenerateMonthlyWithholdingObligationsDialog(BaseDialog):
    """Generate the 12 monthly withholding-tax obligations for a year."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._generated: list[TaxObligationDTO] = []

        super().__init__(
            "Generate Monthly Withholding Obligations",
            parent,
            help_key="dialog.tax.generate_withholding_obligations",
        )
        self.setObjectName("GenerateMonthlyWithholdingObligationsDialog")
        self.resize(520, 320)

        intro = QLabel(
            "Generate the 12 monthly withholding-tax obligations for the "
            "selected calendar year. Each month is due in the following "
            "month. Existing obligations are preserved (idempotent).",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        frame = _section_frame(self, "Calendar")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._year_spin = QSpinBox(frame)
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(date.today().year)
        grid.addWidget(QLabel("Year"), 1, 0)
        grid.addWidget(self._year_spin, 1, 1)

        self._due_day_spin = QSpinBox(frame)
        self._due_day_spin.setRange(1, 28)
        self._due_day_spin.setValue(15)
        grid.addWidget(QLabel("Due day of next month"), 2, 0)
        grid.addWidget(self._due_day_spin, 2, 1)

        self.body_layout.addWidget(frame)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Generate")
            ok_btn.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_submit)

    def _handle_submit(self) -> None:
        self._error_label.hide()
        command = GenerateMonthlyWithholdingObligationsCommand(
            year=int(self._year_spin.value()),
            due_day_of_next_month=int(self._due_day_spin.value()),
        )
        try:
            self._generated = (
                self._service_registry.tax_obligation_service.generate_monthly_withholding_obligations(
                    self._company_id, command
                )
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Generate Withholding Obligations", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Generate Withholding Obligations",
                f"Could not generate obligations.\n\n{exc}",
            )
            return

        self.accept()

    def generated_obligations(self) -> list[TaxObligationDTO]:
        return list(self._generated)


# ─────────────── Generate annual Patente obligation (T19) ────────────────


class GenerateAnnualPatenteObligationDialog(BaseDialog):
    """Generate the single annual Patente (business-license) obligation."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._generated: TaxObligationDTO | None = None

        super().__init__(
            "Generate Annual Patente Obligation",
            parent,
            help_key="dialog.tax.generate_patente_obligation",
        )
        self.setObjectName("GenerateAnnualPatenteObligationDialog")
        self.resize(520, 340)

        intro = QLabel(
            "Generate the annual Patente obligation for the selected year. "
            "A Patente obligation already on file for this year is preserved "
            "(idempotent).",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        frame = _section_frame(self, "Year and due date")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._year_spin = QSpinBox(frame)
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(date.today().year)
        grid.addWidget(QLabel("Year"), 1, 0)
        grid.addWidget(self._year_spin, 1, 1)

        self._due_month_spin = QSpinBox(frame)
        self._due_month_spin.setRange(1, 12)
        self._due_month_spin.setValue(2)
        grid.addWidget(QLabel("Due month"), 2, 0)
        grid.addWidget(self._due_month_spin, 2, 1)

        self._due_day_spin = QSpinBox(frame)
        self._due_day_spin.setRange(1, 31)
        self._due_day_spin.setValue(28)
        grid.addWidget(QLabel("Due day"), 3, 0)
        grid.addWidget(self._due_day_spin, 3, 1)

        self.body_layout.addWidget(frame)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Generate")
            ok_btn.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_submit)

    def _handle_submit(self) -> None:
        self._error_label.hide()
        command = GenerateAnnualPatenteObligationCommand(
            year=int(self._year_spin.value()),
            due_month=int(self._due_month_spin.value()),
            due_day=int(self._due_day_spin.value()),
        )
        try:
            self._generated = (
                self._service_registry.tax_obligation_service.generate_annual_patente_obligation(
                    self._company_id, command
                )
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Generate Patente Obligation", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Generate Patente Obligation",
                f"Could not generate obligation.\n\n{exc}",
            )
            return

        self.accept()

    def generated_obligation(self) -> TaxObligationDTO | None:
        return self._generated


# ─────────────────── Generate monthly TSR obligations (T20) ──────────────


class GenerateMonthlyTSRObligationsDialog(BaseDialog):
    """Generate the 12 monthly TSR (specific service tax) obligations."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._generated: list[TaxObligationDTO] = []

        super().__init__(
            "Generate Monthly TSR Obligations",
            parent,
            help_key="dialog.tax.generate_tsr_obligations",
        )
        self.setObjectName("GenerateMonthlyTSRObligationsDialog")
        self.resize(520, 320)

        intro = QLabel(
            "Generate the 12 monthly Tax on Specific Services (TSR) "
            "obligations for the selected calendar year. Existing "
            "obligations are preserved (idempotent).",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        frame = _section_frame(self, "Calendar")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._year_spin = QSpinBox(frame)
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(date.today().year)
        grid.addWidget(QLabel("Year"), 1, 0)
        grid.addWidget(self._year_spin, 1, 1)

        self._due_day_spin = QSpinBox(frame)
        self._due_day_spin.setRange(1, 28)
        self._due_day_spin.setValue(15)
        grid.addWidget(QLabel("Due day of next month"), 2, 0)
        grid.addWidget(self._due_day_spin, 2, 1)

        self.body_layout.addWidget(frame)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Generate")
            ok_btn.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_submit)

    def _handle_submit(self) -> None:
        self._error_label.hide()
        command = GenerateMonthlyTSRObligationsCommand(
            year=int(self._year_spin.value()),
            due_day_of_next_month=int(self._due_day_spin.value()),
        )
        try:
            self._generated = (
                self._service_registry.tax_obligation_service.generate_monthly_tsr_obligations(
                    self._company_id, command
                )
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Generate TSR Obligations", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Generate TSR Obligations",
                f"Could not generate obligations.\n\n{exc}",
            )
            return

        self.accept()

    def generated_obligations(self) -> list[TaxObligationDTO]:
        return list(self._generated)


# ─────────────────── Record customs duty obligation (T21) ────────────────


class RecordCustomsDutyObligationDialog(BaseDialog):
    """Record a single per-declaration customs-duty obligation."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._generated: TaxObligationDTO | None = None

        super().__init__(
            "Record Customs Duty Obligation",
            parent,
            help_key="dialog.tax.record_customs_duty",
        )
        self.setObjectName("RecordCustomsDutyObligationDialog")
        self.resize(560, 380)

        intro = QLabel(
            "Record a customs-duty obligation for a single import "
            "declaration. The declaration reference is stored in the "
            "obligation notes.",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        frame = _section_frame(self, "Declaration")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._declaration_date_edit = QDateEdit(frame)
        self._declaration_date_edit.setCalendarPopup(True)
        self._declaration_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._declaration_date_edit.setDate(_to_qdate(date.today()))
        grid.addWidget(QLabel("Declaration date"), 1, 0)
        grid.addWidget(self._declaration_date_edit, 1, 1)

        self._due_date_edit = QDateEdit(frame)
        self._due_date_edit.setCalendarPopup(True)
        self._due_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._due_date_edit.setDate(_to_qdate(date.today()))
        grid.addWidget(QLabel("Due date"), 2, 0)
        grid.addWidget(self._due_date_edit, 2, 1)

        self._reference_edit = QLineEdit(frame)
        self._reference_edit.setPlaceholderText("e.g. DEC-2026-00451")
        grid.addWidget(QLabel("Declaration reference"), 3, 0)
        grid.addWidget(self._reference_edit, 3, 1)

        self._notes_edit = QLineEdit(frame)
        self._notes_edit.setPlaceholderText("Optional notes")
        grid.addWidget(QLabel("Notes"), 4, 0)
        grid.addWidget(self._notes_edit, 4, 1)

        self.body_layout.addWidget(frame)
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
        self._error_label.hide()
        ref = self._reference_edit.text().strip() or None
        notes = self._notes_edit.text().strip() or None
        command = CreateCustomsDutyObligationCommand(
            declaration_date=_from_qdate(self._declaration_date_edit.date()),
            due_date=_from_qdate(self._due_date_edit.date()),
            declaration_reference=ref,
            notes=notes,
        )
        try:
            self._generated = (
                self._service_registry.tax_obligation_service.create_customs_duty_obligation(
                    self._company_id, command
                )
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except ConflictError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, PermissionDeniedError) as exc:
            show_error(self, "Record Customs Duty", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Record Customs Duty",
                f"Could not record obligation.\n\n{exc}",
            )
            return

        self.accept()

    def generated_obligation(self) -> TaxObligationDTO | None:
        return self._generated


# ───────────────────── Export tax return as PDF (T24) ────────────────────


class ExportTaxReturnPDFDialog(BaseDialog):
    """Pick an output path and render the selected return as PDF."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        tax_return: TaxReturnDTO,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._tax_return = tax_return
        self._company_name = company_name
        self._result: ExportTaxReturnPDFResultDTO | None = None

        super().__init__(
            "Export Tax Return as PDF",
            parent,
            help_key="dialog.tax.export_return_pdf",
        )
        self.setObjectName("ExportTaxReturnPDFDialog")
        self.resize(560, 280)

        intro = QLabel(
            f"Render tax return #{tax_return.id} ({tax_return.tax_type_code}, "
            f"{tax_return.period_start.isoformat()} \u2014 "
            f"{tax_return.period_end.isoformat()}) as a printable PDF.",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        frame = _section_frame(self, "Output")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._path_edit = QLineEdit(frame)
        suggested = (
            f"tax_return_{tax_return.tax_type_code}_"
            f"{tax_return.period_start.isoformat()}_"
            f"{tax_return.period_end.isoformat()}.pdf"
        )
        self._path_edit.setText(str(Path.home() / "Documents" / suggested))
        grid.addWidget(QLabel("Output PDF file"), 1, 0)

        path_row = QWidget(frame)
        h = QHBoxLayout(path_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        h.addWidget(self._path_edit, 1)
        browse = QPushButton("Browse\u2026", path_row)
        browse.clicked.connect(self._handle_browse)
        h.addWidget(browse)
        grid.addWidget(path_row, 1, 1)

        self.body_layout.addWidget(frame)
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Export")
            ok_btn.setProperty("variant", "primary")
        self.button_box.accepted.connect(self._handle_submit)

    def _handle_browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Tax Return PDF",
            self._path_edit.text(),
            "PDF files (*.pdf)",
        )
        if path:
            if not path.lower().endswith(".pdf"):
                path = path + ".pdf"
            self._path_edit.setText(path)

    def _handle_submit(self) -> None:
        self._error_label.hide()
        path = self._path_edit.text().strip()
        if not path:
            self._error_label.setText("An output path is required.")
            self._error_label.show()
            return
        if not path.lower().endswith(".pdf"):
            self._error_label.setText("Output path must end with .pdf.")
            self._error_label.show()
            return
        command = ExportTaxReturnPDFCommand(
            return_id=self._tax_return.id,
            output_path=path,
        )
        try:
            self._result = (
                self._service_registry.tax_return_pdf_export_service.export(
                    self._company_id, command
                )
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Export Tax Return PDF", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Export Tax Return PDF",
                f"Could not export return.\n\n{exc}",
            )
            return

        self.accept()

    def export_result(self) -> ExportTaxReturnPDFResultDTO | None:
        return self._result
