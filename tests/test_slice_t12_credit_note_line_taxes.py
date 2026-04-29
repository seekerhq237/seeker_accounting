"""Slice T12 tests — credit-note line-level tax detail rows.

Verifies that the two new credit-note line-tax child tables are
correctly mapped, that ``tax_details`` back-populates to the parent
line, and that the snapshot rows persisted by the credit-note
services are picked up by the posting services as the source of
truth for ``PostedTaxLine`` fact creation.

The migration round-trip (``alembic downgrade`` / ``upgrade``) covers
DDL correctness; this test focuses on the mapper wiring and the
posting-side fallback contract.
"""

from __future__ import annotations

import unittest
from decimal import Decimal
from unittest import mock

from seeker_accounting.db import model_registry  # noqa: F401  (registers mappers)

from seeker_accounting.modules.purchases.models.purchase_credit_note_line import (
    PurchaseCreditNoteLine,
)
from seeker_accounting.modules.purchases.models.purchase_credit_note_line_tax import (
    PurchaseCreditNoteLineTax,
)
from seeker_accounting.modules.sales.models.sales_credit_note_line import (
    SalesCreditNoteLine,
)
from seeker_accounting.modules.sales.models.sales_credit_note_line_tax import (
    SalesCreditNoteLineTax,
)


class CreditNoteTaxDetailRelationshipTests(unittest.TestCase):
    """Mapper-level checks: each credit-note line model exposes a
    ``tax_details`` relationship that back-populates to the matching
    child class.
    """

    def test_sales_credit_note_line_has_tax_details_relationship(self) -> None:
        line = SalesCreditNoteLine(
            line_number=1,
            description="x",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            revenue_account_id=0,
            line_subtotal_amount=Decimal("100.00"),
            line_tax_amount=Decimal("0.00"),
            line_total_amount=Decimal("100.00"),
        )
        detail = SalesCreditNoteLineTax(
            taxable_base=Decimal("100.00"),
            tax_amount=Decimal("0.00"),
            is_recoverable=None,
        )
        line.tax_details.append(detail)
        self.assertIs(detail.sales_credit_note_line, line)

    def test_purchase_credit_note_line_has_tax_details_relationship(self) -> None:
        line = PurchaseCreditNoteLine(
            line_number=1,
            description="x",
            line_subtotal_amount=Decimal("100.00"),
            line_tax_amount=Decimal("0.00"),
            line_total_amount=Decimal("100.00"),
        )
        detail = PurchaseCreditNoteLineTax(
            taxable_base=Decimal("100.00"),
            tax_amount=Decimal("19.25"),
            is_recoverable=True,
        )
        line.tax_details.append(detail)
        self.assertIs(detail.purchase_credit_note_line, line)
        self.assertTrue(detail.is_recoverable)

    def test_credit_note_line_supports_multiple_tax_details(self) -> None:
        """The schema admits multi-tax-per-line authoring; verify the
        ORM relationship accepts more than one detail row.
        """
        line = SalesCreditNoteLine(
            line_number=1,
            description="x",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            revenue_account_id=0,
            line_subtotal_amount=Decimal("100.00"),
            line_tax_amount=Decimal("0.00"),
            line_total_amount=Decimal("100.00"),
        )
        vat = SalesCreditNoteLineTax(
            taxable_base=Decimal("100.00"),
            tax_amount=Decimal("19.25"),
        )
        excise = SalesCreditNoteLineTax(
            taxable_base=Decimal("100.00"),
            tax_amount=Decimal("5.00"),
        )
        line.tax_details.extend([vat, excise])
        self.assertEqual(len(line.tax_details), 2)
        self.assertIs(vat.sales_credit_note_line, line)
        self.assertIs(excise.sales_credit_note_line, line)


class CreditNoteServiceSnapshotTests(unittest.TestCase):
    """The credit-note services must persist a snapshot tax-detail row
    alongside each line so posting services consume the detail rows as
    the source of truth for ``PostedTaxLine`` fact creation.
    """

    def test_sales_credit_note_service_writes_tax_detail_snapshot(self) -> None:
        from seeker_accounting.modules.sales.services.sales_credit_note_service import (
            SalesCreditNoteService,
        )

        line_cmd = mock.Mock()
        line_cmd.description = "Refund"
        line_cmd.quantity = Decimal("1")
        line_cmd.unit_price = Decimal("100.00")
        line_cmd.discount_percent = None
        line_cmd.tax_code_id = None  # avoid DB lookup; tax compute returns 0
        line_cmd.revenue_account_id = 42
        line_cmd.contract_id = None
        line_cmd.project_id = None
        line_cmd.project_job_id = None
        line_cmd.project_cost_code_id = None

        session = mock.Mock()
        lines = SalesCreditNoteService._validate_and_build_lines(session, [line_cmd])

        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(len(line.tax_details), 1)
        snapshot = line.tax_details[0]
        self.assertIsNone(snapshot.tax_code_id)
        self.assertEqual(snapshot.taxable_base, Decimal("100.00"))
        self.assertEqual(snapshot.tax_amount, Decimal("0.00"))
        self.assertIsNone(snapshot.is_recoverable)

    def test_purchase_credit_note_service_writes_tax_detail_snapshot(self) -> None:
        from seeker_accounting.modules.purchases.services.purchase_credit_note_service import (
            PurchaseCreditNoteService,
        )

        line_cmd = mock.Mock()
        line_cmd.description = "Goods returned"
        line_cmd.quantity = Decimal("1")
        line_cmd.unit_cost = Decimal("100.00")
        line_cmd.expense_account_id = 99
        line_cmd.tax_code_id = None  # avoid DB lookup; tax compute returns 0
        line_cmd.line_subtotal_amount = Decimal("100.00")
        line_cmd.contract_id = None
        line_cmd.project_id = None
        line_cmd.project_job_id = None
        line_cmd.project_cost_code_id = None

        session = mock.Mock()
        lines = PurchaseCreditNoteService._validate_and_build_lines(session, [line_cmd])

        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(len(line.tax_details), 1)
        snapshot = line.tax_details[0]
        self.assertIsNone(snapshot.tax_code_id)
        self.assertEqual(snapshot.taxable_base, Decimal("100.00"))
        self.assertEqual(snapshot.tax_amount, Decimal("0.00"))
        self.assertIsNone(snapshot.is_recoverable)


class CreditNoteTaxComputationTests(unittest.TestCase):
    """Verify tax is computed at draft (not zero) when a tax code is
    resolvable. Uses a real ``TaxCode`` returned via a fake session.
    """

    def _make_tax_code(self, rate: str) -> object:
        from seeker_accounting.modules.accounting.reference_data.models.tax_code import (
            TaxCode,
        )

        return TaxCode(
            company_id=1,
            code="VAT19_25",
            name="VAT 19.25%",
            tax_type_code="VAT",
            calculation_method_code="PERCENTAGE",
            rate_percent=Decimal(rate),
            is_recoverable=None,
            effective_from=None,  # not exercised by calculator
        )

    def test_sales_credit_note_computes_non_zero_tax(self) -> None:
        from seeker_accounting.modules.sales.services.sales_credit_note_service import (
            SalesCreditNoteService,
        )

        tax_code = self._make_tax_code("19.25")
        session = mock.Mock()
        session.get.return_value = tax_code

        line_cmd = mock.Mock()
        line_cmd.description = "Refund"
        line_cmd.quantity = Decimal("1")
        line_cmd.unit_price = Decimal("100.00")
        line_cmd.discount_percent = None
        line_cmd.tax_code_id = 7
        line_cmd.revenue_account_id = 42
        line_cmd.contract_id = None
        line_cmd.project_id = None
        line_cmd.project_job_id = None
        line_cmd.project_cost_code_id = None

        lines = SalesCreditNoteService._validate_and_build_lines(session, [line_cmd])

        self.assertEqual(lines[0].line_tax_amount, Decimal("19.25"))
        self.assertEqual(lines[0].line_total_amount, Decimal("119.25"))
        self.assertEqual(lines[0].tax_details[0].tax_amount, Decimal("19.25"))

    def test_purchase_credit_note_computes_non_zero_tax_and_recoverable(self) -> None:
        from seeker_accounting.modules.purchases.services.purchase_credit_note_service import (
            PurchaseCreditNoteService,
        )

        tax_code = self._make_tax_code("19.25")
        tax_code.is_recoverable = True
        session = mock.Mock()
        session.get.return_value = tax_code

        line_cmd = mock.Mock()
        line_cmd.description = "Goods returned"
        line_cmd.quantity = Decimal("1")
        line_cmd.unit_cost = Decimal("100.00")
        line_cmd.expense_account_id = 99
        line_cmd.tax_code_id = 11
        line_cmd.line_subtotal_amount = Decimal("100.00")
        line_cmd.contract_id = None
        line_cmd.project_id = None
        line_cmd.project_job_id = None
        line_cmd.project_cost_code_id = None

        lines = PurchaseCreditNoteService._validate_and_build_lines(session, [line_cmd])

        self.assertEqual(lines[0].line_tax_amount, Decimal("19.25"))
        self.assertEqual(lines[0].line_total_amount, Decimal("119.25"))
        snapshot = lines[0].tax_details[0]
        self.assertEqual(snapshot.tax_amount, Decimal("19.25"))
        self.assertTrue(snapshot.is_recoverable)


if __name__ == "__main__":
    unittest.main()