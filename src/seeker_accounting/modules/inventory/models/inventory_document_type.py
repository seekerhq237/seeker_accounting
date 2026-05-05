"""Reference taxonomy of inventory document types.

Replaces the previous free-string ``document_type_code`` semantic. Document
types are seeded globally for every company by
:class:`~seeker_accounting.modules.inventory.services.inventory_reference_data_service.InventoryReferenceDataService`
when a company is initialised, and any new types are managed by services rather
than ad-hoc UI writes.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class InventoryDocumentType(TimestampMixin, Base):
    """Per-company reference row describing the behaviour of a document type."""

    __tablename__ = "inventory_document_types"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_inventory_document_types_company_id_code"),
        Index("ix_inventory_document_types_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    direction_sign: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    """+1 for stock increase types (receipt, transfer in, count gain, etc.),
    -1 for stock decrease types, 0 for transfer-headers and revaluations."""
    is_transfer: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    is_reversal: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    requires_unit_cost_on_line: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False
    )
    requires_reason_code: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    posts_to_inventory_account: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)

    company: Mapped["Company"] = relationship("Company")
