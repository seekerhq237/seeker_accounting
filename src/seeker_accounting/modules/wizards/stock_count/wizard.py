"""Stock Count Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.stock_count import state_keys as K
from seeker_accounting.modules.wizards.stock_count.advisor import (
    build_stock_count_advisor,
)
from seeker_accounting.modules.wizards.stock_count.steps.confirm_step import ConfirmStep
from seeker_accounting.modules.wizards.stock_count.steps.count_step import CountStep
from seeker_accounting.modules.wizards.stock_count.steps.setup_step import SetupStep
from seeker_accounting.modules.wizards.stock_count.steps.variance_review_step import (
    VarianceReviewStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "stock_count"


@dataclass(slots=True)
class StockCountResult:
    completed: bool
    posted: bool
    document_id: int | None
    document_number: str | None
    variance_lines: int
    wizard_run_id: int | None


class StockCountWizard:
    @staticmethod
    def steps_factory():
        return [SetupStep(), CountStep(), VarianceReviewStep(), ConfirmStep()]

    @staticmethod
    def advisor_factory():
        return build_stock_count_advisor()


def launch_stock_count_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> StockCountResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Stock Count",
        intro=(
            "Reconcile system stock to physical counts. Enter counted quantities, "
            "review variances, and the wizard creates and posts a single "
            "inventory adjustment document for the differences."
        ),
        steps_factory=StockCountWizard.steps_factory,
        advisor_factory=StockCountWizard.advisor_factory,
        feature_label="Stock Count",
        parent=parent,
    )
    if outcome is None:
        return StockCountResult(False, False, None, None, 0, None)
    assert isinstance(outcome, WizardOutcome)
    doc_id = outcome.state.get(K.KEY_RESULT_DOCUMENT_ID)
    return StockCountResult(
        completed=outcome.completed,
        posted=bool(outcome.state.get(K.KEY_POSTED)),
        document_id=int(doc_id) if isinstance(doc_id, int) else None,
        document_number=outcome.state.get(K.KEY_RESULT_DOCUMENT_NUMBER),
        variance_lines=int(outcome.state.get(K.KEY_RESULT_VARIANCE_LINES) or 0),
        wizard_run_id=outcome.wizard_run_id,
    )
