"""Step 1 — Identity & registration: NIU, tax center, segment, regime."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.tax_regime import state_keys as K
from seeker_accounting.modules.wizards.tax_regime.catalog import (
    TAXPAYER_SEGMENT_OPTIONS,
    TAX_REGIME_OPTIONS,
)
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


def _populate(combo: QComboBox, options: tuple[tuple[str, str, str], ...]) -> None:
    combo.clear()
    combo.addItem("(not set)", None)
    for code, label, _ in options:
        combo.addItem(label, code)


def _set_combo_value(combo: QComboBox, value: object) -> None:
    if not isinstance(value, str):
        combo.setCurrentIndex(0)
        return
    idx = combo.findData(value)
    combo.setCurrentIndex(idx if idx >= 0 else 0)


def _combo_value(combo: QComboBox) -> str | None:
    data = combo.currentData()
    return str(data) if isinstance(data, str) and data else None


class IdentityStep(WizardStep):
    key = "identity"
    title = "Identity & registration"
    subtitle = "Capture taxpayer registration information."

    def __init__(self) -> None:
        super().__init__()
        self._niu: QLineEdit | None = None
        self._tax_center: QLineEdit | None = None
        self._segment: QComboBox | None = None
        self._regime: QComboBox | None = None
        self._loaded_from_profile = False

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._niu = QLineEdit(root)
        self._niu.setMaxLength(50)
        self._niu.setPlaceholderText("Numéro d'Identifiant Unique")
        form.addRow(QLabel("NIU:", root), self._niu)

        self._tax_center = QLineEdit(root)
        self._tax_center.setMaxLength(50)
        self._tax_center.setPlaceholderText("e.g. CIME-DOUALA-CENTRE")
        form.addRow(QLabel("Tax center:", root), self._tax_center)

        self._segment = QComboBox(root)
        _populate(self._segment, TAXPAYER_SEGMENT_OPTIONS)
        form.addRow(QLabel("Taxpayer segment:", root), self._segment)

        self._regime = QComboBox(root)
        _populate(self._regime, TAX_REGIME_OPTIONS)
        form.addRow(QLabel("Tax regime:", root), self._regime)

        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        # Hydrate from existing profile on first entry only — afterwards trust user edits.
        if not self._loaded_from_profile:
            try:
                profile = context.service_registry.company_tax_profile_service.get_or_default(
                    context.require_company_id()
                )
            except Exception:
                profile = None
            if profile is not None:
                state.setdefault(K.KEY_NIU, profile.niu)
                state.setdefault(K.KEY_TAX_CENTER_CODE, profile.tax_center_code)
                state.setdefault(K.KEY_TAXPAYER_SEGMENT_CODE, profile.taxpayer_segment_code)
                state.setdefault(K.KEY_TAX_REGIME_CODE, profile.tax_regime_code)
                state.setdefault(K.KEY_IS_VAT_LIABLE, profile.is_vat_liable)
                state.setdefault(K.KEY_VAT_EFFECTIVE_FROM, profile.vat_effective_from)
                state.setdefault(K.KEY_CIT_RATE_PROFILE_CODE, profile.cit_rate_profile_code)
                state.setdefault(K.KEY_CIT_INSTALLMENT_PROFILE_CODE, profile.cit_installment_profile_code)
                state.setdefault(K.KEY_SME_QUALIFIED_FLAG, profile.sme_qualified_flag)
                state.setdefault(K.KEY_DSF_FORM_CODE, profile.dsf_form_code)
                state.setdefault(K.KEY_DSF_SUBMISSION_MODE_CODE, profile.dsf_submission_mode_code)
                state.setdefault(K.KEY_OTP_ENABLED_FLAG, profile.otp_enabled_flag)
                state.setdefault(
                    K.KEY_DEFAULT_WITHHOLDING_APPLICABLE_FLAG,
                    profile.default_withholding_applicable_flag,
                )
            self._loaded_from_profile = True

        if self._niu is not None and state.get(K.KEY_NIU):
            self._niu.setText(str(state[K.KEY_NIU]))
        if self._tax_center is not None and state.get(K.KEY_TAX_CENTER_CODE):
            self._tax_center.setText(str(state[K.KEY_TAX_CENTER_CODE]))
        if self._segment is not None:
            _set_combo_value(self._segment, state.get(K.KEY_TAXPAYER_SEGMENT_CODE))
        if self._regime is not None:
            _set_combo_value(self._regime, state.get(K.KEY_TAX_REGIME_CODE))

    def write_back(self, state: WizardState) -> None:
        if self._niu is not None:
            state[K.KEY_NIU] = self._niu.text().strip() or None
        if self._tax_center is not None:
            state[K.KEY_TAX_CENTER_CODE] = self._tax_center.text().strip() or None
        if self._segment is not None:
            state[K.KEY_TAXPAYER_SEGMENT_CODE] = _combo_value(self._segment)
        if self._regime is not None:
            state[K.KEY_TAX_REGIME_CODE] = _combo_value(self._regime)

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_TAX_REGIME_CODE):
            return StepValidationResult.fail("Pick a tax regime.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        regime = state.get(K.KEY_TAX_REGIME_CODE)
        seg = state.get(K.KEY_TAXPAYER_SEGMENT_CODE)
        if regime:
            return f"{regime}" + (f" / {seg}" if seg else "")
        return None
