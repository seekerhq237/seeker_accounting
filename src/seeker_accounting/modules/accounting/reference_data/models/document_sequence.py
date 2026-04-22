from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class DocumentSequence(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "document_sequences"
    __table_args__ = (
        CheckConstraint("next_number >= 1", name="next_number_positive"),
        CheckConstraint("padding_width >= 0", name="padding_width_non_negative"),
        UniqueConstraint("company_id", "document_type_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_type_code: Mapped[str] = mapped_column(String(50), nullable=False)
    prefix: Mapped[str | None] = mapped_column(String(20), nullable=True)
    suffix: Mapped[str | None] = mapped_column(String(20), nullable=True)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False)
    padding_width: Mapped[int] = mapped_column(Integer, nullable=False)
    reset_frequency_code: Mapped[str | None] = mapped_column(String(30), nullable=True)

    company: Mapped["Company"] = relationship("Company")
