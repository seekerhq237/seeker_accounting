from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from seeker_accounting.db.base import Base


class SystemAdminCredential(Base):
    """Single-row table holding system administrator login credentials.

    Completely isolated from the application User model / UserAuthService.
    Bootstrapped by migration with username='sysadmin' and a password that
    must be configured before the account can be used.
    """

    __tablename__ = "system_admin_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=True,
    )
    is_configured: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
    )
