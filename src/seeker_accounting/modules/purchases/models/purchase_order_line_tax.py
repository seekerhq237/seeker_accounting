from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class PurchaseOrderLineTax(TimestampMixin, Base):
    __tablename__ = "purchase_order_line_taxes"
    __table_args__ = (
        Index("ix_purchase_order_line_taxes_line_id", "purchase_order_line_id"),
        Index("ix_purchase_order_line_taxes_tax_code_id", "tax_code_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_order_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("purchase_order_lines.id", ondelete="CASCADE"),
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

    purchase_order_line: Mapped["PurchaseOrderLine"] = relationship(
        "PurchaseOrderLine", back_populates="tax_details"
    )
    tax_code: Mapped["TaxCode | None"] = relationship("TaxCode")
