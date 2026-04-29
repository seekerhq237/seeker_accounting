"""Year-End Close Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.year_end_close import state_keys as K
from seeker_accounting.modules.wizards.year_end_close.advisor import (
    build_year_end_close_advisor,
)
from seeker_accounting.modules.wizards.year_end_close.steps.confirm_step import ConfirmStep
from seeker_accounting.modules.wizards.year_end_close.steps.periods_review_step import (
    PeriodsReviewStep,
)
from seeker_accounting.modules.wizards.year_end_close.steps.pick_year_step import PickYearStep
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "year_end_close"


@dataclass(slots=True)
class YearEndCloseResult:
    completed: bool
    year_closed: bool
    fiscal_year_id: int | None
    fiscal_year_code: str | None
    periods_locked_count: int
    wizard_run_id: int | None


class YearEndCloseWizard:
    @staticmethod
    def steps_factory():
        return [PickYearStep(), PeriodsReviewStep(), ConfirmStep()]

    @staticmethod
    def advisor_factory():
        return build_year_end_close_advisor()


def launch_year_end_close_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> YearEndCloseResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Year-End Close",
        intro=(
            "Close a fiscal year. The wizard verifies all periods are CLOSED or LOCKED, "
            "optionally locks all CLOSED periods, and finally transitions the year to "
            "CLOSED status."
        ),
        steps_factory=YearEndCloseWizard.steps_factory,
        advisor_factory=YearEndCloseWizard.advisor_factory,
        feature_label="Year-End Close",
        parent=parent,
    )
    if outcome is None:
        return YearEndCloseResult(False, False, None, None, 0, None)
    assert isinstance(outcome, WizardOutcome)
    fy_id = outcome.state.get(K.KEY_FISCAL_YEAR_ID)
    return YearEndCloseResult(
        completed=outcome.completed,
        year_closed=bool(outcome.state.get(K.KEY_YEAR_CLOSED)),
        fiscal_year_id=int(fy_id) if isinstance(fy_id, int) else None,
        fiscal_year_code=outcome.state.get(K.KEY_FISCAL_YEAR_CODE),
        periods_locked_count=int(outcome.state.get(K.KEY_PERIODS_LOCKED_COUNT) or 0),
        wizard_run_id=outcome.wizard_run_id,
    )
