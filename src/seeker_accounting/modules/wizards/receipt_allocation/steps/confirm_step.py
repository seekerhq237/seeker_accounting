"""Step 3 \u2014 Confirm and create the receipt; optionally post."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.sales.dto.customer_receipt_commands import (
    CreateCustomerReceiptCommand,
    CustomerReceiptAllocationCommand,
)
from seeker_accounting.modules.wizards.receipt_allocation import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ConfirmStep(WizardStep):
    key = "confirm"
    title = "Confirm"
    subtitle = "Create the receipt and optionally post it."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._customer_lbl: QLabel | None = None
        self._account_lbl: QLabel | None = None
        self._amount_lbl: QLabel | None = None
        self._allocated_lbl: QLabel | None = None
        self._post_chk: QCheckBox | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        form = QFormLayout()
        self._customer_lbl = QLabel("", root)
        self._account_lbl = QLabel("", root)
        self._amount_lbl = QLabel("", root)
        self._allocated_lbl = QLabel("", root)
        for w in (self._customer_lbl, self._account_lbl, self._amount_lbl, self._allocated_lbl):
            w.setStyleSheet("color: #2E3848; font-size: 12px;")
        form.addRow(QLabel("Customer:", root), self._customer_lbl)
        form.addRow(QLabel("Account:", root), self._account_lbl)
        form.addRow(QLabel("Amount:", root), self._amount_lbl)
        form.addRow(QLabel("Allocated:", root), self._allocated_lbl)
        outer.addLayout(form)

        self._post_chk = QCheckBox("Post receipt to GL after creation", root)
        self._post_chk.setChecked(True)
        outer.addWidget(self._post_chk)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._customer_lbl is not None:
            self._customer_lbl.setText(str(state.get(K.KEY_CUSTOMER_NAME) or ""))
        if self._account_lbl is not None:
            self._account_lbl.setText(str(state.get(K.KEY_FINANCIAL_ACCOUNT_NAME) or ""))
        if self._amount_lbl is not None:
            self._amount_lbl.setText(
                f"{state.get(K.KEY_AMOUNT_RECEIVED)} {state.get(K.KEY_CURRENCY_CODE)}"
            )
        if self._allocated_lbl is not None:
            n = len(state.get(K.KEY_ALLOCATIONS) or [])
            self._allocated_lbl.setText(
                f"{state.get(K.KEY_TOTAL_ALLOCATED)} across {n} invoice(s)"
            )

    def write_back(self, state: WizardState) -> None:
        state[K.KEY_POST_NOW] = bool(self._post_chk and self._post_chk.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if isinstance(state.get(K.KEY_RECEIPT_ID), int):
            return
        company_id = context.require_company_id()
        allocs = tuple(
            CustomerReceiptAllocationCommand(
                sales_invoice_id=int(a["invoice_id"]),
                allocated_amount=Decimal(str(a["allocated"])),
            )
            for a in (state.get(K.KEY_ALLOCATIONS) or [])
        )
        cmd = CreateCustomerReceiptCommand(
            customer_id=int(state[K.KEY_CUSTOMER_ID]),
            financial_account_id=int(state[K.KEY_FINANCIAL_ACCOUNT_ID]),
            receipt_date=date.fromisoformat(str(state[K.KEY_RECEIPT_DATE])),
            currency_code=str(state[K.KEY_CURRENCY_CODE]),
            amount_received=Decimal(str(state[K.KEY_AMOUNT_RECEIVED])),
            reference_number=state.get(K.KEY_REFERENCE_NUMBER),
            notes=state.get(K.KEY_NOTES),
            allocations=allocs,
        )
        receipt = context.service_registry.customer_receipt_service.create_draft_receipt(
            company_id, cmd
        )
        state[K.KEY_RECEIPT_ID] = receipt.id
        state[K.KEY_RECEIPT_NUMBER] = receipt.receipt_number
        state[K.KEY_RECEIPT_STATUS] = receipt.status_code

        if state.get(K.KEY_POST_NOW):
            result = context.service_registry.customer_receipt_posting_service.post_receipt(
                company_id, receipt.id, actor_user_id=context.user_id
            )
            state[K.KEY_POSTED_JOURNAL_ENTRY_ID] = result.journal_entry_id
            state[K.KEY_RECEIPT_STATUS] = "posted"

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        rid = state.get(K.KEY_RECEIPT_ID)
        if rid:
            status = state.get(K.KEY_RECEIPT_STATUS) or "draft"
            return f"Receipt {state.get(K.KEY_RECEIPT_NUMBER) or '#' + str(rid)} \u2014 {status}."
        return "Create receipt."
