from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ControlAccountFoundationStatusDTO:
    role_code: str
    role_label: str
    is_ready: bool
    mapped_account_id: int | None
    mapped_account_code: str | None
    mapped_account_name: str | None
    issues: tuple[str, ...]
