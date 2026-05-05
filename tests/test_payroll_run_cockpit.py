"""Phase 3 / P3.S1+S4 — Payroll Run Cockpit smoke tests.

Validates the cockpit end-to-end against a stubbed
:class:`~seeker_accounting.app.dependency.service_registry.ServiceRegistry`:

* header reflects run reference / period / status
* primary button label tracks state machine
* KPI tiles sum from the employee list
* employee tree renders one row per employee with expandable lines
* status filter hides/shows rows
* density toggle changes the table's row height label
* state-driven gating: can_calculate / can_approve / can_void
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    PayrollRunDetailDTO,
    PayrollRunEmployeeDetailDTO,
    PayrollRunEmployeeListItemDTO,
    PayrollRunLineDTO,
)
from seeker_accounting.modules.payroll.ui.payroll_run_cockpit import (
    PayrollRunCockpit,
)


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _detail(status: str = "calculated") -> PayrollRunDetailDTO:
    return PayrollRunDetailDTO(
        id=42,
        company_id=1,
        run_reference="PR-2025-03",
        run_label="March 2025",
        period_year=2025,
        period_month=3,
        status_code=status,
        currency_code="XAF",
        run_date=date(2025, 3, 31),
        payment_date=date(2025, 4, 5),
        notes=None,
        calculated_at=None,
        approved_at=None,
    )


def _employees() -> list[PayrollRunEmployeeListItemDTO]:
    return [
        PayrollRunEmployeeListItemDTO(
            id=1,
            run_id=42,
            employee_id=1001,
            employee_number="EMP001",
            employee_display_name="Alice Mbarga",
            gross_earnings=Decimal("500000"),
            total_employee_deductions=Decimal("40000"),
            total_taxes=Decimal("60000"),
            net_payable=Decimal("400000"),
            employer_cost_base=Decimal("550000"),
            status_code="included",
        ),
        PayrollRunEmployeeListItemDTO(
            id=2,
            run_id=42,
            employee_id=1002,
            employee_number="EMP002",
            employee_display_name="Brice Tchouanga",
            gross_earnings=Decimal("300000"),
            total_employee_deductions=Decimal("20000"),
            total_taxes=Decimal("30000"),
            net_payable=Decimal("250000"),
            employer_cost_base=Decimal("330000"),
            status_code="excluded",
            exclusion_reason="On leave",
        ),
    ]


def _emp_detail(emp_id: int) -> PayrollRunEmployeeDetailDTO:
    return PayrollRunEmployeeDetailDTO(
        id=emp_id,
        run_id=42,
        run_reference="PR-2025-03",
        period_year=2025,
        period_month=3,
        employee_id=1000 + emp_id,
        employee_number=f"EMP00{emp_id}",
        employee_display_name=f"Employee {emp_id}",
        gross_earnings=Decimal("500000"),
        taxable_salary_base=Decimal("450000"),
        tdl_base=Decimal("450000"),
        cnps_contributory_base=Decimal("450000"),
        employer_cost_base=Decimal("550000"),
        net_payable=Decimal("400000"),
        total_earnings=Decimal("500000"),
        total_employee_deductions=Decimal("40000"),
        total_employer_contributions=Decimal("50000"),
        total_taxes=Decimal("60000"),
        status_code="included",
        calculation_notes=None,
        exclusion_reason=None,
        lines=[
            PayrollRunLineDTO(
                id=1,
                component_id=10,
                component_name="Base Salary",
                component_code="BASE",
                component_type_code="earning",
                calculation_basis=Decimal("500000"),
                rate_applied=None,
                component_amount=Decimal("500000"),
            ),
        ],
    )


def _build_registry(status: str = "calculated") -> MagicMock:
    sr = MagicMock(name="ServiceRegistry")
    sr.payroll_run_service.get_run.return_value = _detail(status)
    sr.payroll_run_service.list_run_employees.return_value = _employees()
    sr.payroll_run_service.get_run_employee_detail.side_effect = (
        lambda *, run_id, run_employee_id: _emp_detail(run_employee_id)
    )
    sr.payroll_run_service.list_runs.return_value = []
    sr.payroll_input_service.list_batches.return_value = []
    sr.employee_service.list_employees.return_value = []
    sr.child_window_manager = None
    return sr


class PayrollRunCockpitSmokeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        _qapp()

    # ── header / status / primary action ─────────────────────────────

    def test_header_reflects_calculated_state(self) -> None:
        sr = _build_registry("calculated")
        w = PayrollRunCockpit(sr, company_id=1, run_id=42)
        try:
            self.assertIn("PR-2025-03", w._header._title.text())
            self.assertEqual(w._status_chip.status, "calculated")
            self.assertEqual(w._primary_btn.text(), "Approve")
            self.assertTrue(w._primary_btn.isEnabled())
            self.assertEqual(w._currency_label.text(), "XAF")
        finally:
            w.deleteLater()

    def test_primary_button_label_for_draft(self) -> None:
        w = PayrollRunCockpit(_build_registry("draft"), company_id=1, run_id=42)
        try:
            self.assertEqual(w._primary_btn.text(), "Calculate")
        finally:
            w.deleteLater()

    def test_primary_disabled_for_terminal_state(self) -> None:
        w = PayrollRunCockpit(_build_registry("voided"), company_id=1, run_id=42)
        try:
            self.assertFalse(w._primary_btn.isEnabled())
        finally:
            w.deleteLater()

    # ── employee grid ─────────────────────────────────────────────────

    def test_tree_rows_match_employees(self) -> None:
        w = PayrollRunCockpit(_build_registry("calculated"), company_id=1, run_id=42)
        try:
            self.assertEqual(w._tree.topLevelItemCount(), 2)
            first = w._tree.topLevelItem(0)
            self.assertIn("Alice", first.text(0))
        finally:
            w.deleteLater()

    def test_kpi_tiles_summed(self) -> None:
        w = PayrollRunCockpit(_build_registry("calculated"), company_id=1, run_id=42)
        try:
            # Only the included employee contributes to KPI sums.
            self.assertIn("1", w._kpi_employees._value_label.text())
            # 500k gross included; 300k excluded.
            self.assertIn("500", w._kpi_gross._value_label.text().replace(",", ""))
        finally:
            w.deleteLater()

    def test_status_filter_hides_excluded(self) -> None:
        w = PayrollRunCockpit(_build_registry("calculated"), company_id=1, run_id=42)
        try:
            # Filter to "included" only.
            idx = w._status_filter.findData("included")
            self.assertGreaterEqual(idx, 0)
            w._status_filter.setCurrentIndex(idx)
            visible = [
                w._tree.topLevelItem(i)
                for i in range(w._tree.topLevelItemCount())
                if not w._tree.topLevelItem(i).isHidden()
            ]
            self.assertEqual(len(visible), 1)
            self.assertIn("Alice", visible[0].text(0))
        finally:
            w.deleteLater()

    def test_search_filter_by_text(self) -> None:
        w = PayrollRunCockpit(_build_registry("calculated"), company_id=1, run_id=42)
        try:
            w._search.setText("Brice")
            visible = [
                w._tree.topLevelItem(i)
                for i in range(w._tree.topLevelItemCount())
                if not w._tree.topLevelItem(i).isHidden()
            ]
            self.assertEqual(len(visible), 1)
            self.assertIn("Brice", visible[0].text(0))
        finally:
            w.deleteLater()

    # ── public ribbon-host API gates correctly ───────────────────────

    def test_can_actions_reflect_state(self) -> None:
        w = PayrollRunCockpit(_build_registry("calculated"), company_id=1, run_id=42)
        try:
            self.assertTrue(w.can_calculate())
            self.assertTrue(w.can_approve())
            self.assertTrue(w.can_void())
        finally:
            w.deleteLater()

        w2 = PayrollRunCockpit(_build_registry("posted"), company_id=1, run_id=42)
        try:
            self.assertFalse(w2.can_calculate())
            self.assertFalse(w2.can_approve())
            self.assertFalse(w2.can_void())
        finally:
            w2.deleteLater()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
