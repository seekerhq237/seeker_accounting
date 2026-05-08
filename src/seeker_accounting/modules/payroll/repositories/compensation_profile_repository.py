from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.payroll.models.employee_compensation_profile import (
    EmployeeCompensationProfile,
)


class CompensationProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_employee(
        self,
        company_id: int,
        employee_id: int,
        active_only: bool = False,
    ) -> list[EmployeeCompensationProfile]:
        stmt = (
            select(EmployeeCompensationProfile)
            .where(
                EmployeeCompensationProfile.company_id == company_id,
                EmployeeCompensationProfile.employee_id == employee_id,
            )
            .options(selectinload(EmployeeCompensationProfile.employee))
            .order_by(EmployeeCompensationProfile.effective_from.desc())
        )
        if active_only:
            stmt = stmt.where(EmployeeCompensationProfile.is_active == True)  # noqa: E712
        return list(self._session.scalars(stmt).all())

    def list_by_company(
        self,
        company_id: int,
        active_only: bool = False,
    ) -> list[EmployeeCompensationProfile]:
        stmt = (
            select(EmployeeCompensationProfile)
            .where(EmployeeCompensationProfile.company_id == company_id)
            .options(selectinload(EmployeeCompensationProfile.employee))
            .order_by(EmployeeCompensationProfile.employee_id, EmployeeCompensationProfile.effective_from.desc())
        )
        if active_only:
            stmt = stmt.where(EmployeeCompensationProfile.is_active == True)  # noqa: E712
        return list(self._session.scalars(stmt).all())

    def get_by_id(
        self, company_id: int, profile_id: int
    ) -> EmployeeCompensationProfile | None:
        stmt = (
            select(EmployeeCompensationProfile)
            .where(
                EmployeeCompensationProfile.id == profile_id,
                EmployeeCompensationProfile.company_id == company_id,
            )
            .options(selectinload(EmployeeCompensationProfile.employee))
        )
        return self._session.scalar(stmt)

    def get_active_for_period(
        self,
        company_id: int,
        employee_id: int,
        period_date: date,
    ) -> EmployeeCompensationProfile | None:
        """Return the profile covering period_date for this employee, or None."""
        stmt = (
            select(EmployeeCompensationProfile)
            .where(
                EmployeeCompensationProfile.company_id == company_id,
                EmployeeCompensationProfile.employee_id == employee_id,
                EmployeeCompensationProfile.is_active == True,  # noqa: E712
                EmployeeCompensationProfile.effective_from <= period_date,
                or_(
                    EmployeeCompensationProfile.effective_to.is_(None),
                    EmployeeCompensationProfile.effective_to >= period_date,
                ),
            )
            .order_by(EmployeeCompensationProfile.effective_from.desc())
            .limit(1)
        )
        return self._session.scalar(stmt)

    def map_active_for_period(
        self,
        company_id: int,
        period_date: date,
    ) -> dict[int, EmployeeCompensationProfile]:
        """Bulk-load: return ``{employee_id: active_profile}`` for the period.

        Single SQL round-trip across all employees of the company. Used by
        the payroll run calculation engine to avoid N+1 queries.
        """
        stmt = (
            select(EmployeeCompensationProfile)
            .where(
                EmployeeCompensationProfile.company_id == company_id,
                EmployeeCompensationProfile.is_active == True,  # noqa: E712
                EmployeeCompensationProfile.effective_from <= period_date,
            )
            .order_by(
                EmployeeCompensationProfile.employee_id,
                EmployeeCompensationProfile.effective_from.desc(),
            )
        )
        result: dict[int, EmployeeCompensationProfile] = {}
        for profile in self._session.scalars(stmt):
            if profile.effective_to is not None and profile.effective_to < period_date:
                continue
            # First match per employee (highest effective_from) wins
            result.setdefault(profile.employee_id, profile)
        return result

    def check_duplicate(
        self,
        company_id: int,
        employee_id: int,
        effective_from: date,
        exclude_id: int | None = None,
    ) -> bool:
        stmt = select(EmployeeCompensationProfile.id).where(
            EmployeeCompensationProfile.company_id == company_id,
            EmployeeCompensationProfile.employee_id == employee_id,
            EmployeeCompensationProfile.effective_from == effective_from,
        )
        if exclude_id is not None:
            stmt = stmt.where(EmployeeCompensationProfile.id != exclude_id)
        return self._session.scalar(stmt) is not None

    def save(self, profile: EmployeeCompensationProfile) -> EmployeeCompensationProfile:
        self._session.add(profile)
        return profile
