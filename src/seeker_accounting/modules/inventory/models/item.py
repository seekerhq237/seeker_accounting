from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
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


class Item(TimestampMixin, Base):
    """Item master for stock, non-stock, and service items."""

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("company_id", "item_code"),
        Index("ix_items_company_id", "company_id"),
        Index("ix_items_company_id_item_type_code", "company_id", "item_type_code"),
        Index("ix_items_company_id_is_active", "company_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_code: Mapped[str] = mapped_column(String(40), nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    item_type_code: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_of_measure_code: Mapped[str] = mapped_column(String(20), nullable=False, default="UNIT")
    unit_of_measure_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=True,
    )
    item_category_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("item_categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    inventory_cost_method_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    inventory_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cogs_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    expense_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    revenue_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    purchase_tax_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tax_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    sales_tax_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tax_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reorder_level_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=True,
        server_default=expression.true(),
    )

    company: Mapped["Company"] = relationship("Company")
    unit_of_measure: Mapped["UnitOfMeasure | None"] = relationship(
        "UnitOfMeasure", foreign_keys=[unit_of_measure_id]
    )
    item_category: Mapped["ItemCategory | None"] = relationship(
        "ItemCategory", foreign_keys=[item_category_id]
    )
    inventory_account: Mapped["Account | None"] = relationship(
        "Account", foreign_keys=[inventory_account_id]
    )
    cogs_account: Mapped["Account | None"] = relationship(
        "Account", foreign_keys=[cogs_account_id]
    )
    expense_account: Mapped["Account | None"] = relationship(
        "Account", foreign_keys=[expense_account_id]
    )
    revenue_account: Mapped["Account | None"] = relationship(
        "Account", foreign_keys=[revenue_account_id]
    )
