from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


BOM_STATUS_CODES: frozenset[str] = frozenset({"draft", "active", "superseded", "inactive"})
BOM_TYPE_CODES: frozenset[str] = frozenset({"kit", "assembly", "service_kit"})


class BillOfMaterial(TimestampMixin, Base):
    """Versioned recipe or kit definition for one finished item."""

    __tablename__ = "bills_of_material"
    __table_args__ = (
        UniqueConstraint("company_id", "item_id", "version", name="uq_bom_company_item_version"),
        Index("ix_bom_company_item_status", "company_id", "item_id", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    status_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    type_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default="assembly", server_default="assembly"
    )
    effective_from: Mapped[date | None] = mapped_column(Date(), nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date(), nullable=True)
    overhead_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    company: Mapped["Company"] = relationship("Company")
    item: Mapped["Item"] = relationship("Item")
    approved_by_user: Mapped["User | None"] = relationship("User")
    components: Mapped[list["BomComponent"]] = relationship(
        "BomComponent",
        back_populates="bom",
        cascade="all, delete-orphan",
        order_by="BomComponent.sequence",
    )
