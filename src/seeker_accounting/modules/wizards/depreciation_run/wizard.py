"""Depreciation Run Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.depreciation_run import state_keys as K
from seeker_accounting.modules.wizards.depreciation_run.advisor import (
    build_depreciation_run_advisor,
)
from seeker_accounting.modules.wizards.depreciation_run.steps.create_run_step import (
    CreateRunStep,
)
from seeker_accounting.modules.wizards.depreciation_run.steps.post_step import PostStep
from seeker_accounting.modules.wizards.depreciation_run.steps.preview_step import (
    PreviewStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "depreciation_run"


@dataclass(slots=True)
class DepreciationRunResult:
    completed: bool
    run_id: int | None
    posted_journal_entry_id: int | None
    wizard_run_id: int | None


class DepreciationRunWizard:
    @staticmethod
    def steps_factory():
        return [CreateRunStep(), PreviewStep(), PostStep()]

    @staticmethod
    def advisor_factory():
        return build_depreciation_run_advisor()


def launch_depreciation_run_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> DepreciationRunResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Depreciation Run",
        intro=(
            "Compute depreciation for the chosen period, review per-asset lines, "
            "then post one balanced journal entry to the GL."
        ),
        steps_factory=DepreciationRunWizard.steps_factory,
        advisor_factory=DepreciationRunWizard.advisor_factory,
        feature_label="Depreciation Run",
        parent=parent,
    )
    if outcome is None:
        return DepreciationRunResult(False, None, None, None)
    assert isinstance(outcome, WizardOutcome)
    run_id = outcome.state.get(K.KEY_RUN_ID)
    je = outcome.state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID)
    return DepreciationRunResult(
        completed=outcome.completed,
        run_id=int(run_id) if isinstance(run_id, int) else None,
        posted_journal_entry_id=int(je) if isinstance(je, int) else None,
        wizard_run_id=outcome.wizard_run_id,
    )
