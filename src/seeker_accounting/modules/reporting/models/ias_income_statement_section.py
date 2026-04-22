from __future__ import annotations

from sqlalchemy import Boolean, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import expression

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class IasIncomeStatementSection(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "ias_income_statement_sections"
    __table_args__ = (
        UniqueConstraint("statement_profile_code", "section_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_profile_code: Mapped[str] = mapped_column(String(80), nullable=False)
    section_code: Mapped[str] = mapped_column(String(80), nullable=False)
    section_label: Mapped[str] = mapped_column(String(160), nullable=False)
    parent_section_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    row_kind_code: Mapped[str] = mapped_column(String(20), nullable=False)
    is_mapping_target: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False, server_default=expression.false())

