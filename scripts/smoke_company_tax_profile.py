"""Smoke for the Company Tax Profile page (Slice T6)."""

from __future__ import annotations

import os
import sys
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.shell.main_window import MainWindow
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.companies.dto.company_commands import (
    CreateCompanyCommand,
)
from seeker_accounting.modules.taxation.dto.company_tax_profile_dto import (
    UpsertCompanyTaxProfileCommand,
)
from seeker_accounting.modules.taxation.ui.company_tax_profile_dialog import (
    CompanyTaxProfileDialog,
)
from seeker_accounting.modules.taxation.ui.company_tax_profile_page import (
    CompanyTaxProfilePage,
)


def _get_page(main_window, nav_id, page_class, app):
    main_window._service_registry.navigation_service.navigate(nav_id)
    app.processEvents()
    page = main_window.findChild(page_class)
    if page is None:
        raise SystemExit(
            f"Expected {page_class.__name__} for nav_id {nav_id} not found"
        )
    return page


def main() -> int:
    app = QApplication([])
    from seeker_accounting.modules.administration.rbac_catalog import (
        ALL_SYSTEM_PERMISSION_CODES,
    )

    bootstrap = bootstrap_script_runtime(
        app, permission_snapshot=ALL_SYSTEM_PERMISSION_CODES
    )
    registry = bootstrap.service_registry

    with registry.session_context.unit_of_work_factory() as uow:
        session = uow.session
        if session.get(Country, "CM") is None:
            session.add(Country(code="CM", name="Cameroon", is_active=True))
        if session.get(Currency, "XAF") is None:
            session.add(
                Currency(
                    code="XAF",
                    name="Central African CFA franc",
                    symbol="FCFA",
                    decimal_places=0,
                    is_active=True,
                )
            )
        uow.commit()

    company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name="Smoke Tax Profile Co",
            display_name="Smoke Tax Profile Co",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    registry.company_context_service.set_active_company(company.id)

    main_window = MainWindow(registry)
    main_window.show()
    app.processEvents()

    page = _get_page(main_window, nav_ids.TAX_PROFILE, CompanyTaxProfilePage, app)
    print(
        "tax_profile_loaded_with_active",
        page._stack.currentWidget() is page._detail_card,
    )
    print(
        "tax_profile_default_exists",
        page._profile.exists if page._profile else None,
    )

    registry.company_tax_profile_service.upsert(
        company.id,
        UpsertCompanyTaxProfileCommand(
            niu="P000111222333A",
            tax_center_code="DPMI_DOUALA",
            taxpayer_segment_code="MEDIUM",
            tax_regime_code="REAL",
            is_vat_liable=True,
            vat_effective_from=date(2024, 1, 1),
            cit_rate_profile_code="STANDARD",
            cit_installment_profile_code="QUARTERLY",
            sme_qualified_flag=False,
            dsf_form_code="DSF_REAL",
            dsf_submission_mode_code="EXCEL",
            otp_enabled_flag=True,
            default_withholding_applicable_flag=False,
        ),
    )
    page.reload()
    app.processEvents()
    print("tax_profile_after_upsert_exists", page._profile.exists)
    print("tax_profile_niu", page._niu_row[1].text())

    dialog = CompanyTaxProfileDialog(
        registry,
        company.id,
        company.display_name,
        page._profile,
        parent=page,
    )
    dialog.show()
    app.processEvents()
    dialog.reject()
    app.processEvents()
    print("dialog_open_close_ok", True)

    registry.company_context_service.clear_active_company()
    app.processEvents()
    page.reload()
    app.processEvents()
    print(
        "tax_profile_no_active",
        page._stack.currentWidget() is page._no_company_card,
    )

    main_window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
