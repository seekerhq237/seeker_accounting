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
    has_cac: Mapped[bool] = mapped_column(nullable=False, default=False)
    base_rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    cac_rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    exemption_kind: Mapped[str | None] = mapped_column(String(30), nullable=True)
    return_box_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Slice T30: orthogonal flags that drive DGI line bucketing alongside
    # ``exemption_kind`` / ``return_box_code``.  ``is_export`` short-circuits
    # taxable sales into L21 (zero-rated exports).  ``is_imported_service``
    # pushes purchases of foreign services into L29 (reverse-charge ready
    # in T33).  Both default to ``False`` so existing tax codes are
    # unaffected.
    is_imported_service: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_export: Mapped[bool] = mapped_column(nullable=False, default=False)
    # Slice T33: when True, purchasing this service triggers a simultaneous
    # output-VAT fact row (self-assessed) alongside the input-VAT row.
    # The two rows net to zero for a fully-recoverable entity; for a
    # partially-exempt entity the pro-rata (T34) still applies to the
    # input side only.
    is_reverse_charge: Mapped[bool] = mapped_column(nullable=False, default=False)
    effective_from: Mapped[Date] = mapped_column(Date(), nullable=False)
    effective_to: Mapped[Date | None] = mapped_column(Date(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
