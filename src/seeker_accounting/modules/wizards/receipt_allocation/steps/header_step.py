"""Step 1 \u2014 Receipt header (customer, fin acct, date, amount, currency, reference)."""
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

from seeker_accounting.modules.wizards.receipt_allocation import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class HeaderStep(WizardStep):
    key = "header"
    title = "Receipt"
    subtitle = "Choose customer, deposit account, and amount received."

    def __init__(self) -> None:
        super().__init__()
        self._customer: QComboBox | None = None
        self._account: QComboBox | None = None
        self._date: QDateEdit | None = None
        self._currency: QLineEdit | None = None
        self._amount: QLineEdit | None = None
        self._reference: QLineEdit | None = None
        self._notes: QTextEdit | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        form = QFormLayout()
        self._customer = QComboBox(root)
        self._customer.setEditable(False)
        self._customer.currentIndexChanged.connect(self._on_customer_changed)
        form.addRow(QLabel("Customer:", root), self._customer)

        self._account = QComboBox(root)
        self._account.currentIndexChanged.connect(self._sync_currency_from_account)
        form.addRow(QLabel("Deposit account:", root), self._account)

        today = date.today()
        self._date = QDateEdit(root)
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("yyyy-MM-dd")
        self._date.setDate(QDate(today.year, today.month, today.day))
        form.addRow(QLabel("Receipt date:", root), self._date)

        self._currency = QLineEdit(root)
        self._currency.setMaxLength(3)
        self._currency.setPlaceholderText("USD")
        form.addRow(QLabel("Currency:", root), self._currency)

        self._amount = QLineEdit(root)
        self._amount.setPlaceholderText("0.00")
        form.addRow(QLabel("Amount received:", root), self._amount)

        self._reference = QLineEdit(root)
        self._reference.setPlaceholderText("Optional cheque/transfer reference")
        form.addRow(QLabel("Reference:", root), self._reference)

        self._notes = QTextEdit(root)
        self._notes.setMaximumHeight(60)
        form.addRow(QLabel("Notes:", root), self._notes)
        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def _on_customer_changed(self, _idx: int) -> None:
        # invalidate previous allocations when customer changes
        pass

    def _sync_currency_from_account(self, _idx: int) -> None:
        if self._account is None or self._currency is None:
            return
        d = self._account.currentData()
        if isinstance(d, dict) and not self._currency.text().strip():
            self._currency.setText(str(d.get("currency", "")))

    def load(self, context: WizardContext, state: WizardState) -> None:
        company_id = context.require_company_id()
        if self._customer is not None and self._customer.count() == 0:
            customers = context.service_registry.customer_service.list_customers(
                company_id, active_only=True
            )
            for c in customers:
                self._customer.addItem(
                    f"{c.customer_code} \u2014 {c.display_name}",
                    {"id": c.id, "name": c.display_name},
                )
            if not customers:
                self._customer.addItem("(no active customers)", None)
        if self._account is not None and self._account.count() == 0:
            accts = context.service_registry.financial_account_service.list_financial_accounts(
                company_id, active_only=True
            )
            for a in accts:
                self._account.addItem(
                    f"{a.account_code} \u2014 {a.name} [{a.currency_code}]",
                    {"id": a.id, "name": a.name, "currency": a.currency_code},
                )

        prior_customer = state.get(K.KEY_CUSTOMER_ID)
        if isinstance(prior_customer, int) and self._customer is not None:
            for i in range(self._customer.count()):
                d = self._customer.itemData(i)
                if isinstance(d, dict) and d.get("id") == prior_customer:
                    self._customer.setCurrentIndex(i)
                    break
        prior_account = state.get(K.KEY_FINANCIAL_ACCOUNT_ID)
        if isinstance(prior_account, int) and self._account is not None:
            for i in range(self._account.count()):
                d = self._account.itemData(i)
                if isinstance(d, dict) and d.get("id") == prior_account:
                    self._account.setCurrentIndex(i)
                    break
        if self._currency and state.get(K.KEY_CURRENCY_CODE):
            self._currency.setText(str(state[K.KEY_CURRENCY_CODE]))
        if self._amount and state.get(K.KEY_AMOUNT_RECEIVED):
            self._amount.setText(str(state[K.KEY_AMOUNT_RECEIVED]))
        if self._reference and state.get(K.KEY_REFERENCE_NUMBER):
            self._reference.setText(str(state[K.KEY_REFERENCE_NUMBER]))
        if self._notes and state.get(K.KEY_NOTES):
            self._notes.setPlainText(str(state[K.KEY_NOTES]))
        if self._date and state.get(K.KEY_RECEIPT_DATE):
            try:
                d = date.fromisoformat(str(state[K.KEY_RECEIPT_DATE]))
                self._date.setDate(QDate(d.year, d.month, d.day))
            except ValueError:
                pass

    def write_back(self, state: WizardState) -> None:
        prior_customer = state.get(K.KEY_CUSTOMER_ID)
        if self._customer is not None:
            d = self._customer.currentData()
            if isinstance(d, dict):
                state[K.KEY_CUSTOMER_ID] = int(d["id"])
                state[K.KEY_CUSTOMER_NAME] = str(d["name"])
        if self._account is not None:
            d = self._account.currentData()
            if isinstance(d, dict):
                state[K.KEY_FINANCIAL_ACCOUNT_ID] = int(d["id"])
                state[K.KEY_FINANCIAL_ACCOUNT_NAME] = str(d["name"])
                state[K.KEY_FINANCIAL_ACCOUNT_CURRENCY] = str(d["currency"])
        if self._date is not None:
            qd = self._date.date()
            state[K.KEY_RECEIPT_DATE] = date(qd.year(), qd.month(), qd.day()).isoformat()
        if self._currency is not None:
            state[K.KEY_CURRENCY_CODE] = self._currency.text().strip().upper()
        if self._amount is not None:
            state[K.KEY_AMOUNT_RECEIVED] = self._amount.text().strip()
        if self._reference is not None:
            state[K.KEY_REFERENCE_NUMBER] = self._reference.text().strip() or None
        if self._notes is not None:
            text = self._notes.toPlainText().strip()
            state[K.KEY_NOTES] = text or None

        # If customer changed, drop stale allocations
        new_customer = state.get(K.KEY_CUSTOMER_ID)
        if prior_customer is not None and new_customer != prior_customer:
            state[K.KEY_ALLOCATIONS] = []

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_CUSTOMER_ID), int):
            return StepValidationResult.fail("Pick a customer.")
        if not isinstance(state.get(K.KEY_FINANCIAL_ACCOUNT_ID), int):
            return StepValidationResult.fail("Pick a deposit account.")
        if not state.get(K.KEY_CURRENCY_CODE) or len(str(state.get(K.KEY_CURRENCY_CODE))) != 3:
            return StepValidationResult.fail("Enter a 3-letter currency code.")
        try:
            amount = Decimal(str(state.get(K.KEY_AMOUNT_RECEIVED) or ""))
        except (InvalidOperation, ValueError):
            return StepValidationResult.fail("Amount received must be a valid number.")
        if amount <= 0:
            return StepValidationResult.fail("Amount received must be greater than zero.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        cust = state.get(K.KEY_CUSTOMER_NAME) or "(no customer)"
        amount = state.get(K.KEY_AMOUNT_RECEIVED) or "0"
        cur = state.get(K.KEY_CURRENCY_CODE) or ""
        return f"Receipt of {amount} {cur} from {cust}."
