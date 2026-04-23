"""Slice P2 smoke — payroll child-window promotion.

Validates:

1. Ribbon registry exposes the two new child-window surfaces.
2. ``PayrollInputBatchWindow`` can be instantiated for a real draft batch,
   reports the expected ribbon state, and routes ``close`` to dismiss.
3. ``ChildWindowManager.open_document`` deduplicates by window key.
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime  # noqa: E402

from seeker_accounting.modules.accounting.reference_data.models.country import Country  # noqa: E402
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency  # noqa: E402
from seeker_accounting.modules.companies.dto.company_commands import (  # noqa: E402
    CreateCompanyCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (  # noqa: E402
    CreateDocumentSequenceCommand,
)
from seeker_accounting.modules.payroll.dto.employee_dto import (  # noqa: E402
    CreateEmployeeCommand,
)
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (  # noqa: E402
    CreatePayrollInputBatchCommand,
    CreatePayrollInputLineCommand,
)
from seeker_accounting.modules.payroll.dto.payroll_setup_commands import (  # noqa: E402
    CreateDepartmentCommand,
    UpsertCompanyPayrollSettingsCommand,
)
from seeker_accounting.modules.administration.rbac_catalog import (  # noqa: E402
    SYSTEM_PERMISSION_BY_CODE,
)
from seeker_accounting.modules.payroll.payroll_permissions import (  # noqa: E402
    ALL_PAYROLL_PERMISSIONS,
)
from seeker_accounting.modules.payroll.ui.payroll_input_batch_window import (  # noqa: E402
    PayrollInputBatchWindow,
)
from seeker_accounting.modules.payroll.ui.payroll_run_employee_window import (  # noqa: E402
    PayrollRunEmployeeWindow,
)


def _ensure_country_and_currency(reg) -> None:
    """Best-effort seed of CM/XAF reference rows used by the smoke."""
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


def main() -> int:
    failures: list[str] = []
    app = QApplication.instance() or QApplication([])

    bootstrap = bootstrap_script_runtime(
        app,
        permission_snapshot=tuple(SYSTEM_PERMISSION_BY_CODE.keys()),
    )
    reg = bootstrap.service_registry

    print("=" * 60)
    print("Slice P2 smoke — payroll child windows")
    print("=" * 60)

    # ── 1. Ribbon registry surfaces ──────────────────────────────────
    print("\n[1] Ribbon surfaces registered")
    rr = reg.ribbon_registry
    batch_key = rr.child_window_key("payroll_input_batch")
    run_emp_key = rr.child_window_key("payroll_run_employee")
    if not _ok("child:payroll_input_batch exists", rr.has(batch_key)):
        failures.append("missing payroll_input_batch surface")
    if not _ok("child:payroll_run_employee exists", rr.has(run_emp_key)):
        failures.append("missing payroll_run_employee surface")

    if rr.has(batch_key):
        surface = rr.get(batch_key)
        command_ids = [
            item.command_id for item in surface.items if hasattr(item, "command_id")
        ]
        required = {
            "payroll_input_batch.add_line",
            "payroll_input_batch.edit_line",
            "payroll_input_batch.delete_line",
            "payroll_input_batch.approve",
            "payroll_input_batch.void",
            "payroll_input_batch.refresh",
            "payroll_input_batch.close",
        }
        _ok(
            "batch surface has required commands",
            required.issubset(set(command_ids)),
            f"missing={required - set(command_ids)}",
        )

    # ── 2. Seed minimum company setup ────────────────────────────────
    print("\n[2] Seeding test company / batch")
    _ensure_country_and_currency(reg)

    import time
    ts = int(time.time())
    company = reg.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"P2 Smoke SARL {ts}",
            display_name=f"P2 Smoke {ts}",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    cid = company.id
    print(f"  company_id={cid}")

    reg.chart_seed_service.ensure_global_chart_reference_seed()
    reg.company_seed_service.seed_built_in_chart(cid)

    reg.numbering_setup_service.create_document_sequence(
        cid,
        CreateDocumentSequenceCommand(
            document_type_code="payroll_input_batch",
            prefix="PIB-",
            next_number=1,
            padding_width=4,
        ),
    )

    reg.payroll_setup_service.upsert_company_payroll_settings(
        cid,
        UpsertCompanyPayrollSettingsCommand(
            default_pay_frequency_code="monthly",
            default_payroll_currency_code="XAF",
            statutory_pack_version_code="CMR_2024_V1",
            cnps_regime_code="general",
            accident_risk_class_code="A",
        ),
    )
    reg.payroll_statutory_pack_service.apply_pack(cid, "CMR_2024_V1")
    components = reg.payroll_component_service.list_components(cid)
    earning = next(
        (c for c in components if (c.component_type_code or "").lower() == "earning"),
        None,
    )
    if earning is None:
        failures.append("no earning components after pack apply")
        print("  [FAIL] no earning component available")
        return 1

    dept = reg.payroll_setup_service.create_department(
        cid, CreateDepartmentCommand(code="OPS", name="Operations")
    )
    emp = reg.employee_service.create_employee(
        cid,
        CreateEmployeeCommand(
            employee_number="P2-EMP001",
            display_name="P2 Tester",
            first_name="P2",
            last_name="Tester",
            hire_date=date(2025, 1, 1),
            base_currency_code="XAF",
            department_id=dept.id,
        ),
    )

    batch = reg.payroll_input_service.create_batch(
        cid,
        CreatePayrollInputBatchCommand(
            period_year=2025, period_month=1, description="P2 smoke batch"
        ),
    )
    reg.payroll_input_service.add_line(
        cid,
        batch.id,
        CreatePayrollInputLineCommand(
            employee_id=emp.id,
            component_id=earning.id,
            input_amount=Decimal("10000"),
            notes="bonus",
        ),
    )
    print(f"  batch_id={batch.id} (draft, 1 line)")

    # ── 3. Instantiate child window directly ─────────────────────────
    print("\n[3] PayrollInputBatchWindow direct instantiation")
    window = PayrollInputBatchWindow(reg, company_id=cid, batch_id=batch.id)
    try:
        _ok(
            "surface_key resolves to child:payroll_input_batch",
            window._surface_key == batch_key,
            window._surface_key,
        )
        _ok(
            "window_key tuple carries batch id",
            window.window_key == ("payroll_input_batch", batch.id),
            str(window.window_key),
        )
        state = window.ribbon_state()
        _ok(
            "draft batch → add_line enabled",
            state.get("payroll_input_batch.add_line") is True,
        )
        _ok(
            "no selection → edit/delete disabled",
            state.get("payroll_input_batch.edit_line") is False
            and state.get("payroll_input_batch.delete_line") is False,
        )
        _ok(
            "refresh/close always enabled",
            state.get("payroll_input_batch.refresh") is True
            and state.get("payroll_input_batch.close") is True,
        )
    finally:
        window.close()

    # ── 4. ChildWindowManager open_document dedup ────────────────────
    print("\n[4] ChildWindowManager.open_document dedup")
    manager = reg.child_window_manager

    def _factory():
        return PayrollInputBatchWindow(reg, company_id=cid, batch_id=batch.id)

    w1 = manager.open_document("payroll_input_batch", batch.id, _factory)
    w2 = manager.open_document("payroll_input_batch", batch.id, _factory)
    _ok("same window returned for same key", w1 is w2)
    if not (w1 is w2):
        failures.append("ChildWindowManager did not dedup")
    w1.close()

    # ── 5. PayrollRunEmployeeWindow import + surface check ───────────
    print("\n[5] PayrollRunEmployeeWindow module importable")
    _ok("PayrollRunEmployeeWindow.DOC_TYPE", PayrollRunEmployeeWindow.DOC_TYPE == "payroll_run_employee")

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if failures:
        print(f"Slice P2 smoke FAIL — {len(failures)} failures")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Slice P2 smoke PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
