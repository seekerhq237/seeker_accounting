"""Step 1 \u2014 Payment header (supplier, fin acct, date, amount, currency, reference)."""
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

from seeker_accounting.modules.wizards.supplier_payment import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class HeaderStep(WizardStep):
    key = "header"
    title = "Payment"
    subtitle = "Choose supplier, source account, and amount paid."

    def __init__(self) -> None:
        super().__init__()
        self._supplier: QComboBox | None = None
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
        self._supplier = QComboBox(root)
        form.addRow(QLabel("Supplier:", root), self._supplier)

        self._account = QComboBox(root)
        self._account.currentIndexChanged.connect(self._sync_currency_from_account)
        form.addRow(QLabel("Source account:", root), self._account)

        today = date.today()
        self._date = QDateEdit(root)
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("yyyy-MM-dd")
        self._date.setDate(QDate(today.year, today.month, today.day))
        form.addRow(QLabel("Payment date:", root), self._date)

        self._currency = QLineEdit(root)
        self._currency.setMaxLength(3)
        self._currency.setPlaceholderText("USD")
        form.addRow(QLabel("Currency:", root), self._currency)

        self._amount = QLineEdit(root)
        self._amount.setPlaceholderText("0.00")
        form.addRow(QLabel("Amount paid:", root), self._amount)

        self._reference = QLineEdit(root)
        self._reference.setPlaceholderText("Optional reference")
        form.addRow(QLabel("Reference:", root), self._reference)

        self._notes = QTextEdit(root)
        self._notes.setMaximumHeight(60)
        form.addRow(QLabel("Notes:", root), self._notes)
        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def _sync_currency_from_account(self, _idx: int) -> None:
        if self._account is None or self._currency is None:
            return
        d = self._account.currentData()
        if isinstance(d, dict) and not self._currency.text().strip():
            self._currency.setText(str(d.get("currency", "")))

    def load(self, context: WizardContext, state: WizardState) -> None:
        company_id = context.require_company_id()
        if self._supplier is not None and self._supplier.count() == 0:
            suppliers = context.service_registry.supplier_service.list_suppliers(
                company_id, active_only=True
            )
            for s in suppliers:
                self._supplier.addItem(
                    f"{s.supplier_code} \u2014 {s.display_name}",
                    {"id": s.id, "name": s.display_name},
                )
            if not suppliers:
                self._supplier.addItem("(no active suppliers)", None)
        if self._account is not None and self._account.count() == 0:
            accts = context.service_registry.financial_account_service.list_financial_accounts(
                company_id, active_only=True
            )
            for a in accts:
                self._account.addItem(
                    f"{a.account_code} \u2014 {a.name} [{a.currency_code}]",
                    {"id": a.id, "name": a.name, "currency": a.currency_code},
                )

        prior_supplier = state.get(K.KEY_SUPPLIER_ID)
        if isinstance(prior_supplier, int) and self._supplier is not None:
            for i in range(self._supplier.count()):
                d = self._supplier.itemData(i)
                if isinstance(d, dict) and d.get("id") == prior_supplier:
                    self._supplier.setCurrentIndex(i)
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
        if self._amount and state.get(K.KEY_AMOUNT_PAID):
            self._amount.setText(str(state[K.KEY_AMOUNT_PAID]))
        if self._reference and state.get(K.KEY_REFERENCE_NUMBER):
            self._reference.setText(str(state[K.KEY_REFERENCE_NUMBER]))
        if self._notes and state.get(K.KEY_NOTES):
            self._notes.setPlainText(str(state[K.KEY_NOTES]))
        if self._date and state.get(K.KEY_PAYMENT_DATE):
            try:
                d = date.fromisoformat(str(state[K.KEY_PAYMENT_DATE]))
                self._date.setDate(QDate(d.year, d.month, d.day))
            except ValueError:
                pass

    def write_back(self, state: WizardState) -> None:
        prior_supplier = state.get(K.KEY_SUPPLIER_ID)
        if self._supplier is not None:
            d = self._supplier.currentData()
            if isinstance(d, dict):
                state[K.KEY_SUPPLIER_ID] = int(d["id"])
                state[K.KEY_SUPPLIER_NAME] = str(d["name"])
        if self._account is not None:
            d = self._account.currentData()
            if isinstance(d, dict):
                state[K.KEY_FINANCIAL_ACCOUNT_ID] = int(d["id"])
                state[K.KEY_FINANCIAL_ACCOUNT_NAME] = str(d["name"])
                state[K.KEY_FINANCIAL_ACCOUNT_CURRENCY] = str(d["currency"])
        if self._date is not None:
            qd = self._date.date()
            state[K.KEY_PAYMENT_DATE] = date(qd.year(), qd.month(), qd.day()).isoformat()
        if self._currency is not None:
            state[K.KEY_CURRENCY_CODE] = self._currency.text().strip().upper()
        if self._amount is not None:
            state[K.KEY_AMOUNT_PAID] = self._amount.text().strip()
        if self._reference is not None:
            state[K.KEY_REFERENCE_NUMBER] = self._reference.text().strip() or None
        if self._notes is not None:
            text = self._notes.toPlainText().strip()
            state[K.KEY_NOTES] = text or None

        new_supplier = state.get(K.KEY_SUPPLIER_ID)
        if prior_supplier is not None and new_supplier != prior_supplier:
            state[K.KEY_ALLOCATIONS] = []

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_SUPPLIER_ID), int):
            return StepValidationResult.fail("Pick a supplier.")
        if not isinstance(state.get(K.KEY_FINANCIAL_ACCOUNT_ID), int):
            return StepValidationResult.fail("Pick a source account.")
        if not state.get(K.KEY_CURRENCY_CODE) or len(str(state.get(K.KEY_CURRENCY_CODE))) != 3:
            return StepValidationResult.fail("Enter a 3-letter currency code.")
        try:
            amount = Decimal(str(state.get(K.KEY_AMOUNT_PAID) or ""))
        except (InvalidOperation, ValueError):
            return StepValidationResult.fail("Amount paid must be a valid number.")
        if amount <= 0:
            return StepValidationResult.fail("Amount paid must be greater than zero.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        sup = state.get(K.KEY_SUPPLIER_NAME) or "(no supplier)"
        amount = state.get(K.KEY_AMOUNT_PAID) or "0"
        cur = state.get(K.KEY_CURRENCY_CODE) or ""
        return f"Payment of {amount} {cur} to {sup}."
