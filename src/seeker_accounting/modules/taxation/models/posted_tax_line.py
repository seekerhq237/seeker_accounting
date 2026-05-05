"""Posted tax line — immutable fact table for posted tax events.

Each row is a single, authoritative tax fact captured at the moment a
sales invoice, sales credit note, purchase bill, or purchase credit
note is posted.  The row is **append-only**: it is never updated, never
deleted in the normal edit/post workflow.  When a source document is
reversed (e.g. a credit note offsets a prior invoice), a *new* row is
inserted on the credit note's posting with **signed-negative** taxable
base and tax amount.  The net for any period therefore reduces to a
plain ``SUM(taxable_base)`` / ``SUM(tax_amount)`` over the rows in
scope — which is the canonical pattern for VAT return drafting and
DSF declarative aggregation.

Direction values:

* ``SALES``    — output VAT (sales invoices, sales credit notes)
* ``PURCHASE`` — input VAT (purchase bills, purchase credit notes)

The fact table never replaces the journal entry — it complements it
by carrying the *taxable base* (which the journal cannot represent
because the base is itself an off-ledger amount) plus the recoverable
flag and a back-link to the journal entry that posted the tax.

See ``docs/taxation_implementation_blueprint.md`` Phase 0 / Slice T11.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


# Direction codes
DIRECTION_SALES = "SALES"
DIRECTION_PURCHASE = "PURCHASE"

# Source document type codes (match journal_entries.source_document_type)
SOURCE_SALES_INVOICE = "sales_invoice"
SOURCE_SALES_CREDIT_NOTE = "sales_credit_note"
SOURCE_PURCHASE_BILL = "purchase_bill"
SOURCE_PURCHASE_CREDIT_NOTE = "purchase_credit_note"


class PostedTaxLine(Base):
    """Immutable tax fact written at posting time.

    No ``updated_at`` column — rows are append-only.
    """

    __tablename__ = "posted_tax_lines"
    __table_args__ = (
        Index("ix_posted_tax_lines_company_id", "company_id"),
        Index(
            "ix_posted_tax_lines_company_period_direction",
            "company_id",
            "fiscal_period_id",
            "direction",
        ),
        Index(
            "ix_posted_tax_lines_source",
            "company_id",
            "source_document_type",
            "source_document_id",
        ),
        Index(
            "ix_posted_tax_lines_company_tax_code",
            "company_id",
            "tax_code_id",
        ),
        Index(
            "ix_posted_tax_lines_company_tax_point_date",
            "company_id",
            "tax_point_date",
        ),
        Index(
            "ix_posted_tax_lines_company_payment_date",
            "company_id",
            "payment_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer(),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fiscal_period_id: Mapped[int] = mapped_column(
        Integer(),
        ForeignKey("fiscal_periods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    source_document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_document_id: Mapped[int] = mapped_column(Integer(), nullable=False)
    source_line_id: Mapped[int | None] = mapped_column(Integer(), nullable=True)

    journal_entry_id: Mapped[int] = mapped_column(
        Integer(),
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )

    tax_code_id: Mapped[int | None] = mapped_column(
        Integer(),
        ForeignKey("tax_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # Signed base + tax: positive on a forward post, negative on a
    # reversal post (e.g. a credit note offsetting a prior invoice).
    taxable_base: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    is_recoverable: Mapped[bool | None] = mapped_column(nullable=True)

    # Tax-point date (Slice T31) — the date that anchors VAT-period
    # filtering. Falls back to the source document date when not
    # supplied by the user.  Nullable for forward-compat with pre-T31
    # historical rows; new posts always populate it.
    tax_point_date: Mapped[date | None] = mapped_column(Date(), nullable=True)

    # T32: payment_date — set (via a separate UPDATE issued by the
    # receipt/payment allocation service) when the source invoice is
    # fully or partially paid. Used by the aggregator when the company
    # runs a cash-basis VAT scheme.  NULL for accrual-basis companies
    # (the vast majority) and for historical pre-T32 rows.
    payment_date: Mapped[date | None] = mapped_column(Date(), nullable=True)

    # T33: snapshot of the reverse-charge flag so the form can route
    # facts correctly even if the tax code's flag is later edited.
    is_reverse_charge: Mapped[bool] = mapped_column(
        nullable=False, default=False
    )

    # T42: set by draft_vat_return to record which return first claimed
    # this fact.  NULL = not yet included in any return.  This allows
    # the aggregator to pick up late-posted facts in subsequent periods.
    included_in_return_id: Mapped[int | None] = mapped_column(
        Integer(),
        ForeignKey("tax_returns.id", ondelete="SET NULL"),
        nullable=True,
    )

    # T44: multi-currency VAT fields.  When the source document is in a
    # foreign currency, these carry the reporting-currency equivalents
    # computed at posting time using the exchange rate in effect.  NULL
    # for domestic-currency documents and for pre-T44 historical rows.
    base_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    taxable_base_reporting_currency: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    tax_amount_reporting_currency: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    exchange_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    rate_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    transaction_currency_code: Mapped[str | None] = mapped_column(
        String(3), nullable=True
    )

    posted_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    posted_by_user_id: Mapped[int | None] = mapped_column(
        Integer(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Append-only: created_at only, no updated_at.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, default=utcnow
    )

    # Relationships (read-only navigation)
    tax_code = relationship("TaxCode", lazy="joined", foreign_keys=[tax_code_id])
    journal_entry = relationship(
        "JournalEntry", lazy="select", foreign_keys=[journal_entry_id]
    )
    fiscal_period = relationship(
        "FiscalPeriod", lazy="select", foreign_keys=[fiscal_period_id]
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PostedTaxLine company_id={self.company_id} "
            f"direction={self.direction} source={self.source_document_type}#"
            f"{self.source_document_id} base={self.taxable_base} "
            f"tax={self.tax_amount}>"
        )
