"""Period Reopen Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.period_reopen import state_keys as K
from seeker_accounting.modules.wizards.period_reopen.advisor import (
    build_period_reopen_advisor,
)
from seeker_accounting.modules.wizards.period_reopen.steps.pick_period_step import (
    PickPeriodStep,
)
from seeker_accounting.modules.wizards.period_reopen.steps.reason_step import ReasonStep
from seeker_accounting.modules.wizards.period_reopen.steps.reopen_step import ReopenStep
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "period_reopen"


@dataclass(slots=True)
class PeriodReopenResult:
    completed: bool
    period_id: int | None
    new_status_code: str | None
    wizard_run_id: int | None


class PeriodReopenWizard:
    @staticmethod
    def steps_factory():
        return [PickPeriodStep(), ReasonStep(), ReopenStep()]

    @staticmethod
    def advisor_factory():
        return build_period_reopen_advisor()


def launch_period_reopen_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> PeriodReopenResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Reopen Period",
        intro=(
            "Reopen a closed or locked fiscal period. The action is gated by the "
            "fiscal.periods.reopen permission and is recorded with your reason."
        ),
        steps_factory=PeriodReopenWizard.steps_factory,
        advisor_factory=PeriodReopenWizard.advisor_factory,
        feature_label="Reopen Period",
        parent=parent,
    )
    if outcome is None:
        return PeriodReopenResult(False, None, None, None)
    assert isinstance(outcome, WizardOutcome)
    period_id = outcome.state.get(K.KEY_REOPEN_RESULT_PERIOD_ID) or outcome.state.get(K.KEY_PERIOD_ID)
    return PeriodReopenResult(
        completed=outcome.completed,
        period_id=int(period_id) if isinstance(period_id, int) else None,
        new_status_code=outcome.state.get(K.KEY_REOPEN_RESULT_NEW_STATUS),
        wizard_run_id=outcome.wizard_run_id,
    )
