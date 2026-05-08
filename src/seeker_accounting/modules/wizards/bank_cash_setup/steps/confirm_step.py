"""Step 3 — Confirm: create the financial account."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.treasury.dto.financial_account_commands import (
    CreateFinancialAccountCommand,
)
from seeker_accounting.modules.wizards.bank_cash_setup import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ConfirmStep(WizardStep):
    key = "confirm"
    title = "Confirm"
    subtitle = "Review and create the financial account."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._summary: QLabel | None = None
        self._result: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
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
        if self._summary is not None:
            html = (
                f"<b>Type:</b> {state.get(K.KEY_ACCOUNT_TYPE_CODE)}<br>"
                f"<b>Currency:</b> {state.get(K.KEY_CURRENCY_CODE)}<br>"
                f"<b>Code:</b> {state.get(K.KEY_ACCOUNT_CODE)}<br>"
                f"<b>Name:</b> {state.get(K.KEY_ACCOUNT_NAME)}<br>"
                f"<b>GL account:</b> #{state.get(K.KEY_GL_ACCOUNT_ID)}"
            )
            if state.get(K.KEY_ACCOUNT_TYPE_CODE) == "bank":
                html += (
                    f"<br><b>Bank:</b> {state.get(K.KEY_BANK_NAME) or '(none)'}"
                    f"<br><b>Account #:</b> {state.get(K.KEY_BANK_ACCOUNT_NUMBER) or '(none)'}"
                    f"<br><b>Branch:</b> {state.get(K.KEY_BANK_BRANCH) or '(none)'}"
                )
            self._summary.setText(html)
        if self._result is not None and state.get(K.KEY_FINANCIAL_ACCOUNT_ID):
            self._result.setText(
                f"Financial account #{state[K.KEY_FINANCIAL_ACCOUNT_ID]} created."
            )

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if isinstance(state.get(K.KEY_FINANCIAL_ACCOUNT_ID), int):
            return
        company_id = context.require_company_id()
        cmd = CreateFinancialAccountCommand(
            account_code=str(state[K.KEY_ACCOUNT_CODE]),
            name=str(state[K.KEY_ACCOUNT_NAME]),
            financial_account_type_code=str(state[K.KEY_ACCOUNT_TYPE_CODE]),
            gl_account_id=int(state[K.KEY_GL_ACCOUNT_ID]),
            currency_code=str(state[K.KEY_CURRENCY_CODE]),
            bank_name=state.get(K.KEY_BANK_NAME),
            bank_account_number=state.get(K.KEY_BANK_ACCOUNT_NUMBER),
            bank_branch=state.get(K.KEY_BANK_BRANCH),
        )
        fa = context.service_registry.financial_account_service.create_financial_account(
            company_id, cmd
        )
        state[K.KEY_FINANCIAL_ACCOUNT_ID] = fa.id

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        faid = state.get(K.KEY_FINANCIAL_ACCOUNT_ID)
        return f"Financial account #{faid}" if faid else "Ready to create."
