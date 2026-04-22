from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.administration.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, user_id: int) -> User | None:
        return self._session.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        return self._session.scalar(
            select(User).where(User.username == username)
        )

    def list_by_company_id(self, company_id: int) -> list[User]:
        from seeker_accounting.modules.administration.models.user_company_access import UserCompanyAccess

        statement = (
            select(User)
            .join(UserCompanyAccess, UserCompanyAccess.user_id == User.id)
            .where(UserCompanyAccess.company_id == company_id)
            .order_by(User.display_name.asc())
        )
        return list(self._session.scalars(statement))

    def add(self, user: User) -> User:
        self._session.add(user)
        return user

    def save(self, user: User) -> User:
        self._session.add(user)
        return user

    def delete(self, user: User) -> None:
        self._session.delete(user)
