from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("company_id", "project_code"),
        Index("ix_projects_company_id", "company_id"),
        Index("ix_projects_contract_id", "contract_id"),
        Index("ix_projects_customer_id", "customer_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_code: Mapped[str] = mapped_column(String(40), nullable=False)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contract_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    customer_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_type_code: Mapped[str] = mapped_column(String(20), nullable=False)
    project_manager_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    currency_code: Mapped[str | None] = mapped_column(
        String(3),
        ForeignKey("currencies.code", ondelete="RESTRICT"),
        nullable=True,
    )
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(Date(), nullable=True)
    planned_end_date: Mapped[datetime | None] = mapped_column(Date(), nullable=True)
    actual_end_date: Mapped[datetime | None] = mapped_column(Date(), nullable=True)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    budget_control_mode_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company")
    contract: Mapped["Contract | None"] = relationship("Contract")
    customer: Mapped["Customer | None"] = relationship("Customer")
    project_manager: Mapped["User | None"] = relationship("User", foreign_keys=[project_manager_user_id])
    currency: Mapped["Currency | None"] = relationship("Currency")
    created_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])
    updated_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_user_id])