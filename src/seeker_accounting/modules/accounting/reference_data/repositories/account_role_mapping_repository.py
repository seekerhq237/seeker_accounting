from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.reference_data.models.account_role_mapping import AccountRoleMapping


class AccountRoleMappingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int) -> list[AccountRoleMapping]:
        statement = select(AccountRoleMapping).where(AccountRoleMapping.company_id == company_id)
        statement = statement.order_by(AccountRoleMapping.role_code.asc(), AccountRoleMapping.id.asc())
        return list(self._session.scalars(statement))

    def get_by_role_code(self, company_id: int, role_code: str) -> AccountRoleMapping | None:
        statement = select(AccountRoleMapping).where(
            AccountRoleMapping.company_id == company_id,
            AccountRoleMapping.role_code == role_code,
        )
        return self._session.scalar(statement)

    def add(self, mapping: AccountRoleMapping) -> AccountRoleMapping:
        self._session.add(mapping)
        return mapping

    def save(self, mapping: AccountRoleMapping) -> AccountRoleMapping:
        self._session.add(mapping)
        return mapping

    def delete(self, mapping: AccountRoleMapping) -> None:
        self._session.delete(mapping)

