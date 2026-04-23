"""Slice P1 smoke — payroll setup + payroll calculation ribbon surfaces.

Validates that:
  * all P1 payroll ribbon surfaces are registered,
  * the four payroll setup tabs each report the correct
    ``current_ribbon_surface_key()`` for an empty selection,
  * the four payroll calculation tabs do the same,
  * each workspace's ``_ribbon_commands()`` map exactly matches the
    command ids declared on its surfaces' button items.

This is an infrastructure-only smoke; it does NOT invoke handlers that
open dialogs (those belong to later slices' integration tests).
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime

from seeker_accounting.app.shell.ribbon.ribbon_models import RibbonButtonDef


_EXPECTED_SURFACES = (
    # payroll_setup
    "payroll_setup",
    "payroll_setup.settings",
    "payroll_setup.employees.none",
    "payroll_setup.employees.active",
    "payroll_setup.employees.inactive",
    "payroll_setup.components.none",
    "payroll_setup.components.selected",
    "payroll_setup.rules.none",
    "payroll_setup.rules.selected",
    # payroll_calculation
    "payroll_calculation",
    "payroll_calculation.profiles.none",
    "payroll_calculation.profiles.selected",
    "payroll_calculation.assignments.none",
    "payroll_calculation.assignments.selected",
    "payroll_calculation.inputs.none",
    "payroll_calculation.inputs.selected",
    "payroll_calculation.runs.none",
    "payroll_calculation.runs.run_selected",
    "payroll_calculation.runs.employee_selected",
)


def _surface_command_ids(registry, surface_key: str) -> set[str]:
    surface = registry.ribbon_registry.get(surface_key)
    assert surface is not None, f"surface not registered: {surface_key}"
    return {
        item.command_id
        for item in surface.items
        if isinstance(item, RibbonButtonDef)
    }


def main() -> int:
    app = QApplication.instance() or QApplication([])
    runtime = bootstrap_script_runtime(
        app,
        permission_snapshot=(
            "payroll.setup.view",
            "payroll.setup.edit",
            "payroll.calculation.view",
            "payroll.calculation.edit",
        ),
    )
    registry = runtime.service_registry

    # ── 1. All expected surfaces are registered ───────────────────────
    for key in _EXPECTED_SURFACES:
        assert registry.ribbon_registry.has(key), f"missing ribbon surface: {key}"

    # ── 2. PayrollSetupPage — tab-driven surface key flips ────────────
    from seeker_accounting.modules.payroll.ui.payroll_setup_page import PayrollSetupPage

    setup_page = PayrollSetupPage(registry)
    for _ in range(4):
        app.processEvents()

    setup_expected = {
        0: "payroll_setup.settings",
        1: "payroll_setup.employees.none",
        2: "payroll_setup.components.none",
        3: "payroll_setup.rules.none",
    }
    for index, expected_key in setup_expected.items():
        setup_page._tabs.setCurrentIndex(index)
        for _ in range(2):
            app.processEvents()
        actual = setup_page.current_ribbon_surface_key()
        assert actual == expected_key, (
            f"setup tab {index}: expected {expected_key!r}, got {actual!r}"
        )

    # Command map must cover every button command id across all setup
    # variant surfaces (selection variants share the same item list).
    setup_command_ids: set[str] = set()
    for key in (
        "payroll_setup.settings",
        "payroll_setup.employees.none",
        "payroll_setup.components.none",
        "payroll_setup.rules.none",
    ):
        setup_command_ids |= _surface_command_ids(registry, key)
    setup_handlers = set(setup_page._ribbon_commands().keys())
    missing_setup_handlers = setup_command_ids - setup_handlers
    assert not missing_setup_handlers, (
        f"PayrollSetupPage missing handlers for: {sorted(missing_setup_handlers)}"
    )

    # Every command in ribbon_state() must be a valid handler.
    setup_state = setup_page.ribbon_state()
    unknown_state_keys = set(setup_state.keys()) - setup_handlers
    assert not unknown_state_keys, (
        f"PayrollSetupPage.ribbon_state has unknown keys: {sorted(unknown_state_keys)}"
    )

    # ── 3. PayrollCalculationWorkspace — tab-driven surface key flips ─
    from PySide6.QtWidgets import QStackedWidget
    from seeker_accounting.modules.payroll.ui.payroll_calculation_workspace import (
        PayrollCalculationWorkspace,
    )

    holder_stack = QStackedWidget()
    calc_workspace = PayrollCalculationWorkspace(registry, holder_stack)
    for _ in range(4):
        app.processEvents()

    calc_expected = {
        0: "payroll_calculation.profiles.none",
        1: "payroll_calculation.assignments.none",
        2: "payroll_calculation.inputs.none",
        3: "payroll_calculation.runs.none",
    }
    for index, expected_key in calc_expected.items():
        calc_workspace._tabs.setCurrentIndex(index)
        for _ in range(2):
            app.processEvents()
        actual = calc_workspace.current_ribbon_surface_key()
        assert actual == expected_key, (
            f"calc tab {index}: expected {expected_key!r}, got {actual!r}"
        )

    calc_command_ids: set[str] = set()
    for key in (
        "payroll_calculation.profiles.none",
        "payroll_calculation.assignments.none",
        "payroll_calculation.inputs.none",
        "payroll_calculation.runs.none",
    ):
        calc_command_ids |= _surface_command_ids(registry, key)
    calc_handlers = set(calc_workspace._ribbon_commands().keys())
    missing_calc_handlers = calc_command_ids - calc_handlers
    assert not missing_calc_handlers, (
        f"PayrollCalculationWorkspace missing handlers for: {sorted(missing_calc_handlers)}"
    )

    calc_state = calc_workspace.ribbon_state()
    unknown_calc_state_keys = set(calc_state.keys()) - calc_handlers
    assert not unknown_calc_state_keys, (
        f"PayrollCalculationWorkspace.ribbon_state has unknown keys: "
        f"{sorted(unknown_calc_state_keys)}"
    )

    # With no company set and empty selections, action ribbon_state for
    # selection-dependent commands should all be False.
    for cmd_id in (
        "payroll_calculation.edit_profile",
        "payroll_calculation.toggle_profile",
        "payroll_calculation.edit_assignment",
        "payroll_calculation.toggle_assignment",
        "payroll_calculation.open_batch",
        "payroll_calculation.calculate_run",
        "payroll_calculation.approve_run",
        "payroll_calculation.void_run",
        "payroll_calculation.employee_detail",
        "payroll_calculation.project_allocations",
    ):
        assert calc_state[cmd_id] is False, (
            f"{cmd_id} should be disabled when nothing is selected"
        )

    print("payroll_ribbon_p1_smoke PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
