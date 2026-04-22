#!/usr/bin/env python3
"""Quick test of the new company_project_preference_service."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.modules.companies.dto.company_project_preference_dto import (
    UpdateCompanyProjectPreferencesCommand,
)
from seeker_accounting.modules.companies.models.company import Company


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

    # Test the service exists
    print("Service registry created successfully")
    print(f"company_project_preference_service: {registry.company_project_preference_service}")

    # Test with a company that exists
    with registry.session_context.unit_of_work_factory() as uow:
        session = uow.session
        if session is None:
            raise RuntimeError("Unit of work has no active session.")

        # Get first company
        company = session.query(Company).first()
        if company is None:
            print("No companies found, skipping test")
            return 0

        company_id = company.id
        print(f"Testing with company ID: {company_id}")

        # Test get (should return defaults)
        prefs = registry.company_project_preference_service.get_company_project_preferences(company_id)
        print(f"Initial preferences: {prefs}")

        # Test update
        update_cmd = UpdateCompanyProjectPreferencesCommand(
            allow_projects_without_contract=False,
            default_budget_control_mode_code="warn",
            default_commitment_control_mode_code="hard_stop",
            budget_warning_percent_threshold=80.0,
            require_job_on_cost_posting=True,
            require_cost_code_on_cost_posting=True,
        )
        updated = registry.company_project_preference_service.update_company_project_preferences(company_id, update_cmd)
        print(f"Updated preferences: {updated}")

        # Test get again
        prefs2 = registry.company_project_preference_service.get_company_project_preferences(company_id)
        print(f"Retrieved preferences: {prefs2}")

        print("Test completed successfully!")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())