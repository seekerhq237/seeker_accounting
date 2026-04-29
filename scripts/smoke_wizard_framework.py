"""Offscreen smoke test for the wizard framework.

Builds the company-setup wizard's controller + host dialog without any
service calls (CompanyInfoStep widget construction only) and verifies
the framework wires correctly.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from seeker_accounting.platform.wizards import (
    AssistantEngine,
    StepValidationResult,
    WizardContext,
    WizardController,
    WizardState,
    WizardStep,
)
from seeker_accounting.platform.wizards.host_dialog import WizardHostDialog
from seeker_accounting.modules.wizards.company_setup.advisor import (
    build_company_setup_advisor,
)


class _StubStep(WizardStep):
    key = "stub"
    title = "Stub"
    subtitle = "Smoke step that does nothing."

    def build_widget(self, parent=None):
        from PySide6.QtWidgets import QLabel
        return QLabel("Smoke step", parent)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    state = WizardState()
    context = WizardContext(
        service_registry=None,  # type: ignore[arg-type]
        company_id=None,
        user_id=None,
        wizard_run_id=None,
    )
    controller = WizardController(
        wizard_code="smoke",
        steps=[_StubStep(), _StubStep()],
        context=context,
        state=state,
        advisor=build_company_setup_advisor(),
        assistant_engine=AssistantEngine(),
    )
    dialog = WizardHostDialog(
        controller=controller,
        title="Wizard Smoke",
        intro="Offscreen smoke for the wizard host dialog.",
    )
    dialog.show()
    app.processEvents()

    # Validate state machine basics.
    assert controller.is_first
    result = controller.advance()
    assert isinstance(result, StepValidationResult) and result.is_valid
    assert controller.current_index == 1
    controller.back()
    assert controller.current_index == 0

    print("OK wizard host smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
