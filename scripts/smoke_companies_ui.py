from __future__ import annotations

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.app.dependency.factories import (
    create_active_company_context,
    create_app_context,
    create_navigation_service,
    create_service_registry,
    create_session_context,
    create_theme_manager,
)
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.shell.main_window import MainWindow
from seeker_accounting.app.shell.topbar import ShellTopBar
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.companies.ui.company_form_dialog import CompanyFormDialog
from seeker_accounting.modules.companies.ui.company_selector_dialog import CompanySelectorDialog
from seeker_accounting.modules.companies.ui.organisation_settings_page import OrganisationSettingsPage


def main() -> int:
    app = QApplication([])
    bootstrap = bootstrap_script_runtime(app)
    settings = bootstrap.settings
    app_context = bootstrap.app_context
    session_context = bootstrap.session_context
    active_company_context = bootstrap.active_company_context
    navigation_service = bootstrap.navigation_service
    theme_manager = bootstrap.theme_manager
    registry = bootstrap.service_registry

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
                    name="Central African CFA franc",
                    symbol="FCFA",
                    decimal_places=0,
                    is_active=True,
                )
            )
        uow.commit()

    main_window = MainWindow(registry)
    main_window.show()
    registry.navigation_service.navigate(nav_ids.ORGANISATION_SETTINGS)
    app.processEvents()

    company_page = main_window.findChild(OrganisationSettingsPage)
    topbar = main_window.findChild(ShellTopBar)
    if company_page is None or topbar is None:
        raise RuntimeError("Organisation Settings page or shell topbar could not be located.")

    print("page_empty_before", company_page._empty_state.isVisible())
    print(
        "topbar_before",
        topbar._fiscal_value_label.text(),
        topbar._user_name_label.text(),
        topbar._search_trigger.isEnabled(),
    )

    create_dialog = CompanyFormDialog(registry, parent=company_page)
    create_dialog._legal_name_edit.setText("Seeker Accounting Cameroon SARL")
    create_dialog._display_name_edit.setText("Seeker Cameroon")
    create_dialog._country_combo.set_current_value("CM")
    create_dialog._currency_combo.set_current_value("XAF")
    create_dialog._handle_create_next()
    create_dialog._city_edit.setText("Douala")
    create_dialog._region_edit.setText("Littoral")
    create_dialog._handle_create_next()
    created_company = create_dialog.saved_company
    if created_company is None:
        raise RuntimeError("Create dialog did not save a company.")

    company_page.reload_companies(selected_company_id=created_company.id)
    app.processEvents()
    print("created", created_company.id, created_company.display_name)
    print("page_empty_after_create", company_page._empty_state.isVisible())
    print("page_rows_after_create", company_page._table.rowCount())

    edit_dialog = CompanyFormDialog(registry, company_id=created_company.id, parent=company_page)
    edit_dialog._display_name_edit.setText("Seeker Cameroon HQ")
    edit_dialog._region_edit.setText("Littoral Region")
    edit_dialog._handle_edit_submit()
    updated_company = edit_dialog.saved_company
    if updated_company is None:
        raise RuntimeError("Edit dialog did not save the updated company.")

    company_page.reload_companies(selected_company_id=updated_company.id)
    app.processEvents()
    print("updated", updated_company.id, updated_company.display_name, updated_company.region)

    selector_dialog = CompanySelectorDialog(registry, initial_company_id=updated_company.id, parent=main_window)
    selector_dialog._apply_selection()
    selected_active_company = selector_dialog.selected_active_company
    if selected_active_company is None:
        raise RuntimeError("Selector dialog did not set the active company.")

    app.processEvents()
    print(
        "active_selected",
        selected_active_company.company_id,
        selected_active_company.company_name,
        selected_active_company.base_currency_code,
    )
    print(
        "topbar_after",
        topbar._fiscal_value_label.text(),
        topbar._user_name_label.text(),
        topbar._search_trigger.isEnabled(),
    )

    main_window.close()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
