"""Tax Regime Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.tax_regime import state_keys as K
from seeker_accounting.modules.wizards.tax_regime.advisor import build_tax_regime_advisor
from seeker_accounting.modules.wizards.tax_regime.steps.dsf_flags_step import DsfFlagsStep
from seeker_accounting.modules.wizards.tax_regime.steps.identity_step import IdentityStep
from seeker_accounting.modules.wizards.tax_regime.steps.vat_cit_step import VatCitStep
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "tax_regime"


@dataclass(slots=True)
class TaxRegimeResult:
    completed: bool
    profile_persisted: bool
    wizard_run_id: int | None


class TaxRegimeWizard:
    @staticmethod
    def steps_factory():
        return [IdentityStep(), VatCitStep(), DsfFlagsStep()]

    @staticmethod
    def advisor_factory():
        return build_tax_regime_advisor()


def launch_tax_regime_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> TaxRegimeResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Tax Regime",
        intro=(
            "Declare the company's tax regime, VAT/CIT obligations, and DSF reporting "
            "profile. The platform reads this profile to drive validations, returns, "
            "and reminders."
        ),
        steps_factory=TaxRegimeWizard.steps_factory,
        advisor_factory=TaxRegimeWizard.advisor_factory,
        feature_label="Tax Regime",
        parent=parent,
    )
    if outcome is None:
        return TaxRegimeResult(False, False, None)
    assert isinstance(outcome, WizardOutcome)
    return TaxRegimeResult(
        completed=outcome.completed,
        profile_persisted=bool(outcome.state.get(K.KEY_PROFILE_PERSISTED)),
        wizard_run_id=outcome.wizard_run_id,
    )
