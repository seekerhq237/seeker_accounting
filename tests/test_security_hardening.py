from __future__ import annotations

import unittest
from datetime import datetime, UTC

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.base import Base
from seeker_accounting.db.model_registry import load_model_registry
from seeker_accounting.db.unit_of_work import create_unit_of_work_factory
from seeker_accounting.modules.administration.models.auth_lockout import AuthenticationLockout
from seeker_accounting.modules.administration.models.user import User
from seeker_accounting.modules.administration.repositories.auth_lockout_repository import AuthLockoutRepository
from seeker_accounting.modules.administration.repositories.user_repository import UserRepository
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.administration.services.user_auth_service import UserAuthService
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.companies.models.system_admin_credential import SystemAdminCredential
from seeker_accounting.modules.companies.repositories.system_admin_credential_repository import (
    SystemAdminCredentialRepository,
)
from seeker_accounting.modules.companies.services.company_service import CompanyService
from seeker_accounting.modules.companies.services.system_admin_service import SystemAdminService
from seeker_accounting.platform.exceptions import PermissionDeniedError, ValidationError


def _unused_factory(*_args, **_kwargs):  # noqa: ANN001, ANN002
    raise AssertionError("Repository access should not happen when permission is denied first.")


class _CompanyContextStub:
    def get_active_company(self):  # noqa: ANN201
        return None

    def clear_active_company(self) -> None:
        return None


class SecurityHardeningTests(unittest.TestCase):
    def _permission_service(
        self,
        *,
        current_user_id: int | None,
        permissions: tuple[str, ...] = tuple(),
    ) -> PermissionService:
        return PermissionService(
            AppContext(
                current_user_id=current_user_id,
                current_user_display_name="Tester" if current_user_id else "",
                active_company_id=None,
                active_company_name=None,
                theme_name="light",
                permission_snapshot=permissions,
            )
        )

    def _company_service(self, permission_service: PermissionService) -> CompanyService:
        return CompanyService(
            unit_of_work_factory=_unused_factory,
            company_repository_factory=_unused_factory,
            company_preference_repository_factory=_unused_factory,
            company_fiscal_default_repository_factory=_unused_factory,
            country_repository_factory=_unused_factory,
            currency_repository_factory=_unused_factory,
            company_context_service=_CompanyContextStub(),
            user_company_access_repository_factory=_unused_factory,
            permission_service=permission_service,
        )

    def _session_factory(self, *tables) -> sessionmaker[Session]:
        load_model_registry()
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine, tables=list(tables))
        return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)

    def test_company_service_requires_login_before_listing_companies(self) -> None:
        service = self._company_service(self._permission_service(current_user_id=None))

        with self.assertRaises(PermissionDeniedError) as raised:
            service.list_companies()

        self.assertEqual(
            str(raised.exception),
            "You must log in before viewing available organisations.",
        )

    def test_company_service_fails_closed_for_creation_without_permission(self) -> None:
        service = self._company_service(
            self._permission_service(current_user_id=7, permissions=tuple())
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.create_company(
                CreateCompanyCommand(
                    legal_name="Acme Corporation",
                    display_name="Acme",
                    registration_number=None,
                    tax_identifier=None,
                    phone=None,
                    email=None,
                    website=None,
                    sector_of_operation=None,
                    address_line_1=None,
                    address_line_2=None,
                    city=None,
                    region=None,
                    country_code="CM",
                    base_currency_code="XAF",
                )
            )

        self.assertEqual(
            str(raised.exception),
            "You do not have permission to register new companies in the application.",
        )

    def test_company_service_blocks_system_admin_only_operations(self) -> None:
        service = self._company_service(
            self._permission_service(current_user_id=7, permissions=("companies.deactivate",))
        )

        with self.assertRaises(PermissionDeniedError) as raised:
            service.reactivate_company(1)

        self.assertEqual(
            str(raised.exception),
            "Company reactivation is reserved for the system administrator workflow.",
        )

    def test_user_auth_lockout_persists_across_service_instances(self) -> None:
        session_factory = self._session_factory(User.__table__, AuthenticationLockout.__table__)
        uow_factory = create_unit_of_work_factory(session_factory)

        with uow_factory() as uow:
            user = User(
                username="alice",
                display_name="Alice",
                password_hash=UserAuthService.hash_password("CorrectPass9"),
                must_change_password=False,
                password_changed_at=datetime.now(UTC).replace(tzinfo=None),
            )
            UserRepository(uow.session).add(user)
            uow.commit()

        permission_service = self._permission_service(current_user_id=None)
        service1 = UserAuthService(
            unit_of_work_factory=uow_factory,
            user_repository_factory=UserRepository,
            role_repository_factory=_unused_factory,
            user_role_repository_factory=_unused_factory,
            user_company_access_repository_factory=_unused_factory,
            permission_repository_factory=_unused_factory,
            permission_service=permission_service,
            auth_lockout_repository_factory=AuthLockoutRepository,
        )

        for _ in range(5):
            with self.assertRaises(ValidationError):
                service1.authenticate("alice", "wrong-password")

        service2 = UserAuthService(
            unit_of_work_factory=uow_factory,
            user_repository_factory=UserRepository,
            role_repository_factory=_unused_factory,
            user_role_repository_factory=_unused_factory,
            user_company_access_repository_factory=_unused_factory,
            permission_repository_factory=_unused_factory,
            permission_service=permission_service,
            auth_lockout_repository_factory=AuthLockoutRepository,
        )

        with self.assertRaises(ValidationError) as raised:
            service2.authenticate("alice", "CorrectPass9")

        self.assertIn("Too many failed login attempts", str(raised.exception))

    def test_system_admin_requires_explicit_bootstrap_before_authentication(self) -> None:
        session_factory = self._session_factory(
            SystemAdminCredential.__table__,
            AuthenticationLockout.__table__,
        )
        uow_factory = create_unit_of_work_factory(session_factory)

        with uow_factory() as uow:
            uow.session.add(
                SystemAdminCredential(
                    id=1,
                    username="sysadmin",
                    password_hash="",
                    must_change_password=True,
                    is_configured=False,
                )
            )
            uow.commit()

        service = SystemAdminService(
            unit_of_work_factory=uow_factory,
            credential_repository_factory=SystemAdminCredentialRepository,
            auth_lockout_repository_factory=AuthLockoutRepository,
        )

        self.assertFalse(service.is_configured())
        self.assertFalse(service.verify_credentials("sysadmin", "anything"))

        service.set_password_direct("SecurePass9")

        self.assertTrue(service.is_configured())
        self.assertTrue(service.verify_credentials("sysadmin", "SecurePass9"))


if __name__ == "__main__":
    unittest.main()
