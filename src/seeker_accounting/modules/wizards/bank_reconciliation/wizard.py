"""Bank Reconciliation Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.bank_reconciliation import state_keys as K
from seeker_accounting.modules.wizards.bank_reconciliation.advisor import (
    build_bank_reconciliation_advisor,
)
from seeker_accounting.modules.wizards.bank_reconciliation.steps.finalize_step import (
    FinalizeStep,
)
from seeker_accounting.modules.wizards.bank_reconciliation.steps.match_summary_step import (
    MatchSummaryStep,
)
from seeker_accounting.modules.wizards.bank_reconciliation.steps.statement_step import (
    StatementStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "bank_reconciliation"


@dataclass(slots=True)
class BankReconciliationResult:
    completed: bool
    session_id: int | None
    session_status: str | None
    wizard_run_id: int | None


class BankReconciliationWizard:
    @staticmethod
    def steps_factory():
        return [StatementStep(), MatchSummaryStep(), FinalizeStep()]

    @staticmethod
    def advisor_factory():
        return build_bank_reconciliation_advisor()


def launch_bank_reconciliation_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> BankReconciliationResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Bank Reconciliation",
        intro=(
            "Open a reconciliation session for a bank/cash account, record "
            "matches in the Treasury workspace, then finalize here."
        ),
        steps_factory=BankReconciliationWizard.steps_factory,
        advisor_factory=BankReconciliationWizard.advisor_factory,
        feature_label="Bank Reconciliation",
        parent=parent,
    )
    if outcome is None:
        return BankReconciliationResult(False, None, None, None)
    assert isinstance(outcome, WizardOutcome)
    sid = outcome.state.get(K.KEY_SESSION_ID)
    return BankReconciliationResult(
        completed=outcome.completed,
        session_id=int(sid) if isinstance(sid, int) else None,
        session_status=outcome.state.get(K.KEY_SESSION_STATUS),
        wizard_run_id=outcome.wizard_run_id,
    )
