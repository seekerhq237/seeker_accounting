from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class SalesInvoiceLineTax(TimestampMixin, Base):
    """One tax breakdown row for a sales invoice line.

    A line currently records a single aggregate tax amount; this child
    table is the canonical per-tax-code breakdown that downstream
    obligations / returns / DSF reporting reads from. Today the system
    writes one row per line (mirroring the legacy single-tax shape);
    the schema admits multiple rows so multi-tax-per-line authoring can
    be added without another migration.
    """

    __tablename__ = "sales_invoice_line_taxes"
    __table_args__ = (
        Index("ix_sales_invoice_line_taxes_line_id", "sales_invoice_line_id"),
        Index("ix_sales_invoice_line_taxes_tax_code_id", "tax_code_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sales_invoice_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sales_invoice_lines.id", ondelete="CASCADE"),
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

    sales_invoice_line: Mapped["SalesInvoiceLine"] = relationship(
        "SalesInvoiceLine", back_populates="tax_details"
    )
    tax_code: Mapped["TaxCode | None"] = relationship("TaxCode")
