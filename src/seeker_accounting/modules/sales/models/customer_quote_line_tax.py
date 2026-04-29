from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class CustomerQuoteLineTax(TimestampMixin, Base):
    __tablename__ = "customer_quote_line_taxes"
    __table_args__ = (
        Index("ix_customer_quote_line_taxes_line_id", "customer_quote_line_id"),
        Index("ix_customer_quote_line_taxes_tax_code_id", "tax_code_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_quote_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("customer_quote_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    tax_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tax_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    taxable_base: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    is_recoverable: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)

    customer_quote_line: Mapped["CustomerQuoteLine"] = relationship(
        "CustomerQuoteLine", back_populates="tax_details"
    )
    tax_code: Mapped["TaxCode | None"] = relationship("TaxCode")
