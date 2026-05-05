"""Edit dialog for the company tax profile (one row per company).

Mirrors the OrganisationSettings "Modify" pattern: a focused dialog with
clearly labelled sections, restrained widgets, and combos driven by
the taxation constant module so codes never drift.
"""

from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.taxation.constants import (
    CIT_RATE_PROFILE_EXEMPT,
    CIT_RATE_PROFILE_SME,
    CIT_RATE_PROFILE_STANDARD,
    DSF_FORM_LIBERATORY,
    DSF_FORM_NONE,
    DSF_FORM_REAL,
    DSF_FORM_SIMPLIFIED,
    DSF_SUBMISSION_API,
    DSF_SUBMISSION_EXCEL,
    DSF_SUBMISSION_MANUAL,
    TAX_REGIME_LIBERATORY,
    TAX_REGIME_REAL,
    TAX_REGIME_SIMPLIFIED,
    TAXPAYER_SEGMENT_DIVISIONAL,
    TAXPAYER_SEGMENT_LARGE,
    TAXPAYER_SEGMENT_MEDIUM,
    TAXPAYER_SEGMENT_SPECIALIZED,
    VAT_BASIS_ACCRUAL,
    VAT_BASIS_CASH,
)
from seeker_accounting.modules.taxation.dto.company_tax_profile_dto import (
    CompanyTaxProfileDTO,
    UpsertCompanyTaxProfileCommand,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.message_boxes import show_error


_REGIME_OPTIONS: tuple[tuple[str, str], ...] = (
    ("", "—"),
    (TAX_REGIME_REAL, "Real"),
    (TAX_REGIME_SIMPLIFIED, "Simplified"),
    (TAX_REGIME_LIBERATORY, "Liberatory"),
)

_SEGMENT_OPTIONS: tuple[tuple[str, str], ...] = (
    ("", "—"),
    (TAXPAYER_SEGMENT_LARGE, "Large taxpayer"),
    (TAXPAYER_SEGMENT_MEDIUM, "Medium taxpayer"),
    (TAXPAYER_SEGMENT_DIVISIONAL, "Divisional"),
    (TAXPAYER_SEGMENT_SPECIALIZED, "Specialized"),
)

_CIT_RATE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("", "—"),
    (CIT_RATE_PROFILE_STANDARD, "Standard (30% + CAC)"),
    (CIT_RATE_PROFILE_SME, "SME (25% + CAC)"),
    (CIT_RATE_PROFILE_EXEMPT, "Exempt"),
)

_DSF_FORM_OPTIONS: tuple[tuple[str, str], ...] = (
    ("", "—"),
    (DSF_FORM_REAL, "DSF — Real"),
    (DSF_FORM_SIMPLIFIED, "DSF — Simplified"),
    (DSF_FORM_LIBERATORY, "DSF — Liberatory"),
    (DSF_FORM_NONE, "None"),
)

_DSF_SUBMISSION_OPTIONS: tuple[tuple[str, str], ...] = (
    ("", "—"),
    (DSF_SUBMISSION_EXCEL, "Excel upload"),
    (DSF_SUBMISSION_API, "API"),
    (DSF_SUBMISSION_MANUAL, "Manual"),
)

_VAT_BASIS_OPTIONS: tuple[tuple[str, str], ...] = (
    (VAT_BASIS_ACCRUAL, "Accrual (invoice) basis"),
    (VAT_BASIS_CASH, "Cash (payment) basis"),
)


class CompanyTaxProfileDialog(BaseDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        profile: CompanyTaxProfileDTO,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._company_name = company_name
        self._profile = profile
        self._saved_profile: CompanyTaxProfileDTO | None = None

        super().__init__(
            "Edit Tax Profile",
            parent,
            help_key="dialog.company_tax_profile",
        )
        self.setObjectName("CompanyTaxProfileDialog")
        apply_window_size(self, "modules.taxation.ui.company.tax.profile.dialog.0")

        intro = QLabel(
            "Configure the company's tax-compliance identity. These values drive "
            "obligation generation, return drafting, and DSF filing.",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        company_row = QLabel(f"Company: <b>{company_name}</b>", self)
        company_row.setTextFormat(Qt.TextFormat.RichText)
        self.body_layout.addWidget(company_row)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_identity_section())
        self.body_layout.addWidget(self._build_vat_section())
        self.body_layout.addWidget(self._build_cit_section())
        self.body_layout.addWidget(self._build_dsf_section())
        self.body_layout.addWidget(self._build_flags_section())
        self.body_layout.addStretch(1)

        self.button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        self.button_box.accepted.connect(self._handle_submit)
        save_btn = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn is not None:
            save_btn.setText("Save Profile")
            save_btn.setProperty("variant", "primary")
        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setProperty("variant", "secondary")

        self._populate_from_profile(profile)

    # ── Sections ─────────────────────────────────────────────────────

    def _build_identity_section(self) -> QFrame:
        frame = self._section_frame("Tax Identity")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._niu_edit = QLineEdit(frame)
        self._niu_edit.setMaxLength(50)
        self._niu_edit.setPlaceholderText("e.g. P012345678901A")
        grid.addWidget(QLabel("NIU"), 1, 0)
        grid.addWidget(self._niu_edit, 1, 1)

        self._tax_center_edit = QLineEdit(frame)
        self._tax_center_edit.setMaxLength(50)
        self._tax_center_edit.setPlaceholderText("e.g. DPMI_DOUALA")
        grid.addWidget(QLabel("Tax centre code"), 2, 0)
        grid.addWidget(self._tax_center_edit, 2, 1)

        self._segment_combo = self._make_combo(frame, _SEGMENT_OPTIONS)
        grid.addWidget(QLabel("Taxpayer segment"), 3, 0)
        grid.addWidget(self._segment_combo, 3, 1)

        self._regime_combo = self._make_combo(frame, _REGIME_OPTIONS)
        grid.addWidget(QLabel("Tax regime"), 4, 0)
        grid.addWidget(self._regime_combo, 4, 1)

        return frame

    def _build_vat_section(self) -> QFrame:
        frame = self._section_frame("VAT")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._vat_liable_check = QCheckBox("Company is VAT liable", frame)
        grid.addWidget(self._vat_liable_check, 1, 0, 1, 2)

        self._vat_effective_edit = QDateEdit(frame)
        self._vat_effective_edit.setCalendarPopup(True)
        self._vat_effective_edit.setDisplayFormat("yyyy-MM-dd")
        self._vat_effective_edit.setSpecialValueText("—")
        self._vat_effective_edit.setMinimumDate(QDate(2000, 1, 1))
        self._vat_effective_edit.setDate(self._vat_effective_edit.minimumDate())
        grid.addWidget(QLabel("VAT effective from"), 2, 0)
        grid.addWidget(self._vat_effective_edit, 2, 1)

        self._vat_basis_combo = self._make_combo(frame, _VAT_BASIS_OPTIONS)
        grid.addWidget(QLabel("VAT accounting basis"), 3, 0)
        grid.addWidget(self._vat_basis_combo, 3, 1)

        self._vat_pro_rata_spin = QDoubleSpinBox(frame)
        self._vat_pro_rata_spin.setRange(0.0, 100.0)
        self._vat_pro_rata_spin.setDecimals(2)
        self._vat_pro_rata_spin.setSuffix(" %")
        self._vat_pro_rata_spin.setSpecialValueText("N/A (fully taxable)")
        self._vat_pro_rata_spin.setValue(0.0)
        self._vat_pro_rata_spin.setToolTip(
            "Set to 0 when the company is fully taxable. "
            "Enter the agreed pro-rata % for partial-exemption filers."
        )
        grid.addWidget(QLabel("Pro-rata recovery %"), 4, 0)
        grid.addWidget(self._vat_pro_rata_spin, 4, 1)

        self._vat_liable_check.toggled.connect(
            self._vat_effective_edit.setEnabled
        )
        self._vat_liable_check.toggled.connect(
            self._vat_basis_combo.setEnabled
        )
        self._vat_liable_check.toggled.connect(
            self._vat_pro_rata_spin.setEnabled
        )

        return frame

    def _build_cit_section(self) -> QFrame:
        frame = self._section_frame("Corporate Income Tax")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._cit_rate_combo = self._make_combo(frame, _CIT_RATE_OPTIONS)
        grid.addWidget(QLabel("CIT rate profile"), 1, 0)
        grid.addWidget(self._cit_rate_combo, 1, 1)

        self._cit_installment_edit = QLineEdit(frame)
        self._cit_installment_edit.setMaxLength(50)
        self._cit_installment_edit.setPlaceholderText("e.g. QUARTERLY")
        grid.addWidget(QLabel("CIT installment profile"), 2, 0)
        grid.addWidget(self._cit_installment_edit, 2, 1)

        self._sme_check = QCheckBox("Qualifies as SME for tax purposes", frame)
        grid.addWidget(self._sme_check, 3, 0, 1, 2)

        return frame

    def _build_dsf_section(self) -> QFrame:
        frame = self._section_frame("DSF Filing")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._dsf_form_combo = self._make_combo(frame, _DSF_FORM_OPTIONS)
        grid.addWidget(QLabel("DSF form"), 1, 0)
        grid.addWidget(self._dsf_form_combo, 1, 1)

        self._dsf_submission_combo = self._make_combo(
            frame, _DSF_SUBMISSION_OPTIONS
        )
        grid.addWidget(QLabel("Submission mode"), 2, 0)
        grid.addWidget(self._dsf_submission_combo, 2, 1)

        return frame

    def _build_flags_section(self) -> QFrame:
        frame = self._section_frame("Other Settings")
        grid: QGridLayout = frame.layout()  # type: ignore[assignment]

        self._otp_check = QCheckBox("OTP-based filings enabled", frame)
        grid.addWidget(self._otp_check, 1, 0, 1, 2)

        self._wht_check = QCheckBox(
            "Withholding tax applies by default to vendor payments", frame
        )
        grid.addWidget(self._wht_check, 2, 0, 1, 2)

        return frame

    # ── Helpers ──────────────────────────────────────────────────────

    def _section_frame(self, title: str) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("DialogSection")
        frame.setProperty("card", True)
        grid = QGridLayout(frame)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        header = QLabel(title, frame)
        header.setObjectName("SectionHeader")
        header.setStyleSheet("font-weight: 600; color: #111827;")
        grid.addWidget(header, 0, 0, 1, 2)
        grid.setColumnStretch(1, 1)
        return frame

    @staticmethod
    def _make_combo(
        parent: QWidget, options: tuple[tuple[str, str], ...]
    ) -> QComboBox:
        combo = QComboBox(parent)
        for code, label in options:
            combo.addItem(label, code)
        return combo

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str | None) -> None:
        target = value or ""
        for index in range(combo.count()):
            if combo.itemData(index) == target:
                combo.setCurrentIndex(index)
                return
        combo.setCurrentIndex(0)

    def _populate_from_profile(self, profile: CompanyTaxProfileDTO) -> None:
        self._niu_edit.setText(profile.niu or "")
        self._tax_center_edit.setText(profile.tax_center_code or "")
        self._set_combo_value(self._segment_combo, profile.taxpayer_segment_code)
        self._set_combo_value(self._regime_combo, profile.tax_regime_code)

        self._vat_liable_check.setChecked(bool(profile.is_vat_liable))
        if profile.vat_effective_from is not None:
            d = profile.vat_effective_from
            self._vat_effective_edit.setDate(QDate(d.year, d.month, d.day))
        else:
            self._vat_effective_edit.setDate(self._vat_effective_edit.minimumDate())
        self._vat_effective_edit.setEnabled(bool(profile.is_vat_liable))

        vat_basis = getattr(profile, "vat_accounting_basis", VAT_BASIS_ACCRUAL) or VAT_BASIS_ACCRUAL
        self._set_combo_value(self._vat_basis_combo, vat_basis)
        self._vat_basis_combo.setEnabled(bool(profile.is_vat_liable))

        pro_rata = getattr(profile, "vat_pro_rata_percent", None)
        self._vat_pro_rata_spin.setValue(float(pro_rata) if pro_rata is not None else 0.0)
        self._vat_pro_rata_spin.setEnabled(bool(profile.is_vat_liable))

        self._set_combo_value(self._cit_rate_combo, profile.cit_rate_profile_code)
        self._cit_installment_edit.setText(profile.cit_installment_profile_code or "")
        self._sme_check.setChecked(bool(profile.sme_qualified_flag))

        self._set_combo_value(self._dsf_form_combo, profile.dsf_form_code)
        self._set_combo_value(
            self._dsf_submission_combo, profile.dsf_submission_mode_code
        )

        self._otp_check.setChecked(bool(profile.otp_enabled_flag))
        self._wht_check.setChecked(bool(profile.default_withholding_applicable_flag))

    def _build_command(self) -> UpsertCompanyTaxProfileCommand:
        vat_liable = self._vat_liable_check.isChecked()
        if vat_liable:
            qd = self._vat_effective_edit.date()
            vat_from: date | None = date(qd.year(), qd.month(), qd.day())
        else:
            vat_from = None

        pro_rata_val = self._vat_pro_rata_spin.value()
        pro_rata: float | None = pro_rata_val if pro_rata_val > 0.0 else None

        return UpsertCompanyTaxProfileCommand(
            niu=(self._niu_edit.text().strip() or None),
            tax_center_code=(self._tax_center_edit.text().strip() or None),
            taxpayer_segment_code=(self._segment_combo.currentData() or None),
            tax_regime_code=(self._regime_combo.currentData() or None),
            is_vat_liable=vat_liable,
            vat_effective_from=vat_from,
            vat_accounting_basis=self._vat_basis_combo.currentData() or VAT_BASIS_ACCRUAL,
            vat_pro_rata_percent=pro_rata,
            cit_rate_profile_code=(self._cit_rate_combo.currentData() or None),
            cit_installment_profile_code=(
                self._cit_installment_edit.text().strip() or None
            ),
            sme_qualified_flag=self._sme_check.isChecked(),
            dsf_form_code=(self._dsf_form_combo.currentData() or None),
            dsf_submission_mode_code=(
                self._dsf_submission_combo.currentData() or None
            ),
            otp_enabled_flag=self._otp_check.isChecked(),
            default_withholding_applicable_flag=self._wht_check.isChecked(),
        )

    def _handle_submit(self) -> None:
        self._error_label.hide()
        try:
            command = self._build_command()
            saved = self._service_registry.company_tax_profile_service.upsert(
                self._company_id, command
            )
        except ValidationError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Tax Profile", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(
                self,
                "Tax Profile",
                f"The tax profile could not be saved.\n\n{exc}",
            )
            return

        self._saved_profile = saved
        self.accept()

    def saved_profile(self) -> CompanyTaxProfileDTO | None:
        return self._saved_profile
