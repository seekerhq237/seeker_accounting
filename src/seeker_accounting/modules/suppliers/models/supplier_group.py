from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class SupplierGroup(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "supplier_groups"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        Index("ix_supplier_groups_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    company: Mapped["Company"] = relationship("Company")
    suppliers: Mapped[list["Supplier"]] = relationship("Supplier", back_populates="supplier_group")
