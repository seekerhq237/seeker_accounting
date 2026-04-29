"""Purchase Credit Note Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.purchase_credit_note import state_keys as K
from seeker_accounting.modules.wizards.purchase_credit_note.advisor import (
    build_purchase_credit_note_advisor,
)
from seeker_accounting.modules.wizards.purchase_credit_note.steps.confirm_step import (
    ConfirmStep,
)
from seeker_accounting.modules.wizards.purchase_credit_note.steps.header_step import HeaderStep
from seeker_accounting.modules.wizards.purchase_credit_note.steps.lines_step import LinesStep
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "purchase_credit_note"


@dataclass(slots=True)
class PurchaseCreditNoteResult:
    completed: bool
    credit_note_id: int | None
    credit_note_status: str | None
    posted_journal_entry_id: int | None
    wizard_run_id: int | None


class PurchaseCreditNoteWizard:
    @staticmethod
    def steps_factory():
        return [HeaderStep(), LinesStep(), ConfirmStep()]

    @staticmethod
    def advisor_factory():
        return build_purchase_credit_note_advisor()


def launch_purchase_credit_note_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> PurchaseCreditNoteResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Purchase Credit Note",
        intro=(
            "Record a supplier credit note. Header, line items, then optional posting "
            "in one guided flow."
        ),
        steps_factory=PurchaseCreditNoteWizard.steps_factory,
        advisor_factory=PurchaseCreditNoteWizard.advisor_factory,
        feature_label="Purchase Credit Note",
        parent=parent,
    )
    if outcome is None:
        return PurchaseCreditNoteResult(False, None, None, None, None)
    assert isinstance(outcome, WizardOutcome)
    cnid = outcome.state.get(K.KEY_CREDIT_NOTE_ID)
    jeid = outcome.state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID)
    status = outcome.state.get(K.KEY_CREDIT_NOTE_STATUS)
    return PurchaseCreditNoteResult(
        completed=outcome.completed,
        credit_note_id=int(cnid) if isinstance(cnid, int) else None,
        credit_note_status=str(status) if status else None,
        posted_journal_entry_id=int(jeid) if isinstance(jeid, int) else None,
        wizard_run_id=outcome.wizard_run_id,
    )
