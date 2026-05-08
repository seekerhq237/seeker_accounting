"""Step 3 — DSF & flags + persist via CompanyTaxProfileService.upsert."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.taxation.dto.company_tax_profile_dto import (
    UpsertCompanyTaxProfileCommand,
)
from seeker_accounting.modules.wizards.tax_regime import state_keys as K
from seeker_accounting.modules.wizards.tax_regime.catalog import (
    DSF_FORM_OPTIONS,
    DSF_SUBMISSION_OPTIONS,
)
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


class DsfFlagsStep(WizardStep):
    key = "dsf_flags"
    title = "DSF & flags"
    subtitle = "Statistical & fiscal return form, withholding posture, and saving."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._dsf_form: QComboBox | None = None
        self._dsf_submission: QComboBox | None = None
        self._otp_flag: QCheckBox | None = None
        self._wht_flag: QCheckBox | None = None
        self._summary: QLabel | None = None
        self._result: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._dsf_form = QComboBox(root)
        _populate(self._dsf_form, DSF_FORM_OPTIONS)
        form.addRow(QLabel("DSF form:", root), self._dsf_form)

        self._dsf_submission = QComboBox(root)
        _populate(self._dsf_submission, DSF_SUBMISSION_OPTIONS)
        form.addRow(QLabel("DSF submission mode:", root), self._dsf_submission)

        self._otp_flag = QCheckBox("Two-factor (OTP) enabled for tax submissions", root)
        form.addRow(QLabel("", root), self._otp_flag)

        self._wht_flag = QCheckBox(
            "Default withholding applicable on supplier invoices", root
        )
        form.addRow(QLabel("", root), self._wht_flag)

        outer.addLayout(form)

        self._summary = QLabel(root)
        self._summary.setWordWrap(True)
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._summary)

        self._result = QLabel(root)
        self._result.setObjectName("WizardSuccessText")
        outer.addWidget(self._result)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._dsf_form is not None:
            _set_combo_value(self._dsf_form, state.get(K.KEY_DSF_FORM_CODE))
        if self._dsf_submission is not None:
            _set_combo_value(self._dsf_submission, state.get(K.KEY_DSF_SUBMISSION_MODE_CODE))
        if self._otp_flag is not None:
            self._otp_flag.setChecked(bool(state.get(K.KEY_OTP_ENABLED_FLAG)))
        if self._wht_flag is not None:
            self._wht_flag.setChecked(
                bool(state.get(K.KEY_DEFAULT_WITHHOLDING_APPLICABLE_FLAG))
            )

        if self._summary is not None:
            self._summary.setText(self._build_summary_html(state))
        if self._result is not None and state.get(K.KEY_PROFILE_PERSISTED):
            self._result.setText("Tax profile saved.")

    def _build_summary_html(self, state: WizardState) -> str:
        return (
            f"<b>Regime:</b> {state.get(K.KEY_TAX_REGIME_CODE) or '(not set)'}<br>"
            f"<b>NIU:</b> {state.get(K.KEY_NIU) or '(not set)'}<br>"
            f"<b>Tax center:</b> {state.get(K.KEY_TAX_CENTER_CODE) or '(not set)'}<br>"
            f"<b>Segment:</b> {state.get(K.KEY_TAXPAYER_SEGMENT_CODE) or '(not set)'}<br>"
            f"<b>VAT liable:</b> {'yes' if state.get(K.KEY_IS_VAT_LIABLE) else 'no'}"
            + (
                f" (from {state.get(K.KEY_VAT_EFFECTIVE_FROM)})"
                if state.get(K.KEY_IS_VAT_LIABLE) and state.get(K.KEY_VAT_EFFECTIVE_FROM)
                else ""
            )
            + "<br>"
            f"<b>CIT profile:</b> {state.get(K.KEY_CIT_RATE_PROFILE_CODE) or '(not set)'}"
            + (" + SME" if state.get(K.KEY_SME_QUALIFIED_FLAG) else "")
            + "<br>"
            f"<b>CIT installments:</b> {state.get(K.KEY_CIT_INSTALLMENT_PROFILE_CODE) or '(not set)'}"
        )

    def write_back(self, state: WizardState) -> None:
        if self._dsf_form is not None:
            state[K.KEY_DSF_FORM_CODE] = _combo_value(self._dsf_form)
        if self._dsf_submission is not None:
            state[K.KEY_DSF_SUBMISSION_MODE_CODE] = _combo_value(self._dsf_submission)
        if self._otp_flag is not None:
            state[K.KEY_OTP_ENABLED_FLAG] = bool(self._otp_flag.isChecked())
        if self._wht_flag is not None:
            state[K.KEY_DEFAULT_WITHHOLDING_APPLICABLE_FLAG] = bool(
                self._wht_flag.isChecked()
            )

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_PROFILE_PERSISTED):
            return
        company_id = context.require_company_id()
        cmd = UpsertCompanyTaxProfileCommand(
            niu=state.get(K.KEY_NIU),
            tax_center_code=state.get(K.KEY_TAX_CENTER_CODE),
            taxpayer_segment_code=state.get(K.KEY_TAXPAYER_SEGMENT_CODE),
            tax_regime_code=state.get(K.KEY_TAX_REGIME_CODE),
            is_vat_liable=bool(state.get(K.KEY_IS_VAT_LIABLE)),
            vat_effective_from=state.get(K.KEY_VAT_EFFECTIVE_FROM),
            cit_rate_profile_code=state.get(K.KEY_CIT_RATE_PROFILE_CODE),
            cit_installment_profile_code=state.get(K.KEY_CIT_INSTALLMENT_PROFILE_CODE),
            sme_qualified_flag=bool(state.get(K.KEY_SME_QUALIFIED_FLAG)),
            dsf_form_code=state.get(K.KEY_DSF_FORM_CODE),
            dsf_submission_mode_code=state.get(K.KEY_DSF_SUBMISSION_MODE_CODE),
            otp_enabled_flag=bool(state.get(K.KEY_OTP_ENABLED_FLAG)),
            default_withholding_applicable_flag=bool(
                state.get(K.KEY_DEFAULT_WITHHOLDING_APPLICABLE_FLAG)
            ),
        )
        context.service_registry.company_tax_profile_service.upsert(
            company_id, cmd, actor_user_id=context.user_id
        )
        state[K.KEY_PROFILE_PERSISTED] = True

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        return "Profile saved." if state.get(K.KEY_PROFILE_PERSISTED) else "Ready to save."
