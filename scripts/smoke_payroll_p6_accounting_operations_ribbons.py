"""Slice P6 smoke — payroll accounting + operations ribbon surfaces.

Validates that:
  * all P6 payroll accounting + operations ribbon surfaces are registered
  * each workspace reports the correct ``current_ribbon_surface_key()``
    per tab with an empty selection
  * each workspace's ``_ribbon_commands()`` map covers every command id
    declared on its surfaces' button items
  * every command in ``ribbon_state()`` is a valid handler
  * selection-dependent commands are disabled when nothing is selected
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from PySide6.QtWidgets import QApplication, QStackedWidget

from shared.bootstrap import bootstrap_script_runtime

from seeker_accounting.app.shell.ribbon.ribbon_models import RibbonButtonDef


_EXPECTED_SURFACES = (
    # payroll_accounting
    "payroll_accounting",
    "payroll_accounting.posting.none",
    "payroll_accounting.posting.postable_run",
    "payroll_accounting.posting.posted_run",
    "payroll_accounting.payments.none",
    "payroll_accounting.payments.run_selected",
    "payroll_accounting.payments.employee_selected",
    "payroll_accounting.remittances.none",
    "payroll_accounting.remittances.batch_selected",
    "payroll_accounting.summary",
    # payroll_operations
    "payroll_operations",
    "payroll_operations.validation.none",
    "payroll_operations.validation.blocker_selected",
    "payroll_operations.validation.warning_selected",
    "payroll_operations.packs",
    "payroll_operations.imports",
    "payroll_operations.print",
    "payroll_operations.audit",
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
            "payroll.accounting.view",
            "payroll.accounting.edit",
            "payroll.operations.view",
            "payroll.operations.edit",
        ),
    )
    registry = runtime.service_registry

    # ── 1. All expected surfaces registered ───────────────────────────
    for key in _EXPECTED_SURFACES:
        assert registry.ribbon_registry.has(key), f"missing ribbon surface: {key}"

    # ── 2. PayrollAccountingWorkspace — tab-driven surface key flips ──
    from seeker_accounting.modules.payroll.ui.payroll_accounting_workspace import (
        PayrollAccountingWorkspace,
    )

    acct_stack = QStackedWidget()
    acct_workspace = PayrollAccountingWorkspace(registry, acct_stack)
    for _ in range(4):
        app.processEvents()

    acct_expected = {
        0: "payroll_accounting.posting.none",
        1: "payroll_accounting.payments.none",
        2: "payroll_accounting.remittances.none",
        3: "payroll_accounting.summary",
    }
    for index, expected_key in acct_expected.items():
        acct_workspace._tabs.setCurrentIndex(index)
        for _ in range(2):
            app.processEvents()
        actual = acct_workspace.current_ribbon_surface_key()
        assert actual == expected_key, (
            f"accounting tab {index}: expected {expected_key!r}, got {actual!r}"
        )

    acct_command_ids: set[str] = set()
    for key in (
        "payroll_accounting.posting.none",
        "payroll_accounting.payments.none",
        "payroll_accounting.remittances.none",
        "payroll_accounting.summary",
    ):
        acct_command_ids |= _surface_command_ids(registry, key)
    acct_handlers = set(acct_workspace._ribbon_commands().keys())
    missing = acct_command_ids - acct_handlers
    assert not missing, (
        f"PayrollAccountingWorkspace missing handlers for: {sorted(missing)}"
    )

    acct_state = acct_workspace.ribbon_state()
    unknown = set(acct_state.keys()) - acct_handlers
    assert not unknown, (
        f"PayrollAccountingWorkspace.ribbon_state has unknown keys: {sorted(unknown)}"
    )

    # Selection-dependent commands should be disabled with nothing selected.
    for cmd_id in (
        "payroll_accounting.post_to_gl",
        "payroll_accounting.posting_detail",
        "payroll_accounting.record_payment",
        "payroll_accounting.open_batch",
        "payroll_accounting.add_line",
        "payroll_accounting.cancel_batch",
    ):
        assert acct_state[cmd_id] is False, (
            f"{cmd_id} should be disabled when nothing is selected"
        )

    # ── 3. PayrollOperationsWorkspace — tab-driven surface key flips ──
    from seeker_accounting.modules.payroll.ui.payroll_operations_workspace import (
        PayrollOperationsWorkspace,
    )

    ops_stack = QStackedWidget()
    ops_workspace = PayrollOperationsWorkspace(registry, ops_stack)
    for _ in range(4):
        app.processEvents()

    ops_expected = {
        0: "payroll_operations.validation.none",
        1: "payroll_operations.packs",
        2: "payroll_operations.imports",
        3: "payroll_operations.print",
        4: "payroll_operations.audit",
    }
    for index, expected_key in ops_expected.items():
        ops_workspace._tabs.setCurrentIndex(index)
        for _ in range(2):
            app.processEvents()
        actual = ops_workspace.current_ribbon_surface_key()
        assert actual == expected_key, (
            f"operations tab {index}: expected {expected_key!r}, got {actual!r}"
        )

    ops_command_ids: set[str] = set()
    for key in (
        "payroll_operations.validation.none",
        "payroll_operations.packs",
        "payroll_operations.imports",
        "payroll_operations.print",
        "payroll_operations.audit",
    ):
        ops_command_ids |= _surface_command_ids(registry, key)
    ops_handlers = set(ops_workspace._ribbon_commands().keys())
    missing = ops_command_ids - ops_handlers
    assert not missing, (
        f"PayrollOperationsWorkspace missing handlers for: {sorted(missing)}"
    )

    ops_state = ops_workspace.ribbon_state()
    unknown = set(ops_state.keys()) - ops_handlers
    assert not unknown, (
        f"PayrollOperationsWorkspace.ribbon_state has unknown keys: {sorted(unknown)}"
    )

    for cmd_id in (
        "payroll_operations.open_check_detail",
        "payroll_operations.apply_pack",
        "payroll_operations.preview_pack",
        "payroll_operations.preview_import",
        "payroll_operations.execute_import",
        "payroll_operations.print_payslips",
        "payroll_operations.print_summary",
        "payroll_operations.save_pdf",
    ):
        assert ops_state[cmd_id] is False, (
            f"{cmd_id} should be disabled when nothing is selected"
        )

    print("payroll_ribbon_p6_smoke PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
