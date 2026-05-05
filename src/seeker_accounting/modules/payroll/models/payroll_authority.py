"""Statutory authority registry (Phase 5 / P5.S1).

A first-class catalogue of authorities a company remits to (DGI, CNPS,
FNE, CFC, etc.) — replacing the hardcoded ``{"dgi","cnps","other"}``
string set used by the legacy remittance wizard. Authorities are
company-scoped because filing cadence, default GL liability accounts,
and even codes vary by jurisdiction.
"""
from __future__ import annotations

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class PayrollAuthority(TimestampMixin, ActiveFlagMixin, Base):
    """A statutory authority a company files / remits to.

    ``filing_cadence_code`` (service-enforced): ``monthly``, ``quarterly``,
    ``annual``, ``ad_hoc``.

    ``deadline_rule_code`` (service-enforced, advisory in P5.S1):
    ``day_of_following_month`` / ``day_of_quarter`` etc. — the actual
    deadline date is computed by the remittance engine in P5.S3.
    """

    __tablename__ = "payroll_authorities"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "code", name="uq_payroll_authorities_company_code",
        ),
        Index("ix_payroll_authorities_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    jurisdiction_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    filing_cadence_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default="monthly",
    )
    deadline_rule_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    deadline_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gl_liability_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    gl_liability_account: Mapped["Account | None"] = relationship(
        "Account", foreign_keys=[gl_liability_account_id]
    )

    mappings: Mapped[list["PayrollComponentAuthorityMap"]] = relationship(
        "PayrollComponentAuthorityMap",
        back_populates="authority",
        cascade="all, delete-orphan",
    )
