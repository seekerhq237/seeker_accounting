"""Smoke tests for P1.S6 (WizardShell) and P4.S2 (Hire BP wizard UI)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication, QLabel

from seeker_accounting.shared.ui.components.inline_issue_band import ValidationIssue
from seeker_accounting.shared.ui.components.wizard_shell import (
    WizardShell,
    WizardStepDescriptor,
)


class WizardShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _make(self) -> WizardShell:
        return WizardShell(
            "Test wizard",
            (
                WizardStepDescriptor("a", "Alpha"),
                WizardStepDescriptor("b", "Beta"),
                WizardStepDescriptor("c", "Gamma"),
            ),
        )

    def test_initial_step_active(self) -> None:
        shell = self._make()
        self.assertEqual(shell.current_step_id(), "a")
        self.assertFalse(shell.is_last_step())
        self.assertEqual(shell.state_map()["a"], "active")
        self.assertEqual(shell.state_map()["b"], "pending")

    def test_set_step_widget_swaps(self) -> None:
        shell = self._make()
        widget = QLabel("hello")
        shell.set_step_widget("b", widget)
        # Should not crash; widget registered under step b.
        self.assertEqual(shell.current_step_id(), "a")

    def test_advance_marks_complete(self) -> None:
        shell = self._make()
        shell.advance_step(mark_complete=True)
        self.assertEqual(shell.current_step_id(), "b")
        self.assertEqual(shell.state_map()["a"], "complete")
        self.assertEqual(shell.state_map()["b"], "active")

    def test_go_back(self) -> None:
        shell = self._make()
        shell.advance_step()
        shell.go_back()
        self.assertEqual(shell.current_step_id(), "a")

    def test_set_step_issues_marks_blocked(self) -> None:
        shell = self._make()
        shell.set_step_issues("a", [ValidationIssue(severity="error", message="bad")])
        self.assertEqual(shell.state_map()["a"], "issues")

    def test_step_changed_signal(self) -> None:
        shell = self._make()
        events = []
        shell.step_changed.connect(events.append)
        shell.advance_step()
        self.assertEqual(events, ["b"])

    def test_finish_signal_on_last_step(self) -> None:
        shell = self._make()
        shell.advance_step()
        shell.advance_step()
        self.assertTrue(shell.is_last_step())
        emitted: list[bool] = []
        shell.finish_requested.connect(lambda: emitted.append(True))
        shell._on_primary()  # type: ignore[attr-defined]
        self.assertEqual(emitted, [True])

    def test_requires_at_least_one_step(self) -> None:
        with self.assertRaises(ValueError):
            WizardShell("X", ())


class EmployeeOnboardingWizardDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _stub_service(self, *, draft_id: int = 1):
        from seeker_accounting.modules.payroll.dto.employee_onboarding_dto import (
            EmployeeOnboardingDraftDTO,
            EmployeeOnboardingState,
        )

        def make_dto(state=EmployeeOnboardingState.DRAFT_IDENTITY.value, payload=None):
            return EmployeeOnboardingDraftDTO(
                id=draft_id,
                company_id=1,
                status_code=state,
                current_step=state,
                payload=payload or {
                    "identity": {}, "employment": {}, "compensation": {},
                    "payment": {}, "statutory": {}, "components": {},
                },
                started_by_user_id=None,
                last_modified_by_user_id=None,
                completed_at=None,
                abandoned_at=None,
                abandon_reason=None,
                produced_employee_id=None,
                created_at=None,
                updated_at=None,
            )

        service = MagicMock()
        current = {"dto": make_dto()}

        def start_draft(_):
            current["dto"] = make_dto()
            return current["dto"]

        def update_step(_company_id, cmd):
            payload = dict(current["dto"].payload)
            payload[cmd.step_code] = dict(cmd.patch)
            current["dto"] = make_dto(current["dto"].status_code, payload)
            return current["dto"]

        def transition_state(_company_id, cmd):
            current["dto"] = make_dto(cmd.target_state, current["dto"].payload)
            return current["dto"]

        def complete(_company_id, _draft_id, actor_user_id=None):
            payload = current["dto"].payload
            current["dto"] = EmployeeOnboardingDraftDTO(
                id=draft_id, company_id=1,
                status_code=EmployeeOnboardingState.COMPLETED.value,
                current_step=EmployeeOnboardingState.COMPLETED.value,
                payload=payload,
                started_by_user_id=None, last_modified_by_user_id=None,
                completed_at=None, abandoned_at=None, abandon_reason=None,
                produced_employee_id=999,
                created_at=None, updated_at=None,
            )
            return current["dto"]

        service.start_draft.side_effect = start_draft
        service.update_step.side_effect = update_step
        service.transition_state.side_effect = transition_state
        service.complete.side_effect = complete
        service.get_draft.side_effect = lambda c, d: current["dto"]
        return service

    def _make_dialog(self):
        from seeker_accounting.modules.payroll.ui.bp.employee_onboarding_wizard import (
            EmployeeOnboardingWizardDialog,
        )

        registry = MagicMock()
        registry.employee_onboarding_service = self._stub_service()
        return EmployeeOnboardingWizardDialog(
            service_registry=registry, company_id=1, actor_user_id=None,
        )

    def test_dialog_constructs_and_starts_draft(self) -> None:
        dlg = self._make_dialog()
        self.assertIsNotNone(dlg.draft)
        self.assertEqual(dlg.current_step_id(), "identity")

    def test_step_advance_calls_service(self) -> None:
        dlg = self._make_dialog()
        # Fill identity then click Next.
        identity = dlg._step_widgets["identity"]  # type: ignore[attr-defined]
        identity._first_name.setText("Ada")
        identity._last_name.setText("Lovelace")
        dlg._on_next("identity")  # type: ignore[attr-defined]
        self.assertEqual(dlg.current_step_id(), "employment")

    def test_finish_requires_review_step(self) -> None:
        dlg = self._make_dialog()
        # Drive directly to review by simulating advances.
        for _ in range(6):
            dlg.advance_step(mark_complete=False)
        self.assertEqual(dlg.current_step_id(), "review")
        dlg._on_finish()  # type: ignore[attr-defined]
        self.assertEqual(dlg.created_employee_id, 999)


if __name__ == "__main__":
    unittest.main()
