from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.administration.models.user_company_access import UserCompanyAccess


class UserCompanyAccessRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_user_and_company(self, user_id: int, company_id: int) -> UserCompanyAccess | None:
        return self._session.scalar(
            select(UserCompanyAccess)
            .where(UserCompanyAccess.user_id == user_id)
            .where(UserCompanyAccess.company_id == company_id)
        )

    def list_by_user_id(self, user_id: int) -> list[UserCompanyAccess]:
        return list(self._session.scalars(
            select(UserCompanyAccess).where(UserCompanyAccess.user_id == user_id)
        ))

    def list_by_company_id(self, company_id: int) -> list[UserCompanyAccess]:
        return list(self._session.scalars(
            select(UserCompanyAccess).where(UserCompanyAccess.company_id == company_id)
        ))

    def add(self, access: UserCompanyAccess) -> UserCompanyAccess:
        self._session.add(access)
        return access

    def delete_by_user_and_company(self, user_id: int, company_id: int) -> None:
        self._session.execute(
            delete(UserCompanyAccess)
            .where(UserCompanyAccess.user_id == user_id)
            .where(UserCompanyAccess.company_id == company_id)
        )

    def delete_by_company_id(self, company_id: int) -> None:
        self._session.execute(
            delete(UserCompanyAccess).where(UserCompanyAccess.company_id == company_id)
        )
