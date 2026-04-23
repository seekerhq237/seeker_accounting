"""
Smoke: accounting ribbon "Related" navigation buttons.

Verifies:
  1. Each of the 7 accounting surfaces has its Related group
     appended (divider + expected goto buttons, in order).
  2. Every goto command_id resolves to a handler on the corresponding
     page that calls ``navigation_service.navigate(target_nav_id)``.
  3. ``ribbon_state()`` reports every goto command as enabled.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime  # type: ignore

from seeker_accounting.app.shell.ribbon.ribbon_models import (
    RibbonButtonDef,
    RibbonDividerDef,
)
from seeker_accounting.app.shell.ribbon.ribbon_registry import (
    RELATED_PAGES,
    RibbonRegistry,
    related_goto_command_id,
)
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.companies.dto.company_commands import (
    CreateCompanyCommand,
)


PAGE_FACTORIES = [
    (
        "chart_of_accounts",
        "seeker_accounting.modules.accounting.chart_of_accounts.ui.chart_of_accounts_page",
        "ChartOfAccountsPage",
    ),
    (
        "journals",
        "seeker_accounting.modules.accounting.journals.ui.journals_page",
        "JournalsPage",
    ),
    (
        "fiscal_periods",
        "seeker_accounting.modules.accounting.fiscal_periods.ui.fiscal_periods_page",
        "FiscalPeriodsPage",
    ),
    (
        "payment_terms",
        "seeker_accounting.modules.accounting.reference_data.ui.payment_terms_page",
        "PaymentTermsPage",
    ),
    (
        "tax_codes",
        "seeker_accounting.modules.accounting.reference_data.ui.tax_codes_page",
        "TaxCodesPage",
    ),
    (
        "document_sequences",
        "seeker_accounting.modules.accounting.reference_data.ui.document_sequences_page",
        "DocumentSequencesPage",
    ),
    (
        "account_role_mappings",
        "seeker_accounting.modules.accounting.reference_data.ui.account_role_mappings_page",
        "AccountRoleMappingsPage",
    ),
]


def _assert_registry_shape() -> None:
    reg = RibbonRegistry()
    for surface_key, spec in RELATED_PAGES.items():
        surface = reg.get(surface_key)
        assert surface is not None, f"surface missing: {surface_key}"
        items = list(surface.items)

        # Find the 'before_related' divider — must be present exactly once.
        dividers = [
            (idx, item)
            for idx, item in enumerate(items)
            if isinstance(item, RibbonDividerDef) and item.key == "before_related"
        ]
        assert len(dividers) == 1, (
            f"{surface_key}: expected exactly one 'before_related' divider, "
            f"got {len(dividers)}"
        )
        divider_idx = dividers[0][0]

        # Everything after the divider must be the goto buttons in spec order.
        trailing = items[divider_idx + 1 :]
        assert len(trailing) == len(spec), (
            f"{surface_key}: expected {len(spec)} related buttons, "
            f"got {len(trailing)} — {[getattr(i, 'command_id', i) for i in trailing]}"
        )
        for button, (target_nav_id, label, icon_name) in zip(trailing, spec):
            assert isinstance(button, RibbonButtonDef), (
                f"{surface_key}: non-button in Related group: {button}"
            )
            expected_id = related_goto_command_id(surface_key, target_nav_id)
            assert button.command_id == expected_id, (
                f"{surface_key}: expected {expected_id}, got {button.command_id}"
            )
            assert button.label == label, f"{surface_key}: bad label on {expected_id}"
            assert button.icon_name == icon_name, (
                f"{surface_key}: bad icon on {expected_id}"
            )
    print("registry_shape_ok", len(RELATED_PAGES), "surfaces")


def _seed_company(service_registry) -> int:
    with service_registry.session_context.unit_of_work_factory() as uow:
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

    unique = str(int(time.time() * 1000))
    company = service_registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"Related Nav Smoke {unique}",
            display_name="Related Nav Smoke",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    service_registry.company_context_service.set_active_company(company.id)
    return company.id


def _exercise_pages(service_registry) -> None:
    import importlib

    # Capture navigate() calls so we don't actually switch the shell.
    calls: list[str] = []
    original_navigate = service_registry.navigation_service.navigate
    service_registry.navigation_service.navigate = lambda nav_id, **kw: calls.append(  # type: ignore[assignment]
        nav_id
    )

    try:
        for surface_key, module_path, class_name in PAGE_FACTORIES:
            module = importlib.import_module(module_path)
            page_cls = getattr(module, class_name)
            try:
                page = page_cls(service_registry=service_registry)
            except TypeError:
                page = page_cls(service_registry)

            commands = page._ribbon_commands()
            state = page.ribbon_state()

            expected_nav_ids = [t[0] for t in RELATED_PAGES[surface_key]]
            for target_nav_id in expected_nav_ids:
                cmd_id = related_goto_command_id(surface_key, target_nav_id)
                assert cmd_id in commands, (
                    f"{surface_key}: missing handler for {cmd_id}"
                )
                assert state.get(cmd_id) is True, (
                    f"{surface_key}: {cmd_id} not enabled in ribbon_state()"
                )

                calls.clear()
                commands[cmd_id]()
                assert calls == [target_nav_id], (
                    f"{surface_key}: expected navigate({target_nav_id!r}), "
                    f"got {calls!r}"
                )

            page.deleteLater()
            print(f"page_ok {surface_key}")
    finally:
        service_registry.navigation_service.navigate = original_navigate  # type: ignore[assignment]


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    runtime = bootstrap_script_runtime(
        app,
        permission_snapshot=(
            "companies.create",
            "companies.view",
            "chart.accounts.view",
            "journals.entries.view",
            "fiscal.years.view",
            "fiscal.periods.view",
            "reference.payment_terms.view",
            "reference.tax_codes.view",
            "reference.document_sequences.view",
            "reference.account_role_mappings.view",
        ),
    )
    service_registry = runtime.service_registry

    _assert_registry_shape()
    _seed_company(service_registry)
    _exercise_pages(service_registry)

    print("ribbon_related_navigation_smoke PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
