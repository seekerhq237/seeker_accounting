from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ItemVariant(TimestampMixin, Base):
    """Mapping from a non-stock parent item to an independently costed child SKU."""

    __tablename__ = "item_variants"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "parent_item_id",
            "attribute_value_combination_hash",
            name="uq_item_variants_company_parent_hash",
        ),
        UniqueConstraint("company_id", "child_item_id", name="uq_item_variants_company_child"),
        Index("ix_item_variants_parent_item_id", "parent_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    parent_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    child_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    attribute_value_combination_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attribute_values_json: Mapped[str] = mapped_column(Text(), nullable=False)
    variant_sku_suffix: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )

    company: Mapped["Company"] = relationship("Company")
    parent_item: Mapped["Item"] = relationship("Item", foreign_keys=[parent_item_id])
    child_item: Mapped["Item"] = relationship("Item", foreign_keys=[child_item_id])
