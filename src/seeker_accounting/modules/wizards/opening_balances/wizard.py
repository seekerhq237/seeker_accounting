"""Opening Balances Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.opening_balances import state_keys as K
from seeker_accounting.modules.wizards.opening_balances.advisor import (
    build_opening_balances_advisor,
)
from seeker_accounting.modules.wizards.opening_balances.steps.confirm_step import (
    ConfirmStep,
)
from seeker_accounting.modules.wizards.opening_balances.steps.header_step import HeaderStep
from seeker_accounting.modules.wizards.opening_balances.steps.lines_step import LinesStep
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "opening_balances"


@dataclass(slots=True)
class OpeningBalancesResult:
    completed: bool
    journal_entry_id: int | None
    journal_entry_number: str | None
    wizard_run_id: int | None


class OpeningBalancesWizard:
    @staticmethod
    def steps_factory():
        return [HeaderStep(), LinesStep(), ConfirmStep()]

    @staticmethod
    def advisor_factory():
        return build_opening_balances_advisor()


def launch_opening_balances_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> OpeningBalancesResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Opening Balances",
        intro=(
            "Capture brought-forward balances as a draft OPENING journal entry. "
            "Debits must equal credits before saving."
        ),
        steps_factory=OpeningBalancesWizard.steps_factory,
        advisor_factory=OpeningBalancesWizard.advisor_factory,
        feature_label="Opening Balances",
        parent=parent,
    )
    if outcome is None:
        return OpeningBalancesResult(False, None, None, None)
    assert isinstance(outcome, WizardOutcome)
    jeid = outcome.state.get(K.KEY_JOURNAL_ENTRY_ID)
    num = outcome.state.get(K.KEY_JOURNAL_ENTRY_NUMBER)
    return OpeningBalancesResult(
        completed=outcome.completed,
        journal_entry_id=int(jeid) if isinstance(jeid, int) else None,
        journal_entry_number=str(num) if num else None,
        wizard_run_id=outcome.wizard_run_id,
    )
