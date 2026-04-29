"""Slice T2 tests — `is_tax_inclusive` document header flag plumbing.

Covers the two pieces of behavior that are unique to slice T2:

1. ``_calculate_line_totals`` honors the inclusive flag and uses
   ``TaxCalculationService.calculate_line_tax`` (gross-in / net-out for
   inclusive, net-in / gross-out for exclusive).
2. ``_resolve_effective_tax_inclusive`` follows the documented
   precedence: explicit command value > company preference default >
   False.

The service-level orchestration (header persistence, DTO exposure,
migration) is exercised end-to-end by the existing smoke scripts and
the migration round-trip already validated in the slice.
"""

from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

# Ensure mappers are configured before any ORM-aware code runs.
from seeker_accounting.db import model_registry  # noqa: F401

from seeker_accounting.modules.purchases.dto.purchase_bill_commands import (
    PurchaseBillLineCommand,
)
from seeker_accounting.modules.purchases.dto.purchase_order_commands import (
    PurchaseOrderLineCommand,
)
from seeker_accounting.modules.purchases.services.purchase_bill_service import (
    PurchaseBillService,
)
from seeker_accounting.modules.purchases.services.purchase_order_service import (
    PurchaseOrderService,
)
from seeker_accounting.modules.sales.dto.customer_quote_commands import (
    CustomerQuoteLineCommand,
)
from seeker_accounting.modules.sales.dto.sales_invoice_commands import (
    SalesInvoiceLineCommand,
)
from seeker_accounting.modules.sales.dto.sales_order_commands import (
    SalesOrderLineCommand,
)
from seeker_accounting.modules.sales.services.customer_quote_service import (
    CustomerQuoteService,
)
from seeker_accounting.modules.sales.services.sales_invoice_service import (
    SalesInvoiceService,
)
from seeker_accounting.modules.sales.services.sales_order_service import (
    SalesOrderService,
)


def _build_service(service_cls):
    """Construct a service instance with all repository factories mocked.

    The tests below only call helper methods (`_calculate_line_totals`,
    `_resolve_effective_tax_inclusive`) so the mocks never need to act
    like real repositories.
    """
    factory_kwargs = {
        "unit_of_work_factory": lambda: MagicMock(),
        "company_repository_factory": MagicMock(),
        "currency_repository_factory": MagicMock(),
        "account_repository_factory": MagicMock(),
        "tax_code_repository_factory": MagicMock(),
        "project_dimension_validation_service": MagicMock(),
        "permission_service": MagicMock(),
        "audit_service": None,
        "company_preference_repository_factory": MagicMock(),
    }
    if service_cls is SalesInvoiceService:
        factory_kwargs.update(
            customer_repository_factory=MagicMock(),
            sales_invoice_repository_factory=MagicMock(),
            sales_invoice_line_repository_factory=MagicMock(),
            customer_receipt_allocation_repository_factory=MagicMock(),
        )
    elif service_cls is SalesOrderService:
        factory_kwargs.update(
            customer_repository_factory=MagicMock(),
            sales_order_repository_factory=MagicMock(),
            sales_order_line_repository_factory=MagicMock(),
            sales_invoice_repository_factory=MagicMock(),
            sales_invoice_service=MagicMock(),
        )
    elif service_cls is CustomerQuoteService:
        factory_kwargs.update(
            customer_repository_factory=MagicMock(),
            customer_quote_repository_factory=MagicMock(),
            customer_quote_line_repository_factory=MagicMock(),
            sales_invoice_repository_factory=MagicMock(),
            sales_invoice_service=MagicMock(),
        )
    elif service_cls is PurchaseOrderService:
        factory_kwargs.update(
            supplier_repository_factory=MagicMock(),
            purchase_order_repository_factory=MagicMock(),
            purchase_order_line_repository_factory=MagicMock(),
            purchase_bill_repository_factory=MagicMock(),
            purchase_bill_service=MagicMock(),
        )
    elif service_cls is PurchaseBillService:
        factory_kwargs.update(
            supplier_repository_factory=MagicMock(),
            purchase_bill_repository_factory=MagicMock(),
            purchase_bill_line_repository_factory=MagicMock(),
            supplier_payment_allocation_repository_factory=MagicMock(),
        )
    return service_cls(**factory_kwargs)


def _percentage_tax_code(rate: str = "19.25"):
    return SimpleNamespace(
        calculation_method_code="PERCENTAGE",
        rate_percent=Decimal(rate),
    )


class CalculateLineTotalsInclusiveTests(unittest.TestCase):
    """Inclusive math: a 119.25 gross line at 19.25% should yield
    net=100.00, tax=19.25, gross=119.25.
    """

    def test_sales_invoice_inclusive(self) -> None:
        service = _build_service(SalesInvoiceService)
        command = SalesInvoiceLineCommand(
            description="Inclusive sale",
            quantity=Decimal("1"),
            unit_price=Decimal("119.25"),
            revenue_account_id=0,
        )
        net, tax, gross = service._calculate_line_totals(
            command, _percentage_tax_code(), is_tax_inclusive=True
        )
        self.assertEqual(net, Decimal("100.00"))
        self.assertEqual(tax, Decimal("19.25"))
        self.assertEqual(gross, Decimal("119.25"))

    def test_sales_invoice_exclusive(self) -> None:
        service = _build_service(SalesInvoiceService)
        command = SalesInvoiceLineCommand(
            description="Exclusive sale",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            revenue_account_id=0,
        )
        net, tax, gross = service._calculate_line_totals(
            command, _percentage_tax_code(), is_tax_inclusive=False
        )
        self.assertEqual(net, Decimal("100.00"))
        self.assertEqual(tax, Decimal("19.25"))
        self.assertEqual(gross, Decimal("119.25"))

    def test_sales_order_inclusive(self) -> None:
        service = _build_service(SalesOrderService)
        command = SalesOrderLineCommand(
            description="Inclusive order",
            quantity=Decimal("2"),
            unit_price=Decimal("59.625"),
            revenue_account_id=0,
        )
        net, tax, gross = service._calculate_line_totals(
            command, _percentage_tax_code(), is_tax_inclusive=True
        )
        self.assertEqual(gross, Decimal("119.25"))
        self.assertEqual(tax, Decimal("19.25"))
        self.assertEqual(net, Decimal("100.00"))

    def test_customer_quote_inclusive(self) -> None:
        service = _build_service(CustomerQuoteService)
        command = CustomerQuoteLineCommand(
            description="Inclusive quote",
            quantity=Decimal("1"),
            unit_price=Decimal("119.25"),
            revenue_account_id=0,
        )
        net, tax, gross = service._calculate_line_totals(
            command, _percentage_tax_code(), is_tax_inclusive=True
        )
        self.assertEqual(net, Decimal("100.00"))
        self.assertEqual(tax, Decimal("19.25"))

    def test_purchase_order_inclusive(self) -> None:
        service = _build_service(PurchaseOrderService)
        command = PurchaseOrderLineCommand(
            description="Inclusive PO",
            quantity=Decimal("1"),
            unit_cost=Decimal("119.25"),
        )
        net, tax, gross = service._calculate_line_totals(
            command, _percentage_tax_code(), is_tax_inclusive=True
        )
        self.assertEqual(net, Decimal("100.00"))
        self.assertEqual(tax, Decimal("19.25"))
        self.assertEqual(gross, Decimal("119.25"))


class ResolveEffectiveTaxInclusiveTests(unittest.TestCase):
    """Precedence: explicit command override > company preference > False."""

    def _make_service_with_pref(self, pref_value: bool | None):
        service = _build_service(SalesInvoiceService)
        if pref_value is None:
            preference = None
        else:
            preference = SimpleNamespace(tax_inclusive_default=pref_value)
        repo = MagicMock()
        repo.get_by_company_id.return_value = preference
        service._company_preference_repository_factory = lambda session: repo
        return service

    def test_command_override_true_wins_over_preference_false(self) -> None:
        service = self._make_service_with_pref(False)
        self.assertTrue(
            service._resolve_effective_tax_inclusive(MagicMock(), 1, True)
        )

    def test_command_override_false_wins_over_preference_true(self) -> None:
        service = self._make_service_with_pref(True)
        self.assertFalse(
            service._resolve_effective_tax_inclusive(MagicMock(), 1, False)
        )

    def test_preference_true_used_when_command_is_none(self) -> None:
        service = self._make_service_with_pref(True)
        self.assertTrue(
            service._resolve_effective_tax_inclusive(MagicMock(), 1, None)
        )

    def test_preference_false_used_when_command_is_none(self) -> None:
        service = self._make_service_with_pref(False)
        self.assertFalse(
            service._resolve_effective_tax_inclusive(MagicMock(), 1, None)
        )

    def test_no_preference_falls_back_to_false(self) -> None:
        service = self._make_service_with_pref(None)
        self.assertFalse(
            service._resolve_effective_tax_inclusive(MagicMock(), 1, None)
        )


if __name__ == "__main__":
    unittest.main()
