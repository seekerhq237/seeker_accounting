"""New Item Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.new_item import state_keys as K
from seeker_accounting.modules.wizards.new_item.advisor import build_new_item_advisor
from seeker_accounting.modules.wizards.new_item.steps.accounts_step import AccountsStep
from seeker_accounting.modules.wizards.new_item.steps.classification_step import (
    ClassificationStep,
)
from seeker_accounting.modules.wizards.new_item.steps.identity_step import IdentityStep
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "new_item"


@dataclass(slots=True)
class NewItemResult:
    completed: bool
    item_id: int | None
    wizard_run_id: int | None


class NewItemWizard:
    @staticmethod
    def steps_factory():
        return [IdentityStep(), ClassificationStep(), AccountsStep()]

    @staticmethod
    def advisor_factory():
        return build_new_item_advisor()


def launch_new_item_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> NewItemResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="New Item",
        intro=(
            "Create an inventory, non-stock, or service item with classification "
            "and default GL accounts in one guided flow."
        ),
        steps_factory=NewItemWizard.steps_factory,
        advisor_factory=NewItemWizard.advisor_factory,
        feature_label="New Item",
        parent=parent,
    )
    if outcome is None:
        return NewItemResult(False, None, None)
    assert isinstance(outcome, WizardOutcome)
    iid = outcome.state.get(K.KEY_ITEM_ID)
    return NewItemResult(
        completed=outcome.completed,
        item_id=int(iid) if isinstance(iid, int) else None,
        wizard_run_id=outcome.wizard_run_id,
    )
