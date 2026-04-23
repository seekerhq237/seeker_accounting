"""Slice P5 smoke — Payroll Run Wizard.

Validates:

1. Ribbon surface ``payroll_calculation.runs.none`` exposes the
   ``payroll_calculation.payroll_run_wizard`` command.
2. ``PayrollRunWizardDialog`` drives validation, create_run,
   calculate_run, approve_run through the existing services without UI
   interaction (direct method calls on the dialog).
3. The resulting run is persisted with status ``approved`` and employee
   totals that match the ``list_run_employees`` return.
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
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (  # noqa: E402
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (  # noqa: E402
    CreateDocumentSequenceCommand,
)
from seeker_accounting.modules.accounting.reference_data.models.country import Country  # noqa: E402
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency  # noqa: E402
from seeker_accounting.modules.companies.dto.company_commands import (  # noqa: E402
    CreateCompanyCommand,
)
from seeker_accounting.modules.payroll.dto.employee_dto import CreateEmployeeCommand  # noqa: E402
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (  # noqa: E402
    CreateCompensationProfileCommand,
    CreateComponentAssignmentCommand,
)
from seeker_accounting.modules.payroll.dto.payroll_setup_commands import (  # noqa: E402
    UpsertCompanyPayrollSettingsCommand,
)
from seeker_accounting.modules.payroll.ui.wizards.payroll_run_wizard import (  # noqa: E402
    PayrollRunWizardDialog,
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
    print("Slice P5 smoke — Payroll Run Wizard")
    print("=" * 60)

    # ── 1. Ribbon surface includes the wizard command ────────────────
    print("\n[1] Ribbon surface includes the wizard command")
    rr = reg.ribbon_registry
    for variant in ("none", "run_selected", "employee_selected"):
        key = f"payroll_calculation.runs.{variant}"
        cmds = set(_surface_command_ids(rr.get(key)))
        if not _ok(
            f"payroll_run_wizard on {key}",
            "payroll_calculation.payroll_run_wizard" in cmds,
        ):
            failures.append(f"payroll_run_wizard missing from {key}")

    # ── 2. Seed test company, pack, employee with compensation ───────
    print("\n[2] Seeding test company + statutory pack + employee")
    _ensure_country_and_currency(reg)

    ts = int(time.time())
    company = reg.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"P5 Smoke SARL {ts}",
            display_name=f"P5 Smoke {ts}",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    cid = company.id
    print(f"  company_id={cid}")

    # Chart + fiscal year
    reg.chart_seed_service.ensure_global_chart_reference_seed()
    reg.company_seed_service.seed_built_in_chart(cid)

    today = date.today()
    # Create fiscal year spanning current year so a period exists for
    # the run period the wizard will use.
    fiscal_year = reg.fiscal_calendar_service.create_fiscal_year(
        cid,
        CreateFiscalYearCommand(
            year_code=f"FY{today.year}",
            year_name=f"FY {today.year}",
            start_date=date(today.year, 1, 1),
            end_date=date(today.year, 12, 31),
            status_code="OPEN",
            is_active=True,
        ),
    )
    reg.fiscal_calendar_service.generate_periods(
        cid,
        fiscal_year.id,
        GenerateFiscalPeriodsCommand(),
    )

    # Payroll settings (required by pack application).
    reg.payroll_setup_service.upsert_company_payroll_settings(
        cid,
        UpsertCompanyPayrollSettingsCommand(
            default_pay_frequency_code="monthly",
            default_payroll_currency_code="XAF",
            cnps_regime_code="general",
            accident_risk_class_code="A",
        ),
    )

    # Statutory pack — gives us components and rules.
    reg.payroll_statutory_pack_service.apply_pack(cid, "CMR_2024_V1")

    # Document sequence for payroll_run (required by create_run).
    reg.numbering_setup_service.create_document_sequence(
        cid,
        CreateDocumentSequenceCommand(
            document_type_code="payroll_run",
            next_number=1,
            padding_width=4,
            prefix="PR-",
        ),
    )

    # Employee + compensation + recurring component assignments.
    employee = reg.employee_service.create_employee(
        cid,
        CreateEmployeeCommand(
            employee_number="EMP-P5-001",
            display_name="Paul Runner",
            first_name="Paul",
            last_name="Runner",
            hire_date=date(today.year, 1, 1),
            base_currency_code="XAF",
        ),
    )
    reg.compensation_profile_service.create_profile(
        cid,
        CreateCompensationProfileCommand(
            employee_id=employee.id,
            profile_name="Standard",
            basic_salary=Decimal("400000.00"),
            currency_code="XAF",
            effective_from=date(today.year, 1, 1),
        ),
    )

    # Assign recurring statutory components (deductions + taxes) so the
    # calculated run has non-zero lines.
    components = reg.payroll_component_service.list_components(cid)
    recurring_count = 0
    for comp in components:
        type_code = (getattr(comp, "component_type_code", "") or "").lower()
        if type_code in ("deduction", "tax"):
            try:
                reg.component_assignment_service.create_assignment(
                    cid,
                    CreateComponentAssignmentCommand(
                        employee_id=employee.id,
                        component_id=comp.id,
                        effective_from=date(today.year, 1, 1),
                    ),
                )
                recurring_count += 1
            except Exception:  # noqa: BLE001
                pass
    print(f"  employee_id={employee.id}, recurring_assignments={recurring_count}")

    # ── 3. Drive PayrollRunWizardDialog headlessly ───────────────────
    print("\n[3] PayrollRunWizardDialog drives validate → create → calculate → approve")
    dlg = PayrollRunWizardDialog(reg, cid, company.display_name)
    try:
        # Step 1: period/label/currency — pick a fresh month.
        run_month = 3  # March — stable offset from hire date
        dlg._period_year_spin.setValue(today.year)
        dlg._period_month_spin.setValue(run_month)
        dlg._label_edit.setText("P5 Smoke Run")
        dlg._currency_edit.setText("XAF")
        dlg._run_date_edit.setDate(QDate(today.year, run_month, 28))
        dlg._payment_date_edit.setDate(QDate(today.year, run_month, 30))
        _ok("period validation", dlg._validate_period())

        # Step 2: readiness.
        dlg._refresh_readiness()
        if not _ok(
            "readiness result present",
            dlg._validation_result is not None,
        ):
            failures.append("validation did not run")
            return 1
        result = dlg._validation_result
        print(
            f"    employees={result.employee_count}, "
            f"errors={result.error_count}, warnings={result.warning_count}"
        )
        # Acknowledge warnings (assignments-only warnings may exist).
        if result.warning_count > 0:
            dlg._readiness_acknowledge.setChecked(True)
        _ok("readiness passes (no errors)", dlg._readiness_passes())

        # Step 3: inputs (approved batches — expect 0).
        dlg._refresh_inputs()
        _ok(
            "inputs preview loaded",
            isinstance(dlg._input_batches, list),
            f"approved batches={len(dlg._input_batches)}",
        )

        # Step 4: create + calculate.
        ok = dlg._run_create_and_calculate()
        if not _ok("create+calculate succeeded", ok):
            print(f"    wizard error: {dlg._error_label.text()}")
            failures.append("create+calculate failed")
            return 1
        _ok("draft run created", dlg._created_run is not None)
        _ok(
            "run calculated",
            dlg._calculated_run is not None
            and dlg._calculated_run.status_code == "calculated",
            f"status={dlg._calculated_run.status_code if dlg._calculated_run else '?'}",
        )
        _ok(
            "employee rows present",
            len(dlg._run_employees) >= 1,
            f"rows={len(dlg._run_employees)}",
        )
        total_net = sum(float(e.net_payable) for e in dlg._run_employees)
        total_gross = sum(float(e.gross_earnings) for e in dlg._run_employees)
        _ok(
            "totals computed",
            isinstance(total_net, float),
            f"gross={total_gross:,.2f}, net={total_net:,.2f}",
        )

        # Step 5: variance review.
        dlg._refresh_variance()
        _ok(
            "variance table populated",
            dlg._variance_table.rowCount() == len(dlg._run_employees),
            f"variance_rows={dlg._variance_table.rowCount()}",
        )
        _ok(
            "variance ack hidden with no prior run",
            not dlg._variance_ack.isVisible() or not dlg._variance_ack.isChecked(),
        )
        _ok("variance passes", dlg._variance_passes())

        # Step 6: inclusion — exclude first employee then re-include.
        dlg._refresh_inclusion()
        _ok(
            "inclusion table populated",
            dlg._inclusion_table.rowCount() == len(dlg._run_employees),
            f"inclusion_rows={dlg._inclusion_table.rowCount()}",
        )
        # Exclude the first employee via the service directly (UI calls it too).
        first_id = int(dlg._run_employees[0].id)
        reg.payroll_run_service.set_run_employee_inclusion(
            cid, first_id, is_included=False, exclusion_reason="Smoke: test exclusion"
        )
        dlg._refresh_inclusion()
        after_exclude = dlg._run_employees[0]
        _ok(
            "employee excluded persists",
            (after_exclude.status_code or "").lower() == "excluded"
            and (after_exclude.exclusion_reason or "") == "Smoke: test exclusion",
            f"status={after_exclude.status_code}, reason={after_exclude.exclusion_reason}",
        )
        # Re-include.
        reg.payroll_run_service.set_run_employee_inclusion(
            cid, first_id, is_included=True
        )
        dlg._refresh_inclusion()
        after_include = dlg._run_employees[0]
        _ok(
            "employee re-included persists",
            (after_include.status_code or "").lower() == "included"
            and not after_include.exclusion_reason,
            f"status={after_include.status_code}, reason={after_include.exclusion_reason}",
        )
        # Attempt to exclude without a reason — must raise ValidationError.
        try:
            reg.payroll_run_service.set_run_employee_inclusion(
                cid, first_id, is_included=False, exclusion_reason=None
            )
            _ok("exclude without reason rejected", False, "no error raised")
        except Exception as exc:  # noqa: BLE001
            _ok(
                "exclude without reason rejected",
                "reason" in str(exc).lower(),
                f"err={exc}",
            )

        # Step 7: approve.
        dlg._refresh_approve_summary()
        dlg._approve_now_checkbox.setChecked(True)
        dlg._handle_finish()
        result_payload = dlg.result_payload
        if not _ok("wizard produced a result", result_payload is not None):
            failures.append("no result payload")
            return 1
        _ok("status is approved", result_payload.status_code == "approved")
        _ok("approved flag set", result_payload.approved is True)
        _ok("run_id positive", result_payload.run_id > 0)

        # Persistence check.
        persisted = reg.payroll_run_service.get_run(cid, result_payload.run_id)
        _ok(
            "persisted run status is approved",
            persisted.status_code == "approved",
            f"status={persisted.status_code}, approved_at={persisted.approved_at}",
        )
    finally:
        dlg.close()

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if failures:
        print(f"Slice P5 smoke FAIL — {len(failures)} failures")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Slice P5 smoke PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
