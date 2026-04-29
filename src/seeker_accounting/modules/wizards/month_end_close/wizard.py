"""Month-End Close Wizard composition + launcher."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.month_end_close.advisor import (
    build_month_end_close_advisor,
)
from seeker_accounting.modules.wizards.month_end_close.steps.close_step import CloseStep
from seeker_accounting.modules.wizards.month_end_close.steps.drafts_check_step import (
    DraftsCheckStep,
)
from seeker_accounting.modules.wizards.month_end_close.steps.period_selection_step import (
    PeriodSelectionStep,
)
from seeker_accounting.modules.wizards.month_end_close.steps.reconciliation_check_step import (
    ReconciliationCheckStep,
)
from seeker_accounting.platform.wizards import (
    AssistantEngine,
    WizardContext,
    WizardController,
    WizardLifecycleStatus,
    WizardState,
)
from seeker_accounting.platform.wizards.host_dialog import WizardHostDialog

logger = logging.getLogger("seeker_accounting.modules.wizards.month_end_close")

WIZARD_CODE = "month_end_close"


@dataclass(slots=True)
class MonthEndCloseResult:
    completed: bool
    period_id: int | None
    new_status_code: str | None
    wizard_run_id: int | None


class MonthEndCloseWizard:
    @staticmethod
    def build_controller(
        service_registry: ServiceRegistry,
        *,
        company_id: int,
        user_id: int | None,
        wizard_run_id: int | None,
        initial_state: WizardState | None = None,
    ) -> WizardController:
        steps = [
            PeriodSelectionStep(),
            DraftsCheckStep(),
            ReconciliationCheckStep(),
            CloseStep(),
        ]
        context = WizardContext(
            service_registry=service_registry,
            company_id=company_id,
            user_id=user_id,
            wizard_run_id=wizard_run_id,
        )
        return WizardController(
            wizard_code=WIZARD_CODE,
            steps=steps,
            context=context,
            state=initial_state or WizardState(),
            advisor=build_month_end_close_advisor(),
            assistant_engine=AssistantEngine(),
        )


def launch_month_end_close_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> MonthEndCloseResult:
    company_id = _resolve_active_company_id(service_registry)
    if company_id is None:
        QMessageBox.warning(
            parent,
            "Month-End Close",
            "Pick an active company before running the close wizard.",
        )
        return MonthEndCloseResult(
            completed=False, period_id=None, new_status_code=None, wizard_run_id=None
        )

    user_id = _resolve_user_id(service_registry)
    run_service = getattr(service_registry, "wizard_run_service", None)

    wizard_run_id: int | None = None
    if run_service is not None and user_id is not None:
        try:
            run = run_service.begin_run(
                wizard_code=WIZARD_CODE,
                user_id=user_id,
                company_id=company_id,
                initial_state_payload=None,
            )
            wizard_run_id = run.id
        except Exception:  # noqa: BLE001
            logger.exception("Failed to record wizard run; proceeding without persistence.")

    controller = MonthEndCloseWizard.build_controller(
        service_registry,
        company_id=company_id,
        user_id=user_id,
        wizard_run_id=wizard_run_id,
    )

    dialog = WizardHostDialog(
        controller=controller,
        title="Month-End Close",
        intro=(
            "Pick a period, review unposted drafts, confirm reconciliations, "
            "and close. The period will move from OPEN to CLOSED — postings "
            "are blocked thereafter until reopened."
        ),
        parent=parent,
    )
    code = dialog.exec()

    completed = (
        code == QDialog.DialogCode.Accepted
        and controller.lifecycle is WizardLifecycleStatus.COMMITTED
    )
    period_id = controller.state.get("close_result_period_id")
    new_status = controller.state.get("close_result_new_status")

    if run_service is not None and wizard_run_id is not None:
        try:
            payload = controller.state.to_json()
            if completed:
                run_service.complete_run(wizard_run_id, final_state_payload=payload)
            elif controller.lifecycle is WizardLifecycleStatus.FAILED:
                run_service.fail_run(wizard_run_id, "Wizard failed during commit.")
            else:
                run_service.cancel_run(wizard_run_id)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to update wizard run final status (run_id=%s).", wizard_run_id)

    return MonthEndCloseResult(
        completed=completed,
        period_id=int(period_id) if isinstance(period_id, int) else None,
        new_status_code=new_status if isinstance(new_status, str) else None,
        wizard_run_id=wizard_run_id,
    )


def _resolve_user_id(service_registry: ServiceRegistry) -> int | None:
    app_context = getattr(service_registry, "app_context", None)
    if app_context is None:
        return None
    return getattr(app_context, "current_user_id", None)


def _resolve_active_company_id(service_registry: ServiceRegistry) -> int | None:
    ctx = getattr(service_registry, "active_company_context", None)
    if ctx is None:
        return None
    return ctx.company_id
