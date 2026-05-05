"""Component → Authority mapping (Phase 5 / P5.S1).

Defines which payroll components contribute to which authority's
remittance, on what side, and at what fraction. The remittance engine
(P5.S3) consumes this map to auto-seed remittance lines from posted
payroll runs — eliminating the manual amount-entry smell in the legacy
wizard.

Schema:

* ``side`` — one of ``employee`` / ``employer`` / ``total``. A single
  component can map to multiple authorities (e.g. CNPS contributory
  earnings feed both the employer and employee CNPS lines).
* ``fraction`` — multiplier applied to the component's posted amount.
  Defaults to ``1.0`` (use 100% of the component's amount). Values
  outside ``[0, 1]`` are allowed (e.g. for split contributions or
  jurisdictions with employer top-ups beyond 100%).
* ``line_kind`` — service-enforced free string (``contribution``,
  ``tax``, ``levy``, etc.) used to bucket mapping rows on the
  remittance form.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class PayrollComponentAuthorityMap(TimestampMixin, Base):
    """Maps a payroll component to a remittance authority."""

    __tablename__ = "payroll_component_authority_map"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "component_id",
            "authority_id",
            "side",
            name="uq_payroll_component_authority_map",
        ),
        Index(
            "ix_payroll_component_authority_map_company_id",
            "company_id",
        ),
        Index(
            "ix_payroll_component_authority_map_authority_id",
            "authority_id",
        ),
        Index(
            "ix_payroll_component_authority_map_component_id",
            "component_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    component_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("payroll_components.id", ondelete="CASCADE"),
        nullable=False,
    )
    authority_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("payroll_authorities.id", ondelete="CASCADE"),
        nullable=False,
    )
    side: Mapped[str] = mapped_column(String(20), nullable=False, default="total")
    line_kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default="contribution",
    )
    fraction: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=Decimal("1.0"),
    )

    component: Mapped["PayrollComponent"] = relationship(
        "PayrollComponent",
        foreign_keys=[component_id],
    )
    authority: Mapped["PayrollAuthority"] = relationship(
        "PayrollAuthority",
        back_populates="mappings",
        foreign_keys=[authority_id],
    )
