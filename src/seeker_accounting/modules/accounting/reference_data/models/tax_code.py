from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class TaxCode(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "tax_codes"
    __table_args__ = (
        UniqueConstraint("company_id", "code", "effective_from"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    tax_type_code: Mapped[str] = mapped_column(String(50), nullable=False)
    calculation_method_code: Mapped[str] = mapped_column(String(50), nullable=False)
    rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 4), nullable=True)
    is_recoverable: Mapped[bool | None] = mapped_column(nullable=True)
    effective_from: Mapped[Date] = mapped_column(Date(), nullable=False)
    effective_to: Mapped[Date | None] = mapped_column(Date(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
