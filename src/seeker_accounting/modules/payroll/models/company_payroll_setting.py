from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base


class CompanyPayrollSetting(Base):
    """One-to-one payroll configuration anchor per company.

    company_id is both the primary key and the FK to companies.id.
    No surrogate PK — exactly one row per company.
    """

    __tablename__ = "company_payroll_settings"

    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    statutory_pack_version_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cnps_regime_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    accident_risk_class_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    default_pay_frequency_code: Mapped[str] = mapped_column(String(20), nullable=False)
    default_payroll_currency_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("currencies.code", ondelete="RESTRICT"),
        nullable=False,
    )
    overtime_policy_mode_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    benefit_in_kind_policy_mode_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payroll_number_prefix: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payroll_number_padding_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # P7: Segregation-of-duties enforcement.
    # When True, the user who submits a run cannot also approve or post it,
    # and the user who approves cannot also post.
    sod_strict: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default="0"
    )
    variance_threshold_percent: Mapped[object] = mapped_column(
        Numeric(5, 2), nullable=False, default=10, server_default="10.00"
    )
    variance_per_component_thresholds: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    default_payroll_currency: Mapped["Currency"] = relationship("Currency")
    updated_by_user: Mapped["User | None"] = relationship("User")
