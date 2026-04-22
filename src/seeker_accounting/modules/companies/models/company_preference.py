from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from seeker_accounting.db.base import Base, utcnow


class CompanyPreference(Base):
    __tablename__ = "company_preferences"

    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    date_format_code: Mapped[str] = mapped_column(String(50), nullable=False)
    number_format_code: Mapped[str] = mapped_column(String(50), nullable=False)
    decimal_places: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_inclusive_default: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    allow_negative_stock: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default=expression.false(),
    )
    default_inventory_cost_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    idle_timeout_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
        server_default="2",
    )
    password_expiry_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        server_default="30",
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company", back_populates="preferences")
    updated_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_user_id])
