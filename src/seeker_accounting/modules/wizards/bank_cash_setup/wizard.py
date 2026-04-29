"""Bank & Cash Setup Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.bank_cash_setup import state_keys as K
from seeker_accounting.modules.wizards.bank_cash_setup.advisor import (
    build_bank_cash_setup_advisor,
)
from seeker_accounting.modules.wizards.bank_cash_setup.steps.confirm_step import ConfirmStep
from seeker_accounting.modules.wizards.bank_cash_setup.steps.details_step import DetailsStep
from seeker_accounting.modules.wizards.bank_cash_setup.steps.type_step import TypeStep
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "bank_cash_setup"


@dataclass(slots=True)
class BankCashSetupResult:
    completed: bool
    financial_account_id: int | None
    wizard_run_id: int | None


class BankCashSetupWizard:
    @staticmethod
    def steps_factory():
        return [TypeStep(), DetailsStep(), ConfirmStep()]

    @staticmethod
    def advisor_factory():
        return build_bank_cash_setup_advisor()


def launch_bank_cash_setup_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> BankCashSetupResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Bank & Cash Setup",
        intro=(
            "Add a bank, cash, or petty-cash financial account. Pick the type and currency, "
            "fill in the details, then confirm."
        ),
        steps_factory=BankCashSetupWizard.steps_factory,
        advisor_factory=BankCashSetupWizard.advisor_factory,
        feature_label="Bank & Cash Setup",
        parent=parent,
    )
    if outcome is None:
        return BankCashSetupResult(False, None, None)
    assert isinstance(outcome, WizardOutcome)
    faid = outcome.state.get(K.KEY_FINANCIAL_ACCOUNT_ID)
    return BankCashSetupResult(
        completed=outcome.completed,
        financial_account_id=int(faid) if isinstance(faid, int) else None,
        wizard_run_id=outcome.wizard_run_id,
    )
