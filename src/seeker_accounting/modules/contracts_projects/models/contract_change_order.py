from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ContractChangeOrder(TimestampMixin, Base):
    __tablename__ = "contract_change_orders"
    __table_args__ = (
        UniqueConstraint("company_id", "change_order_number"),
        Index("ix_contract_change_orders_company_id", "company_id"),
        Index("ix_contract_change_orders_contract_id", "contract_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    contract_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    change_order_number: Mapped[str] = mapped_column(String(40), nullable=False)
    change_order_date: Mapped[datetime] = mapped_column(Date(), nullable=False)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    change_type_code: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    contract_amount_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    days_extension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_date: Mapped[datetime | None] = mapped_column(Date(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company")
    contract: Mapped["Contract"] = relationship("Contract")
    approved_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_user_id])
