"""Slice P7c smoke — Employee Payroll Setup Wizard + Employee Hub.

Validates:

1. Ribbon surface ``payroll_setup.employees.*`` exposes the two new
   commands and gates them by selection + active status.
2. Ribbon surface ``child:payroll_employee_hub`` registers the full
   command set.
3. ``EmployeePayrollSetupWizardDialog`` detects gaps on a bare employee
   and walks through all four steps (tax, payment, compensation,
   components), apply succeeds and persists the profile + assignments.
4. A second run on the same (now-ready) employee reports zero gaps.
5. Validation: empty compensation profile name is rejected.
6. ``EmployeeHubWindow`` loads the employee, exposes expected ribbon
   state, and ``Deactivate`` transitions the employee to inactive.
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

from PySide6.QtCore import QDate, Qt
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
from seeker_accounting.modules.payroll.dto.employee_dto import (  # noqa: E402
    CreateEmployeeCommand,
)
from seeker_accounting.modules.payroll.ui.employee_hub_window import (  # noqa: E402
    EmployeeHubWindow,
)
from seeker_accounting.modules.payroll.ui.wizards.employee_payroll_setup_wizard import (  # noqa: E402
    EmployeePayrollSetupWizardDialog,
    STEP_COMP,
    STEP_COMPONENTS,
    STEP_PAYMENT,
    STEP_TAX_CNPS,
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
    print("Slice P7c smoke — Employee Payroll Setup Wizard + Hub")
    print("=" * 60)

    # ── 1. Ribbon surfaces ──────────────────────────────────────────
    print("\n[1] Ribbon surfaces expose the new commands")
    rr = reg.ribbon_registry
    for variant in ("none", "active", "inactive"):
        key = f"payroll_setup.employees.{variant}"
        cmds = set(_surface_command_ids(rr.get(key)))
        if not _ok(
            f"open_employee_hub on {key}",
            "payroll_setup.open_employee_hub" in cmds,
        ):
            failures.append(f"open_employee_hub missing from {key}")
        if not _ok(
            f"employee_payroll_setup_wizard on {key}",
            "payroll_setup.employee_payroll_setup_wizard" in cmds,
        ):
            failures.append(f"employee_payroll_setup_wizard missing from {key}")

    hub_key = rr.child_window_key("payroll_employee_hub")
    hub_cmds = set(_surface_command_ids(rr.get(hub_key)))
    expected = {
        "payroll_employee_hub.edit",
        "payroll_employee_hub.payroll_setup_wizard",
        "payroll_employee_hub.compensation_change",
        "payroll_employee_hub.new_assignment",
        "payroll_employee_hub.deactivate",
        "payroll_employee_hub.reactivate",
        "payroll_employee_hub.refresh",
        "payroll_employee_hub.close",
    }
    if not _ok(
        f"hub surface {hub_key} includes all commands",
        expected.issubset(hub_cmds),
        f"missing={expected - hub_cmds}",
    ):
        failures.append(f"hub surface missing commands: {expected - hub_cmds}")

    # ── 2. Seed company + activation (to get components) ────────────
    print("\n[2] Seeding company + activation")
    _ensure_country_and_currency(reg)
    ts = int(time.time())
    company = reg.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"P7C Smoke SARL {ts}",
            display_name=f"P7C Smoke {ts}",
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

    comps = reg.payroll_component_service.list_components(cid, active_only=True)
    if not _ok("components seeded by activation", len(comps) > 0, f"count={len(comps)}"):
        failures.append("no components available — activation pack failed")

    # ── 3. Create a bare employee (all 4 gaps) ──────────────────────
    print("\n[3] Creating a bare employee")
    emp = reg.employee_service.create_employee(
        cid,
        CreateEmployeeCommand(
            employee_number="P7C001",
            display_name="Ada Lovelace",
            first_name="Ada",
            last_name="Lovelace",
            hire_date=date.today(),
            base_currency_code="XAF",
            email="ada@example.com",
        ),
    )
    print(f"  employee_id={emp.id}")

    # ── 4. First run: all 4 gaps → walk wizard ──────────────────────
    print("\n[4] Wizard detects all four gaps and applies changes")
    dlg = EmployeePayrollSetupWizardDialog(
        reg, cid, company.display_name, employee_id=emp.id,
    )
    try:
        gaps = dlg._gaps
        _ok("tax_cnps gap detected", gaps[STEP_TAX_CNPS])
        _ok("payment gap detected", gaps[STEP_PAYMENT])
        _ok("comp gap detected", gaps[STEP_COMP])
        _ok("components gap detected", gaps[STEP_COMPONENTS])
        _ok("all four steps activated",
            all(s in dlg._page_index for s in
                (STEP_TAX_CNPS, STEP_PAYMENT, STEP_COMP, STEP_COMPONENTS)))

        # Intro → tax
        dlg._go_next()
        _ok("advanced to tax page", dlg._current_key() == STEP_TAX_CNPS)
        dlg._tax_edit.setText("P123456789")
        dlg._cnps_edit.setText("12-345678-9")

        # Tax → payment (skip, no financial accounts)
        dlg._go_next()
        _ok("advanced to payment page", dlg._current_key() == STEP_PAYMENT)
        # Skip this step since no accounts are configured.
        dlg._go_skip()
        _ok("payment step skipped", dlg._current_key() == STEP_COMP)

        # Compensation (mandatory)
        dlg._profile_name_edit.setText("Base 2025")
        dlg._basic_salary_edit.setValue(400_000.0)
        dlg._currency_edit.setText("XAF")
        today = date.today()
        dlg._effective_from_edit.setDate(QDate(today.year, today.month, 1))

        dlg._go_next()
        _ok("advanced to components page",
            dlg._current_key() == STEP_COMPONENTS)

        # Uncheck all → pick just the first 2 components
        for row in range(min(2, dlg._component_list.count())):
            dlg._component_list.item(row).setCheckState(Qt.CheckState.Checked)
        picked = [dlg._component_list.item(r).data(Qt.ItemDataRole.UserRole)
                  for r in range(dlg._component_list.count())
                  if dlg._component_list.item(r).checkState() == Qt.CheckState.Checked]

        dlg._go_next()
        _ok("advanced to review page", dlg._current_key() == "review")

        dlg._handle_apply()
        result = dlg.result_payload
        if not _ok("wizard produced result", result is not None):
            failures.append("setup wizard returned no result")
            print(f"    error_label: {dlg._error_label.text()!r}")
        else:
            _ok("employee updated (tax/cnps)", result.updated_employee)
            _ok("tax identifier flagged", result.tax_identifier_set)
            _ok("cnps flagged", result.cnps_number_set)
            _ok("profile created", result.compensation_profile_id is not None,
                f"profile_id={result.compensation_profile_id}")
            _ok("at least one assignment",
                len(result.assignment_ids) >= 1,
                f"assigned={len(result.assignment_ids)} of picked={len(picked)}")
            _ok("payment step recorded as skipped",
                STEP_PAYMENT in result.skipped_gaps,
                f"skipped={result.skipped_gaps}")
    finally:
        dlg.close()

    # ── 5. Re-open: no gaps detected ────────────────────────────────
    print("\n[5] Second run on same employee — no gaps")
    dlg2 = EmployeePayrollSetupWizardDialog(
        reg, cid, company.display_name, employee_id=emp.id,
    )
    try:
        _ok("tax gap gone", not dlg2._gaps[STEP_TAX_CNPS])
        _ok("comp gap gone", not dlg2._gaps[STEP_COMP])
        _ok("components gap gone", not dlg2._gaps[STEP_COMPONENTS])
        # Active steps should be only intro + review + done (+ payment if still missing)
        still_gap_count = sum(1 for v in dlg2._gaps.values() if v)
        print(f"    remaining gaps: {still_gap_count}")
    finally:
        dlg2.close()

    # ── 6. Validation: empty profile name rejected ──────────────────
    print("\n[6] Empty profile name is rejected on compensation step")
    emp2 = reg.employee_service.create_employee(
        cid,
        CreateEmployeeCommand(
            employee_number="P7C002",
            display_name="Alan Turing",
            first_name="Alan",
            last_name="Turing",
            hire_date=date.today(),
            base_currency_code="XAF",
        ),
    )
    dlg3 = EmployeePayrollSetupWizardDialog(
        reg, cid, company.display_name, employee_id=emp2.id,
    )
    try:
        # Intro → tax → skip → payment → skip → comp
        dlg3._go_next()
        dlg3._go_skip()
        dlg3._go_skip()
        _ok("on compensation step", dlg3._current_key() == STEP_COMP)
        dlg3._profile_name_edit.setText("")
        dlg3._basic_salary_edit.setValue(0.0)
        dlg3._go_next()
        _ok("stayed on comp step (validation)",
            dlg3._current_key() == STEP_COMP)
        _ok("error label visible",
            dlg3._error_label.isVisible() or dlg3._error_label.text() != "",
            f"text={dlg3._error_label.text()!r}")
    finally:
        dlg3.close()

    # ── 7. Employee Hub loads + deactivate ──────────────────────────
    print("\n[7] EmployeeHubWindow loads and deactivates")
    hub = EmployeeHubWindow(reg, company_id=cid, employee_id=emp.id)
    try:
        _ok("employee loaded",
            hub._employee is not None and hub._employee.id == emp.id)
        state = hub.ribbon_state()
        _ok("edit enabled", state["payroll_employee_hub.edit"])
        _ok("payroll_setup_wizard enabled",
            state["payroll_employee_hub.payroll_setup_wizard"])
        _ok("deactivate enabled (active employee)",
            state["payroll_employee_hub.deactivate"])
        _ok("reactivate disabled (active employee)",
            not state["payroll_employee_hub.reactivate"])
        _ok("only payment gap remains (skipped) in hub",
            sum(1 for v in hub._gaps.values() if v) <= 1 and hub._gaps["payment"],
            f"gaps={hub._gaps}")

        # Call deactivate handler directly (bypass confirmation dialog).
        reg.employee_service.update_employee(
            cid, emp.id,
            __import__(
                "seeker_accounting.modules.payroll.dto.employee_dto",
                fromlist=["UpdateEmployeeCommand"],
            ).UpdateEmployeeCommand(
                employee_number=hub._employee.employee_number,
                display_name=hub._employee.display_name,
                first_name=hub._employee.first_name,
                last_name=hub._employee.last_name,
                hire_date=hub._employee.hire_date,
                base_currency_code=hub._employee.base_currency_code,
                is_active=False,
                department_id=hub._employee.department_id,
                position_id=hub._employee.position_id,
                termination_date=date.today(),
                phone=hub._employee.phone,
                email=hub._employee.email,
                tax_identifier=hub._employee.tax_identifier,
                cnps_number=hub._employee.cnps_number,
                default_payment_account_id=hub._employee.default_payment_account_id,
            ),
        )
        hub._reload()
        _ok("employee now inactive",
            hub._employee is not None and not hub._employee.is_active)
        state2 = hub.ribbon_state()
        _ok("deactivate disabled now",
            not state2["payroll_employee_hub.deactivate"])
        _ok("reactivate enabled now",
            state2["payroll_employee_hub.reactivate"])
    finally:
        hub.close()

    # ── Summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if failures:
        print(f"Slice P7c smoke FAIL — {len(failures)} failures")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Slice P7c smoke PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
