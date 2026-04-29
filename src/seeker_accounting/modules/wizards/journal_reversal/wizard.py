"""Journal Reversal Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.journal_reversal import state_keys as K
from seeker_accounting.modules.wizards.journal_reversal.advisor import (
    build_journal_reversal_advisor,
)
from seeker_accounting.modules.wizards.journal_reversal.steps.confirm_step import (
    ConfirmStep,
)
from seeker_accounting.modules.wizards.journal_reversal.steps.details_step import (
    DetailsStep,
)
from seeker_accounting.modules.wizards.journal_reversal.steps.pick_step import (
    PickJournalStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "journal_reversal"


@dataclass(slots=True)
class JournalReversalResult:
    completed: bool
    posted: bool
    source_journal_entry_id: int | None
    reversal_journal_entry_id: int | None
    reversal_entry_number: str | None
    auto_posted: bool
    wizard_run_id: int | None


class JournalReversalWizard:
    @staticmethod
    def steps_factory():
        return [PickJournalStep(), DetailsStep(), ConfirmStep()]

    @staticmethod
    def advisor_factory():
        return build_journal_reversal_advisor()


def launch_journal_reversal_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> JournalReversalResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Reverse Journal Entry",
        intro=(
            "Create a balanced reversing journal entry for a posted journal. "
            "The reversal copies every line of the source entry with debits "
            "and credits swapped. Optionally posts it immediately."
        ),
        steps_factory=JournalReversalWizard.steps_factory,
        advisor_factory=JournalReversalWizard.advisor_factory,
        feature_label="Journal Reversal",
        parent=parent,
    )
    if outcome is None:
        return JournalReversalResult(False, False, None, None, None, False, None)
    assert isinstance(outcome, WizardOutcome)
    src = outcome.state.get(K.KEY_SOURCE_JE_ID)
    rev = outcome.state.get(K.KEY_RESULT_REVERSAL_JE_ID)
    return JournalReversalResult(
        completed=outcome.completed,
        posted=bool(outcome.state.get(K.KEY_POSTED)),
        source_journal_entry_id=int(src) if isinstance(src, int) else None,
        reversal_journal_entry_id=int(rev) if isinstance(rev, int) else None,
        reversal_entry_number=outcome.state.get(K.KEY_RESULT_REVERSAL_ENTRY_NUMBER),
        auto_posted=bool(outcome.state.get(K.KEY_RESULT_AUTO_POSTED)),
        wizard_run_id=outcome.wizard_run_id,
    )
