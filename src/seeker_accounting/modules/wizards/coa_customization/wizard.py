"""COA Customization Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.coa_customization import state_keys as K
from seeker_accounting.modules.wizards.coa_customization.advisor import (
    build_coa_customization_advisor,
)
from seeker_accounting.modules.wizards.coa_customization.steps.baseline_step import BaselineStep
from seeker_accounting.modules.wizards.coa_customization.steps.confirm_step import ConfirmStep
from seeker_accounting.modules.wizards.coa_customization.steps.role_mapping_step import (
    RoleMappingStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "coa_customization"


@dataclass(slots=True)
class CoaCustomizationResult:
    completed: bool
    baseline_applied: bool
    baseline_imported_count: int
    mappings_updated_count: int
    mappings_cleared_count: int
    wizard_run_id: int | None


class CoaCustomizationWizard:
    @staticmethod
    def steps_factory():
        return [BaselineStep(), RoleMappingStep(), ConfirmStep()]

    @staticmethod
    def advisor_factory():
        return build_coa_customization_advisor()


def launch_coa_customization_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> CoaCustomizationResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Chart of Accounts Customization",
        intro=(
            "Apply the OHADA baseline (additive), review system role mappings "
            "(AR control, AP control, VAT, retained earnings, ...), and persist "
            "your mapping decisions."
        ),
        steps_factory=CoaCustomizationWizard.steps_factory,
        advisor_factory=CoaCustomizationWizard.advisor_factory,
        feature_label="Chart of Accounts Customization",
        parent=parent,
    )
    if outcome is None:
        return CoaCustomizationResult(False, False, 0, 0, 0, None)
    assert isinstance(outcome, WizardOutcome)
    return CoaCustomizationResult(
        completed=outcome.completed,
        baseline_applied=bool(outcome.state.get(K.KEY_BASELINE_APPLIED)),
        baseline_imported_count=int(outcome.state.get(K.KEY_BASELINE_RESULT_IMPORTED) or 0),
        mappings_updated_count=int(outcome.state.get(K.KEY_MAPPINGS_UPDATED_COUNT) or 0),
        mappings_cleared_count=int(outcome.state.get(K.KEY_MAPPINGS_CLEARED_COUNT) or 0),
        wizard_run_id=outcome.wizard_run_id,
    )
