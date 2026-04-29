"""New Supplier Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.new_supplier import state_keys as K
from seeker_accounting.modules.wizards.new_supplier.advisor import (
    build_new_supplier_advisor,
)
from seeker_accounting.modules.wizards.new_supplier.steps.contact_step import ContactStep
from seeker_accounting.modules.wizards.new_supplier.steps.financial_step import (
    FinancialStep,
)
from seeker_accounting.modules.wizards.new_supplier.steps.identity_step import (
    IdentityStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "new_supplier"


@dataclass(slots=True)
class NewSupplierResult:
    completed: bool
    supplier_id: int | None
    wizard_run_id: int | None


class NewSupplierWizard:
    @staticmethod
    def steps_factory():
        return [IdentityStep(), ContactStep(), FinancialStep()]

    @staticmethod
    def advisor_factory():
        return build_new_supplier_advisor()


def launch_new_supplier_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> NewSupplierResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="New Supplier",
        intro=(
            "Create a supplier with identity, contact, and financial defaults "
            "in one guided flow."
        ),
        steps_factory=NewSupplierWizard.steps_factory,
        advisor_factory=NewSupplierWizard.advisor_factory,
        feature_label="New Supplier",
        parent=parent,
    )
    if outcome is None:
        return NewSupplierResult(False, None, None)
    assert isinstance(outcome, WizardOutcome)
    sid = outcome.state.get(K.KEY_SUPPLIER_ID)
    return NewSupplierResult(
        completed=outcome.completed,
        supplier_id=int(sid) if isinstance(sid, int) else None,
        wizard_run_id=outcome.wizard_run_id,
    )
