"""Tests for the native Payroll Workbench People pane (P2.S3 / P4.S2).

Validates:

- Pane renders with no active company: hire button disabled, empty table.
- Pane renders with company + employees: hire button enabled, table loaded.
- Selection gates the edit button.
- "Show inactive" toggle calls list_employees with active_only=False.
- Hire opens EmployeeOnboardingWizardDialog and refreshes on success.
- Edit / row-activate opens EmployeeHubWindow via child_window_manager.
- EmployeeOnboardingWizardDialog unavailable (service None): hire is a no-op.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import MagicMock, patch, call

from PySide6.QtWidgets import QApplication

from seeker_accounting.modules.payroll.dto.employee_dto import EmployeeListItemDTO
from seeker_accounting.modules.payroll.ui.workbench.panes.people_pane import (
    PeoplePaneWidget,
    _EmployeeTableModel,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_dto(
    id: int = 1,
    employee_number: str = "EMP001",
    display_name: str = "Alice Demo",
    is_active: bool = True,
) -> EmployeeListItemDTO:
    dto = MagicMock(spec=EmployeeListItemDTO)
    dto.id = id
    dto.employee_number = employee_number
    dto.display_name = display_name
    dto.department_name = "Engineering"
    dto.position_name = "Developer"
    dto.hire_date = None
    dto.is_active = is_active
    return dto


def _build_sr(*, with_company: bool, employees=None, onboarding_svc=True):
    sr = MagicMock(name="ServiceRegistry")
    if with_company:
        company = MagicMock()
        company.id = 7
        company.name = "Test SARL"
        sr.company_context_service.get_active_company.return_value = company
    else:
        sr.company_context_service.get_active_company.return_value = None

    sr.employee_service.list_employees.return_value = list(employees or [])
    sr.current_user = None

    if not onboarding_svc:
        sr.employee_onboarding_service = None
    else:
        sr.employee_onboarding_service = MagicMock(name="EmployeeOnboardingService")

    sr.child_window_manager = MagicMock(name="ChildWindowManager")
    return sr


# ── Table model tests ─────────────────────────────────────────────────────────


class EmployeeTableModelTests(unittest.TestCase):
    def test_empty_model(self) -> None:
        model = _EmployeeTableModel()
        self.assertEqual(model.rowCount(), 0)
        self.assertEqual(model.columnCount(), 6)

    def test_load_and_row_dto(self) -> None:
        model = _EmployeeTableModel()
        dto = _make_dto()
        model.load([dto])
        self.assertEqual(model.rowCount(), 1)
        self.assertIs(model.row_dto(0), dto)
        self.assertIsNone(model.row_dto(99))

    def test_display_role_columns(self) -> None:
        from PySide6.QtCore import QModelIndex, Qt

        model = _EmployeeTableModel()
        dto = _make_dto(employee_number="X01", display_name="Bob")
        model.load([dto])

        idx = model.index(0, 0)
        self.assertEqual(model.data(idx, Qt.ItemDataRole.DisplayRole), "X01")
        idx = model.index(0, 1)
        self.assertEqual(model.data(idx, Qt.ItemDataRole.DisplayRole), "Bob")

    def test_status_column(self) -> None:
        from PySide6.QtCore import Qt

        model = _EmployeeTableModel()
        active_dto = _make_dto(is_active=True)
        inactive_dto = _make_dto(id=2, employee_number="E02", is_active=False)
        model.load([active_dto, inactive_dto])

        idx_active = model.index(0, 5)
        idx_inactive = model.index(1, 5)
        self.assertEqual(model.data(idx_active, Qt.ItemDataRole.DisplayRole), "Active")
        self.assertEqual(
            model.data(idx_inactive, Qt.ItemDataRole.DisplayRole), "Inactive"
        )


# ── Pane widget tests ─────────────────────────────────────────────────────────


class PeoplePaneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_renders_no_company(self) -> None:
        sr = _build_sr(with_company=False)
        pane = PeoplePaneWidget(sr)
        try:
            self.assertFalse(pane._hire_btn.isEnabled())  # noqa: SLF001
            self.assertFalse(pane._edit_btn.isEnabled())  # noqa: SLF001
            self.assertEqual(pane._model.rowCount(), 0)  # noqa: SLF001
        finally:
            pane.deleteLater()

    def test_renders_with_company_loads_employees(self) -> None:
        dtos = [_make_dto(id=1), _make_dto(id=2, employee_number="EMP002")]
        sr = _build_sr(with_company=True, employees=dtos)
        pane = PeoplePaneWidget(sr)
        try:
            self.assertTrue(pane._hire_btn.isEnabled())  # noqa: SLF001
            self.assertEqual(pane._model.rowCount(), 2)  # noqa: SLF001
        finally:
            pane.deleteLater()

    def test_employee_service_none_gives_empty_table(self) -> None:
        sr = _build_sr(with_company=True)
        sr.employee_service = None
        pane = PeoplePaneWidget(sr)
        try:
            self.assertEqual(pane._model.rowCount(), 0)  # noqa: SLF001
        finally:
            pane.deleteLater()

    def test_selection_enables_edit_btn(self) -> None:
        dtos = [_make_dto()]
        sr = _build_sr(with_company=True, employees=dtos)
        pane = PeoplePaneWidget(sr)
        try:
            self.assertFalse(pane._edit_btn.isEnabled())  # noqa: SLF001
            # Simulate DataTable emitting selection_changed with source row 0.
            pane._on_selection_changed([0])
            self.assertTrue(pane._edit_btn.isEnabled())  # noqa: SLF001
            # Clear selection.
            pane._on_selection_changed([])
            self.assertFalse(pane._edit_btn.isEnabled())  # noqa: SLF001
        finally:
            pane.deleteLater()

    def test_inactive_toggle_calls_list_with_active_only_false(self) -> None:
        sr = _build_sr(with_company=True, employees=[])
        pane = PeoplePaneWidget(sr)
        try:
            sr.employee_service.list_employees.reset_mock()
            pane._on_inactive_toggled(True)
            sr.employee_service.list_employees.assert_called_once_with(7, active_only=False)
        finally:
            pane.deleteLater()

    def test_hire_no_op_when_onboarding_service_none(self) -> None:
        sr = _build_sr(with_company=True, onboarding_svc=False)
        pane = PeoplePaneWidget(sr)
        try:
            # Should not raise or open any dialog.
            with patch(
                "seeker_accounting.modules.payroll.ui.bp.employee_onboarding_wizard"
                ".EmployeeOnboardingWizardDialog"
            ) as MockDlg:
                pane._on_hire()
                MockDlg.assert_not_called()
        finally:
            pane.deleteLater()

    def test_hire_opens_wizard_and_refreshes_on_success(self) -> None:
        sr = _build_sr(with_company=True, employees=[])
        pane = PeoplePaneWidget(sr)
        try:
            refresh_calls: list[None] = []
            original_refresh = pane.refresh

            def _spy_refresh():
                refresh_calls.append(None)
                original_refresh()

            pane.refresh = _spy_refresh

            with patch(
                "seeker_accounting.modules.payroll.ui.bp.employee_onboarding_wizard"
                ".EmployeeOnboardingWizardDialog"
            ) as MockDlg:
                instance = MockDlg.return_value
                instance.exec.return_value = True
                instance.created_employee_id = 42

                pane._on_hire()

                MockDlg.assert_called_once_with(
                    service_registry=sr,
                    company_id=7,
                    actor_user_id=None,
                    draft_id=None,
                    parent=pane,
                )
                instance.exec.assert_called_once()
                # refresh should have been called once on success
                self.assertGreaterEqual(len(refresh_calls), 1)
        finally:
            pane.deleteLater()

    def test_hire_no_refresh_when_dialog_cancelled(self) -> None:
        sr = _build_sr(with_company=True, employees=[])
        pane = PeoplePaneWidget(sr)
        try:
            refresh_calls: list[None] = []
            original_refresh = pane.refresh

            def _spy_refresh():
                # Only count calls after initial build (refresh() called in __init__)
                refresh_calls.append(None)
                original_refresh()

            with patch(
                "seeker_accounting.modules.payroll.ui.bp.employee_onboarding_wizard"
                ".EmployeeOnboardingWizardDialog"
            ) as MockDlg:
                instance = MockDlg.return_value
                instance.exec.return_value = False  # cancelled
                instance.created_employee_id = None

                pane.refresh = _spy_refresh
                pane._on_hire()

                self.assertEqual(len(refresh_calls), 0)
        finally:
            pane.deleteLater()

    def test_edit_opens_hub_window_via_manager(self) -> None:
        dto = _make_dto(id=5)
        sr = _build_sr(with_company=True, employees=[dto])
        pane = PeoplePaneWidget(sr)
        try:
            pane._on_selection_changed([0])

            with patch(
                "seeker_accounting.modules.payroll.ui.employee_hub_window"
                ".EmployeeHubWindow"
            ) as MockHub:
                MockHub.DOC_TYPE = "payroll_employee_hub"
                pane._on_edit()

                sr.child_window_manager.open_document.assert_called_once()
                doc_type_arg = sr.child_window_manager.open_document.call_args[0][0]
                emp_id_arg = sr.child_window_manager.open_document.call_args[0][1]
                self.assertEqual(doc_type_arg, "payroll_employee_hub")
                self.assertEqual(emp_id_arg, 5)
        finally:
            pane.deleteLater()

    def test_row_activated_opens_hub_window(self) -> None:
        dto = _make_dto(id=9)
        sr = _build_sr(with_company=True, employees=[dto])
        pane = PeoplePaneWidget(sr)
        try:
            with patch(
                "seeker_accounting.modules.payroll.ui.employee_hub_window"
                ".EmployeeHubWindow"
            ) as MockHub:
                MockHub.DOC_TYPE = "payroll_employee_hub"
                pane._on_row_activated(0)

                sr.child_window_manager.open_document.assert_called_once()
                emp_id_arg = sr.child_window_manager.open_document.call_args[0][1]
                self.assertEqual(emp_id_arg, 9)
        finally:
            pane.deleteLater()


if __name__ == "__main__":
    unittest.main()
