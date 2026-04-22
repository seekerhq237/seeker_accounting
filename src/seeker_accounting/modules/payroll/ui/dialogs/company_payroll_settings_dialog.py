from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_setup_commands import (
    UpsertCompanyPayrollSettingsCommand,
)
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error

_log = logging.getLogger(__name__)

_PAY_FREQUENCIES = [
    ("monthly",    "Monthly"),
    ("bi_monthly", "Bi-Monthly (twice a month)"),
    ("bi_weekly",  "Bi-Weekly (every 2 weeks)"),
    ("weekly",     "Weekly"),
    ("daily",      "Daily"),
]

_CNPS_REGIMES = [
    ("",            "— Not specified —"),
    ("GENERAL",     "General Regime"),
    ("AGRICULTURAL","Agricultural Regime"),
]

_ACCIDENT_CLASSES = [
    ("",        "— Not specified —"),
    ("CLASS_1", "Class 1 (1.75%)"),
    ("CLASS_2", "Class 2 (2.50%)"),
    ("CLASS_3", "Class 3 (5.00%)"),
    ("CLASS_4", "Class 4 (7.00%)"),
]

_OVERTIME_MODES = [
    ("",             "— Not specified —"),
    ("CNPS_BAREME",  "CNPS Bareme"),
    ("COMPANY_POLICY","Company Policy"),
]

_BIK_MODES = [
    ("",             "— Not specified —"),
    ("DGI_TABLE",    "DGI Table"),
    ("COMPANY_POLICY","Company Policy"),
]


class CompanyPayrollSettingsDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sr = service_registry
        self._company_id = company_id

        self.setWindowTitle(f"Company Payroll Settings — {company_name}")
        self.setModal(True)
        self.resize(520, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ── Core settings card ────────────────────────────────────────────────
        core_card = QFrame(self)
        core_card.setObjectName("PageCard")
        core_form = QFormLayout(core_card)
        core_form.setContentsMargins(18, 16, 18, 16)
        core_form.setSpacing(10)
        core_hdr = QLabel("Core Settings", core_card)
        core_hdr.setObjectName("CardTitle")
        core_form.addRow(core_hdr)

        self._freq_combo = QComboBox(core_card)
        for code, label in _PAY_FREQUENCIES:
            self._freq_combo.addItem(label, code)
        core_form.addRow("Default Pay Frequency *", self._freq_combo)

        self._currency_combo = QComboBox(core_card)
        core_form.addRow("Default Payroll Currency *", self._currency_combo)

        layout.addWidget(core_card)

        # ── Cameroon statutory settings ───────────────────────────────────────
        stat_card = QFrame(self)
        stat_card.setObjectName("PageCard")
        stat_form = QFormLayout(stat_card)
        stat_form.setContentsMargins(18, 16, 18, 16)
        stat_form.setSpacing(10)
        stat_hdr = QLabel("Cameroon Statutory Settings", stat_card)
        stat_hdr.setObjectName("CardTitle")
        stat_form.addRow(stat_hdr)

        self._pack_input = QLineEdit(stat_card)
        self._pack_input.setPlaceholderText("e.g. CMR_2024_V1")
        stat_form.addRow("Statutory Pack Version", self._pack_input)

        self._cnps_combo = QComboBox(stat_card)
        for code, label in _CNPS_REGIMES:
            self._cnps_combo.addItem(label, code)
        stat_form.addRow("CNPS Regime", self._cnps_combo)

        self._accident_combo = QComboBox(stat_card)
        for code, label in _ACCIDENT_CLASSES:
            self._accident_combo.addItem(label, code)
        stat_form.addRow("Accident Risk Class", self._accident_combo)

        self._overtime_combo = QComboBox(stat_card)
        for code, label in _OVERTIME_MODES:
            self._overtime_combo.addItem(label, code)
        stat_form.addRow("Overtime Policy Mode", self._overtime_combo)

        self._bik_combo = QComboBox(stat_card)
        for code, label in _BIK_MODES:
            self._bik_combo.addItem(label, code)
        stat_form.addRow("Benefits in Kind Mode", self._bik_combo)

        layout.addWidget(stat_card)

        # ── Payroll number format ─────────────────────────────────────────────
        num_card = QFrame(self)
        num_card.setObjectName("PageCard")
        num_form = QFormLayout(num_card)
        num_form.setContentsMargins(18, 16, 18, 16)
        num_form.setSpacing(10)
        num_hdr = QLabel("Payroll Number Format", num_card)
        num_hdr.setObjectName("CardTitle")
        num_form.addRow(num_hdr)

        self._prefix_input = QLineEdit(num_card)
        self._prefix_input.setPlaceholderText("e.g. PAY")
        self._prefix_input.setMaxLength(20)
        num_form.addRow("Prefix", self._prefix_input)

        self._padding_spin = QSpinBox(num_card)
        self._padding_spin.setMinimum(1)
        self._padding_spin.setMaximum(10)
        self._padding_spin.setValue(5)
        self._padding_spin.setSpecialValueText("None")
        num_form.addRow("Number Padding Width", self._padding_spin)

        layout.addWidget(num_card)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        # ── Bottom row: Save/Cancel right ──────────────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)

        bottom_row.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        bottom_row.addWidget(buttons)

        layout.addLayout(bottom_row)

        self._load_currencies()
        self._load_existing()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.company_payroll_settings", dialog=True)

    def _load_currencies(self) -> None:
        try:
            currencies = self._sr.reference_data_service.list_active_currencies()
        except Exception:
            currencies = []
        self._currency_combo.clear()
        self._currency_combo.addItem("— Select currency —", None)
        for c in currencies:
            self._currency_combo.addItem(f"{c.code} — {c.name}", c.code)
        if not currencies:
            self._currency_combo.addItem("(No active currencies available)", None)

    def _load_existing(self) -> None:
        try:
            s = self._sr.payroll_setup_service.get_company_payroll_settings(self._company_id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        if s is None:
            return
        idx = self._freq_combo.findData(s.default_pay_frequency_code)
        if idx >= 0:
            self._freq_combo.setCurrentIndex(idx)
        self._set_combo_value(self._currency_combo, s.default_payroll_currency_code)
        self._pack_input.setText(s.statutory_pack_version_code or "")
        self._set_combo_value(self._cnps_combo, s.cnps_regime_code or "")
        self._set_combo_value(self._accident_combo, s.accident_risk_class_code or "")
        self._set_combo_value(self._overtime_combo, s.overtime_policy_mode_code or "")
        self._set_combo_value(self._bik_combo, s.benefit_in_kind_policy_mode_code or "")
        self._prefix_input.setText(s.payroll_number_prefix or "")
        if s.payroll_number_padding_width:
            self._padding_spin.setValue(s.payroll_number_padding_width)

    def _set_combo_value(self, combo: QComboBox, value: str | None) -> None:
        if value is None:
            return
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _submit(self) -> None:
        self._error_label.hide()
        freq = self._freq_combo.currentData()
        currency = self._currency_combo.currentData()

        if not freq:
            self._show_error("Default pay frequency is required.")
            return
        if not currency:
            self._show_error("Default payroll currency is required.")
            return

        prefix = self._prefix_input.text().strip() or None
        padding = self._padding_spin.value() if self._padding_spin.value() > 1 else None
        pack = self._pack_input.text().strip() or None
        cnps = self._cnps_combo.currentData() or None
        accident = self._accident_combo.currentData() or None
        overtime = self._overtime_combo.currentData() or None
        bik = self._bik_combo.currentData() or None

        try:
            self._sr.payroll_setup_service.upsert_company_payroll_settings(
                self._company_id,
                UpsertCompanyPayrollSettingsCommand(
                    default_pay_frequency_code=freq,
                    default_payroll_currency_code=currency,
                    statutory_pack_version_code=pack,
                    cnps_regime_code=cnps,
                    accident_risk_class_code=accident,
                    overtime_policy_mode_code=overtime,
                    benefit_in_kind_policy_mode_code=bik,
                    payroll_number_prefix=prefix,
                    payroll_number_padding_width=padding,
                ),
            )
            self.accept()
        except ValidationError as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
