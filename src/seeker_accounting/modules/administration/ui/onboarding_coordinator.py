"""Guided organisation setup from the landing page."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from PySide6.QtWidgets import QMessageBox, QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.chart_of_accounts.ui.chart_import_dialog import ChartImportDialog
from seeker_accounting.modules.accounting.fiscal_periods.ui.fiscal_year_dialog import FiscalYearDialog
from seeker_accounting.modules.accounting.fiscal_periods.ui.generate_periods_dialog import GeneratePeriodsDialog
from seeker_accounting.modules.administration.dto.user_commands import CreateUserCommand
from seeker_accounting.modules.administration.dto.user_dto import UserDTO
from seeker_accounting.modules.administration.rbac_catalog import BASELINE_SYSTEM_ROLE_CODES
from seeker_accounting.modules.administration.ui.password_change_dialog import PasswordChangeDialog
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.companies.services.system_admin_company_service import (
    SystemAdminCompanyService,
)
from seeker_accounting.modules.companies.ui.company_form_dialog import CompanyFormDialog
from seeker_accounting.modules.accounting.reference_data.repositories.country_repository import CountryRepository
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository
from seeker_accounting.shared.ui.message_boxes import show_error, show_info

logger = logging.getLogger("seeker_accounting.onboarding")

_DEFAULT_ADMIN_USERNAME = "admin"
_DEFAULT_ADMIN_DISPLAY_NAME = "admin"


@dataclass(slots=True)
class OnboardingResult:
    """Returned on successful completion of the onboarding flow."""

    company_id: int
    company_name: str
    admin_username: str


class OnboardingCoordinator:
    """Runs the guided setup flow as a chain of modal dialogs."""

    def __init__(self, service_registry: ServiceRegistry) -> None:
        self._service_registry = service_registry
        self._system_admin_company_service = SystemAdminCompanyService(
            unit_of_work_factory=service_registry.session_context.unit_of_work_factory,
            company_repository_factory=CompanyRepository,
            country_repository_factory=CountryRepository,
            currency_repository_factory=CurrencyRepository,
            company_context_service=service_registry.company_context_service,
            audit_service=service_registry.audit_service,
        )

    def run(self, parent: QWidget | None = None) -> OnboardingResult | None:
        company = CompanyFormDialog.create_company(
            self._service_registry,
            create_company_handler=self._system_admin_company_service.create_company,
            get_company_handler=self._system_admin_company_service.get_company,
            parent=parent,
        )
        if company is None:
            return None

        company_id = company.id
        company_name = company.display_name
        self._created_admin_user_id: int | None = None

        try:
            return self._run_post_creation_steps(company_id, company_name, parent)
        except _OnboardingCancelled:
            self._clear_onboarding_context()
            self._rollback_company(company_id)
            return None
        finally:
            self._clear_onboarding_context()

    def _run_post_creation_steps(
        self,
        company_id: int,
        company_name: str,
        parent: QWidget | None,
    ) -> OnboardingResult:
        admin_username = self._build_admin_username(company_name, company_id)
        password_result = PasswordChangeDialog.prompt(
            username=admin_username,
            allow_skip=False,
            title="Set Organisation Admin Password",
            submit_label="Continue",
            parent=parent,
        )
        if password_result is None:
            raise _OnboardingCancelled()

        admin_user = self._create_admin_user(
            company_id=company_id,
            company_name=company_name,
            admin_password=password_result.new_password,
            parent=parent,
        )
        self._created_admin_user_id = admin_user.id
        self._show_admin_credentials(admin_user, parent)

        permissions: tuple[str, ...] = ()
        try:
            permissions = self._service_registry.user_auth_service.get_user_permission_codes(admin_user.id)
        except Exception:
            logger.warning("Could not load permission snapshot for admin user.", exc_info=True)

        ctx = self._service_registry.app_context
        ctx.current_user_id = admin_user.id
        ctx.current_user_display_name = admin_user.display_name
        ctx.permission_snapshot = permissions

        self._seed_baseline_data(company_id, parent)

        self._prompt_chart_setup(company_id, company_name, parent)
        self._prompt_fiscal_setup(company_id, company_name, parent)

        return OnboardingResult(
            company_id=company_id,
            company_name=company_name,
            admin_username=admin_user.username,
        )

    def _create_admin_user(
        self,
        company_id: int,
        company_name: str,
        admin_password: str,
        parent: QWidget | None,
    ) -> UserDTO:
        auth_service = self._service_registry.user_auth_service
        username = self._build_admin_username(company_name, company_id)

        command = CreateUserCommand(
            username=username,
            display_name=_DEFAULT_ADMIN_DISPLAY_NAME,
            password=admin_password,
            must_change_password=False,
        )
        try:
            user_dto = auth_service.create_user(command)
        except Exception as exc:
            logger.error("Failed to create admin user for company %s.", company_id, exc_info=True)
            show_error(
                parent,
                "Setup Error",
                f"Could not create the admin user.\n\n{exc}",
            )
            raise _OnboardingCancelled() from exc

        try:
            auth_service.grant_company_access(
                user_id=user_dto.id,
                company_id=company_id,
                is_default=True,
            )
        except Exception as exc:
            logger.error("Could not grant company access to admin user.", exc_info=True)
            show_error(
                parent,
                "Setup Error",
                f"Could not grant company access to the admin user.\n\n{exc}",
            )
            raise _OnboardingCancelled() from exc

        try:
            auth_service.assign_role_by_code(user_dto.id, BASELINE_SYSTEM_ROLE_CODES[0])
        except Exception as exc:
            logger.error("Could not assign admin role to onboarding admin user.", exc_info=True)
            show_error(
                parent,
                "Setup Error",
                f"Could not assign administrator role to the admin user.\n\n{exc}",
            )
            raise _OnboardingCancelled() from exc

        return user_dto

    def _seed_baseline_data(self, company_id: int, parent: QWidget | None) -> None:
        try:
            self._service_registry.company_seed_service.initialize_new_company(
                company_id, seed_built_in_chart=True
            )
        except Exception:
            logger.warning("Baseline seed for company %s completed with issues.", company_id, exc_info=True)

    def _show_admin_credentials(self, admin_user: UserDTO, parent: QWidget | None) -> None:
        show_info(
            parent,
            "Admin Account Created",
            "The organisation admin account has been created.\n\n"
            f"Username: {admin_user.username}\n"
            f"Display name: {admin_user.display_name}\n\n"
            "Use the password you just set to log in after onboarding finishes.",
        )

    def _prompt_chart_setup(
        self, company_id: int, company_name: str, parent: QWidget | None
    ) -> None:
        reply = QMessageBox.question(
            parent,
            "Chart of Accounts",
            "Would you like to import a chart of accounts template now?\n\n"
            "You can skip this and set up the chart later from Accounting Setup.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            raise _OnboardingCancelled()
        if reply == QMessageBox.StandardButton.No:
            return

        ChartImportDialog.import_chart_template(
            self._service_registry,
            company_id=company_id,
            company_name=company_name,
            parent=parent,
        )

    def _prompt_fiscal_setup(
        self, company_id: int, company_name: str, parent: QWidget | None
    ) -> None:
        reply = QMessageBox.question(
            parent,
            "Fiscal Year",
            "Would you like to create your first fiscal year now?\n\n"
            "You can skip this and configure fiscal periods later.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            raise _OnboardingCancelled()
        if reply == QMessageBox.StandardButton.No:
            return

        fiscal_year = FiscalYearDialog.create_fiscal_year(
            self._service_registry,
            company_id=company_id,
            company_name=company_name,
            parent=parent,
        )
        if fiscal_year is not None:
            GeneratePeriodsDialog.generate_periods(
                self._service_registry,
                company_id=company_id,
                company_name=company_name,
                fiscal_year_id=fiscal_year.id,
                fiscal_year_code=fiscal_year.year_code,
                parent=parent,
            )

    @staticmethod
    def _build_admin_username(company_name: str, company_id: int) -> str:
        normalized_name = re.sub(r"[^a-z0-9]+", "_", company_name.strip().lower()).strip("_")
        if not normalized_name:
            normalized_name = "company"
        return f"{_DEFAULT_ADMIN_USERNAME}_{normalized_name}_{company_id}"

    def _clear_onboarding_context(self) -> None:
        ctx = self._service_registry.app_context
        ctx.current_user_id = None
        ctx.current_user_display_name = ""
        ctx.permission_snapshot = ()
        self._service_registry.company_context_service.clear_active_company()

    def _rollback_company(self, company_id: int) -> None:
        logger.info("Rolling back onboarding for company %s.", company_id)
        try:
            self._system_admin_company_service.deactivate_company(company_id)
        except Exception:
            logger.warning("Rollback: could not deactivate company %s.", company_id, exc_info=True)

        admin_user_id = getattr(self, "_created_admin_user_id", None)
        if admin_user_id is not None:
            try:
                self._service_registry.user_auth_service.set_user_active(
                    user_id=admin_user_id,
                    is_active=False,
                )
            except Exception:
                logger.warning(
                    "Rollback: could not deactivate admin user %s.", admin_user_id, exc_info=True
                )


class _OnboardingCancelled(Exception):
    """Internal signal that the user cancelled mid-onboarding."""
