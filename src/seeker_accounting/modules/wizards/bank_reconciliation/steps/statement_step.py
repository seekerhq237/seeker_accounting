"""Step 1 \u2014 Pick a financial account and capture statement details, create the session."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.treasury.dto.bank_reconciliation_commands import (
    CreateReconciliationSessionCommand,
)
from seeker_accounting.modules.wizards.bank_reconciliation import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class StatementStep(WizardStep):
    key = "statement"
    title = "Statement"
    subtitle = "Pick the bank account and enter the statement closing balance."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._account: QComboBox | None = None
        self._end_date: QDateEdit | None = None
        self._ending_balance: QLineEdit | None = None
        self._notes: QTextEdit | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        intro = QLabel(
            "After this step a draft reconciliation session is created. Use "
            "the Treasury workspace to record matches against statement lines, "
            "then come back to finalize.",
            root,
        )
        intro.setWordWrap(True)
        intro.setObjectName("WizardMutedText")
        outer.addWidget(intro)

        form = QFormLayout()
        self._account = QComboBox(root)
        form.addRow(QLabel("Financial account:", root), self._account)

        today = date.today()
        self._end_date = QDateEdit(root)
        self._end_date.setCalendarPopup(True)
        self._end_date.setDisplayFormat("yyyy-MM-dd")
        self._end_date.setDate(QDate(today.year, today.month, today.day))
        form.addRow(QLabel("Statement end date:", root), self._end_date)

        self._ending_balance = QLineEdit(root)
        self._ending_balance.setPlaceholderText("0.00")
        form.addRow(QLabel("Ending balance:", root), self._ending_balance)

        self._notes = QTextEdit(root)
        self._notes.setMaximumHeight(60)
        self._notes.setPlaceholderText("Optional notes")
        form.addRow(QLabel("Notes:", root), self._notes)
        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._account is None:
            return
        if self._account.count() == 0:
            company_id = context.require_company_id()
            accounts = context.service_registry.financial_account_service.list_financial_accounts(
                company_id, active_only=True
            )
            for a in accounts:
                self._account.addItem(
                    f"{a.account_code} \u2014 {a.name}",
                    {"id": a.id, "name": a.name},
                )
            if not accounts:
                self._account.addItem("(no active financial accounts)", None)

        prior = state.get(K.KEY_FINANCIAL_ACCOUNT_ID)
        if isinstance(prior, int):
            for i in range(self._account.count()):
                d = self._account.itemData(i)
                if isinstance(d, dict) and d.get("id") == prior:
                    self._account.setCurrentIndex(i)
                    break

    def write_back(self, state: WizardState) -> None:
        if self._account is not None:
            d = self._account.currentData()
            if isinstance(d, dict):
                state[K.KEY_FINANCIAL_ACCOUNT_ID] = int(d["id"])
                state[K.KEY_FINANCIAL_ACCOUNT_NAME] = str(d["name"])
        if self._end_date is not None:
            qd = self._end_date.date()
            state[K.KEY_STATEMENT_END_DATE] = date(qd.year(), qd.month(), qd.day()).isoformat()
        if self._ending_balance is not None:
            state[K.KEY_STATEMENT_ENDING_BALANCE] = self._ending_balance.text().strip()
        if self._notes is not None:
            text = self._notes.toPlainText().strip()
            state[K.KEY_NOTES] = text or None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_FINANCIAL_ACCOUNT_ID), int):
            return StepValidationResult.fail("Pick a financial account.")
        try:
            Decimal(str(state.get(K.KEY_STATEMENT_ENDING_BALANCE) or ""))
        except (InvalidOperation, ValueError):
            return StepValidationResult.fail("Ending balance must be a valid amount.")
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if isinstance(state.get(K.KEY_SESSION_ID), int):
            return
        company_id = context.require_company_id()
        cmd = CreateReconciliationSessionCommand(
            financial_account_id=int(state[K.KEY_FINANCIAL_ACCOUNT_ID]),
            statement_end_date=date.fromisoformat(str(state[K.KEY_STATEMENT_END_DATE])),
            statement_ending_balance=Decimal(str(state[K.KEY_STATEMENT_ENDING_BALANCE])),
            notes=state.get(K.KEY_NOTES),
        )
        session_dto = context.service_registry.bank_reconciliation_service.create_reconciliation_session(
            company_id, cmd, actor_user_id=context.user_id
        )
        state[K.KEY_SESSION_ID] = session_dto.id
        state[K.KEY_SESSION_STATUS] = session_dto.status_code

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        if state.get(K.KEY_SESSION_ID):
            return f"Draft session #{state.get(K.KEY_SESSION_ID)} created."
        name = state.get(K.KEY_FINANCIAL_ACCOUNT_NAME) or "(no account)"
        return f"Open a reconciliation session for {name}."
