"""Unit tests for the shared transaction TaxCalculationService.

These tests pin down the expected behaviour of the calculator that
sales (invoices, orders, quotes) and purchases (orders, bills) all
delegate to. They also cover the tax-inclusive math that the next
taxation slice will rely on.
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from seeker_accounting.modules.accounting.reference_data.services.tax_calculation_service import (
    TaxCalculationService,
)
from seeker_accounting.platform.exceptions import ValidationError


def _tax_code(
    *,
    method: str,
    rate: Decimal | None = None,
    is_recoverable: bool | None = None,
    effective_from: date = date(2024, 1, 1),
    effective_to: date | None = None,
):
    """Lightweight stand-in for the TaxCode ORM model.

    The calculator only reads ``calculation_method_code``, ``rate_percent``,
    ``is_recoverable``, ``effective_from``, and ``effective_to`` — so a
    SimpleNamespace is sufficient and avoids touching the database.
    """
    return SimpleNamespace(
        calculation_method_code=method,
        rate_percent=rate,
        is_recoverable=is_recoverable,
        effective_from=effective_from,
        effective_to=effective_to,
    )


class TaxCalculationServiceTests(unittest.TestCase):
    # --- PERCENTAGE ---------------------------------------------------

    def test_percentage_exclusive_standard_vat(self):
        tax_code = _tax_code(method="PERCENTAGE", rate=Decimal("19.25"))
        result = TaxCalculationService.calculate_line_tax(Decimal("100.00"), tax_code)
        self.assertEqual(result.taxable_base, Decimal("100.00"))
        self.assertEqual(result.tax_amount, Decimal("19.25"))
        self.assertEqual(result.gross_amount, Decimal("119.25"))

    def test_percentage_inclusive_extracts_tax_from_gross(self):
        tax_code = _tax_code(method="PERCENTAGE", rate=Decimal("19.25"))
        result = TaxCalculationService.calculate_line_tax(
            Decimal("119.25"), tax_code, is_tax_inclusive=True
        )
        self.assertEqual(result.taxable_base, Decimal("100.00"))
        self.assertEqual(result.tax_amount, Decimal("19.25"))
        self.assertEqual(result.gross_amount, Decimal("119.25"))

    def test_percentage_inclusive_zero_rate_is_pass_through(self):
        tax_code = _tax_code(method="PERCENTAGE", rate=Decimal("0"))
        result = TaxCalculationService.calculate_line_tax(
            Decimal("100.00"), tax_code, is_tax_inclusive=True
        )
        self.assertEqual(result.taxable_base, Decimal("100.00"))
        self.assertEqual(result.tax_amount, Decimal("0.00"))
        self.assertEqual(result.gross_amount, Decimal("100.00"))

    def test_percentage_missing_rate_raises(self):
        tax_code = _tax_code(method="PERCENTAGE", rate=None)
        with self.assertRaises(ValidationError):
            TaxCalculationService.calculate_line_tax(Decimal("100.00"), tax_code)

    # --- FIXED_AMOUNT --------------------------------------------------

    def test_fixed_amount_exclusive(self):
        tax_code = _tax_code(method="FIXED_AMOUNT", rate=Decimal("5.00"))
        result = TaxCalculationService.calculate_line_tax(Decimal("50.00"), tax_code)
        self.assertEqual(result.taxable_base, Decimal("50.00"))
        self.assertEqual(result.tax_amount, Decimal("5.00"))
        self.assertEqual(result.gross_amount, Decimal("55.00"))

    def test_fixed_amount_inclusive_subtracts_from_gross(self):
        tax_code = _tax_code(method="FIXED_AMOUNT", rate=Decimal("5.00"))
        result = TaxCalculationService.calculate_line_tax(
            Decimal("55.00"), tax_code, is_tax_inclusive=True
        )
        self.assertEqual(result.taxable_base, Decimal("50.00"))
        self.assertEqual(result.tax_amount, Decimal("5.00"))
        self.assertEqual(result.gross_amount, Decimal("55.00"))

    def test_fixed_amount_missing_rate_yields_zero(self):
        tax_code = _tax_code(method="FIXED_AMOUNT", rate=None)
        result = TaxCalculationService.calculate_line_tax(Decimal("50.00"), tax_code)
        self.assertEqual(result.tax_amount, Decimal("0.00"))

    def test_fixed_amount_inclusive_below_tax_raises(self):
        tax_code = _tax_code(method="FIXED_AMOUNT", rate=Decimal("10.00"))
        with self.assertRaises(ValidationError):
            TaxCalculationService.calculate_line_tax(
                Decimal("5.00"), tax_code, is_tax_inclusive=True
            )

    # --- EXEMPT / unknown / None --------------------------------------

    def test_exempt_returns_zero_tax(self):
        tax_code = _tax_code(method="EXEMPT")
        result = TaxCalculationService.calculate_line_tax(Decimal("100.00"), tax_code)
        self.assertEqual(result.tax_amount, Decimal("0.00"))
        self.assertEqual(result.gross_amount, Decimal("100.00"))

    def test_unknown_method_returns_zero_tax(self):
        tax_code = _tax_code(method="GIBBERISH")
        result = TaxCalculationService.calculate_line_tax(Decimal("100.00"), tax_code)
        self.assertEqual(result.tax_amount, Decimal("0.00"))

    def test_none_tax_code_returns_zero_tax(self):
        result = TaxCalculationService.calculate_line_tax(Decimal("123.45"), None)
        self.assertEqual(result.taxable_base, Decimal("123.45"))
        self.assertEqual(result.tax_amount, Decimal("0.00"))
        self.assertEqual(result.gross_amount, Decimal("123.45"))

    # --- Effective date validation ------------------------------------

    def test_validate_within_range_passes(self):
        tax_code = _tax_code(
            method="PERCENTAGE",
            rate=Decimal("19.25"),
            effective_from=date(2024, 1, 1),
            effective_to=date(2025, 12, 31),
        )
        TaxCalculationService.validate_tax_code_for_date(tax_code, date(2025, 6, 1))

    def test_validate_before_effective_from_raises(self):
        tax_code = _tax_code(method="PERCENTAGE", rate=Decimal("19.25"), effective_from=date(2025, 1, 1))
        with self.assertRaises(ValidationError):
            TaxCalculationService.validate_tax_code_for_date(tax_code, date(2024, 12, 31))

    def test_validate_after_effective_to_raises(self):
        tax_code = _tax_code(
            method="PERCENTAGE",
            rate=Decimal("19.25"),
            effective_from=date(2024, 1, 1),
            effective_to=date(2024, 12, 31),
        )
        with self.assertRaises(ValidationError):
            TaxCalculationService.validate_tax_code_for_date(tax_code, date(2025, 1, 1))

    def test_validate_none_tax_code_is_noop(self):
        TaxCalculationService.validate_tax_code_for_date(None, date(2025, 1, 1))

    # --- Recoverability ------------------------------------------------

    def test_is_recoverable_default_true_when_unset(self):
        tax_code = _tax_code(method="PERCENTAGE", rate=Decimal("19.25"), is_recoverable=None)
        self.assertTrue(TaxCalculationService.is_recoverable_tax(tax_code))

    def test_is_recoverable_true_when_explicit(self):
        tax_code = _tax_code(method="PERCENTAGE", rate=Decimal("19.25"), is_recoverable=True)
        self.assertTrue(TaxCalculationService.is_recoverable_tax(tax_code))

    def test_is_recoverable_false_when_explicit(self):
        tax_code = _tax_code(method="PERCENTAGE", rate=Decimal("19.25"), is_recoverable=False)
        self.assertFalse(TaxCalculationService.is_recoverable_tax(tax_code))

    def test_is_recoverable_none_tax_code_is_true(self):
        self.assertTrue(TaxCalculationService.is_recoverable_tax(None))

    # --- Convenience helper -------------------------------------------

    def test_calculate_line_tax_amount_returns_only_tax(self):
        tax_code = _tax_code(method="PERCENTAGE", rate=Decimal("10.00"))
        amount = TaxCalculationService.calculate_line_tax_amount(Decimal("250.00"), tax_code)
        self.assertEqual(amount, Decimal("25.00"))


if __name__ == "__main__":
    unittest.main()
