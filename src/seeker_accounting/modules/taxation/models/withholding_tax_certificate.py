"""Withholding tax certificate — Phase 5 / Slice T13.

A standalone register that captures the withholding-tax events a
business must track for compliance:

* **INBOUND** — certificates received from a customer (often a
  public-sector body or large taxpayer) who withheld tax on a payment
  due to us. The withheld amount is a receivable from the tax
  authority and must be available to offset our own liabilities.

* **OUTBOUND** — certificates we issue when *we* withhold tax on a
  payment to a counterparty (typical Cameroon cases: TSR on
  non-resident services, ``précompte`` on rent paid to landlords,
  AIT on certain supplier categories). The amount becomes a
  liability owed to the tax authority and the certificate is the
  legal proof the supplier needs.

The register is intentionally loose about the linked source document
and counterparty. Many real certificates are reconciliation-only and
have no Seeker-side document; counterparty data is snapshot at
creation so the certificate stays valid even if the customer or
supplier record is later edited or deactivated.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


from seeker_accounting.db.base import Base, TimestampMixin


# Direction codes
DIRECTION_INBOUND = "INBOUND"
DIRECTION_OUTBOUND = "OUTBOUND"

# Counterparty kind codes
COUNTERPARTY_CUSTOMER = "CUSTOMER"
COUNTERPARTY_SUPPLIER = "SUPPLIER"
COUNTERPARTY_OTHER = "OTHER"

# Status codes
STATUS_ISSUED = "ISSUED"
STATUS_RECEIVED = "RECEIVED"
STATUS_VOIDED = "VOIDED"


class WithholdingTaxCertificate(TimestampMixin, Base):
    __tablename__ = "withholding_tax_certificates"
    __table_args__ = (
        Index(
            "ix_withholding_tax_certificates_company_id",
            "company_id",
        ),
        Index(
            "ix_withholding_tax_certificates_company_period",
            "company_id",
            "fiscal_period_id",
        ),
        Index(
            "ix_withholding_tax_certificates_company_direction",
            "company_id",
            "direction",
        ),
        Index(
            "ix_withholding_tax_certificates_tax_code_id",
            "tax_code_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fiscal_period_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("fiscal_periods.id", ondelete="RESTRICT"),
        nullable=True,
    )
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    counterparty_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    counterparty_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counterparty_name: Mapped[str] = mapped_column(String(200), nullable=False)
    counterparty_niu: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tax_code_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tax_codes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    certificate_number: Mapped[str] = mapped_column(String(80), nullable=False)
    certificate_date: Mapped[date] = mapped_column(Date(), nullable=False)
    source_document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    taxable_base: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    evidence_attachment_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    recorded_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tax_code: Mapped["TaxCode"] = relationship("TaxCode")
