"""Focused offscreen smoke for contracts/projects ribbons and workspace windows."""

from __future__ import annotations

import os
import sys
import time
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.accounting.reference_data.models.country import Country
from seeker_accounting.modules.accounting.reference_data.models.currency import Currency
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.contracts_projects.dto.contract_dto import CreateContractCommand
from seeker_accounting.modules.contracts_projects.dto.project_dto import CreateProjectCommand
from seeker_accounting.modules.customers.dto.customer_commands import (
    CreateCustomerCommand,
    CreateCustomerGroupCommand,
)


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
    runtime = bootstrap_script_runtime(
        app,
        permission_snapshot=(
            "companies.create",
            "companies.view",
            "customers.groups.create",
            "customers.groups.view",
            "customers.create",
            "customers.view",
        ),
    )
    registry = runtime.service_registry

    _seed_reference_data(registry)

    unique = str(int(time.time() * 1000))
    company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"Contracts Projects Smoke {unique}",
            display_name=f"Contracts Projects Smoke {unique}",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    company_id = company.id
    registry.company_context_service.set_active_company(company_id)

    group = registry.customer_service.create_customer_group(
        company_id,
        CreateCustomerGroupCommand(code=f"CP{unique[-4:]}", name="Smoke Customers"),
    )
    customer = registry.customer_service.create_customer(
        company_id,
        CreateCustomerCommand(
            customer_group_id=group.id,
            customer_code=f"CUST{unique[-6:]}",
            display_name="Ribbon Smoke Customer",
            country_code="CM",
        ),
    )

    contract = registry.contract_service.create_contract(
        CreateContractCommand(
            company_id=company_id,
            contract_number=f"CTR-{unique[-6:]}",
            contract_title="Ribbon Smoke Contract",
            customer_id=customer.id,
            contract_type_code="fixed_price",
            currency_code="XAF",
            base_contract_amount=Decimal("1500000.00"),
            start_date=date(2026, 1, 1),
            planned_end_date=date(2026, 12, 31),
            billing_basis_code="milestone",
        )
    )
    project = registry.project_service.create_project(
        CreateProjectCommand(
            company_id=company_id,
            project_code=f"PRJ-{unique[-6:]}",
            project_name="Ribbon Smoke Project",
            contract_id=contract.id,
            customer_id=customer.id,
            project_type_code="external",
            currency_code="XAF",
            start_date=date(2026, 1, 15),
            planned_end_date=date(2026, 11, 30),
            budget_control_mode_code="warn",
        )
    )

    assert registry.ribbon_registry.has("contracts"), "missing contracts surface"
    assert registry.ribbon_registry.has("projects"), "missing projects surface"
    assert registry.ribbon_registry.has("child:contract_workspace"), "missing contract workspace surface"
    assert registry.ribbon_registry.has("child:project_workspace"), "missing project workspace surface"

    from seeker_accounting.modules.contracts_projects.ui.contracts_page import ContractsPage
    from seeker_accounting.modules.contracts_projects.ui.projects_page import ProjectsPage

    contracts_page = ContractsPage(registry)
    projects_page = ProjectsPage(registry)
    for _ in range(8):
        app.processEvents()

    contract_state = contracts_page.ribbon_state()
    project_state = projects_page.ribbon_state()
    assert contract_state["contracts.open_workspace"] is True
    assert contract_state["contracts.summary"] is True
    assert project_state["projects.open_workspace"] is True
    assert project_state["projects.variance"] is True
    assert project_state["projects.contract_summary"] is True

    contracts_page._ribbon_commands()["contracts.open_workspace"]()
    projects_page._ribbon_commands()["projects.open_workspace"]()
    for _ in range(8):
        app.processEvents()

    manager = registry.child_window_manager
    assert manager is not None, "child window manager missing"
    contract_window = manager.get("contract_workspace", contract.id)
    project_window = manager.get("project_workspace", project.id)
    assert contract_window is not None, "contract workspace did not open"
    assert project_window is not None, "project workspace did not open"

    # Overview tab: lifecycle enabled, CO/project actions disabled.
    overview_state = contract_window.ribbon_state()
    assert overview_state["contract_workspace.edit"] is True
    assert overview_state["contract_workspace.activate"] is True
    assert overview_state["contract_workspace.co_new"] is False
    assert overview_state["contract_workspace.project_new"] is False

    # Switch to Change Orders tab and verify New CO becomes enabled.
    contract_window._tabs.setCurrentIndex(contract_window._TAB_CHANGE_ORDERS)
    for _ in range(4):
        app.processEvents()
    co_state = contract_window.ribbon_state()
    assert co_state["contract_workspace.co_new"] is True
    assert co_state["contract_workspace.co_edit"] is False  # no CO selected yet

    # Seed a draft change order via the service, reload tab, check CO ribbon state.
    from seeker_accounting.modules.contracts_projects.dto.contract_change_order_commands import (
        CreateContractChangeOrderCommand,
    )

    co_dto = registry.contract_change_order_service.create_change_order(
        CreateContractChangeOrderCommand(
            company_id=company_id,
            contract_id=contract.id,
            change_order_number="CO-001",
            change_order_date=date(2026, 3, 1),
            change_type_code="price",
            description="Smoke CO",
        )
    )
    contract_window._reload_change_orders(selected_id=co_dto.id)
    for _ in range(4):
        app.processEvents()
    co_selected_state = contract_window.ribbon_state()
    assert co_selected_state["contract_workspace.co_edit"] is True
    assert co_selected_state["contract_workspace.co_submit"] is True
    assert co_selected_state["contract_workspace.co_approve"] is False

    # Switch to Projects tab; project_new enabled, linked project listed.
    contract_window._tabs.setCurrentIndex(contract_window._TAB_PROJECTS)
    for _ in range(4):
        app.processEvents()
    projects_state = contract_window.ribbon_state()
    assert projects_state["contract_workspace.project_new"] is True
    assert projects_state["contract_workspace.project_open"] is True, "seeded project should be listed and selected"
    assert projects_state["contract_workspace.project_edit"] is True
    assert len(contract_window._projects) == 1
    assert contract_window._projects[0].id == project.id

    nav_calls: list[tuple[str, dict[str, object]]] = []
    original_navigate = registry.navigation_service.navigate

    def _capture(nav_id: str, *, context=None, resume_token=None, force_emit=False):
        nav_calls.append((nav_id, dict(context or {})))

    registry.navigation_service.navigate = _capture  # type: ignore[assignment]
    try:
        contract_window.handle_ribbon_command("contract_workspace.summary")
        project_window.handle_ribbon_command("project_workspace.variance")
        project_window.handle_ribbon_command("project_workspace.contract_summary")
    finally:
        registry.navigation_service.navigate = original_navigate  # type: ignore[assignment]

    assert nav_calls[0] == (nav_ids.CONTRACT_SUMMARY, {"contract_id": contract.id})
    assert nav_calls[1] == (nav_ids.PROJECT_VARIANCE_ANALYSIS, {"project_id": project.id})
    assert nav_calls[2] == (nav_ids.CONTRACT_SUMMARY, {"contract_id": contract.id})

    print("contracts_projects_ribbon_smoke PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())