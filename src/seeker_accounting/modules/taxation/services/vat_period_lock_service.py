"""VAT Period Lock Service (T43).

Provides lock/unlock management and the ``is_period_locked()`` check
used by posting services.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.platform.exceptions import PermissionDeniedError
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.taxation.models.vat_period_lock import VatPeriodLock
from seeker_accounting.modules.taxation.repositories.vat_period_lock_repository import (
    VatPeriodLockRepository,
)
from seeker_accounting.modules.administration.services.permission_service import PermissionService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
VatPeriodLockRepositoryFactory = Callable[[Session], VatPeriodLockRepository]


@dataclass
class VatPeriodLockDTO:
    id: int
    company_id: int
    period_start: datetime.date
    period_end: datetime.date
    tax_type_code: str
    locked_at: datetime.datetime
    locked_by_user_id: int | None
    return_id: int | None
    notes: str | None


class VATPeriodLockService:
    PERMISSION_VIEW = "taxation.returns.view"
    PERMISSION_MANAGE = "taxation.returns.manage"
    PERMISSION_UNLOCK = "taxation.periods.unlock"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        company_repository_factory: CompanyRepositoryFactory,
        vat_period_lock_repository_factory: VatPeriodLockRepositoryFactory,
        permission_service: PermissionService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._app_context = app_context
        self._company_repository_factory = company_repository_factory
        self._vat_period_lock_repository_factory = vat_period_lock_repository_factory
        self._permission_service = permission_service

    # ── Read ──────────────────────────────────────────────────────────────

    def list_locks(
        self,
        company_id: int,
        tax_type_code: str | None = None,
    ) -> list[VatPeriodLockDTO]:
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._vat_period_lock_repository_factory(uow.session)
            locks = repo.list_by_company(company_id, tax_type_code=tax_type_code)
            return [self._to_dto(lock) for lock in locks]

    def is_period_locked(
        self,
        company_id: int,
        tax_point_date: datetime.date,
        tax_type_code: str = "VAT",
    ) -> bool:
        """Return True if the date falls within a locked VAT period."""
        with self._unit_of_work_factory() as uow:
            repo = self._vat_period_lock_repository_factory(uow.session)
            return repo.is_locked(company_id, tax_point_date, tax_type_code)

    # ── Write ─────────────────────────────────────────────────────────────

    def lock_period(
        self,
        company_id: int,
        period_start: datetime.date,
        period_end: datetime.date,
        tax_type_code: str = "VAT",
        *,
        return_id: int | None = None,
        notes: str | None = None,
        actor_user_id: int | None = None,
    ) -> VatPeriodLockDTO:
        """Create a lock for the period.  Idempotent — returns existing if already locked."""
        self._permission_service.require_permission(self.PERMISSION_MANAGE)
        actor_id = (
            actor_user_id
            if actor_user_id is not None
            else self._app_context.current_user_id
        )
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._vat_period_lock_repository_factory(uow.session)
            existing = repo.find_by_period(
                company_id, period_start, period_end, tax_type_code
            )
            if existing is not None:
                return self._to_dto(existing)
            lock = VatPeriodLock(
                company_id=company_id,
                period_start=period_start,
                period_end=period_end,
                tax_type_code=tax_type_code,
                locked_at=datetime.datetime.utcnow(),
                locked_by_user_id=actor_id,
                return_id=return_id,
                notes=notes,
            )
            repo.add(lock)
            uow.commit()
            return self._to_dto(lock)

    def unlock_period(
        self,
        company_id: int,
        period_start: datetime.date,
        period_end: datetime.date,
        tax_type_code: str = "VAT",
        actor_user_id: int | None = None,
    ) -> None:
        """Remove the lock for the period.  Requires the unlock permission."""
        self._permission_service.require_permission(self.PERMISSION_UNLOCK)
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._vat_period_lock_repository_factory(uow.session)
            lock = repo.find_by_period(
                company_id, period_start, period_end, tax_type_code
            )
            if lock is None:
                raise NotFoundError(
                    f"No {tax_type_code} period lock found for "
                    f"{period_start.isoformat()} – {period_end.isoformat()}."
                )
            repo.delete(lock)
            uow.commit()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _require_company_exists(self, session: Session, company_id: int) -> None:
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    @staticmethod
    def _to_dto(lock: VatPeriodLock) -> VatPeriodLockDTO:
        return VatPeriodLockDTO(
            id=lock.id,
            company_id=lock.company_id,
            period_start=lock.period_start,
            period_end=lock.period_end,
            tax_type_code=lock.tax_type_code,
            locked_at=lock.locked_at,
            locked_by_user_id=lock.locked_by_user_id,
            return_id=lock.return_id,
            notes=lock.notes,
        )
