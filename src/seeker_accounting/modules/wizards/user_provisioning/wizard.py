"""User Provisioning Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.user_provisioning import state_keys as K
from seeker_accounting.modules.wizards.user_provisioning.advisor import (
    build_user_provisioning_advisor,
)
from seeker_accounting.modules.wizards.user_provisioning.steps.confirm_step import ConfirmStep
from seeker_accounting.modules.wizards.user_provisioning.steps.identity_step import IdentityStep
from seeker_accounting.modules.wizards.user_provisioning.steps.roles_access_step import (
    RolesAccessStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "user_provisioning"


@dataclass(slots=True)
class UserProvisioningResult:
    completed: bool
    user_id: int | None
    wizard_run_id: int | None


class UserProvisioningWizard:
    @staticmethod
    def steps_factory():
        return [IdentityStep(), RolesAccessStep(), ConfirmStep()]

    @staticmethod
    def advisor_factory():
        return build_user_provisioning_advisor()


def launch_user_provisioning_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> UserProvisioningResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="User Provisioning",
        intro=(
            "Provision a new user account: capture identity, assign roles, "
            "and grant access to the current company."
        ),
        steps_factory=UserProvisioningWizard.steps_factory,
        advisor_factory=UserProvisioningWizard.advisor_factory,
        feature_label="User Provisioning",
        parent=parent,
    )
    if outcome is None:
        return UserProvisioningResult(False, None, None)
    assert isinstance(outcome, WizardOutcome)
    uid = outcome.state.get(K.KEY_USER_ID)
    return UserProvisioningResult(
        completed=outcome.completed,
        user_id=int(uid) if isinstance(uid, int) else None,
        wizard_run_id=outcome.wizard_run_id,
    )
