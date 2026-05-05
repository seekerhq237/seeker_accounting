from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from seeker_accounting.db.base import Base, TimestampMixin


class ItemAttributeDefinition(TimestampMixin, Base):
    """Company-scoped variant attribute such as size, colour, or pack."""

    __tablename__ = "item_attribute_definitions"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "item_category_id",
            "attribute_code",
            name="uq_item_attr_defs_company_category_code",
        ),
        Index("ix_item_attr_defs_company_category", "company_id", "item_category_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    item_category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("item_categories.id", ondelete="RESTRICT"), nullable=True
    )
    attribute_code: Mapped[str] = mapped_column(String(40), nullable=False)
    attribute_name: Mapped[str] = mapped_column(String(120), nullable=False)
    allowed_values_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=True, server_default=expression.true()
    )

    company: Mapped["Company"] = relationship("Company")
    item_category: Mapped["ItemCategory | None"] = relationship("ItemCategory")
