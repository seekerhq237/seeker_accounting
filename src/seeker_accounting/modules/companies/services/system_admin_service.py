from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

import bcrypt
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.models.auth_lockout import AuthenticationLockout
from seeker_accounting.modules.administration.repositories.auth_lockout_repository import AuthLockoutRepository
from seeker_accounting.modules.companies.repositories.system_admin_credential_repository import (
    SystemAdminCredentialRepository,
)
from seeker_accounting.platform.exceptions import ValidationError

logger = logging.getLogger(__name__)

SystemAdminCredentialRepositoryFactory = Callable[[Session], SystemAdminCredentialRepository]
AuthLockoutRepositoryFactory = Callable[[Session], AuthLockoutRepository]

_MIN_PASSWORD_LENGTH = 8
_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_DURATION = timedelta(minutes=15)


class SystemAdminService:
    """Manages system administrator credentials."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        credential_repository_factory: SystemAdminCredentialRepositoryFactory,
        auth_lockout_repository_factory: AuthLockoutRepositoryFactory | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._credential_repository_factory = credential_repository_factory
        self._auth_lockout_repository_factory = auth_lockout_repository_factory
        self._failed_attempts: dict[str, tuple[int, datetime]] = {}

    def _check_rate_limit(self, key: str) -> None:
        if self._auth_lockout_repository_factory is not None:
            now = datetime.utcnow()
            with self._unit_of_work_factory() as uow:
                repo = self._auth_lockout_repository_factory(uow.session)
                record = repo.get_by_scope_key(key)
                if record is None:
                    return
                if record.locked_until is None:
                    return
                if record.locked_until <= now:
                    repo.delete_by_scope_key(key)
                    uow.commit()
                    return
                raise ValidationError("Too many failed attempts. Please try again later.")

        record = self._failed_attempts.get(key)
        if record is None:
            return
        fail_count, last_failure = record
        if fail_count >= _MAX_FAILED_ATTEMPTS:
            if datetime.utcnow() - last_failure < _LOCKOUT_DURATION:
                raise ValidationError("Too many failed attempts. Please try again later.")
            del self._failed_attempts[key]

    def _record_failed_attempt(self, key: str) -> None:
        if self._auth_lockout_repository_factory is not None:
            now = datetime.utcnow()
            with self._unit_of_work_factory() as uow:
                repo = self._auth_lockout_repository_factory(uow.session)
                record = repo.get_by_scope_key(key)
                if record is None:
                    record = AuthenticationLockout(
                        scope_key=key,
                        failed_count=1,
                        last_failed_at=now,
                        locked_until=None,
                    )
                else:
                    reset_window = (
                        record.last_failed_at is None
                        or record.locked_until is not None and record.locked_until <= now
                        or now - record.last_failed_at >= _LOCKOUT_DURATION
                    )
                    record.failed_count = 1 if reset_window else record.failed_count + 1
                    record.last_failed_at = now
                    record.locked_until = None

                if record.failed_count >= _MAX_FAILED_ATTEMPTS:
                    record.locked_until = now + _LOCKOUT_DURATION

                repo.save(record)
                uow.commit()
            return

        record = self._failed_attempts.get(key)
        now = datetime.utcnow()
        if record is None:
            self._failed_attempts[key] = (1, now)
        else:
            fail_count, last_failure = record
            if now - last_failure >= _LOCKOUT_DURATION:
                self._failed_attempts[key] = (1, now)
            else:
                self._failed_attempts[key] = (fail_count + 1, now)

    def _clear_failed_attempts(self, key: str) -> None:
        if self._auth_lockout_repository_factory is not None:
            with self._unit_of_work_factory() as uow:
                repo = self._auth_lockout_repository_factory(uow.session)
                repo.delete_by_scope_key(key)
                uow.commit()
            return

        self._failed_attempts.pop(key, None)

    def is_configured(self) -> bool:
        try:
            with self._unit_of_work_factory() as uow:
                repo = self._credential_repository_factory(uow.session)
                record = repo.get()
                return bool(record is not None and record.is_configured and record.password_hash)
        except Exception:
            logger.exception("Error checking system admin configuration state.")
            return False

    def verify_credentials(self, username: str, password: str) -> bool:
        rate_key = "sysadmin"
        self._check_rate_limit(rate_key)
        try:
            with self._unit_of_work_factory() as uow:
                repo = self._credential_repository_factory(uow.session)
                record = repo.get()
                if record is None:
                    logger.error("system_admin_credentials row is missing; database may not be fully migrated.")
                    self._record_failed_attempt(rate_key)
                    return False
                if not record.is_configured or not record.password_hash:
                    logger.warning("System admin credentials are not configured yet.")
                    return False
                if record.username != username.strip():
                    self._record_failed_attempt(rate_key)
                    return False
                if not bcrypt.checkpw(password.encode("utf-8"), record.password_hash.encode("utf-8")):
                    self._record_failed_attempt(rate_key)
                    return False
                self._clear_failed_attempts(rate_key)
                return True
        except ValidationError:
            raise
        except Exception:
            logger.exception("Error verifying sysadmin credentials.")
            return False

    def must_change_password(self) -> bool:
        try:
            with self._unit_of_work_factory() as uow:
                repo = self._credential_repository_factory(uow.session)
                record = repo.get()
                return bool(record is not None and record.is_configured and record.must_change_password)
        except Exception:
            logger.exception("Error checking sysadmin must_change_password flag.")
            return False

    def change_password(self, current_password: str, new_password: str) -> None:
        new_password = new_password.strip() if new_password else ""
        if len(new_password) < _MIN_PASSWORD_LENGTH:
            raise ValidationError(f"New password must be at least {_MIN_PASSWORD_LENGTH} characters.")

        with self._unit_of_work_factory() as uow:
            repo = self._credential_repository_factory(uow.session)
            record = repo.get()
            if record is None:
                raise ValidationError("System admin credentials record not found.")
            if not record.is_configured or not record.password_hash:
                raise ValidationError("System administrator setup is not complete yet.")
            if not bcrypt.checkpw(current_password.encode("utf-8"), record.password_hash.encode("utf-8")):
                raise ValidationError("Current password is incorrect.")
            if bcrypt.checkpw(new_password.encode("utf-8"), record.password_hash.encode("utf-8")):
                raise ValidationError("New password must differ from the current password.")

            record.password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            record.must_change_password = False
            record.is_configured = True
            repo.save(record)
            uow.commit()

    def set_password_direct(self, new_password: str) -> None:
        new_password = new_password.strip() if new_password else ""
        if len(new_password) < _MIN_PASSWORD_LENGTH:
            raise ValidationError(f"New password must be at least {_MIN_PASSWORD_LENGTH} characters.")
        if new_password == "sys_admin":
            raise ValidationError("Password does not meet requirements.")

        with self._unit_of_work_factory() as uow:
            repo = self._credential_repository_factory(uow.session)
            record = repo.get()
            if record is None:
                raise ValidationError("System admin credentials record not found.")
            if record.password_hash and bcrypt.checkpw(new_password.encode("utf-8"), record.password_hash.encode("utf-8")):
                raise ValidationError("New password must differ from the current password.")

            record.password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            record.must_change_password = False
            record.is_configured = True
            repo.save(record)
            uow.commit()
