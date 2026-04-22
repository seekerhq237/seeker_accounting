from __future__ import annotations

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.companies.dto.company_commands import (
    CreateCompanyCommand,
    UpdateCompanyCommand,
    UpdateCompanyFiscalDefaultsCommand,
    UpdateCompanyPreferencesCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError


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

    print("list_before", registry.company_service.list_companies())

    try:
        registry.company_service.get_company(999)
    except NotFoundError as exc:
        print("get_missing", type(exc).__name__)

    created = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name="Seeker Accounting Cameroon SARL",
            display_name="Seeker Cameroon",
            country_code="CM",
            base_currency_code="XAF",
            city="Douala",
        )
    )
    print("created", created.id, created.display_name, created.preferences, created.fiscal_defaults)

    try:
        registry.company_service.create_company(
            CreateCompanyCommand(
                legal_name="Seeker Accounting Cameroon SARL",
                display_name="Seeker Cameroon Duplicate",
                country_code="CM",
                base_currency_code="XAF",
            )
        )
    except ConflictError as exc:
        print("duplicate", type(exc).__name__)

    updated = registry.company_service.update_company(
        created.id,
        UpdateCompanyCommand(
            legal_name="Seeker Accounting Cameroon SARL",
            display_name="Seeker Cameroon HQ",
            country_code="CM",
            base_currency_code="XAF",
            city="Douala",
            region="Littoral",
        ),
    )
    print("updated", updated.id, updated.display_name, updated.region)

    preferences = registry.company_service.update_company_preferences(
        created.id,
        UpdateCompanyPreferencesCommand(
            date_format_code="DMY_SLASH",
            number_format_code="SPACE_COMMA",
            decimal_places=0,
            tax_inclusive_default=False,
            allow_negative_stock=False,
        ),
    )
    print("preferences", preferences.company_id, preferences.date_format_code, preferences.decimal_places)

    fiscal_defaults = registry.company_service.update_company_fiscal_defaults(
        created.id,
        UpdateCompanyFiscalDefaultsCommand(
            fiscal_year_start_month=1,
            fiscal_year_start_day=1,
            default_posting_grace_days=5,
        ),
    )
    print("fiscal_defaults", fiscal_defaults.company_id, fiscal_defaults.fiscal_year_start_month, fiscal_defaults.default_posting_grace_days)

    active_company = registry.company_context_service.set_active_company(created.id)
    print("active_set", active_company.company_id, active_company.company_name, active_company.base_currency_code)
    print("active_get", registry.company_context_service.get_active_company())
    registry.company_context_service.clear_active_company()
    print("active_cleared", registry.company_context_service.get_active_company())

    registry.company_context_service.set_active_company(created.id)
    registry.company_service.deactivate_company(created.id)
    print("after_deactivate_active", registry.company_context_service.get_active_company())

    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
