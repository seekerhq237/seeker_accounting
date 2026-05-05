"""VAT Exception Report Service (T41).

Scans operational documents within a date range and surfaces potential
VAT compliance issues in three buckets:

1. **DRAFT_DOCUMENT** — unposted sales invoices or purchase bills dated
   within the period that would be missed by the return if filed now.
2. **FOREIGN_CURRENCY** — posted documents whose ``currency_code`` is
   not the company's functional currency (non-XAF / non-local).  The
   VAT base must be converted and any rounding may cause discrepancies.
3. **MISSING_TAX_CODE** — posted document lines with a non-zero amount
   but no tax code assigned (possible mis-classification).

The service intentionally reads across the sales and purchases modules
via direct ORM queries.  It does NOT post or mutate anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice

_PERMISSION_VIEW = "taxation.returns.view"

# Functional (local) currency code used in Cameroon.
_LOCAL_CURRENCY = "XAF"


@dataclass(frozen=True)
class VATExceptionItem:
    """A single compliance exception identified by the report."""

    exception_type: str     # "DRAFT_DOCUMENT" | "FOREIGN_CURRENCY" | "MISSING_TAX_CODE"
    document_type: str      # "SALES_INVOICE" | "PURCHASE_BILL"
    document_id: int
    document_number: str
    document_date: date
    total_amount: Decimal
    detail: str


class VATExceptionReportService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        permission_service: PermissionService,
    ) -> None:
        self._uow_factory = uow_factory
        self._permission_service = permission_service

    def list_exceptions(
        self,
        company_id: int,
        period_start: date,
        period_end: date,
    ) -> list[VATExceptionItem]:
        """Return all VAT exceptions within the given date window."""
        self._permission_service.require_permission(_PERMISSION_VIEW)
        with self._uow_factory() as uow:
            results: list[VATExceptionItem] = []
            results.extend(
                self._draft_sales_invoices(uow.session, company_id, period_start, period_end)
            )
            results.extend(
                self._draft_purchase_bills(uow.session, company_id, period_start, period_end)
            )
            results.extend(
                self._foreign_currency_sales_invoices(uow.session, company_id, period_start, period_end)
            )
            results.extend(
                self._foreign_currency_purchase_bills(uow.session, company_id, period_start, period_end)
            )
            results.extend(
                self._missing_tax_code_sales_invoices(uow.session, company_id, period_start, period_end)
            )
            results.extend(
                self._missing_tax_code_purchase_bills(uow.session, company_id, period_start, period_end)
            )
            return results

    # ── Bucket 1: Draft documents ──────────────────────────────────

    def _draft_sales_invoices(
        self,
        session: Session,
        company_id: int,
        period_start: date,
        period_end: date,
    ) -> list[VATExceptionItem]:
        """Find sales invoices in DRAFT status dated within the period."""
        stmt = select(SalesInvoice).where(
            SalesInvoice.company_id == company_id,
            SalesInvoice.status_code.in_(["draft", "DRAFT"]),
            SalesInvoice.invoice_date >= period_start,
            SalesInvoice.invoice_date <= period_end,
        ).order_by(SalesInvoice.invoice_date)
        invoices = list(session.scalars(stmt))
        return [
            VATExceptionItem(
                exception_type="DRAFT_DOCUMENT",
                document_type="SALES_INVOICE",
                document_id=inv.id,
                document_number=inv.invoice_number,
                document_date=inv.invoice_date,
                total_amount=inv.total_amount,
                detail="Invoice is unposted — not included in VAT return.",
            )
            for inv in invoices
        ]

    def _draft_purchase_bills(
        self,
        session: Session,
        company_id: int,
        period_start: date,
        period_end: date,
    ) -> list[VATExceptionItem]:
        """Find purchase bills in DRAFT status dated within the period."""
        try:
            from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
        except ImportError:
            return []

        stmt = select(PurchaseBill).where(
            PurchaseBill.company_id == company_id,
            PurchaseBill.status_code.in_(["draft", "DRAFT"]),
            PurchaseBill.bill_date >= period_start,
            PurchaseBill.bill_date <= period_end,
        ).order_by(PurchaseBill.bill_date)
        bills = list(session.scalars(stmt))
        return [
            VATExceptionItem(
                exception_type="DRAFT_DOCUMENT",
                document_type="PURCHASE_BILL",
                document_id=bill.id,
                document_number=bill.bill_number,
                document_date=bill.bill_date,
                total_amount=bill.total_amount,
                detail="Bill is unposted — input VAT not yet recoverable.",
            )
            for bill in bills
        ]

    # ── Bucket 2: Foreign-currency documents ────────────────────────

    def _foreign_currency_sales_invoices(
        self,
        session: Session,
        company_id: int,
        period_start: date,
        period_end: date,
    ) -> list[VATExceptionItem]:
        """Find posted sales invoices not in the local functional currency."""
        stmt = select(SalesInvoice).where(
            SalesInvoice.company_id == company_id,
            SalesInvoice.status_code.in_(["posted", "POSTED"]),
            SalesInvoice.currency_code != _LOCAL_CURRENCY,
            SalesInvoice.invoice_date >= period_start,
            SalesInvoice.invoice_date <= period_end,
        ).order_by(SalesInvoice.invoice_date)
        invoices = list(session.scalars(stmt))
        return [
            VATExceptionItem(
                exception_type="FOREIGN_CURRENCY",
                document_type="SALES_INVOICE",
                document_id=inv.id,
                document_number=inv.invoice_number,
                document_date=inv.invoice_date,
                total_amount=inv.total_amount,
                detail=f"Invoice is in {inv.currency_code} — verify VAT base conversion.",
            )
            for inv in invoices
        ]

    def _foreign_currency_purchase_bills(
        self,
        session: Session,
        company_id: int,
        period_start: date,
        period_end: date,
    ) -> list[VATExceptionItem]:
        """Find posted purchase bills not in the local functional currency."""
        try:
            from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
        except ImportError:
            return []

        stmt = select(PurchaseBill).where(
            PurchaseBill.company_id == company_id,
            PurchaseBill.status_code.in_(["posted", "POSTED"]),
            PurchaseBill.currency_code != _LOCAL_CURRENCY,
            PurchaseBill.bill_date >= period_start,
            PurchaseBill.bill_date <= period_end,
        ).order_by(PurchaseBill.bill_date)
        bills = list(session.scalars(stmt))
        return [
            VATExceptionItem(
                exception_type="FOREIGN_CURRENCY",
                document_type="PURCHASE_BILL",
                document_id=bill.id,
                document_number=bill.bill_number,
                document_date=bill.bill_date,
                total_amount=bill.total_amount,
                detail=f"Bill is in {bill.currency_code} — verify VAT base conversion.",
            )
            for bill in bills
        ]

    # ── Bucket 3: Missing tax code on posted lines ───────────────────

    def _missing_tax_code_sales_invoices(
        self,
        session: Session,
        company_id: int,
        period_start: date,
        period_end: date,
    ) -> list[VATExceptionItem]:
        """Find posted invoices where at least one line has no tax code."""
        try:
            from seeker_accounting.modules.sales.models.sales_invoice_line import SalesInvoiceLine
        except ImportError:
            return []

        sub = (
            select(SalesInvoiceLine.sales_invoice_id)
            .where(
                SalesInvoiceLine.tax_code_id.is_(None),
                SalesInvoiceLine.unit_price > Decimal("0"),
            )
        )
        stmt = (
            select(SalesInvoice)
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.status_code.in_(["posted", "POSTED"]),
                SalesInvoice.invoice_date >= period_start,
                SalesInvoice.invoice_date <= period_end,
                SalesInvoice.id.in_(sub),
            )
            .order_by(SalesInvoice.invoice_date)
        )
        invoices = list(session.scalars(stmt))
        return [
            VATExceptionItem(
                exception_type="MISSING_TAX_CODE",
                document_type="SALES_INVOICE",
                document_id=inv.id,
                document_number=inv.invoice_number,
                document_date=inv.invoice_date,
                total_amount=inv.total_amount,
                detail="One or more lines have no tax code — VAT may be under-reported.",
            )
            for inv in invoices
        ]

    def _missing_tax_code_purchase_bills(
        self,
        session: Session,
        company_id: int,
        period_start: date,
        period_end: date,
    ) -> list[VATExceptionItem]:
        """Find posted bills where at least one line has no tax code."""
        try:
            from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
            from seeker_accounting.modules.purchases.models.purchase_bill_line import PurchaseBillLine
        except ImportError:
            return []

        sub = (
            select(PurchaseBillLine.purchase_bill_id)
            .where(
                PurchaseBillLine.tax_code_id.is_(None),
                PurchaseBillLine.line_subtotal_amount > Decimal("0"),
            )
        )
        stmt = (
            select(PurchaseBill)
            .where(
                PurchaseBill.company_id == company_id,
                PurchaseBill.status_code.in_(["posted", "POSTED"]),
                PurchaseBill.bill_date >= period_start,
                PurchaseBill.bill_date <= period_end,
                PurchaseBill.id.in_(sub),
            )
            .order_by(PurchaseBill.bill_date)
        )
        bills = list(session.scalars(stmt))
        return [
            VATExceptionItem(
                exception_type="MISSING_TAX_CODE",
                document_type="PURCHASE_BILL",
                document_id=bill.id,
                document_number=bill.bill_number,
                document_date=bill.bill_date,
                total_amount=bill.total_amount,
                detail="One or more lines have no tax code — input VAT may be overstated.",
            )
            for bill in bills
        ]
