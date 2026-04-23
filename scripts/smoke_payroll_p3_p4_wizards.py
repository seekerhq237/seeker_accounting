"""Slice P3/P4 smoke — payroll activation + employee hire wizards.

Validates:

1. Ribbon surface registers wizard command ids on ``payroll_setup.settings``
   and all ``payroll_setup.employees.*`` variants.
2. ``PayrollActivationWizardDialog`` drives settings + pack + structure
   services without user interaction (direct method calls on the dialog).
3. ``EmployeeHireWizardDialog`` creates an employee + compensation profile
   + recurring component assignments.
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QCheckBox

from shared.bootstrap import bootstrap_script_runtime  # noqa: E402

from seeker_accounting.modules.administration.rbac_catalog import (  # noqa: E402
    SYSTEM_PERMISSION_BY_CODE,
)
from seeker_accounting.modules.accounting.reference_data.models.country import Country  # noqa: E402
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency  # noqa: E402
from seeker_accounting.modules.companies.dto.company_commands import (  # noqa: E402
    CreateCompanyCommand,
)
from seeker_accounting.modules.payroll.ui.wizards.employee_hire_wizard import (  # noqa: E402
    EmployeeHireWizardDialog,
)
from seeker_accounting.modules.payroll.ui.wizards.payroll_activation_wizard import (  # noqa: E402
    PayrollActivationWizardDialog,
)


def _ensure_country_and_currency(reg) -> None:
    with reg.session_context.unit_of_work_factory() as uow:
        session = uow.session
        if not session.get(Country, "CM"):
            session.add(Country(code="CM", name="Cameroon", is_active=True))
        if not session.get(Currency, "XAF"):
            session.add(
                Currency(
                    code="XAF",
                    name="CFA Franc BEAC",
                    symbol="FCFA",
                    decimal_places=0,
                    is_active=True,
                )
            )
        uow.commit()


def _ok(label: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}{(': ' + detail) if detail else ''}")
    return ok


def _surface_command_ids(surface):
    return [item.command_id for item in surface.items if hasattr(item, "command_id")]


def main() -> int:
    failures: list[str] = []
    app = QApplication.instance() or QApplication([])
    bootstrap = bootstrap_script_runtime(
        app,
        permission_snapshot=tuple(SYSTEM_PERMISSION_BY_CODE.keys()),
    )
    reg = bootstrap.service_registry

    print("=" * 60)
    print("Slice P3/P4 smoke — payroll wizards")
    print("=" * 60)

    # ── 1. Ribbon surfaces include wizard commands ───────────────────
    print("\n[1] Ribbon surfaces include wizard commands")
    rr = reg.ribbon_registry
    settings_cmds = set(_surface_command_ids(rr.get("payroll_setup.settings")))
    if not _ok(
        "activation_wizard on settings surface",
        "payroll_setup.activation_wizard" in settings_cmds,
    ):
        failures.append("activation_wizard missing from payroll_setup.settings")

    for variant in ("none", "active", "inactive"):
        key = f"payroll_setup.employees.{variant}"
        cmds = set(_surface_command_ids(rr.get(key)))
        if not _ok(
            f"hire_employee_wizard on {key}",
            "payroll_setup.hire_employee_wizard" in cmds,
        ):
            failures.append(f"hire_employee_wizard missing from {key}")

    # ── 2. Seed company ──────────────────────────────────────────────
    print("\n[2] Seeding test company")
    _ensure_country_and_currency(reg)

    import time
    ts = int(time.time())
    company = reg.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"P3P4 Smoke SARL {ts}",
            display_name=f"P3P4 Smoke {ts}",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    cid = company.id
    print(f"  company_id={cid}")
    reg.chart_seed_service.ensure_global_chart_reference_seed()
    reg.company_seed_service.seed_built_in_chart(cid)

    # ── 3. Drive PayrollActivationWizardDialog headlessly ────────────
    print("\n[3] PayrollActivationWizardDialog drives services")
    act_dlg = PayrollActivationWizardDialog(reg, cid, company.display_name)
    try:
        # Ensure pack combo picked CMR_2024_V1 if available.
        idx = act_dlg._pack_combo.findData("CMR_2024_V1")
        if idx >= 0:
            act_dlg._pack_combo.setCurrentIndex(idx)
        act_dlg._dept_code_edit.setText("OPS")
        act_dlg._dept_name_edit.setText("Operations")
        act_dlg._pos_code_edit.setText("MGR")
        act_dlg._pos_name_edit.setText("Manager")

        act_dlg._handle_apply()
        result = act_dlg.result_payload
        if not _ok("activation wizard produced a result", result is not None):
            failures.append("activation wizard returned no result")
        else:
            _ok("settings applied", result.settings_applied)
            _ok(
                "pack applied (components created)",
                (result.pack_code or "").startswith("CMR") and result.components_created > 0,
                f"pack={result.pack_code}, components={result.components_created}, rules={result.rule_sets_created}",
            )
            _ok(
                "department created",
                result.departments_created == 1,
            )
            _ok(
                "position created",
                result.positions_created == 1,
            )
    finally:
        act_dlg.close()

    # Re-running is idempotent: department/position conflicts should not
    # be fatal (wizard swallows ConflictError on structure).
    print("\n[3b] Activation wizard is re-runnable (no-op on existing structure)")
    act_dlg2 = PayrollActivationWizardDialog(reg, cid, company.display_name)
    try:
        idx = act_dlg2._pack_combo.findData("CMR_2024_V1")
        if idx >= 0:
            act_dlg2._pack_combo.setCurrentIndex(idx)
        # Same dept/pos codes — should not raise.
        act_dlg2._handle_apply()
        _ok("re-run did not error", act_dlg2.result_payload is not None)
    finally:
        act_dlg2.close()

    # ── 4. Drive EmployeeHireWizardDialog ────────────────────────────
    print("\n[4] EmployeeHireWizardDialog drives services")
    hire_dlg = EmployeeHireWizardDialog(reg, cid, company.display_name)
    try:
        hire_dlg._employee_number_edit.setText("EMPW001")
        hire_dlg._first_name_edit.setText("Alice")
        hire_dlg._last_name_edit.setText("Smith")
        hire_dlg._display_name_edit.setText("Alice Smith")
        hire_dlg._email_edit.setText("alice@example.com")
        today = date.today()
        hire_dlg._hire_date_edit.setDate(QDate(today.year, 1, 1))
        hire_dlg._currency_edit.setText("XAF")

        # Select first department / position (index 1 = first real entry)
        if hire_dlg._department_combo.count() > 1:
            hire_dlg._department_combo.setCurrentIndex(1)
        if hire_dlg._position_combo.count() > 1:
            hire_dlg._position_combo.setCurrentIndex(1)

        hire_dlg._profile_name_edit.setText("Standard")
        hire_dlg._salary_spin.setValue(400_000.0)
        hire_dlg._profile_currency_edit.setText("XAF")
        hire_dlg._effective_from_edit.setDate(QDate(today.year, 1, 1))

        # Count pre-selected components (deductions/taxes are checked by default).
        preselected = 0
        for i in range(hire_dlg._components_list.count()):
            item = hire_dlg._components_list.item(i)
            w = hire_dlg._components_list.itemWidget(item)
            if isinstance(w, QCheckBox) and w.isChecked():
                preselected += 1
        print(f"  pre-selected components: {preselected}")

        hire_dlg._handle_apply()
        result = hire_dlg.result_payload
        if not _ok("hire wizard produced a result", result is not None):
            failures.append("hire wizard returned no result")
        else:
            _ok("employee row created", result.employee_id > 0)
            _ok("compensation profile created", result.profile_id is not None)
            _ok(
                "component assignments created",
                len(result.assignment_ids) == preselected,
                f"count={len(result.assignment_ids)} expected={preselected}",
            )
    finally:
        hire_dlg.close()

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if failures:
        print(f"Slice P3/P4 smoke FAIL — {len(failures)} failures")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Slice P3/P4 smoke PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
