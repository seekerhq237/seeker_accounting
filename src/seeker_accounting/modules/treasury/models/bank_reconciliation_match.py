from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class BankReconciliationMatch(Base):
    __tablename__ = "bank_reconciliation_matches"
    __table_args__ = (
        UniqueConstraint(
            "reconciliation_session_id",
            "bank_statement_line_id",
            "match_entity_type",
            "match_entity_id",
        ),
        Index(
            "ix_bank_reconciliation_matches_session_id",
            "reconciliation_session_id",
        ),
        Index(
            "ix_bank_reconciliation_matches_statement_line_id",
            "bank_statement_line_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reconciliation_session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("bank_reconciliation_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bank_statement_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("bank_statement_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    match_entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    match_entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

    reconciliation_session: Mapped["BankReconciliationSession"] = relationship(
        "BankReconciliationSession", back_populates="matches"
    )
    bank_statement_line: Mapped["BankStatementLine"] = relationship("BankStatementLine")
