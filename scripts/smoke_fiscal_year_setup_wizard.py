"""Focused offscreen smoke for FiscalYearSetupWizardDialog.

Boots the script runtime, seeds a company, walks the wizard through happy-path,
back navigation, conflict, and validation-error paths.
"""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from PySide6.QtCore import QDate  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from shared.bootstrap import bootstrap_script_runtime  # noqa: E402
from seeker_accounting.modules.accounting.fiscal_periods.ui.fiscal_year_setup_wizard_dialog import (  # noqa: E402
    FiscalYearSetupWizardDialog,
)
from seeker_accounting.modules.accounting.reference_data.models.country import Country  # noqa: E402
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency  # noqa: E402
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand  # noqa: E402


def _seed_reference_data(registry) -> None:
    with registry.session_context.unit_of_work_factory() as uow:
        session = uow.session
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        if session.get(Country, "CM") is None:
            session.add(Country(code="CM", name="Cameroon", is_active=True))
        if session.get(Currency, "XAF") is None:
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


def main() -> int:
    app = QApplication.instance() or QApplication([])
    bootstrap = bootstrap_script_runtime(
        app,
        permission_snapshot=(
            "companies.create",
            "companies.view",
            "fiscal.years.view",
            "fiscal.years.create",
            "fiscal.periods.view",
            "fiscal.periods.generate",
        ),
    )
    registry = bootstrap.service_registry

    _seed_reference_data(registry)

    unique_suffix = str(int(time.time() * 1000))
    company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"Fiscal Year Wizard Smoke Co. {unique_suffix}",
            display_name=f"Fiscal Year Wizard Smoke Co. {unique_suffix}",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    company_id = company.id
    company_name = company.display_name
    print("company_created", company_id)

    # ── Happy path ───────────────────────────────────────────────
    dialog = FiscalYearSetupWizardDialog(registry, company_id, company_name)
    assert dialog._stack.currentIndex() == 0, "should start on step 1"
    assert dialog._year_code_edit.text().startswith("FY"), dialog._year_code_edit.text()

    dialog._year_code_edit.setText("FY2026")
    dialog._year_name_edit.setText("Fiscal Year 2026")
    dialog._start_date_edit.setDate(QDate(2026, 1, 1))
    dialog._end_date_edit.setDate(QDate(2026, 12, 31))

    dialog._go_next()
    assert dialog._stack.currentIndex() == 1, "expected to advance to review step"
    assert dialog._preview_table.rowCount() == 12, "should preview 12 monthly periods"
    print(f"review_step_periods {dialog._preview_table.rowCount()}")

    dialog._handle_apply()
    assert dialog._result is not None, (
        f"wizard failed on apply: {dialog._error_label.text()!r}"
    )
    assert dialog._stack.currentIndex() == 2, "expected done step"
    assert dialog._result.period_count == 12
    assert dialog._result.fiscal_year.year_code == "FY2026"
    print(f"wizard_success {dialog._result.summary!r}")
    dialog.close()

    # ── Back navigation ─────────────────────────────────────────
    dialog_nav = FiscalYearSetupWizardDialog(registry, company_id, company_name)
    dialog_nav._year_code_edit.setText("FY2027")
    dialog_nav._year_name_edit.setText("Fiscal Year 2027")
    dialog_nav._start_date_edit.setDate(QDate(2027, 1, 1))
    dialog_nav._end_date_edit.setDate(QDate(2027, 12, 31))
    dialog_nav._go_next()
    assert dialog_nav._stack.currentIndex() == 1
    dialog_nav._go_back()
    assert dialog_nav._stack.currentIndex() == 0
    print("back_navigation_ok")
    dialog_nav.close()

    # ── Conflict path (duplicate code + overlapping range) ───────
    dialog_dup = FiscalYearSetupWizardDialog(registry, company_id, company_name)
    dialog_dup._year_code_edit.setText("FY2026")
    dialog_dup._year_name_edit.setText("Duplicate")
    dialog_dup._start_date_edit.setDate(QDate(2026, 1, 1))
    dialog_dup._end_date_edit.setDate(QDate(2026, 12, 31))
    dialog_dup._go_next()
    dialog_dup._handle_apply()
    assert dialog_dup._result is None, "duplicate run should not produce a result"
    assert dialog_dup._error_label.text(), "conflict should surface inline error text"
    assert dialog_dup._stack.currentIndex() == 1, "should remain on review step"
    print(f"conflict_inline_error {dialog_dup._error_label.text()!r}")
    dialog_dup.close()

    # ── Validation error (end before start) ──────────────────────
    dialog_bad = FiscalYearSetupWizardDialog(registry, company_id, company_name)
    dialog_bad._start_date_edit.setDate(QDate(2028, 12, 31))
    dialog_bad._end_date_edit.setDate(QDate(2028, 1, 1))
    dialog_bad._go_next()
    assert dialog_bad._stack.currentIndex() == 0, "invalid inputs must keep us on step 1"
    assert dialog_bad._error_label.text(), "validation error should be surfaced"
    print(f"validation_inline_error {dialog_bad._error_label.text()!r}")
    dialog_bad.close()

    print("fiscal_year_setup_wizard_smoke PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
