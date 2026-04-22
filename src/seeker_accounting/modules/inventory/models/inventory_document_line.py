from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class InventoryDocumentLine(Base):
    """Line items on stock receipts, issues, and adjustments."""

    __tablename__ = "inventory_document_lines"
    __table_args__ = (
        UniqueConstraint("inventory_document_id", "line_number"),
        Index("ix_inventory_document_lines_document_id", "inventory_document_id"),
        Index("ix_inventory_document_lines_item_id", "item_id"),
        Index("ix_inventory_document_lines_project_id", "project_id"),
        Index("ix_inventory_document_lines_project_job_id", "project_job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    line_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    counterparty_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    line_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transaction_uom_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=True,
    )
    uom_ratio_snapshot: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    base_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    contract_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_job_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project_jobs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_cost_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project_cost_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

    inventory_document: Mapped["InventoryDocument"] = relationship(
        "InventoryDocument", back_populates="lines"
    )
    item: Mapped["Item"] = relationship("Item")
    transaction_uom: Mapped["UnitOfMeasure | None"] = relationship(
        "UnitOfMeasure", foreign_keys=[transaction_uom_id]
    )
    counterparty_account: Mapped["Account | None"] = relationship(
        "Account", foreign_keys=[counterparty_account_id]
    )
    contract: Mapped["Contract | None"] = relationship("Contract")
    project: Mapped["Project | None"] = relationship("Project")
    project_job: Mapped["ProjectJob | None"] = relationship("ProjectJob")
    project_cost_code: Mapped["ProjectCostCode | None"] = relationship("ProjectCostCode")
