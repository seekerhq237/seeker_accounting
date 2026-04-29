"""FX Revaluation Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.fx_revaluation import state_keys as K
from seeker_accounting.modules.wizards.fx_revaluation.advisor import (
    build_fx_revaluation_advisor,
)
from seeker_accounting.modules.wizards.fx_revaluation.steps.confirm_step import (
    ConfirmStep,
)
from seeker_accounting.modules.wizards.fx_revaluation.steps.lines_step import (
    LinesStep,
)
from seeker_accounting.modules.wizards.fx_revaluation.steps.setup_step import (
    SetupStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "fx_revaluation"


@dataclass(slots=True)
class FxRevaluationResult:
    completed: bool
    posted: bool
    journal_entry_id: int | None
    journal_entry_number: str | None
    wizard_run_id: int | None


class FxRevaluationWizard:
    @staticmethod
    def steps_factory():
        return [SetupStep(), LinesStep(), ConfirmStep()]

    @staticmethod
    def advisor_factory():
        return build_fx_revaluation_advisor()


def launch_fx_revaluation_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> FxRevaluationResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="FX Revaluation",
        intro=(
            "Revalue foreign-currency accounts at period-end. Enter the current "
            "local-currency carrying amount and the target amount for each "
            "account; the wizard posts a single balanced journal entry that "
            "books the unrealized gain or loss."
        ),
        steps_factory=FxRevaluationWizard.steps_factory,
        advisor_factory=FxRevaluationWizard.advisor_factory,
        feature_label="FX Revaluation",
        parent=parent,
    )
    if outcome is None:
        return FxRevaluationResult(False, False, None, None, None)
    assert isinstance(outcome, WizardOutcome)
    je_id = outcome.state.get(K.KEY_RESULT_JE_ID)
    return FxRevaluationResult(
        completed=outcome.completed,
        posted=bool(outcome.state.get(K.KEY_POSTED)),
        journal_entry_id=int(je_id) if isinstance(je_id, int) else None,
        journal_entry_number=outcome.state.get(K.KEY_RESULT_JE_NUMBER),
        wizard_run_id=outcome.wizard_run_id,
    )
