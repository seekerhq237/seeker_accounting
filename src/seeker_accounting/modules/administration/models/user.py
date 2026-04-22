from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class User(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default=expression.false(),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    # ── Avatar / profile picture ──
    avatar_storage_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_updated_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    user_roles: Mapped[list["UserRole"]] = relationship("UserRole", back_populates="user")
    company_access_entries: Mapped[list["UserCompanyAccess"]] = relationship(
        "UserCompanyAccess",
        back_populates="user",
        foreign_keys="UserCompanyAccess.user_id",
    )

