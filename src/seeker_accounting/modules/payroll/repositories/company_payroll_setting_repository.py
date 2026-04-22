from __future__ import annotations

from sqlalchemy.orm import Session

from seeker_accounting.modules.payroll.models.company_payroll_setting import CompanyPayrollSetting


class CompanyPayrollSettingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_company(self, company_id: int) -> CompanyPayrollSetting | None:
        return self._session.get(CompanyPayrollSetting, company_id)

    def save(self, setting: CompanyPayrollSetting) -> CompanyPayrollSetting:
        self._session.add(setting)
        return setting
