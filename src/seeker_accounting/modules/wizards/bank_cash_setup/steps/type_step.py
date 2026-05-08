"""Step 1 — Pick account type and currency."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.bank_cash_setup import state_keys as K
from seeker_accounting.modules.wizards.bank_cash_setup.catalog import ACCOUNT_TYPE_OPTIONS
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class TypeStep(WizardStep):
    key = "type"
    title = "Type & currency"
    subtitle = "Choose the kind of financial account and its operating currency."

    def __init__(self) -> None:
        super().__init__()
        self._type: QComboBox | None = None
        self._currency: QComboBox | None = None
        self._desc: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._type = QComboBox(root)
        for code, label, _detail in ACCOUNT_TYPE_OPTIONS:
            self._type.addItem(label, code)
        form.addRow(QLabel("Account type:", root), self._type)

        self._currency = QComboBox(root)
        form.addRow(QLabel("Currency:", root), self._currency)

        self._desc = QLabel(root)
        self._desc.setWordWrap(True)
        self._desc.setObjectName("WizardMutedText")
        form.addRow(QLabel("", root), self._desc)

        outer.addLayout(form)
        outer.addStretch(1)
        self._type.currentIndexChanged.connect(self._on_type_changed)
        return root

    def _on_type_changed(self, _idx: int) -> None:
        if self._desc is None or self._type is None:
            return
        code = self._type.currentData()
        for c, _label, detail in ACCOUNT_TYPE_OPTIONS:
            if c == code:
                self._desc.setText(detail)
                return
        self._desc.setText("")

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._currency is not None and self._currency.count() == 0:
            for opt in context.service_registry.reference_data_service.list_active_currencies():
                self._currency.addItem(f"{opt.code} \u2014 {opt.name}", opt.code)
            prior_cc = state.get(K.KEY_CURRENCY_CODE)
            if isinstance(prior_cc, str):
                idx = self._currency.findData(prior_cc)
                if idx >= 0:
                    self._currency.setCurrentIndex(idx)
        if self._type is not None:
            prior_t = state.get(K.KEY_ACCOUNT_TYPE_CODE)
            if isinstance(prior_t, str):
                idx = self._type.findData(prior_t)
                if idx >= 0:
                    self._type.setCurrentIndex(idx)
            self._on_type_changed(self._type.currentIndex())

    def write_back(self, state: WizardState) -> None:
        if self._type is not None:
            data = self._type.currentData()
            state[K.KEY_ACCOUNT_TYPE_CODE] = str(data) if data else None
        if self._currency is not None:
            data = self._currency.currentData()
            state[K.KEY_CURRENCY_CODE] = str(data) if data else None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_ACCOUNT_TYPE_CODE):
            return StepValidationResult.fail("Pick an account type.")
        if not state.get(K.KEY_CURRENCY_CODE):
            return StepValidationResult.fail("Pick a currency.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        t = state.get(K.KEY_ACCOUNT_TYPE_CODE)
        cc = state.get(K.KEY_CURRENCY_CODE)
        if t and cc:
            return f"{t} account in {cc}"
        return None
