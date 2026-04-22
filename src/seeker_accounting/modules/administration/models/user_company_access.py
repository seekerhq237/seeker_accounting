from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from seeker_accounting.db.base import Base, utcnow


class UserCompanyAccess(Base):
    __tablename__ = "user_company_access"
    __table_args__ = (UniqueConstraint("user_id", "company_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    role_scope_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default_company: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default=expression.false(),
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    granted_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="company_access_entries",
        foreign_keys=[user_id],
    )
    company: Mapped["Company"] = relationship("Company", back_populates="user_access_entries")
    granted_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[granted_by_user_id])
