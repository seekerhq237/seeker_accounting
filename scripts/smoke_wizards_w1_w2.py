"""Offscreen smoke for Month-End Close & Payroll Run wizards.

Constructs each wizard's controller and host dialog (without invoking any
service-driven commits) to verify wiring end-to-end.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

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
from seeker_accounting.modules.wizards.payroll_run.advisor import build_payroll_run_advisor
from seeker_accounting.modules.wizards.payroll_run.steps.approve_step import ApproveStep
from seeker_accounting.modules.wizards.payroll_run.steps.period_and_calculate_step import (
    PeriodAndCalculateStep,
)
from seeker_accounting.modules.wizards.payroll_run.steps.post_step import PostStep
from seeker_accounting.modules.wizards.payroll_run.steps.review_employees_step import (
    ReviewEmployeesStep,
)
from seeker_accounting.platform.wizards import (
    AssistantEngine,
    WizardContext,
    WizardController,
    WizardState,
)
from seeker_accounting.platform.wizards.host_dialog import WizardHostDialog


def _build_dialog(steps, advisor, *, company_id):
    registry = MagicMock()
    # Make list_periods return [] so PeriodSelectionStep renders cleanly.
    registry.fiscal_calendar_service.list_periods.return_value = []
    registry.journal_service.list_journal_entries.return_value = []
    registry.payroll_run_service.list_run_employees.return_value = []
    registry.active_company_context.base_currency_code = "XAF"

    context = WizardContext(
        service_registry=registry,
        company_id=company_id,
        user_id=1,
        wizard_run_id=None,
    )
    controller = WizardController(
        wizard_code="smoke",
        steps=steps,
        context=context,
        state=WizardState(),
        advisor=advisor,
        assistant_engine=AssistantEngine(),
    )
    dialog = WizardHostDialog(
        controller=controller,
        title="Smoke",
        intro="Offscreen render check.",
    )
    dialog.show()
    return dialog


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    # Month-End Close
    mec = _build_dialog(
        [PeriodSelectionStep(), DraftsCheckStep(), ReconciliationCheckStep(), CloseStep()],
        build_month_end_close_advisor(),
        company_id=42,
    )
    app.processEvents()
    mec.close()

    # Payroll Run
    pr = _build_dialog(
        [PeriodAndCalculateStep(), ReviewEmployeesStep(), ApproveStep(), PostStep()],
        build_payroll_run_advisor(),
        company_id=42,
    )
    app.processEvents()
    pr.close()

    print("OK month-end close + payroll run smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
