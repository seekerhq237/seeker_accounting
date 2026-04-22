from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class CustomerGroup(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "customer_groups"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        Index("ix_customer_groups_company_id", "company_id"),
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
    customers: Mapped[list["Customer"]] = relationship("Customer", back_populates="customer_group")
