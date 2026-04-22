from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.fixed_assets.models.macrs_profile import MacrsProfile


class MacrsProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self, active_only: bool = True) -> list[MacrsProfile]:
        stmt = select(MacrsProfile).order_by(MacrsProfile.recovery_period_years, MacrsProfile.convention_code)
        if active_only:
            stmt = stmt.where(MacrsProfile.is_active == True)  # noqa: E712
        return list(self._session.execute(stmt).scalars().all())

    def get_by_id(self, profile_id: int) -> MacrsProfile | None:
        stmt = select(MacrsProfile).where(MacrsProfile.id == profile_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_class_and_convention(self, class_code: str, convention_code: str) -> MacrsProfile | None:
        stmt = (
            select(MacrsProfile)
            .where(MacrsProfile.class_code == class_code)
            .where(MacrsProfile.convention_code == convention_code)
        )
        return self._session.execute(stmt).scalar_one_or_none()
