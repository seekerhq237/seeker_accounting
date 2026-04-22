from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class PurchaseOrder(TimestampMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("company_id", "order_number"),
        Index("ix_purchase_orders_company_id", "company_id"),
        Index(
            "ix_purchase_orders_company_id_supplier_id_order_date",
            "company_id",
            "supplier_id",
            "order_date",
        ),
        Index("ix_purchase_orders_company_id_status_code", "company_id", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    order_number: Mapped[str] = mapped_column(String(40), nullable=False)
    supplier_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    order_date: Mapped[date] = mapped_column(Date(), nullable=False)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    currency_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("currencies.code", ondelete="RESTRICT"),
        nullable=False,
    )
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
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
    converted_to_bill_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("purchase_bills.id", ondelete="RESTRICT"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company")
    supplier: Mapped["Supplier"] = relationship("Supplier")
    contract: Mapped["Contract | None"] = relationship("Contract")
    project: Mapped["Project | None"] = relationship("Project")
    currency: Mapped["Currency"] = relationship("Currency")
    converted_to_bill: Mapped["PurchaseBill | None"] = relationship(
        "PurchaseBill",
        foreign_keys=[converted_to_bill_id],
    )
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        "PurchaseOrderLine",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderLine.line_number",
    )
