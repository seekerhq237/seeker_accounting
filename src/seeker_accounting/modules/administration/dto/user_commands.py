from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateUserCommand:
    username: str
    display_name: str
    password: str
    email: str | None = None
    must_change_password: bool = False


@dataclass(frozen=True, slots=True)
class ChangePasswordCommand:
    user_id: int
    new_password: str
    current_password: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateUserCommand:
    user_id: int
    display_name: str
    email: str | None = None
    must_change_password: bool = False
