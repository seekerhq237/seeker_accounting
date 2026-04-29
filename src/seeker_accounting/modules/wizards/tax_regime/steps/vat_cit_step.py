"""Step 2 — VAT and CIT obligations."""
from __future__ import annotations

from datetime import date as date_type

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.tax_regime import state_keys as K
from seeker_accounting.modules.wizards.tax_regime.catalog import CIT_RATE_PROFILE_OPTIONS
from seeker_accounting.modules.wizards.tax_regime.steps.identity_step import (
    _combo_value,
    _populate,
    _set_combo_value,
)
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class VatCitStep(WizardStep):
    key = "vat_cit"
    title = "VAT & CIT"
    subtitle = "Declare VAT liability and corporate income tax profile."

    def __init__(self) -> None:
        super().__init__()
        self._is_vat: QCheckBox | None = None
        self._vat_from: QDateEdit | None = None
        self._cit_profile: QComboBox | None = None
        self._cit_installments: QComboBox | None = None
        self._sme_flag: QCheckBox | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._is_vat = QCheckBox("VAT liable", root)
        form.addRow(QLabel("VAT:", root), self._is_vat)

        self._vat_from = QDateEdit(root)
        self._vat_from.setCalendarPopup(True)
        self._vat_from.setDisplayFormat("yyyy-MM-dd")
        self._vat_from.setDate(QDate.currentDate())
        form.addRow(QLabel("VAT effective from:", root), self._vat_from)

        self._cit_profile = QComboBox(root)
        _populate(self._cit_profile, CIT_RATE_PROFILE_OPTIONS)
        form.addRow(QLabel("CIT rate profile:", root), self._cit_profile)

        # Installment profile is open-ended free string per project convention; combo with a
        # small canonical set + custom retained from profile.
        self._cit_installments = QComboBox(root)
        self._cit_installments.setEditable(True)
        for code in ("(not set)", "MONTHLY", "QUARTERLY", "ANNUAL"):
            self._cit_installments.addItem(code)
        form.addRow(QLabel("CIT installment cadence:", root), self._cit_installments)

        self._sme_flag = QCheckBox("SME-qualified for reduced CIT", root)
        form.addRow(QLabel("", root), self._sme_flag)

        outer.addLayout(form)
        outer.addStretch(1)
        self._is_vat.toggled.connect(self._on_vat_toggled)
        return root

    def _on_vat_toggled(self, checked: bool) -> None:
        if self._vat_from is not None:
            self._vat_from.setEnabled(checked)

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._is_vat is not None:
            self._is_vat.setChecked(bool(state.get(K.KEY_IS_VAT_LIABLE)))
        if self._vat_from is not None:
            value = state.get(K.KEY_VAT_EFFECTIVE_FROM)
            if isinstance(value, date_type):
                self._vat_from.setDate(QDate(value.year, value.month, value.day))
            self._vat_from.setEnabled(bool(state.get(K.KEY_IS_VAT_LIABLE)))
        if self._cit_profile is not None:
            _set_combo_value(self._cit_profile, state.get(K.KEY_CIT_RATE_PROFILE_CODE))
        if self._cit_installments is not None:
            value = state.get(K.KEY_CIT_INSTALLMENT_PROFILE_CODE)
            if value:
                idx = self._cit_installments.findText(str(value))
                if idx >= 0:
                    self._cit_installments.setCurrentIndex(idx)
                else:
                    self._cit_installments.setEditText(str(value))
            else:
                self._cit_installments.setCurrentIndex(0)
        if self._sme_flag is not None:
            self._sme_flag.setChecked(bool(state.get(K.KEY_SME_QUALIFIED_FLAG)))

    def write_back(self, state: WizardState) -> None:
        if self._is_vat is not None:
            state[K.KEY_IS_VAT_LIABLE] = bool(self._is_vat.isChecked())
        if self._vat_from is not None and state.get(K.KEY_IS_VAT_LIABLE):
            qd = self._vat_from.date()
            state[K.KEY_VAT_EFFECTIVE_FROM] = date_type(qd.year(), qd.month(), qd.day())
        else:
            state[K.KEY_VAT_EFFECTIVE_FROM] = None
        if self._cit_profile is not None:
            state[K.KEY_CIT_RATE_PROFILE_CODE] = _combo_value(self._cit_profile)
        if self._cit_installments is not None:
            text = self._cit_installments.currentText().strip()
            state[K.KEY_CIT_INSTALLMENT_PROFILE_CODE] = (
                None if not text or text == "(not set)" else text
            )
        if self._sme_flag is not None:
            state[K.KEY_SME_QUALIFIED_FLAG] = bool(self._sme_flag.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if state.get(K.KEY_IS_VAT_LIABLE) and not state.get(K.KEY_VAT_EFFECTIVE_FROM):
            return StepValidationResult.fail("Pick the VAT effective-from date.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        parts: list[str] = []
        parts.append("VAT" if state.get(K.KEY_IS_VAT_LIABLE) else "no VAT")
        cit = state.get(K.KEY_CIT_RATE_PROFILE_CODE)
        if cit:
            parts.append(f"CIT {cit}")
        return ", ".join(parts) if parts else None
