from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class Supplier(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("company_id", "supplier_code"),
        Index("ix_suppliers_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    supplier_code: Mapped[str] = mapped_column(String(40), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_group_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("supplier_groups.id", ondelete="RESTRICT"),
        nullable=True,
    )
    payment_term_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("payment_terms.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tax_identifier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country_code: Mapped[str | None] = mapped_column(
        String(2),
        ForeignKey("countries.code", ondelete="RESTRICT"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    supplier_group: Mapped["SupplierGroup | None"] = relationship("SupplierGroup", back_populates="suppliers")
    payment_term: Mapped["PaymentTerm | None"] = relationship("PaymentTerm")
    country: Mapped["Country | None"] = relationship("Country")
