"""Company VAT pro-rata history (Slice T34).

Records the provisional and final pro-rata percentages for each fiscal
year of a company using a mixed VAT regime (partial exemption).

- ``provisional_pct``: percentage used during the year for L31 deduction.
- ``final_pct``: the year-end computed actual percentage (set when the
  fiscal year is closed). A year-end adjustment JE is raised at that point
  if ``final_pct`` differs materially from ``provisional_pct``.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from seeker_accounting.db.base import Base, utcnow


class CompanyProRataHistory(Base):
    __tablename__ = "company_pro_rata_history"
    __table_args__ = (
        Index(
            "ix_company_pro_rata_history_company_year",
            "company_id",
            "fiscal_year",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Calendar or fiscal year label, e.g. 2024.
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)

    # Percentage applied during the year for L31 deduction.
    provisional_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 4), nullable=True
    )
    # Year-end actual percentage. Set when finalized at year close.
    final_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 4), nullable=True
    )
    # ID of the year-end adjustment JE (if one was raised).
    adjustment_journal_entry_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<CompanyProRataHistory company_id={self.company_id} "
            f"year={self.fiscal_year} prov={self.provisional_pct} "
            f"final={self.final_pct}>"
        )
