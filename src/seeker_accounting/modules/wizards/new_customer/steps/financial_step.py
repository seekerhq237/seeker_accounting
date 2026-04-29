"""Step 3 \u2014 Financial settings, then create the customer."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.customers.dto.customer_commands import (
    CreateCustomerCommand,
)
from seeker_accounting.modules.wizards.new_customer import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class FinancialStep(WizardStep):
    key = "financial"
    title = "Financial"
    subtitle = "Payment terms, tax identifier, credit limit."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._payment_term: QComboBox | None = None
        self._tax_id: QLineEdit | None = None
        self._credit_limit: QLineEdit | None = None
        self._notes: QTextEdit | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._payment_term = QComboBox(root)
        form.addRow(QLabel("Payment term:", root), self._payment_term)

        self._tax_id = QLineEdit(root)
        self._tax_id.setPlaceholderText("e.g. VAT number")
        form.addRow(QLabel("Tax identifier:", root), self._tax_id)

        self._credit_limit = QLineEdit(root)
        self._credit_limit.setPlaceholderText("0.00")
        form.addRow(QLabel("Credit limit:", root), self._credit_limit)

        self._notes = QTextEdit(root)
        self._notes.setMaximumHeight(60)
        form.addRow(QLabel("Notes:", root), self._notes)
        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._payment_term is not None and self._payment_term.count() == 0:
            company_id = context.require_company_id()
            self._payment_term.addItem("(none)", None)
            for t in context.service_registry.reference_data_service.list_payment_terms(
                company_id, active_only=True
            ):
                self._payment_term.addItem(f"{t.code} \u2014 {t.name} ({t.days_due}d)", t.id)
            prior = state.get(K.KEY_PAYMENT_TERM_ID)
            if isinstance(prior, int):
                idx = self._payment_term.findData(prior)
                if idx >= 0:
                    self._payment_term.setCurrentIndex(idx)
        if self._tax_id is not None and state.get(K.KEY_TAX_IDENTIFIER):
            self._tax_id.setText(str(state[K.KEY_TAX_IDENTIFIER]))
        if self._credit_limit is not None and state.get(K.KEY_CREDIT_LIMIT_AMOUNT):
            self._credit_limit.setText(str(state[K.KEY_CREDIT_LIMIT_AMOUNT]))
        if self._notes is not None and state.get(K.KEY_NOTES):
            self._notes.setPlainText(str(state[K.KEY_NOTES]))

    def write_back(self, state: WizardState) -> None:
        if self._payment_term is not None:
            data = self._payment_term.currentData()
            state[K.KEY_PAYMENT_TERM_ID] = int(data) if isinstance(data, int) else None
        if self._tax_id is not None:
            state[K.KEY_TAX_IDENTIFIER] = self._tax_id.text().strip() or None
        if self._credit_limit is not None:
            state[K.KEY_CREDIT_LIMIT_AMOUNT] = self._credit_limit.text().strip() or None
        if self._notes is not None:
            state[K.KEY_NOTES] = self._notes.toPlainText().strip() or None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        cl = state.get(K.KEY_CREDIT_LIMIT_AMOUNT)
        if cl:
            try:
                if Decimal(str(cl)) < 0:
                    return StepValidationResult.fail("Credit limit cannot be negative.")
            except (InvalidOperation, ValueError):
                return StepValidationResult.fail("Credit limit must be a valid number.")
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if isinstance(state.get(K.KEY_CUSTOMER_ID), int):
            return
        company_id = context.require_company_id()
        cl_raw = state.get(K.KEY_CREDIT_LIMIT_AMOUNT)
        cmd = CreateCustomerCommand(
            customer_code=str(state[K.KEY_CUSTOMER_CODE]),
            display_name=str(state[K.KEY_DISPLAY_NAME]),
            legal_name=state.get(K.KEY_LEGAL_NAME),
            customer_group_id=state.get(K.KEY_CUSTOMER_GROUP_ID),
            payment_term_id=state.get(K.KEY_PAYMENT_TERM_ID),
            tax_identifier=state.get(K.KEY_TAX_IDENTIFIER),
            phone=state.get(K.KEY_PHONE),
            email=state.get(K.KEY_EMAIL),
            address_line_1=state.get(K.KEY_ADDRESS_LINE_1),
            address_line_2=state.get(K.KEY_ADDRESS_LINE_2),
            city=state.get(K.KEY_CITY),
            region=state.get(K.KEY_REGION),
            country_code=state.get(K.KEY_COUNTRY_CODE),
            credit_limit_amount=Decimal(str(cl_raw)) if cl_raw else None,
            notes=state.get(K.KEY_NOTES),
        )
        customer = context.service_registry.customer_service.create_customer(company_id, cmd)
        state[K.KEY_CUSTOMER_ID] = customer.id

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        cid = state.get(K.KEY_CUSTOMER_ID)
        if cid:
            return f"Customer #{cid} created."
        return f"Create customer {state.get(K.KEY_DISPLAY_NAME) or ''}".strip()
