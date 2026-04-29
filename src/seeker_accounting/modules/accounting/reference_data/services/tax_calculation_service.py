"""Shared transaction tax calculator.

Provides a single, deterministic implementation of line-level tax
calculation and effective-date validation for all transaction-tax
workflows (sales invoices, sales orders, customer quotes, purchase
orders, purchase bills, and credit notes).

This service intentionally has no constructor dependencies and is
stateless. It is exposed as classmethods so callers may invoke it
without going through the dependency-injection registry — it is a pure
pricing utility, not a business workflow.

Calculation methods supported (driven by ``TaxCode.calculation_method_code``):

- ``PERCENTAGE``    — ``rate_percent`` is the rate, in percent.
- ``FIXED_AMOUNT``  — ``rate_percent`` is reused as a flat per-line tax
                      amount (legacy convention preserved from the
                      existing schema).
- ``EXEMPT``        — always zero tax.

Tax-inclusive vs tax-exclusive pricing is supported so the future
``is_tax_inclusive`` document flag can be wired through without further
refactoring of the calculation layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from seeker_accounting.modules.accounting.reference_data.models.tax_code import TaxCode
from seeker_accounting.platform.exceptions import ValidationError


_TWO_PLACES = Decimal("0.00")
_HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class TaxLineComputation:
    """Outcome of computing tax for a single transaction line.

    All amounts are quantized to 2 decimal places.

    - ``taxable_base``: the amount tax is computed on (net of tax).
    - ``tax_amount``:   the computed tax amount.
    - ``gross_amount``: ``taxable_base + tax_amount``.
    """

    taxable_base: Decimal
    tax_amount: Decimal
    gross_amount: Decimal


@dataclass(frozen=True, slots=True)
class TaxComponentSplit:
    """Split of a computed tax amount into its base and CAC parts.

    For a Cameroon standard-rate VAT line, ``base_tax_amount`` is the
    portion booked to the base VAT account (e.g. 4431) and
    ``cac_tax_amount`` is the additional Communal Centimes booked to
    the CAC sub-account (e.g. 4432).  When the tax code does not carry
    a CAC split, ``cac_tax_amount`` is zero and ``base_tax_amount``
    equals the full tax amount.
    """

    base_tax_amount: Decimal
    cac_tax_amount: Decimal


class TaxCalculationService:
    """Stateless calculator for transaction-line taxes."""

    METHOD_PERCENTAGE = "PERCENTAGE"
    METHOD_FIXED_AMOUNT = "FIXED_AMOUNT"
    METHOD_EXEMPT = "EXEMPT"

    # ------------------------------------------------------------------
    # Effective-date validation
    # ------------------------------------------------------------------

    @classmethod
    def validate_tax_code_for_date(
        cls,
        tax_code: TaxCode | None,
        document_date: date,
        *,
        not_yet_effective_message: str = "Tax code is not yet effective for the document date.",
        no_longer_effective_message: str = "Tax code is no longer effective for the document date.",
    ) -> None:
        """Ensure ``tax_code`` is effective on ``document_date``.

        Raises ``ValidationError`` if the date falls outside the tax
        code's effective range. Does nothing when ``tax_code`` is None.
        """
        if tax_code is None:
            return
        if document_date < tax_code.effective_from:
            raise ValidationError(not_yet_effective_message)
        if tax_code.effective_to is not None and document_date > tax_code.effective_to:
            raise ValidationError(no_longer_effective_message)

    # ------------------------------------------------------------------
    # Line-level tax calculation
    # ------------------------------------------------------------------

    @classmethod
    def calculate_line_tax(
        cls,
        line_amount: Decimal,
        tax_code: TaxCode | None,
        *,
        is_tax_inclusive: bool = False,
    ) -> TaxLineComputation:
        """Compute the tax breakdown for a single transaction line.

        When ``is_tax_inclusive`` is False (the default), ``line_amount``
        is treated as the net taxable base; the tax is added on top.

        When ``is_tax_inclusive`` is True, ``line_amount`` is treated as
        the gross amount (already containing tax); the tax is extracted
        out of it and the taxable base reported separately.
        """
        if tax_code is None:
            base = cls._quantize(line_amount)
            return TaxLineComputation(
                taxable_base=base,
                tax_amount=Decimal("0.00"),
                gross_amount=base,
            )

        method_code = (tax_code.calculation_method_code or "").strip().upper()

        if method_code == cls.METHOD_PERCENTAGE:
            return cls._compute_percentage(line_amount, tax_code, is_tax_inclusive)

        if method_code == cls.METHOD_FIXED_AMOUNT:
            return cls._compute_fixed_amount(line_amount, tax_code, is_tax_inclusive)

        # METHOD_EXEMPT or any unrecognized code -> zero tax.
        base = cls._quantize(line_amount)
        return TaxLineComputation(
            taxable_base=base,
            tax_amount=Decimal("0.00"),
            gross_amount=base,
        )

    @classmethod
    def calculate_line_tax_amount(
        cls,
        line_amount: Decimal,
        tax_code: TaxCode | None,
        *,
        is_tax_inclusive: bool = False,
    ) -> Decimal:
        """Convenience wrapper that returns only the computed tax amount."""
        return cls.calculate_line_tax(
            line_amount,
            tax_code,
            is_tax_inclusive=is_tax_inclusive,
        ).tax_amount

    # ------------------------------------------------------------------
    # Recoverability
    # ------------------------------------------------------------------

    @classmethod
    def is_recoverable_tax(cls, tax_code: TaxCode | None) -> bool:
        """Whether the tax represented by ``tax_code`` is recoverable.

        Treats ``None`` and unset ``is_recoverable`` as recoverable for
        backward compatibility with existing data and posting flows.
        Only an explicit ``False`` marks a tax as non-recoverable.
        """
        if tax_code is None:
            return True
        return tax_code.is_recoverable is not False

    # ------------------------------------------------------------------
    # CAC split
    # ------------------------------------------------------------------

    @classmethod
    def split_tax_components(
        cls,
        tax_code: TaxCode | None,
        tax_amount: Decimal,
    ) -> TaxComponentSplit:
        """Decompose ``tax_amount`` into base + CAC portions.

        The decomposition is driven by ``tax_code.has_cac`` and the
        ``base_rate_percent`` / ``cac_rate_percent`` columns introduced
        in slice T14.  Splitting from the actual posted tax amount
        (rather than from the line base) guarantees that the two parts
        always reconcile back to the journal-entry tax amount, even
        after rounding.

        For a Cameroon VAT line whose tax code carries
        ``base_rate=17.5`` and ``cac_rate=10``, the CAC share is
        ``cac_rate / (100 + cac_rate)`` of the total tax amount —
        because the combined rate is built as ``base * (1 + cac/100)``.
        """
        amount = cls._quantize(tax_amount)
        if (
            tax_code is None
            or not bool(getattr(tax_code, "has_cac", False))
            or tax_code.cac_rate_percent is None
        ):
            return TaxComponentSplit(
                base_tax_amount=amount,
                cac_tax_amount=Decimal("0.00"),
            )

        cac_rate = Decimal(str(tax_code.cac_rate_percent))
        if cac_rate <= Decimal("0"):
            return TaxComponentSplit(
                base_tax_amount=amount,
                cac_tax_amount=Decimal("0.00"),
            )

        cac_amount = cls._quantize(amount * cac_rate / (_HUNDRED + cac_rate))
        base_amount = cls._quantize(amount - cac_amount)
        return TaxComponentSplit(
            base_tax_amount=base_amount,
            cac_tax_amount=cac_amount,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _compute_percentage(
        cls,
        line_amount: Decimal,
        tax_code: TaxCode,
        is_tax_inclusive: bool,
    ) -> TaxLineComputation:
        if tax_code.rate_percent is None:
            raise ValidationError("Percentage tax code is missing a rate.")
        rate = Decimal(str(tax_code.rate_percent))

        if is_tax_inclusive and rate > Decimal("0"):
            gross = cls._quantize(line_amount)
            base = cls._quantize(gross * _HUNDRED / (_HUNDRED + rate))
            tax = cls._quantize(gross - base)
            return TaxLineComputation(taxable_base=base, tax_amount=tax, gross_amount=gross)

        base = cls._quantize(line_amount)
        tax = cls._quantize(base * rate / _HUNDRED)
        gross = cls._quantize(base + tax)
        return TaxLineComputation(taxable_base=base, tax_amount=tax, gross_amount=gross)

    @classmethod
    def _compute_fixed_amount(
        cls,
        line_amount: Decimal,
        tax_code: TaxCode,
        is_tax_inclusive: bool,
    ) -> TaxLineComputation:
        if tax_code.rate_percent is None:
            tax = Decimal("0.00")
        else:
            tax = cls._quantize(Decimal(str(tax_code.rate_percent)))

        if is_tax_inclusive:
            gross = cls._quantize(line_amount)
            base = cls._quantize(gross - tax)
            if base < Decimal("0.00"):
                raise ValidationError(
                    "Tax-inclusive line amount cannot be smaller than the fixed tax amount.",
                )
            return TaxLineComputation(taxable_base=base, tax_amount=tax, gross_amount=gross)

        base = cls._quantize(line_amount)
        gross = cls._quantize(base + tax)
        return TaxLineComputation(taxable_base=base, tax_amount=tax, gross_amount=gross)

    @staticmethod
    def _quantize(value: Decimal) -> Decimal:
        return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
