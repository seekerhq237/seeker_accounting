"""Step 3 — Confirm: create draft purchase credit note, optionally post."""
from __future__ import annotations

from datetime import date as _date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.purchases.dto.purchase_credit_note_commands import (
    CreatePurchaseCreditNoteCommand,
    PurchaseCreditNoteLineCommand,
)
from seeker_accounting.modules.wizards.purchase_credit_note import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ConfirmStep(WizardStep):
    key = "confirm"
    title = "Confirm"
    subtitle = "Review and commit the purchase credit note."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._summary: QLabel | None = None
        self._post_check: QCheckBox | None = None
        self._result_label: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._summary = QLabel(root)
        self._summary.setWordWrap(True)
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._summary)

        self._post_check = QCheckBox("Post immediately after creating the draft", root)
        outer.addWidget(self._post_check)

        self._result_label = QLabel(root)
        self._result_label.setStyleSheet("color: #2a7;")
        outer.addWidget(self._result_label)

        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._summary is not None:
            lines = state.get(K.KEY_LINES) or []
            total = Decimal(0)
            for ln in lines:
                try:
                    total += Decimal(str(ln.get("quantity") or "0")) * Decimal(str(ln.get("unit_cost") or "0"))
                except Exception:
                    continue
            html = (
                f"<b>Supplier:</b> #{state.get(K.KEY_SUPPLIER_ID)}<br>"
                f"<b>Date:</b> {state.get(K.KEY_CREDIT_DATE)}<br>"
                f"<b>Currency:</b> {state.get(K.KEY_CURRENCY_CODE)}<br>"
                f"<b>Source bill:</b> {state.get(K.KEY_SOURCE_BILL_ID) or '(none)'}<br>"
                f"<b>Lines:</b> {len(lines)} \u00b7 <b>Subtotal:</b> {total:.2f}"
            )
            self._summary.setText(html)
        if self._post_check is not None and state.get(K.KEY_POST_NOW):
            self._post_check.setChecked(True)
        if self._result_label is not None:
            cnid = state.get(K.KEY_CREDIT_NOTE_ID)
            if cnid:
                jeid = state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID)
                msg = f"Draft purchase credit note #{cnid} created."
                if jeid:
                    msg += f" Posted as journal entry #{jeid}."
                self._result_label.setText(msg)

    def write_back(self, state: WizardState) -> None:
        if self._post_check is not None:
            state[K.KEY_POST_NOW] = bool(self._post_check.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        company_id = context.require_company_id()
        cnid = state.get(K.KEY_CREDIT_NOTE_ID)
        post_now = bool(state.get(K.KEY_POST_NOW))

        if not isinstance(cnid, int):
            credit_date = _date.fromisoformat(str(state[K.KEY_CREDIT_DATE]))
            line_cmds: list[PurchaseCreditNoteLineCommand] = []
            for ln in state.get(K.KEY_LINES) or []:
                qty = Decimal(str(ln.get("quantity") or "0"))
                unit_cost = Decimal(str(ln.get("unit_cost") or "0"))
                subtotal = (qty * unit_cost).quantize(Decimal("0.01"))
                line_cmds.append(
                    PurchaseCreditNoteLineCommand(
                        description=str(ln.get("description") or ""),
                        quantity=qty,
                        unit_cost=unit_cost,
                        expense_account_id=int(ln["expense_account_id"]),
                        tax_code_id=ln.get("tax_code_id") if isinstance(ln.get("tax_code_id"), int) else None,
                        line_subtotal_amount=subtotal,
                        contract_id=None,
                        project_id=None,
                        project_job_id=None,
                        project_cost_code_id=None,
                    )
                )
            cmd = CreatePurchaseCreditNoteCommand(
                company_id=company_id,
                supplier_id=int(state[K.KEY_SUPPLIER_ID]),
                supplier_credit_reference=state.get(K.KEY_SUPPLIER_CREDIT_REFERENCE),
                credit_date=credit_date,
                currency_code=str(state[K.KEY_CURRENCY_CODE]),
                exchange_rate=None,
                reason_text=state.get(K.KEY_REASON_TEXT),
                source_bill_id=state.get(K.KEY_SOURCE_BILL_ID),
                contract_id=None,
                project_id=None,
                lines=line_cmds,
                actor_user_id=context.user_id,
            )
            cn = context.service_registry.purchase_credit_note_service.create_draft_credit_note(cmd)
            state[K.KEY_CREDIT_NOTE_ID] = cn.id
            state[K.KEY_CREDIT_NOTE_STATUS] = cn.status_code
            cnid = cn.id

        if post_now and not state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID):
            result = context.service_registry.purchase_credit_note_posting_service.post_credit_note(
                company_id, int(cnid), context.user_id
            )
            state[K.KEY_POSTED_JOURNAL_ENTRY_ID] = result.journal_entry_id
            state[K.KEY_CREDIT_NOTE_STATUS] = result.status_code

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        cnid = state.get(K.KEY_CREDIT_NOTE_ID)
        if cnid:
            jeid = state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID)
            return f"Purchase credit note #{cnid}" + (f" posted as JE #{jeid}" if jeid else " (draft)")
        return "Ready to create purchase credit note."
