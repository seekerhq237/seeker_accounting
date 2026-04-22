from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import expression

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class IasIncomeStatementTemplate(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "ias_income_statement_templates"
    __table_args__ = (
        UniqueConstraint("statement_profile_code", "template_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_profile_code: Mapped[str] = mapped_column(String(80), nullable=False)
    template_code: Mapped[str] = mapped_column(String(80), nullable=False)
    template_title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    standard_note: Mapped[str] = mapped_column(String(120), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    row_height: Mapped[int] = mapped_column(Integer, nullable=False, default=28)
    section_background: Mapped[str] = mapped_column(String(20), nullable=False)
    subtotal_background: Mapped[str] = mapped_column(String(20), nullable=False)
    statement_background: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_font_size: Mapped[int] = mapped_column(Integer, nullable=False, default=11)
    label_font_size: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

