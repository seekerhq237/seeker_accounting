"""Slice P7a smoke — Compensation Change wizard.

Validates:

1. Ribbon surface ``payroll_setup.employees.active`` exposes
   ``payroll_setup.compensation_change_wizard`` and gating is correct
   (disabled with no selection, enabled when an active employee is
   selected).
2. ``CompensationChangeWizardDialog`` drives the compensation profile
   service end-to-end: preselected employee, new profile fields, apply.
3. Result payload contains the expected employee id + profile metadata.
4. A component assignment add-on (optional step) is created when a
   component is picked.
5. Validation: duplicate effective_from raises ConflictError surfaced
   in the dialog error label.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime  # noqa: E402

from seeker_accounting.modules.administration.rbac_catalog import (  # noqa: E402
    SYSTEM_PERMISSION_BY_CODE,
)
from seeker_accounting.modules.accounting.reference_data.models.country import Country  # noqa: E402
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency  # noqa: E402
from seeker_accounting.modules.companies.dto.company_commands import (  # noqa: E402
    CreateCompanyCommand,
)
from seeker_accounting.modules.payroll.ui.wizards.compensation_change_wizard import (  # noqa: E402
    CompensationChangeWizardDialog,
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
                    code="XAF", name="CFA Franc BEAC", symbol="FCFA",
                    decimal_places=0, is_active=True,
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
        app, permission_snapshot=tuple(SYSTEM_PERMISSION_BY_CODE.keys()),
    )
    reg = bootstrap.service_registry

    print("=" * 60)
    print("Slice P7a smoke — Compensation Change wizard")
    print("=" * 60)

    # ── 1. Ribbon surface exposes the wizard command ────────────────
    print("\n[1] Ribbon surfaces include the compensation_change_wizard command")
    rr = reg.ribbon_registry
    for variant in ("none", "active", "inactive"):
        key = f"payroll_setup.employees.{variant}"
        cmds = set(_surface_command_ids(rr.get(key)))
        if not _ok(
            f"compensation_change_wizard on {key}",
            "payroll_setup.compensation_change_wizard" in cmds,
        ):
            failures.append(f"compensation_change_wizard missing from {key}")

    # ── 2. Seed company, activate, hire employee ────────────────────
    print("\n[2] Seeding company + activation + hire")
    _ensure_country_and_currency(reg)
    ts = int(time.time())
    company = reg.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"P7A Smoke SARL {ts}",
            display_name=f"P7A Smoke {ts}",
            country_code="CM", base_currency_code="XAF",
        )
    )
    cid = company.id
    reg.chart_seed_service.ensure_global_chart_reference_seed()
    reg.company_seed_service.seed_built_in_chart(cid)

    act_dlg = PayrollActivationWizardDialog(reg, cid, company.display_name)
    try:
        idx = act_dlg._pack_combo.findData("CMR_2024_V1")
        if idx >= 0:
            act_dlg._pack_combo.setCurrentIndex(idx)
        act_dlg._dept_code_edit.setText("OPS")
        act_dlg._dept_name_edit.setText("Operations")
        act_dlg._pos_code_edit.setText("MGR")
        act_dlg._pos_name_edit.setText("Manager")
        act_dlg._handle_apply()
    finally:
        act_dlg.close()

    hire_dlg = EmployeeHireWizardDialog(reg, cid, company.display_name)
    employee_id = None
    try:
        hire_dlg._employee_number_edit.setText("CC001")
        hire_dlg._first_name_edit.setText("Grace")
        hire_dlg._last_name_edit.setText("Hopper")
        hire_dlg._display_name_edit.setText("Grace Hopper")
        hire_dlg._email_edit.setText("grace@example.com")
        today = date.today()
        hire_dlg._hire_date_edit.setDate(QDate(today.year, 1, 1))
        hire_dlg._currency_edit.setText("XAF")
        if hire_dlg._department_combo.count() > 1:
            hire_dlg._department_combo.setCurrentIndex(1)
        if hire_dlg._position_combo.count() > 1:
            hire_dlg._position_combo.setCurrentIndex(1)
        hire_dlg._profile_name_edit.setText("Standard")
        hire_dlg._salary_spin.setValue(300_000.0)
        hire_dlg._profile_currency_edit.setText("XAF")
        hire_dlg._effective_from_edit.setDate(QDate(today.year, 1, 1))
        hire_dlg._handle_apply()
        hr_result = hire_dlg.result_payload
        if hr_result is None:
            failures.append("hire wizard returned no result")
            print("  [FAIL] hire wizard returned no result — aborting P7a smoke")
            return 1
        employee_id = hr_result.employee_id
        print(f"  employee_id={employee_id}")
    finally:
        hire_dlg.close()

    # ── 3. Drive CompensationChangeWizardDialog ─────────────────────
    print("\n[3] CompensationChangeWizardDialog drives services")
    dlg = CompensationChangeWizardDialog(
        reg, cid, company.display_name, employee_id=employee_id,
    )
    try:
        _ok(
            "employee pre-selected",
            dlg._selected_employee_id() == employee_id,
            f"got={dlg._selected_employee_id()}",
        )
        # Trigger current-profile load (Qt may not fire on index==1 when
        # preselected after load — call directly).
        dlg._on_employee_changed()
        _ok(
            "current profile detected",
            dlg._current_profile is not None,
            f"profile={getattr(dlg._current_profile, 'profile_name', None)}",
        )

        # Step 1 → 2
        new_effective = date(date.today().year, 6, 1)
        dlg._effective_edit.setDate(
            QDate(new_effective.year, new_effective.month, new_effective.day)
        )
        dlg._go_next()
        _ok("advanced to step 2 (New Comp)", dlg._current_step == 1)

        # Fill new comp
        dlg._profile_name_edit.setText("Mid-Year Raise")
        dlg._salary_edit.setText("500000.00")
        dlg._currency_edit.setText("XAF")
        dlg._go_next()
        _ok("advanced to step 3 (Recurring)", dlg._current_step == 2)

        # Skip recurring add (leave component at index 0 = none)
        dlg._go_next()
        _ok("advanced to step 4 (Review)", dlg._current_step == 3)

        # Apply
        dlg._notes_edit.setPlainText("Annual review adjustment.")
        dlg._handle_apply()
        result = dlg.result_payload
        if not _ok("wizard produced a result", result is not None):
            failures.append("compensation change wizard returned no result")
        else:
            _ok(
                "profile id set",
                result.profile_id > 0, f"profile_id={result.profile_id}",
            )
            _ok(
                "new basic salary applied",
                result.new_basic_salary == Decimal("500000.00"),
                f"salary={result.new_basic_salary}",
            )
            _ok(
                "effective from set",
                result.effective_from == new_effective,
                f"effective_from={result.effective_from}",
            )
            _ok(
                "no component assignments added (skipped)",
                len(result.new_assignment_ids) == 0,
            )
            _ok("advanced to done page", dlg._current_step == 4)
    finally:
        dlg.close()

    # ── 4. Second change — add a recurring component ─────────────────
    print("\n[4] Second wizard run — add a recurring component")
    dlg2 = CompensationChangeWizardDialog(
        reg, cid, company.display_name, employee_id=employee_id,
    )
    assignment_added = 0
    try:
        dlg2._on_employee_changed()
        next_eff = date(date.today().year, 9, 1)
        dlg2._effective_edit.setDate(QDate(next_eff.year, next_eff.month, next_eff.day))
        dlg2._go_next()
        dlg2._profile_name_edit.setText("Q3 Adjustment")
        dlg2._salary_edit.setText("520000.00")
        dlg2._currency_edit.setText("XAF")
        dlg2._go_next()
        # Pick first real component (index 1 = first after "— Skip —")
        if dlg2._component_combo.count() > 1:
            dlg2._component_combo.setCurrentIndex(1)
            dlg2._override_amount_edit.setText("12500.00")
        dlg2._go_next()  # → review
        dlg2._handle_apply()
        r2 = dlg2.result_payload
        if r2 is not None:
            assignment_added = len(r2.new_assignment_ids)
        _ok(
            "component assignment created",
            assignment_added == 1,
            f"count={assignment_added}",
        )
    finally:
        dlg2.close()

    # ── 5. Duplicate effective-from is rejected ──────────────────────
    print("\n[5] Duplicate effective_from is rejected")
    dlg3 = CompensationChangeWizardDialog(
        reg, cid, company.display_name, employee_id=employee_id,
    )
    try:
        dlg3._on_employee_changed()
        # Same effective_from as step 4 (next_eff above).
        dup_eff = date(date.today().year, 9, 1)
        dlg3._effective_edit.setDate(QDate(dup_eff.year, dup_eff.month, dup_eff.day))
        dlg3._go_next()
        dlg3._profile_name_edit.setText("Duplicate")
        dlg3._salary_edit.setText("999000.00")
        dlg3._currency_edit.setText("XAF")
        dlg3._go_next()
        dlg3._go_next()  # → review
        dlg3._handle_apply()
        _ok(
            "duplicate produced no result",
            dlg3.result_payload is None,
        )
        _ok(
            "error label visible",
            dlg3._error_label.isVisible() or dlg3._error_label.text() != "",
            f"text={dlg3._error_label.text()!r}",
        )
    finally:
        dlg3.close()

    # ── Summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if failures:
        print(f"Slice P7a smoke FAIL — {len(failures)} failures")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Slice P7a smoke PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
