from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class Company(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tax_identifier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cnps_employer_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sector_of_operation: Mapped[str | None] = mapped_column(String(150), nullable=True)
    address_line_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country_code: Mapped[str] = mapped_column(
        String(2),
        ForeignKey("countries.code", ondelete="RESTRICT"),
        nullable=False,
    )
    base_currency_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("currencies.code", ondelete="RESTRICT"),
        nullable=False,
    )
    logo_storage_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    logo_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    logo_updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    country: Mapped["Country"] = relationship("Country")
    base_currency: Mapped["Currency"] = relationship("Currency")
    preferences: Mapped["CompanyPreference | None"] = relationship(
        "CompanyPreference",
        back_populates="company",
        uselist=False,
    )
    fiscal_defaults: Mapped["CompanyFiscalDefault | None"] = relationship(
        "CompanyFiscalDefault",
        back_populates="company",
        uselist=False,
    )
    user_access_entries: Mapped[list["UserCompanyAccess"]] = relationship(
        "UserCompanyAccess",
        back_populates="company",
    )

