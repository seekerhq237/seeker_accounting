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
    """Header for stock receipts, issues, transfers, and adjustments.

    Phase 0 / Slice 1.4 introduces:

    * ``reason_code_id`` linking adjustments / scrap / count-variance documents
      to a structured taxonomy.
    * ``source_module_code``, ``source_document_type``, ``source_document_id``
      to make the cross-module traceability graph (sales invoice, purchase bill,
      stock count, transfer, production) first-class instead of free-text.

    The legacy ``total_value`` column has been removed: the total is now
    computed from the document lines on demand (no master-table balance
    shortcuts per CLAUDE.md §6).
    """

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
        Index(
            "ix_inventory_documents_company_id_source",
            "company_id",
            "source_module_code",
            "source_document_type",
            "source_document_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_number: Mapped[str] = mapped_column(String(40), nullable=False)
    document_type_code: Mapped[str] = mapped_column(String(40), nullable=False)
    document_date: Mapped[date] = mapped_column(Date(), nullable=False)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    location_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reason_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_reason_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reference_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source_module_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_document_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cancellation_reason_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_reason_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reversal_of_document_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_documents.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reversal_document_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_documents.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reverse_reason_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_reason_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    reversed_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reversing_journal_entry_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )
    from_location_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    to_location_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    transfer_status_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
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
    stock_count_session_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("stock_count_sessions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    bom_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("bills_of_material.id", ondelete="RESTRICT"),
        nullable=True,
    )
    production_order_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("production_orders.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # P2 / Slice 3.3 – GRN traceability back to source PO
    purchase_order_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # P5 / Slice 6.2 – customs and multi-currency import fields
    customs_declaration_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    bill_of_lading_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    port_entry_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    foreign_currency_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    foreign_unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    foreign_exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    location: Mapped["InventoryLocation | None"] = relationship(
        "InventoryLocation", foreign_keys=[location_id]
    )
    from_location: Mapped["InventoryLocation | None"] = relationship(
        "InventoryLocation", foreign_keys=[from_location_id]
    )
    to_location: Mapped["InventoryLocation | None"] = relationship(
        "InventoryLocation", foreign_keys=[to_location_id]
    )
    reason_code: Mapped["InventoryReasonCode | None"] = relationship(
        "InventoryReasonCode", foreign_keys=[reason_code_id]
    )
    cancellation_reason_code: Mapped["InventoryReasonCode | None"] = relationship(
        "InventoryReasonCode", foreign_keys=[cancellation_reason_code_id]
    )
    reverse_reason_code: Mapped["InventoryReasonCode | None"] = relationship(
        "InventoryReasonCode", foreign_keys=[reverse_reason_code_id]
    )
    contract: Mapped["Contract | None"] = relationship("Contract")
    project: Mapped["Project | None"] = relationship("Project")
    posted_journal_entry: Mapped["JournalEntry | None"] = relationship(
        "JournalEntry", foreign_keys=[posted_journal_entry_id]
    )
    reversing_journal_entry: Mapped["JournalEntry | None"] = relationship(
        "JournalEntry", foreign_keys=[reversing_journal_entry_id]
    )
    posted_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[posted_by_user_id])
    submitted_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[submitted_by_user_id]
    )
    approved_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[approved_by_user_id]
    )
    cancelled_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[cancelled_by_user_id]
    )
    reversed_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[reversed_by_user_id]
    )
    reversal_of_document: Mapped["InventoryDocument | None"] = relationship(
        "InventoryDocument", remote_side=[id], foreign_keys=[reversal_of_document_id]
    )
    reversal_document: Mapped["InventoryDocument | None"] = relationship(
        "InventoryDocument", remote_side=[id], foreign_keys=[reversal_document_id]
    )
    stock_count_session: Mapped["StockCountSession | None"] = relationship(
        "StockCountSession", foreign_keys=[stock_count_session_id]
    )
    bill_of_material: Mapped["BillOfMaterial | None"] = relationship(
        "BillOfMaterial", foreign_keys=[bom_id]
    )
    production_order: Mapped["ProductionOrder | None"] = relationship(
        "ProductionOrder", foreign_keys=[production_order_id]
    )
    lines: Mapped[list["InventoryDocumentLine"]] = relationship(
        "InventoryDocumentLine",
        back_populates="inventory_document",
        cascade="all, delete-orphan",
    )

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def total_value(self) -> Decimal:
        """Sum of absolute ``line_amount`` values across the document's lines.

        Replaces the legacy stored ``total_value`` column (CLAUDE.md §6 — no
        master-table balance shortcuts). Returns ``Decimal('0.00')`` when no
        lines have a computed amount.
        """

        total = Decimal("0.00")
        for line in self.lines or ():
            if line.line_amount is not None:
                total += abs(line.line_amount)
        return total
