from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AppContext:
    current_user_id: int | None
    current_user_display_name: str
    active_company_id: int | None
    active_company_name: str | None
    theme_name: str
    permission_snapshot: tuple[str, ...] = field(default_factory=tuple)
    current_session_id: int | None = field(default=None)

    def set_theme(self, theme_name: str) -> None:
        self.theme_name = theme_name

    def set_active_company(self, company_id: int | None, company_name: str | None) -> None:
        self.active_company_id = company_id
        self.active_company_name = company_name
