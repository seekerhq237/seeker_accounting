"""Step 3 — Confirm and create the OPENING journal entry (draft)."""
from __future__ import annotations

from datetime import date as _date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.accounting.journals.dto.journal_commands import (
    CreateJournalEntryCommand,
    JournalLineCommand,
)
from seeker_accounting.modules.wizards.opening_balances import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ConfirmStep(WizardStep):
    key = "confirm"
    title = "Confirm"
    subtitle = "Create the OPENING journal entry as a draft."

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
            lines = state.get(K.KEY_LINES) or []
            valid = [ln for ln in lines if ln.get("account_id")]
            dr_total = Decimal(0)
            for ln in valid:
                try:
                    dr_total += Decimal(str(ln.get("debit_amount") or "0"))
                except Exception:
                    continue
            html = (
                f"<b>Date:</b> {state.get(K.KEY_ENTRY_DATE)}<br>"
                f"<b>Type:</b> OPENING<br>"
                f"<b>Reference:</b> {state.get(K.KEY_REFERENCE_TEXT) or '(none)'}<br>"
                f"<b>Lines:</b> {len(valid)} \u00b7 <b>Total:</b> {dr_total:.2f}"
            )
            self._summary.setText(html)
        if self._result is not None and state.get(K.KEY_JOURNAL_ENTRY_ID):
            jeid = state[K.KEY_JOURNAL_ENTRY_ID]
            num = state.get(K.KEY_JOURNAL_ENTRY_NUMBER) or ""
            self._result.setText(f"Draft journal entry #{jeid} {num} created.")

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if isinstance(state.get(K.KEY_JOURNAL_ENTRY_ID), int):
            return
        company_id = context.require_company_id()
        entry_date = _date.fromisoformat(str(state[K.KEY_ENTRY_DATE]))
        line_cmds: list[JournalLineCommand] = []
        for ln in state.get(K.KEY_LINES) or []:
            acc_id = ln.get("account_id")
            if not isinstance(acc_id, int):
                continue
            dr_raw = ln.get("debit_amount")
            cr_raw = ln.get("credit_amount")
            line_cmds.append(
                JournalLineCommand(
                    account_id=acc_id,
                    line_description=ln.get("line_description"),
                    debit_amount=Decimal(str(dr_raw)) if dr_raw else None,
                    credit_amount=Decimal(str(cr_raw)) if cr_raw else None,
                )
            )
        cmd = CreateJournalEntryCommand(
            entry_date=entry_date,
            transaction_date=entry_date,
            journal_type_code="OPENING",
            reference_text=state.get(K.KEY_REFERENCE_TEXT),
            description=state.get(K.KEY_DESCRIPTION),
            source_module_code="opening_balances_wizard",
            source_document_type=None,
            source_document_id=None,
            lines=tuple(line_cmds),
        )
        je = context.service_registry.journal_service.create_draft_journal(company_id, cmd)
        state[K.KEY_JOURNAL_ENTRY_ID] = je.id
        # Different DTOs expose entry number under different attribute names; be defensive.
        for attr in ("entry_number", "journal_number", "number"):
            val = getattr(je, attr, None)
            if val:
                state[K.KEY_JOURNAL_ENTRY_NUMBER] = str(val)
                break
        state[K.KEY_JOURNAL_STATUS] = getattr(je, "status_code", None)

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        jeid = state.get(K.KEY_JOURNAL_ENTRY_ID)
        if jeid:
            return f"Journal entry #{jeid} (draft, OPENING)"
        return "Ready to create draft OPENING entry."
