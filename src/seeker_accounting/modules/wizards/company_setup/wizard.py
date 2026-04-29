"""Company Setup Wizard composition + launcher.

End-user entry point::

    from seeker_accounting.modules.wizards.company_setup import (
        launch_company_setup_wizard,
    )

    result = launch_company_setup_wizard(service_registry, parent=main_window)
    if result.completed:
        ...

The wizard creates a persistent ``WizardRun`` row up-front so the workflow
is resumable, updates progress on each commit-on-advance, and marks the
run completed/cancelled/failed at exit.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtWidgets import QDialog, QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.company_setup.advisor import (
    build_company_setup_advisor,
)
from seeker_accounting.modules.wizards.company_setup.steps.account_role_mappings_step import (
    AccountRoleMappingsStep,
)
from seeker_accounting.modules.wizards.company_setup.steps.chart_of_accounts_step import (
    ChartOfAccountsStep,
)
from seeker_accounting.modules.wizards.company_setup.steps.company_info_step import (
    CompanyInfoStep,
)
from seeker_accounting.modules.wizards.company_setup.steps.document_sequences_step import (
    DocumentSequencesStep,
)
from seeker_accounting.modules.wizards.company_setup.steps.fiscal_year_step import (
    FiscalYearStep,
)
from seeker_accounting.modules.wizards.company_setup.steps.review_step import (
    ReviewStep,
)
from seeker_accounting.modules.wizards.company_setup.steps.tax_codes_step import (
    TaxCodesStep,
)
from seeker_accounting.platform.wizards import (
    AssistantEngine,
    WizardContext,
    WizardController,
    WizardLifecycleStatus,
    WizardState,
)
from seeker_accounting.platform.wizards.host_dialog import WizardHostDialog

logger = logging.getLogger("seeker_accounting.modules.wizards.company_setup")

WIZARD_CODE = "company_setup"


@dataclass(slots=True)
class CompanySetupResult:
    completed: bool
    company_id: int | None
    wizard_run_id: int | None


class CompanySetupWizard:
    """Compose controller, advisor, and host dialog for the Company Setup flow."""

    @staticmethod
    def build_controller(
        service_registry: ServiceRegistry,
        *,
        user_id: int | None,
        wizard_run_id: int | None,
        initial_state: WizardState | None = None,
    ) -> WizardController:
        steps = [
            CompanyInfoStep(),
            FiscalYearStep(),
            ChartOfAccountsStep(),
            DocumentSequencesStep(),
            TaxCodesStep(),
            AccountRoleMappingsStep(),
            ReviewStep(),
        ]
        context = WizardContext(
            service_registry=service_registry,
            company_id=None,
            user_id=user_id,
            wizard_run_id=wizard_run_id,
        )
        return WizardController(
            wizard_code=WIZARD_CODE,
            steps=steps,
            context=context,
            state=initial_state or WizardState(),
            advisor=build_company_setup_advisor(),
            assistant_engine=AssistantEngine(),
        )


def launch_company_setup_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> CompanySetupResult:
    """Construct the wizard run record, show the host dialog, and persist outcome."""
    user_id = _resolve_user_id(service_registry)
    run_service = getattr(service_registry, "wizard_run_service", None)

    wizard_run_id: int | None = None
    if run_service is not None and user_id is not None:
        try:
            run = run_service.begin_run(
                wizard_code=WIZARD_CODE,
                user_id=user_id,
                company_id=None,
                initial_state_payload=None,
            )
            wizard_run_id = run.id
        except Exception:  # noqa: BLE001
            logger.exception("Failed to record wizard run; proceeding without persistence.")
            wizard_run_id = None

    controller = CompanySetupWizard.build_controller(
        service_registry,
        user_id=user_id,
        wizard_run_id=wizard_run_id,
    )

    dialog = WizardHostDialog(
        controller=controller,
        title="Company Setup Wizard",
        intro=(
            "Guided setup creates the company, opens its first fiscal year, "
            "seeds the chart of accounts, and pre-configures numbering and tax "
            "codes. You can revisit any step before finishing."
        ),
        parent=parent,
    )
    code = dialog.exec()

    company_id = controller.state.get("company_id")
    completed = (
        code == QDialog.DialogCode.Accepted
        and controller.lifecycle is WizardLifecycleStatus.COMMITTED
    )

    # Persist final outcome to the wizard run record.
    if run_service is not None and wizard_run_id is not None:
        try:
            final_payload = controller.state.to_json()
            if completed:
                run_service.complete_run(wizard_run_id, final_state_payload=final_payload)
            elif controller.lifecycle is WizardLifecycleStatus.FAILED:
                run_service.fail_run(wizard_run_id, "Wizard failed during commit.")
            else:
                run_service.cancel_run(wizard_run_id)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to update wizard run final status (run_id=%s).", wizard_run_id)

    return CompanySetupResult(
        completed=completed,
        company_id=company_id if isinstance(company_id, int) else None,
        wizard_run_id=wizard_run_id,
    )


def _resolve_user_id(service_registry: ServiceRegistry) -> int | None:
    app_context = getattr(service_registry, "app_context", None)
    if app_context is None:
        return None
    return getattr(app_context, "current_user_id", None)
