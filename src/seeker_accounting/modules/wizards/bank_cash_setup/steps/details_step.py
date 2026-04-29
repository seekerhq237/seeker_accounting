"""Step 2 — Details (code, name, GL account, bank fields)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.bank_cash_setup import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class DetailsStep(WizardStep):
    key = "details"
    title = "Details"
    subtitle = "Code, display name, linked GL account, and bank metadata."

    def __init__(self) -> None:
        super().__init__()
        self._code: QLineEdit | None = None
        self._name: QLineEdit | None = None
        self._gl_account: QComboBox | None = None
        self._bank_name: QLineEdit | None = None
        self._bank_no: QLineEdit | None = None
        self._bank_branch: QLineEdit | None = None
        self._bank_label_name: QLabel | None = None
        self._bank_label_no: QLabel | None = None
        self._bank_label_branch: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._code = QLineEdit(root)
        self._code.setMaxLength(20)
        self._code.setPlaceholderText("e.g. BNK-001")
        form.addRow(QLabel("Account code:", root), self._code)

        self._name = QLineEdit(root)
        self._name.setMaxLength(120)
        self._name.setPlaceholderText("e.g. Main operating account")
        form.addRow(QLabel("Display name:", root), self._name)

        self._gl_account = QComboBox(root)
        form.addRow(QLabel("Linked GL account:", root), self._gl_account)

        self._bank_label_name = QLabel("Bank name:", root)
        self._bank_name = QLineEdit(root)
        self._bank_name.setMaxLength(120)
        form.addRow(self._bank_label_name, self._bank_name)

        self._bank_label_no = QLabel("Bank account #:", root)
        self._bank_no = QLineEdit(root)
        self._bank_no.setMaxLength(60)
        form.addRow(self._bank_label_no, self._bank_no)

        self._bank_label_branch = QLabel("Branch:", root)
        self._bank_branch = QLineEdit(root)
        self._bank_branch.setMaxLength(120)
        form.addRow(self._bank_label_branch, self._bank_branch)

        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def _set_bank_fields_visible(self, visible: bool) -> None:
        for w in (
            self._bank_label_name, self._bank_name,
            self._bank_label_no, self._bank_no,
            self._bank_label_branch, self._bank_branch,
        ):
            if w is not None:
                w.setVisible(visible)

    def load(self, context: WizardContext, state: WizardState) -> None:
        company_id = context.require_company_id()
        if self._gl_account is not None and self._gl_account.count() == 0:
            self._gl_account.addItem("(pick GL account)", None)
            for a in context.service_registry.chart_of_accounts_service.list_accounts(
                company_id, active_only=True
            ):
                if a.is_active and a.allow_manual_posting:
                    self._gl_account.addItem(f"{a.account_code} \u2014 {a.account_name}", a.id)
        prior_gl = state.get(K.KEY_GL_ACCOUNT_ID)
        if self._gl_account is not None and isinstance(prior_gl, int):
            idx = self._gl_account.findData(prior_gl)
            if idx >= 0:
                self._gl_account.setCurrentIndex(idx)
        if self._code is not None and state.get(K.KEY_ACCOUNT_CODE):
            self._code.setText(str(state[K.KEY_ACCOUNT_CODE]))
        if self._name is not None and state.get(K.KEY_ACCOUNT_NAME):
            self._name.setText(str(state[K.KEY_ACCOUNT_NAME]))
        if self._bank_name is not None and state.get(K.KEY_BANK_NAME):
            self._bank_name.setText(str(state[K.KEY_BANK_NAME]))
        if self._bank_no is not None and state.get(K.KEY_BANK_ACCOUNT_NUMBER):
            self._bank_no.setText(str(state[K.KEY_BANK_ACCOUNT_NUMBER]))
        if self._bank_branch is not None and state.get(K.KEY_BANK_BRANCH):
            self._bank_branch.setText(str(state[K.KEY_BANK_BRANCH]))
        self._set_bank_fields_visible(state.get(K.KEY_ACCOUNT_TYPE_CODE) == "bank")

    def write_back(self, state: WizardState) -> None:
        if self._code is not None:
            state[K.KEY_ACCOUNT_CODE] = self._code.text().strip() or None
        if self._name is not None:
            state[K.KEY_ACCOUNT_NAME] = self._name.text().strip() or None
        if self._gl_account is not None:
            data = self._gl_account.currentData()
            state[K.KEY_GL_ACCOUNT_ID] = int(data) if isinstance(data, int) else None
        if state.get(K.KEY_ACCOUNT_TYPE_CODE) == "bank":
            if self._bank_name is not None:
                state[K.KEY_BANK_NAME] = self._bank_name.text().strip() or None
            if self._bank_no is not None:
                state[K.KEY_BANK_ACCOUNT_NUMBER] = self._bank_no.text().strip() or None
            if self._bank_branch is not None:
                state[K.KEY_BANK_BRANCH] = self._bank_branch.text().strip() or None
        else:
            state[K.KEY_BANK_NAME] = None
            state[K.KEY_BANK_ACCOUNT_NUMBER] = None
            state[K.KEY_BANK_BRANCH] = None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_ACCOUNT_CODE):
            return StepValidationResult.fail("Account code is required.")
        if not state.get(K.KEY_ACCOUNT_NAME):
            return StepValidationResult.fail("Display name is required.")
        if not isinstance(state.get(K.KEY_GL_ACCOUNT_ID), int):
            return StepValidationResult.fail("Pick a linked GL account.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        code = state.get(K.KEY_ACCOUNT_CODE)
        name = state.get(K.KEY_ACCOUNT_NAME)
        if code and name:
            return f"{code} \u2014 {name}"
        return None
