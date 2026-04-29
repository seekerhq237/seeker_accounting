"""Step 3 \u2014 Confirm and create the payment; optionally post."""
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

from seeker_accounting.modules.purchases.dto.supplier_payment_commands import (
    CreateSupplierPaymentCommand,
    SupplierPaymentAllocationCommand,
)
from seeker_accounting.modules.wizards.supplier_payment import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ConfirmStep(WizardStep):
    key = "confirm"
    title = "Confirm"
    subtitle = "Create the payment and optionally post it."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._supplier_lbl: QLabel | None = None
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
        self._supplier_lbl = QLabel("", root)
        self._account_lbl = QLabel("", root)
        self._amount_lbl = QLabel("", root)
        self._allocated_lbl = QLabel("", root)
        for w in (self._supplier_lbl, self._account_lbl, self._amount_lbl, self._allocated_lbl):
            w.setStyleSheet("color: #2E3848; font-size: 12px;")
        form.addRow(QLabel("Supplier:", root), self._supplier_lbl)
        form.addRow(QLabel("Account:", root), self._account_lbl)
        form.addRow(QLabel("Amount:", root), self._amount_lbl)
        form.addRow(QLabel("Allocated:", root), self._allocated_lbl)
        outer.addLayout(form)

        self._post_chk = QCheckBox("Post payment to GL after creation", root)
        self._post_chk.setChecked(True)
        outer.addWidget(self._post_chk)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._supplier_lbl is not None:
            self._supplier_lbl.setText(str(state.get(K.KEY_SUPPLIER_NAME) or ""))
        if self._account_lbl is not None:
            self._account_lbl.setText(str(state.get(K.KEY_FINANCIAL_ACCOUNT_NAME) or ""))
        if self._amount_lbl is not None:
            self._amount_lbl.setText(
                f"{state.get(K.KEY_AMOUNT_PAID)} {state.get(K.KEY_CURRENCY_CODE)}"
            )
        if self._allocated_lbl is not None:
            n = len(state.get(K.KEY_ALLOCATIONS) or [])
            self._allocated_lbl.setText(
                f"{state.get(K.KEY_TOTAL_ALLOCATED)} across {n} bill(s)"
            )

    def write_back(self, state: WizardState) -> None:
        state[K.KEY_POST_NOW] = bool(self._post_chk and self._post_chk.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if isinstance(state.get(K.KEY_PAYMENT_ID), int):
            return
        company_id = context.require_company_id()
        allocs = tuple(
            SupplierPaymentAllocationCommand(
                purchase_bill_id=int(a["bill_id"]),
                allocated_amount=Decimal(str(a["allocated"])),
            )
            for a in (state.get(K.KEY_ALLOCATIONS) or [])
        )
        cmd = CreateSupplierPaymentCommand(
            supplier_id=int(state[K.KEY_SUPPLIER_ID]),
            financial_account_id=int(state[K.KEY_FINANCIAL_ACCOUNT_ID]),
            payment_date=date.fromisoformat(str(state[K.KEY_PAYMENT_DATE])),
            currency_code=str(state[K.KEY_CURRENCY_CODE]),
            amount_paid=Decimal(str(state[K.KEY_AMOUNT_PAID])),
            reference_number=state.get(K.KEY_REFERENCE_NUMBER),
            notes=state.get(K.KEY_NOTES),
            allocations=allocs,
        )
        payment = context.service_registry.supplier_payment_service.create_draft_payment(
            company_id, cmd
        )
        state[K.KEY_PAYMENT_ID] = payment.id
        state[K.KEY_PAYMENT_NUMBER] = payment.payment_number
        state[K.KEY_PAYMENT_STATUS] = payment.status_code

        if state.get(K.KEY_POST_NOW):
            result = context.service_registry.supplier_payment_posting_service.post_payment(
                company_id, payment.id, actor_user_id=context.user_id
            )
            state[K.KEY_POSTED_JOURNAL_ENTRY_ID] = result.journal_entry_id
            state[K.KEY_PAYMENT_STATUS] = "posted"

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        pid = state.get(K.KEY_PAYMENT_ID)
        if pid:
            status = state.get(K.KEY_PAYMENT_STATUS) or "draft"
            return f"Payment {state.get(K.KEY_PAYMENT_NUMBER) or '#' + str(pid)} \u2014 {status}."
        return "Create payment."
