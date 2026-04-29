"""New Customer Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.new_customer import state_keys as K
from seeker_accounting.modules.wizards.new_customer.advisor import (
    build_new_customer_advisor,
)
from seeker_accounting.modules.wizards.new_customer.steps.contact_step import ContactStep
from seeker_accounting.modules.wizards.new_customer.steps.financial_step import (
    FinancialStep,
)
from seeker_accounting.modules.wizards.new_customer.steps.identity_step import (
    IdentityStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "new_customer"


@dataclass(slots=True)
class NewCustomerResult:
    completed: bool
    customer_id: int | None
    wizard_run_id: int | None


class NewCustomerWizard:
    @staticmethod
    def steps_factory():
        return [IdentityStep(), ContactStep(), FinancialStep()]

    @staticmethod
    def advisor_factory():
        return build_new_customer_advisor()


def launch_new_customer_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> NewCustomerResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="New Customer",
        intro=(
            "Create a customer with identity, contact, and financial defaults "
            "in one guided flow."
        ),
        steps_factory=NewCustomerWizard.steps_factory,
        advisor_factory=NewCustomerWizard.advisor_factory,
        feature_label="New Customer",
        parent=parent,
    )
    if outcome is None:
        return NewCustomerResult(False, None, None)
    assert isinstance(outcome, WizardOutcome)
    cid = outcome.state.get(K.KEY_CUSTOMER_ID)
    return NewCustomerResult(
        completed=outcome.completed,
        customer_id=int(cid) if isinstance(cid, int) else None,
        wizard_run_id=outcome.wizard_run_id,
    )
