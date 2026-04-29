"""Slice T3 tests — line-level tax detail rows.

Verifies that the new five line-tax child tables are correctly mapped
and that ``tax_details`` back-populates to the parent line. The
migration round-trip (alembic downgrade/upgrade against the live
SQLite schema) covers DDL correctness; the existing service-level
test suite (which now writes a tax-detail row per line) covers the
write path end-to-end through the regression baseline.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from seeker_accounting.db import model_registry  # noqa: F401  (registers mappers)

from seeker_accounting.modules.sales.models.customer_quote_line import CustomerQuoteLine
from seeker_accounting.modules.sales.models.customer_quote_line_tax import (
    CustomerQuoteLineTax,
)
from seeker_accounting.modules.sales.models.sales_invoice_line import SalesInvoiceLine
from seeker_accounting.modules.sales.models.sales_invoice_line_tax import (
    SalesInvoiceLineTax,
)
from seeker_accounting.modules.sales.models.sales_order_line import SalesOrderLine
from seeker_accounting.modules.sales.models.sales_order_line_tax import (
    SalesOrderLineTax,
)
from seeker_accounting.modules.purchases.models.purchase_bill_line import (
    PurchaseBillLine,
)
from seeker_accounting.modules.purchases.models.purchase_bill_line_tax import (
    PurchaseBillLineTax,
)
from seeker_accounting.modules.purchases.models.purchase_order_line import (
    PurchaseOrderLine,
)
from seeker_accounting.modules.purchases.models.purchase_order_line_tax import (
    PurchaseOrderLineTax,
)


class TaxDetailRelationshipTests(unittest.TestCase):
    """Mapper-level checks: each line model exposes a ``tax_details``
    relationship that back-populates to the matching child class.
    """

    def test_sales_invoice_line_has_tax_details_relationship(self) -> None:
        line = SalesInvoiceLine(
            line_number=1,
            description="x",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            revenue_account_id=0,
            line_subtotal_amount=Decimal("100.00"),
            line_tax_amount=Decimal("19.25"),
            line_total_amount=Decimal("119.25"),
        )
        detail = SalesInvoiceLineTax(
            taxable_base=Decimal("100.00"),
            tax_amount=Decimal("19.25"),
            is_recoverable=None,
        )
        line.tax_details.append(detail)
        self.assertIs(detail.sales_invoice_line, line)

    def test_sales_order_line_has_tax_details_relationship(self) -> None:
        line = SalesOrderLine(
            line_number=1,
            description="x",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            line_subtotal_amount=Decimal("100.00"),
            line_tax_amount=Decimal("0.00"),
            line_total_amount=Decimal("100.00"),
        )
        detail = SalesOrderLineTax(
            taxable_base=Decimal("100.00"),
            tax_amount=Decimal("0.00"),
        )
        line.tax_details.append(detail)
        self.assertIs(detail.sales_order_line, line)

    def test_customer_quote_line_has_tax_details_relationship(self) -> None:
        line = CustomerQuoteLine(
            line_number=1,
            description="x",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            line_subtotal_amount=Decimal("100.00"),
            line_tax_amount=Decimal("0.00"),
            line_total_amount=Decimal("100.00"),
        )
        detail = CustomerQuoteLineTax(
            taxable_base=Decimal("100.00"),
            tax_amount=Decimal("0.00"),
        )
        line.tax_details.append(detail)
        self.assertIs(detail.customer_quote_line, line)

    def test_purchase_order_line_has_tax_details_relationship(self) -> None:
        line = PurchaseOrderLine(
            line_number=1,
            description="x",
            line_subtotal_amount=Decimal("100.00"),
            line_tax_amount=Decimal("19.25"),
            line_total_amount=Decimal("119.25"),
        )
        detail = PurchaseOrderLineTax(
            taxable_base=Decimal("100.00"),
            tax_amount=Decimal("19.25"),
            is_recoverable=True,
        )
        line.tax_details.append(detail)
        self.assertIs(detail.purchase_order_line, line)
        self.assertTrue(detail.is_recoverable)

    def test_purchase_bill_line_has_tax_details_relationship(self) -> None:
        line = PurchaseBillLine(
            line_number=1,
            description="x",
            line_subtotal_amount=Decimal("100.00"),
            line_tax_amount=Decimal("19.25"),
            line_total_amount=Decimal("119.25"),
        )
        detail = PurchaseBillLineTax(
            taxable_base=Decimal("100.00"),
            tax_amount=Decimal("19.25"),
            is_recoverable=False,
        )
        line.tax_details.append(detail)
        self.assertIs(detail.purchase_bill_line, line)
        self.assertFalse(detail.is_recoverable)


if __name__ == "__main__":
    unittest.main()
