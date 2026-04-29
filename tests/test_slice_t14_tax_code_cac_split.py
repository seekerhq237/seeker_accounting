"""Slice T14 tests — TaxCode CAC split + return box code.

Validates the four pieces of behaviour added by slice T14:

1. ``CompanyTaxProfile`` and ``TaxCode`` DTOs / commands now expose
   the new fields (``has_cac``, ``base_rate_percent``,
   ``cac_rate_percent``, ``exemption_kind``, ``return_box_code``).
2. ``TaxSetupService._normalize_cac_split`` enforces the contract:
   either both rate columns are NULL (split disabled) or both are
   populated and reconcile to the combined rate.
3. ``TaxSetupService._normalize_exemption_kind`` validates against
   the closed code set.
4. ``TaxCalculationService.split_tax_components`` decomposes a
   computed tax amount into its base and CAC parts in a way that
   reconciles back to the original amount (no drift from rounding).

These tests are unit-level — they do not exercise the migration or
the persistence path, both of which are covered by the existing
``alembic upgrade / downgrade`` round-trip and the wider smoke
scripts.
"""
from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace

# Ensure mappers configure cleanly when this module is collected on
# its own.
from seeker_accounting.db import model_registry  # noqa: F401

from seeker_accounting.modules.accounting.reference_data.services.tax_calculation_service import (
    TaxCalculationService,
    TaxComponentSplit,
)
from seeker_accounting.modules.accounting.reference_data.services.tax_setup_service import (
    ALL_EXEMPTION_KINDS,
    EXEMPTION_KIND_EXPORT,
    TaxSetupService,
)
from seeker_accounting.platform.exceptions import ValidationError


def _make_service() -> TaxSetupService:
    """Build a ``TaxSetupService`` instance bypassing __init__.

    The CAC / exemption helpers are pure functions that do not touch
    any of the repository factories, so we can reach them via
    ``object.__new__`` to keep the unit tests fast and dependency-free.
    """
    return object.__new__(TaxSetupService)


class CACSplitNormalizationTests(unittest.TestCase):
    """``TaxSetupService._normalize_cac_split`` contract."""

    def test_split_disabled_keeps_rates_null(self) -> None:
        service = _make_service()
        base, cac = service._normalize_cac_split(
            has_cac=False,
            base_rate=None,
            cac_rate=None,
            combined_rate=Decimal("19.25"),
        )
        self.assertIsNone(base)
        self.assertIsNone(cac)

    def test_split_disabled_rejects_populated_rates(self) -> None:
        service = _make_service()
        with self.assertRaises(ValidationError):
            service._normalize_cac_split(
                has_cac=False,
                base_rate=Decimal("17.5"),
                cac_rate=None,
                combined_rate=Decimal("17.5"),
            )

    def test_split_enabled_requires_both_rates(self) -> None:
        service = _make_service()
        with self.assertRaises(ValidationError):
            service._normalize_cac_split(
                has_cac=True,
                base_rate=Decimal("17.5"),
                cac_rate=None,
                combined_rate=Decimal("17.5"),
            )
        with self.assertRaises(ValidationError):
            service._normalize_cac_split(
                has_cac=True,
                base_rate=None,
                cac_rate=Decimal("10"),
                combined_rate=Decimal("10"),
            )

    def test_split_rejects_negative_rates(self) -> None:
        service = _make_service()
        with self.assertRaises(ValidationError):
            service._normalize_cac_split(
                has_cac=True,
                base_rate=Decimal("-1"),
                cac_rate=Decimal("10"),
                combined_rate=Decimal("19.25"),
            )

    def test_split_reconciles_to_combined_rate(self) -> None:
        service = _make_service()
        base, cac = service._normalize_cac_split(
            has_cac=True,
            base_rate=Decimal("17.5"),
            cac_rate=Decimal("10"),
            combined_rate=Decimal("19.25"),
        )
        self.assertEqual(base, Decimal("17.5"))
        self.assertEqual(cac, Decimal("10"))

    def test_split_rejects_inconsistent_combined_rate(self) -> None:
        service = _make_service()
        with self.assertRaises(ValidationError):
            service._normalize_cac_split(
                has_cac=True,
                base_rate=Decimal("17.5"),
                cac_rate=Decimal("10"),
                combined_rate=Decimal("18.00"),
            )

    def test_split_allows_no_combined_rate(self) -> None:
        # When ``combined_rate`` is None (e.g. EXEMPT method), the
        # reconciliation check is skipped — split values still flow
        # through.
        service = _make_service()
        base, cac = service._normalize_cac_split(
            has_cac=True,
            base_rate=Decimal("17.5"),
            cac_rate=Decimal("10"),
            combined_rate=None,
        )
        self.assertEqual(base, Decimal("17.5"))
        self.assertEqual(cac, Decimal("10"))


class ExemptionKindNormalizationTests(unittest.TestCase):
    def test_none_passes_through(self) -> None:
        service = _make_service()
        self.assertIsNone(service._normalize_exemption_kind(None))

    def test_blank_normalises_to_none(self) -> None:
        service = _make_service()
        self.assertIsNone(service._normalize_exemption_kind("   "))

    def test_known_code_uppercased(self) -> None:
        service = _make_service()
        self.assertEqual(
            service._normalize_exemption_kind("export"),
            EXEMPTION_KIND_EXPORT,
        )

    def test_unknown_code_rejected(self) -> None:
        service = _make_service()
        with self.assertRaises(ValidationError):
            service._normalize_exemption_kind("INVENTED")

    def test_all_codes_round_trip(self) -> None:
        service = _make_service()
        for code in ALL_EXEMPTION_KINDS:
            self.assertEqual(service._normalize_exemption_kind(code), code)


class _StubTaxCode:
    """Minimal stand-in matching the attributes
    ``TaxCalculationService.split_tax_components`` reads.
    """

    def __init__(
        self,
        *,
        has_cac: bool,
        base_rate_percent: Decimal | None = None,
        cac_rate_percent: Decimal | None = None,
    ) -> None:
        self.has_cac = has_cac
        self.base_rate_percent = base_rate_percent
        self.cac_rate_percent = cac_rate_percent


class SplitTaxComponentsTests(unittest.TestCase):
    """``TaxCalculationService.split_tax_components`` contract."""

    def test_no_tax_code_returns_full_amount_as_base(self) -> None:
        split = TaxCalculationService.split_tax_components(None, Decimal("19.25"))
        self.assertEqual(
            split,
            TaxComponentSplit(
                base_tax_amount=Decimal("19.25"),
                cac_tax_amount=Decimal("0.00"),
            ),
        )

    def test_tax_code_without_cac_returns_full_amount_as_base(self) -> None:
        tax_code = _StubTaxCode(has_cac=False)
        split = TaxCalculationService.split_tax_components(
            tax_code,
            Decimal("19.25"),
        )
        self.assertEqual(split.cac_tax_amount, Decimal("0.00"))
        self.assertEqual(split.base_tax_amount, Decimal("19.25"))

    def test_cameroon_standard_vat_split(self) -> None:
        tax_code = _StubTaxCode(
            has_cac=True,
            base_rate_percent=Decimal("17.5"),
            cac_rate_percent=Decimal("10"),
        )
        # On a 100,000 base, VAT = 19,250 = 17,500 base + 1,750 CAC.
        split = TaxCalculationService.split_tax_components(
            tax_code,
            Decimal("19250.00"),
        )
        self.assertEqual(split.base_tax_amount, Decimal("17500.00"))
        self.assertEqual(split.cac_tax_amount, Decimal("1750.00"))
        self.assertEqual(
            split.base_tax_amount + split.cac_tax_amount,
            Decimal("19250.00"),
        )

    def test_split_reconciles_after_rounding(self) -> None:
        tax_code = _StubTaxCode(
            has_cac=True,
            base_rate_percent=Decimal("17.5"),
            cac_rate_percent=Decimal("10"),
        )
        # Awkward amount that won't divide evenly — the split must
        # still reconcile back to the original tax amount.
        original = Decimal("123.45")
        split = TaxCalculationService.split_tax_components(tax_code, original)
        self.assertEqual(
            split.base_tax_amount + split.cac_tax_amount,
            original,
        )

    def test_zero_cac_rate_treated_as_no_split(self) -> None:
        tax_code = _StubTaxCode(
            has_cac=True,
            base_rate_percent=Decimal("17.5"),
            cac_rate_percent=Decimal("0"),
        )
        split = TaxCalculationService.split_tax_components(
            tax_code,
            Decimal("17.50"),
        )
        self.assertEqual(split.base_tax_amount, Decimal("17.50"))
        self.assertEqual(split.cac_tax_amount, Decimal("0.00"))


class CommandFieldDefaultsTests(unittest.TestCase):
    """``CreateTaxCodeCommand`` and ``UpdateTaxCodeCommand`` carry the
    new optional fields with safe defaults so existing call sites that
    do not yet pass them keep working.
    """

    def test_create_command_defaults(self) -> None:
        from seeker_accounting.modules.accounting.reference_data.dto.tax_setup_dto import (
            CreateTaxCodeCommand,
        )

        from datetime import date

        command = CreateTaxCodeCommand(
            code="VAT-19.25",
            name="VAT 19.25",
            tax_type_code="VAT",
            calculation_method_code="PERCENTAGE",
            effective_from=date(2026, 1, 1),
            rate_percent=Decimal("19.25"),
        )
        self.assertFalse(command.has_cac)
        self.assertIsNone(command.base_rate_percent)
        self.assertIsNone(command.cac_rate_percent)
        self.assertIsNone(command.exemption_kind)
        self.assertIsNone(command.return_box_code)


if __name__ == "__main__":
    unittest.main()
