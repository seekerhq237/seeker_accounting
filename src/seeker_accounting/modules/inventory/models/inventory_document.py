from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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

from seeker_accounting.db.base import Base, TimestampMixin


class InventoryDocument(TimestampMixin, Base):
    """Header for stock receipts, issues, and adjustments."""

    __tablename__ = "inventory_documents"
    __table_args__ = (
        UniqueConstraint("company_id", "document_number"),
        Index("ix_inventory_documents_company_id", "company_id"),
        Index("ix_inventory_documents_company_id_status_code", "company_id", "status_code"),
        Index(
            "ix_inventory_documents_company_id_document_type_code",
            "company_id",
            "document_type_code",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_number: Mapped[str] = mapped_column(String(40), nullable=False)
    document_type_code: Mapped[str] = mapped_column(String(20), nullable=False)
    document_date: Mapped[date] = mapped_column(Date(), nullable=False)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    location_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reference_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    posted_journal_entry_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
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

    company: Mapped["Company"] = relationship("Company")
    location: Mapped["InventoryLocation | None"] = relationship("InventoryLocation")
    contract: Mapped["Contract | None"] = relationship("Contract")
    project: Mapped["Project | None"] = relationship("Project")
    posted_journal_entry: Mapped["JournalEntry | None"] = relationship("JournalEntry")
    posted_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[posted_by_user_id])
    lines: Mapped[list["InventoryDocumentLine"]] = relationship(
        "InventoryDocumentLine",
        back_populates="inventory_document",
        cascade="all, delete-orphan",
    )
