from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ProjectCommitment(TimestampMixin, Base):
    __tablename__ = "project_commitments"
    __table_args__ = (
        UniqueConstraint("company_id", "commitment_number", name="uq_project_commitments_company_number"),
        Index("ix_project_commitments_company_project_status", "company_id", "project_id", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False,
    )
    commitment_number: Mapped[str] = mapped_column(String(40), nullable=False)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False,
    )
    supplier_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True,
    )
    commitment_type_code: Mapped[str] = mapped_column(String(30), nullable=False)
    commitment_date: Mapped[date] = mapped_column(Date, nullable=False)
    required_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False,
    )
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default="0")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    # Relationships
    company = relationship("Company", foreign_keys=[company_id], lazy="select")
    project = relationship("Project", foreign_keys=[project_id], lazy="select")
    supplier = relationship("Supplier", foreign_keys=[supplier_id], lazy="select")
    currency = relationship("Currency", foreign_keys=[currency_code], lazy="select")
    approved_by_user = relationship("User", foreign_keys=[approved_by_user_id], lazy="select")
    lines: Mapped[list["ProjectCommitmentLine"]] = relationship(
        "ProjectCommitmentLine", back_populates="commitment", lazy="select",
        cascade="all, delete-orphan", order_by="ProjectCommitmentLine.line_number",
    )
