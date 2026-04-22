from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.companies.models.system_admin_credential import SystemAdminCredential


class SystemAdminCredentialRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self) -> SystemAdminCredential | None:
        return self._session.scalar(select(SystemAdminCredential).where(SystemAdminCredential.id == 1))

    def save(self, record: SystemAdminCredential) -> None:
        self._session.add(record)
