"""Reason codes recorded on adjustments, scrap, count variances, and reversals.

Reason codes are mandatory on document types whose
``requires_reason_code`` flag is true and provide structured reporting on stock
losses (damage, theft, expiry, donation, etc.) without forcing free-text notes.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class InventoryReasonCode(TimestampMixin, Base):
    """Per-company reason taxonomy for inventory adjustments and counts."""

    __tablename__ = "inventory_reason_codes"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_inventory_reason_codes_company_id_code"),
        Index("ix_inventory_reason_codes_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    """One of ``damage``, ``theft``, ``expiry``, ``count_variance``, ``donation``,
    ``sample``, ``internal_use``, ``obsolescence``, ``revaluation``, ``other``,
    or any custom company-defined code."""
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)

    company: Mapped["Company"] = relationship("Company")
