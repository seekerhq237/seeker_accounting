from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class ActiveCompanyContext(QObject):
    active_company_changed = Signal(object, object)

    def __init__(
        self,
        company_id: int | None = None,
        company_name: str | None = None,
        base_currency_code: str | None = None,
        logo_storage_path: str | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._company_id = company_id
        self._company_name = company_name
        self._base_currency_code = base_currency_code
        self._logo_storage_path = logo_storage_path

    @property
    def company_id(self) -> int | None:
        return self._company_id

    @property
    def company_name(self) -> str | None:
        return self._company_name

    @property
    def base_currency_code(self) -> str | None:
        return self._base_currency_code

    @property
    def logo_storage_path(self) -> str | None:
        return self._logo_storage_path

    def set_active_company(
        self,
        company_id: int | None,
        company_name: str | None,
        base_currency_code: str | None = None,
        logo_storage_path: str | None = None,
    ) -> None:
        self._company_id = company_id
        self._company_name = company_name
        self._base_currency_code = base_currency_code
        self._logo_storage_path = logo_storage_path
        self.active_company_changed.emit(company_id, company_name)

    def clear_active_company(self) -> None:
        self.set_active_company(None, None, None, None)
