"""Price lists and price list lines (P6 / Slice 7.1).

Supports multi-level price resolution:
  customer-specific → customer-group → company default → item list price

status: is_active flag; optional date window (valid_from / valid_to).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from seeker_accounting.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seeker_accounting.modules.inventory.models.item import Item
    from seeker_accounting.modules.inventory.models.unit_of_measure import UnitOfMeasure


class PriceList(TimestampMixin, Base):
    """A named pricing schedule for a company."""

    __tablename__ = "price_lists"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_price_lists_company_name"),
        Index("ix_price_lists_company", "company_id"),
        Index("ix_price_lists_company_active", "company_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(10), nullable=False, default="XAF")
    valid_from: Mapped[date | None] = mapped_column(Date(), nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date(), nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default=expression.false(),
    )
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=True,
        server_default=expression.true(),
    )

    lines: Mapped[list["PriceListLine"]] = relationship(
        "PriceListLine",
        back_populates="price_list",
        cascade="all, delete-orphan",
    )


class PriceListLine(TimestampMixin, Base):
    """Per-item pricing rule within a price list."""

    __tablename__ = "price_list_lines"
    __table_args__ = (
        Index("ix_price_list_lines_list_id", "price_list_id"),
        Index("ix_price_list_lines_item_id", "item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    price_list_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("price_lists.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    uom_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=True
    )
    valid_from: Mapped[date | None] = mapped_column(Date(), nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date(), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    min_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )

    price_list: Mapped["PriceList"] = relationship("PriceList", back_populates="lines")
    item: Mapped["Item"] = relationship("Item", foreign_keys=[item_id])
    uom: Mapped["UnitOfMeasure | None"] = relationship(
        "UnitOfMeasure", foreign_keys=[uom_id]
    )
