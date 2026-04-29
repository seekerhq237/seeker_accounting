"""Step 1 — Header (customer, date, currency, optional source invoice, reason)."""
from __future__ import annotations

from datetime import date as _date

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

from seeker_accounting.modules.wizards.sales_credit_note import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class HeaderStep(WizardStep):
    key = "header"
    title = "Header"
    subtitle = "Customer, credit date, currency, and optional source invoice."

    def __init__(self) -> None:
        super().__init__()
        self._customer: QComboBox | None = None
        self._date: QDateEdit | None = None
        self._currency: QLineEdit | None = None
        self._source_invoice: QComboBox | None = None
        self._reason: QTextEdit | None = None
        self._reference: QLineEdit | None = None
        self._loaded_customer_id: int | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._customer = QComboBox(root)
        form.addRow(QLabel("Customer:", root), self._customer)

        self._date = QDateEdit(root)
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("yyyy-MM-dd")
        self._date.setDate(QDate.currentDate())
        form.addRow(QLabel("Credit date:", root), self._date)

        self._currency = QLineEdit(root)
        self._currency.setMaxLength(3)
        self._currency.setPlaceholderText("USD")
        form.addRow(QLabel("Currency:", root), self._currency)

        self._source_invoice = QComboBox(root)
        form.addRow(QLabel("Source invoice (optional):", root), self._source_invoice)

        self._reference = QLineEdit(root)
        self._reference.setPlaceholderText("External reference (optional)")
        form.addRow(QLabel("Reference:", root), self._reference)

        self._reason = QTextEdit(root)
        self._reason.setMaximumHeight(60)
        form.addRow(QLabel("Reason:", root), self._reason)

        outer.addLayout(form)
        outer.addStretch(1)

        if self._customer is not None:
            self._customer.currentIndexChanged.connect(self._on_customer_changed)
        return root

    def _on_customer_changed(self, _idx: int) -> None:
        # Refresh source-invoice list when the customer changes.
        if self._source_invoice is None or self._customer is None:
            return
        self._source_invoice.clear()
        self._source_invoice.addItem("(none)", None)

    def load(self, context: WizardContext, state: WizardState) -> None:
        company_id = context.require_company_id()
        if self._customer is not None and self._customer.count() == 0:
            self._customer.addItem("(pick a customer)", None)
            for c in context.service_registry.customer_service.list_customers(
                company_id, active_only=True
            ):
                self._customer.addItem(f"{c.customer_code} \u2014 {c.display_name}", c.id)
            prior = state.get(K.KEY_CUSTOMER_ID)
            if isinstance(prior, int):
                idx = self._customer.findData(prior)
                if idx >= 0:
                    self._customer.setCurrentIndex(idx)
        # Refresh source invoice list against current customer
        cust_id = self._customer.currentData() if self._customer is not None else None
        if self._source_invoice is not None:
            self._source_invoice.clear()
            self._source_invoice.addItem("(none)", None)
            if isinstance(cust_id, int):
                for inv in context.service_registry.sales_invoice_service.list_open_invoices_for_customer(
                    company_id, cust_id
                ):
                    self._source_invoice.addItem(
                        f"{inv.invoice_number} \u2014 {inv.total_amount} {inv.currency_code}",
                        inv.id,
                    )
                prior_inv = state.get(K.KEY_SOURCE_INVOICE_ID)
                if isinstance(prior_inv, int):
                    idx = self._source_invoice.findData(prior_inv)
                    if idx >= 0:
                        self._source_invoice.setCurrentIndex(idx)
            self._loaded_customer_id = cust_id if isinstance(cust_id, int) else None
        if self._date is not None:
            d = state.get(K.KEY_CREDIT_DATE)
            if isinstance(d, str):
                qd = QDate.fromString(d, "yyyy-MM-dd")
                if qd.isValid():
                    self._date.setDate(qd)
        if self._currency is not None:
            self._currency.setText(str(state.get(K.KEY_CURRENCY_CODE) or "USD"))
        if self._reference is not None and state.get(K.KEY_REFERENCE_NUMBER):
            self._reference.setText(str(state[K.KEY_REFERENCE_NUMBER]))
        if self._reason is not None and state.get(K.KEY_REASON_TEXT):
            self._reason.setPlainText(str(state[K.KEY_REASON_TEXT]))

    def write_back(self, state: WizardState) -> None:
        if self._customer is not None:
            data = self._customer.currentData()
            new_cust = int(data) if isinstance(data, int) else None
            if new_cust != state.get(K.KEY_CUSTOMER_ID):
                # customer changed — invalidate stale source-invoice + lines
                state[K.KEY_SOURCE_INVOICE_ID] = None
                state[K.KEY_LINES] = []
            state[K.KEY_CUSTOMER_ID] = new_cust
        if self._date is not None:
            state[K.KEY_CREDIT_DATE] = self._date.date().toString("yyyy-MM-dd")
        if self._currency is not None:
            state[K.KEY_CURRENCY_CODE] = self._currency.text().strip().upper() or "USD"
        if self._source_invoice is not None:
            data = self._source_invoice.currentData()
            state[K.KEY_SOURCE_INVOICE_ID] = int(data) if isinstance(data, int) else None
        if self._reference is not None:
            state[K.KEY_REFERENCE_NUMBER] = self._reference.text().strip() or None
        if self._reason is not None:
            state[K.KEY_REASON_TEXT] = self._reason.toPlainText().strip() or None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_CUSTOMER_ID), int):
            return StepValidationResult.fail("Pick a customer.")
        cc = state.get(K.KEY_CURRENCY_CODE)
        if not cc or len(str(cc)) != 3:
            return StepValidationResult.fail("Currency must be a 3-letter ISO code.")
        d = state.get(K.KEY_CREDIT_DATE)
        if not d:
            return StepValidationResult.fail("Credit date is required.")
        try:
            _date.fromisoformat(str(d))
        except ValueError:
            return StepValidationResult.fail("Credit date is invalid.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        cust = state.get(K.KEY_CUSTOMER_ID)
        d = state.get(K.KEY_CREDIT_DATE)
        if cust and d:
            return f"Credit note for customer #{cust} on {d}"
        return None
