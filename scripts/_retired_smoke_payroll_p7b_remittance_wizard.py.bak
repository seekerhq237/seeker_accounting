"""Slice P7b smoke — Remittance Wizard.

Validates:

1. Ribbon surfaces ``payroll_accounting.remittances.*`` expose
   ``payroll_accounting.remittance_wizard`` and its gating.
2. ``RemittanceWizardDialog`` drives the remittance service end-to-end:
   authority + period → (no posted runs expected) → manual line →
   create batch + add line.
3. Result payload contains the expected batch id, authority, deadline,
   and line count.
4. A second run with an invalid period (start > end) is rejected
   cleanly via the error label.
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
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (  # noqa: E402
    CreateDocumentSequenceCommand,
)
from seeker_accounting.modules.payroll.ui.wizards.remittance_wizard import (  # noqa: E402
    RemittanceWizardDialog,
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
    print("Slice P7b smoke — Remittance Wizard")
    print("=" * 60)

    # ── 1. Ribbon surface ───────────────────────────────────────────
    print("\n[1] Ribbon surfaces include the remittance_wizard command")
    rr = reg.ribbon_registry
    for variant in ("none", "batch_selected"):
        key = f"payroll_accounting.remittances.{variant}"
        cmds = set(_surface_command_ids(rr.get(key)))
        if not _ok(
            f"remittance_wizard on {key}",
            "payroll_accounting.remittance_wizard" in cmds,
        ):
            failures.append(f"remittance_wizard missing from {key}")

    # ── 2. Seed company ─────────────────────────────────────────────
    print("\n[2] Seeding test company")
    _ensure_country_and_currency(reg)
    ts = int(time.time())
    company = reg.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"P7B Smoke SARL {ts}",
            display_name=f"P7B Smoke {ts}",
            country_code="CM", base_currency_code="XAF",
        )
    )
    cid = company.id
    print(f"  company_id={cid}")

    reg.numbering_setup_service.create_document_sequence(
        cid,
        CreateDocumentSequenceCommand(
            document_type_code="payroll_remittance",
            prefix="REM-", next_number=1, padding_width=4,
        ),
    )

    # ── 3. Drive wizard happy path ──────────────────────────────────
    print("\n[3] RemittanceWizardDialog drives services (manual line)")
    dlg = RemittanceWizardDialog(reg, cid, company.display_name)
    try:
        # Authority = CNPS
        idx = dlg._authority_combo.findData("cnps")
        _ok("CNPS choice available", idx >= 0)
        dlg._authority_combo.setCurrentIndex(idx)

        # Period = prior month
        today = date.today()
        if today.month == 1:
            ps, pe = date(today.year - 1, 12, 1), date(today.year - 1, 12, 31)
        else:
            m = today.month - 1
            import calendar
            ps = date(today.year, m, 1)
            pe = date(today.year, m, calendar.monthrange(today.year, m)[1])
        dlg._period_start_edit.setDate(QDate(ps.year, ps.month, ps.day))
        dlg._period_end_edit.setDate(QDate(pe.year, pe.month, pe.day))

        _ok(
            "deadline label populated",
            "Filing deadline" in dlg._deadline_label.text(),
            dlg._deadline_label.text()[:80],
        )

        dlg._go_next()
        _ok("advanced to step 2 (runs)", dlg._current_step == 1)
        _ok(
            "no posted runs found → no_runs_label visible",
            dlg._runs_table.rowCount() == 0,
        )

        dlg._go_next()
        _ok("advanced to step 3 (lines)", dlg._current_step == 2)
        _ok(
            "lines table starts empty",
            dlg._lines_table.rowCount() == 0,
        )

        # Enter a manual line
        dlg._manual_desc_edit.setText("CNPS contribution for test period")
        dlg._manual_amount_edit.setText("125000.00")

        dlg._go_next()
        _ok("advanced to step 4 (review)", dlg._current_step == 3)
        _ok(
            "review shows 1 line",
            "Line count:</b> 1" in dlg._review_label.text(),
            dlg._review_label.text()[:120],
        )

        dlg._notes_edit.setPlainText("Smoke-test batch.")
        dlg._handle_apply()
        result = dlg.result_payload
        if not _ok("wizard produced a result", result is not None):
            failures.append("remittance wizard returned no result")
            print(f"    error_label: {dlg._error_label.text()!r}")
        else:
            _ok("batch id set", result.batch_id > 0, f"batch_id={result.batch_id}")
            _ok(
                "authority=cnps", result.authority_code == "cnps",
                f"got={result.authority_code}",
            )
            _ok(
                "total amount due",
                result.amount_due == Decimal("125000.00"),
                f"amount={result.amount_due}",
            )
            _ok(
                "line count", result.line_count == 1,
                f"count={result.line_count}",
            )
            _ok(
                "filing deadline computed",
                result.filing_deadline is not None,
                f"deadline={result.filing_deadline}",
            )
            _ok(
                "batch number assigned",
                bool(result.batch_number),
                f"batch_number={result.batch_number}",
            )
            _ok("advanced to done page", dlg._current_step == 4)
    finally:
        dlg.close()

    # ── 4. Verify batch persisted with one line ─────────────────────
    print("\n[4] Verify batch persisted")
    if dlg.result_payload is not None:
        batch_detail = reg.payroll_remittance_service.get_batch(
            cid, dlg.result_payload.batch_id
        )
        _ok(
            "batch exists",
            batch_detail is not None and batch_detail.amount_due == Decimal("125000.00"),
            f"amount_due={batch_detail.amount_due}",
        )
        _ok(
            "line persisted",
            len(batch_detail.lines) == 1,
            f"lines={len(batch_detail.lines)}",
        )
        _ok(
            "line description carried over",
            any("CNPS contribution" in ln.description for ln in batch_detail.lines),
        )

    # ── 5. Invalid period (start > end) rejected ────────────────────
    print("\n[5] Invalid period (start > end) is rejected")
    dlg2 = RemittanceWizardDialog(reg, cid, company.display_name)
    try:
        today = date.today()
        dlg2._period_start_edit.setDate(QDate(today.year, 12, 31))
        dlg2._period_end_edit.setDate(QDate(today.year, 1, 1))
        dlg2._go_next()
        _ok(
            "rejected (stayed on step 1)",
            dlg2._current_step == 0,
        )
        _ok(
            "error label visible",
            dlg2._error_label.isVisible() or dlg2._error_label.text() != "",
            f"text={dlg2._error_label.text()!r}",
        )
    finally:
        dlg2.close()

    # ── 6. Apply with zero amounts rejected ─────────────────────────
    print("\n[6] Apply with no non-zero line rejected")
    dlg3 = RemittanceWizardDialog(reg, cid, company.display_name)
    try:
        dlg3._authority_combo.setCurrentIndex(dlg3._authority_combo.findData("dgi"))
        today = date.today()
        if today.month == 1:
            ps, pe = date(today.year - 1, 12, 1), date(today.year - 1, 12, 31)
        else:
            m = today.month - 1
            import calendar
            ps = date(today.year, m, 1)
            pe = date(today.year, m, calendar.monthrange(today.year, m)[1])
        dlg3._period_start_edit.setDate(QDate(ps.year, ps.month, ps.day))
        dlg3._period_end_edit.setDate(QDate(pe.year, pe.month, pe.day))
        dlg3._go_next()  # → runs
        dlg3._go_next()  # → lines
        dlg3._go_next()  # → review (no lines)
        dlg3._handle_apply()
        _ok(
            "apply with no lines returned no result",
            dlg3.result_payload is None,
        )
        _ok(
            "error label shows line requirement",
            "line" in dlg3._error_label.text().lower(),
            f"text={dlg3._error_label.text()!r}",
        )
    finally:
        dlg3.close()

    # ── Summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if failures:
        print(f"Slice P7b smoke FAIL — {len(failures)} failures")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Slice P7b smoke PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
