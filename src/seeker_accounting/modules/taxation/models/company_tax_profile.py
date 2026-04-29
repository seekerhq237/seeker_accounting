"""Company tax profile model.

One profile per company. Holds the company's tax-compliance identity:
NIU, tax center, regime, VAT liability flags, CIT profile, DSF form
selection, OTP participation and other filing-readiness facts.

Distinct from ``CompanyFiscalDefault`` (which only carries fiscal-year
boundaries) and from ``CompanyPreference`` (which is operational UI
preferences). Tax-compliance facts deserve their own bounded entity.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from seeker_accounting.db.base import Base, TimestampMixin


class CompanyTaxProfile(TimestampMixin, Base):
    __tablename__ = "company_tax_profiles"

    # company_id is the PK — exactly one tax profile per company.
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        primary_key=True,
    )

    # --- Tax identity ---------------------------------------------------

    niu: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tax_center_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    taxpayer_segment_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tax_regime_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- VAT ------------------------------------------------------------

    is_vat_liable: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    vat_effective_from: Mapped[date | None] = mapped_column(Date(), nullable=True)

    # --- Corporate income tax -------------------------------------------

    cit_rate_profile_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cit_installment_profile_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sme_qualified_flag: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

    # --- DSF ------------------------------------------------------------

    dsf_form_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dsf_submission_mode_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Operational flags ----------------------------------------------

    otp_enabled_flag: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    default_withholding_applicable_flag: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False
    )

    # --- Audit trail ----------------------------------------------------

    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ``created_at`` and ``updated_at`` come from TimestampMixin.

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return (
            f"<CompanyTaxProfile company_id={self.company_id} "
            f"regime={self.tax_regime_code} vat={self.is_vat_liable}>"
        )
