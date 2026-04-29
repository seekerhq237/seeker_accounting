"""Control Account Reconciliation wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.control_account_reconciliation_dto import (
    ControlAccountReconciliationReportDTO,
)
from seeker_accounting.modules.wizards.control_account_reconciliation import state_keys as K
from seeker_accounting.modules.wizards.control_account_reconciliation.advisor import (
    build_control_account_reconciliation_advisor,
)
from seeker_accounting.modules.wizards.control_account_reconciliation.steps.review_step import (
    ReviewStep,
)
from seeker_accounting.modules.wizards.control_account_reconciliation.steps.setup_step import (
    SetupStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "control_account_reconciliation"


@dataclass(slots=True)
class ControlAccountReconciliationResult:
    completed: bool
    report: ControlAccountReconciliationReportDTO | None
    wizard_run_id: int | None


class ControlAccountReconciliationWizard:
    @staticmethod
    def steps_factory():
        return [SetupStep(), ReviewStep()]

    @staticmethod
    def advisor_factory():
        return build_control_account_reconciliation_advisor()


def launch_control_account_reconciliation_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> ControlAccountReconciliationResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Control Account Reconciliation",
        intro=(
            "Compare AR and AP control account balances against their "
            "subledger aging totals as at a chosen date. This wizard is "
            "read-only — it surfaces variances so you can investigate them."
        ),
        steps_factory=ControlAccountReconciliationWizard.steps_factory,
        advisor_factory=ControlAccountReconciliationWizard.advisor_factory,
        feature_label="Control Account Reconciliation",
        parent=parent,
    )
    if outcome is None:
        return ControlAccountReconciliationResult(False, None, None)
    assert isinstance(outcome, WizardOutcome)
    report = outcome.state.get(K.KEY_REPORT)
    return ControlAccountReconciliationResult(
        completed=outcome.completed,
        report=report if isinstance(report, ControlAccountReconciliationReportDTO) else None,
        wizard_run_id=outcome.wizard_run_id,
    )
