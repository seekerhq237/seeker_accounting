from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class Position(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        Index("ix_positions_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
