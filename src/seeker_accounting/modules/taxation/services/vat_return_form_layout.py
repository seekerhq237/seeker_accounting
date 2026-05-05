"""DGI Cameroon VAT-return form layout (read model).

This module is **presentation-only**.  It takes a stored
``TaxReturnDTO`` and re-projects it into the sectioned DGI VAT-return
layout that the operator actually sees on the official paper return:

    Section 4 – Turnover Realised        (lines L17 … L23)
    Section 5 – VAT Recoverable          (lines L24 … L31)
    Section 6 – VAT Adjustment           (lines L32 … L35)
    Section 7 – VAT Payable or Credit    (lines L36 … L43)
    Section 8 – Total of VAT Payable     (lines L44 … L47)

The shape mirrors the official "Tax Return for Business and Liquor
Licence, Income, Turnover and Specific Activities Taxes" — VAT page —
issued by the Directorate General of Taxation (DGI).

Slice T30 made the L-codes the canonical persistence keys, so the
read model is now a near-pass-through: each row pulls ``base`` from
``TaxReturnLine.base_amount`` and ``amount`` from ``TaxReturnLine.amount``.
Returns drafted with the legacy 6-box internal scheme are still
rendered correctly via a backward-compat bridge: legacy box codes
(TAXABLE_SALES, VAT_OUTPUT, …) are folded into their L-code positions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from seeker_accounting.modules.taxation.constants import (
    ALL_VAT_RETURN_LINE_CODES,
    VAT_BOX_INPUT_TAX_DEDUCTIBLE,
    VAT_BOX_INPUT_TAX_NON_DEDUCTIBLE,
    VAT_BOX_NET_VAT_DUE,
    VAT_BOX_OUTPUT_TAX,
    VAT_BOX_TAXABLE_PURCHASES,
    VAT_BOX_TAXABLE_SALES,
    VAT_RETURN_LINE_L17,
    VAT_RETURN_LINE_L18,
    VAT_RETURN_LINE_L19,
    VAT_RETURN_LINE_L20,
    VAT_RETURN_LINE_L21,
    VAT_RETURN_LINE_L22,
    VAT_RETURN_LINE_L23,
    VAT_RETURN_LINE_L26,
    VAT_RETURN_LINE_L27,
    VAT_RETURN_LINE_L28,
    VAT_RETURN_LINE_L29,
    VAT_RETURN_LINE_L30,
    VAT_RETURN_LINE_L36,
    VAT_RETURN_LINE_L37,
    VAT_RETURN_LINE_L40,
    VAT_RETURN_LINE_L43,
    VAT_RETURN_LINE_L47,
    VAT_RETURN_LINE_NON_DEDUCTIBLE,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    TaxReturnDTO,
    TaxReturnLineDTO,
)


_ZERO = Decimal("0.00")


# ── Row schema ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class VATFormRow:
    """A single line in a DGI VAT-return section.

    Either of ``base`` / ``rate`` / ``amount`` may be ``None`` to
    indicate "field present on the official form but not yet populated
    from posted accounting data". The renderer must show such fields
    as blank-but-visible (e.g. an em-dash) so the form structure is
    preserved.
    """

    code: str                 # Statutory line label, e.g. "L17"
    label: str                # Human-readable name
    base: Decimal | None = None
    rate: str | None = None   # Free-form so we can render "19.25 %", "0 %", "—"
    amount: Decimal | None = None
    emphasis: bool = False    # True for sum / totals rows
    note: str | None = None   # Optional help / formula text


@dataclass(frozen=True, slots=True)
class VATFormSection:
    """One numbered section of the DGI VAT return form."""

    number: str               # "4", "5", …
    title: str
    columns: tuple[str, ...]  # Column headers, e.g. ("Base", "Rate", "Tax")
    rows: tuple[VATFormRow, ...]


@dataclass(frozen=True, slots=True)
class VATFormLayout:
    """Full structured projection of a TaxReturnDTO."""

    return_id: int
    period_label: str
    fiscal_year: int
    month_label: str
    sections: tuple[VATFormSection, ...]
    total_due: Decimal
    total_paid: Decimal
    outstanding: Decimal
    has_unmapped_data: bool = False  # True if stored lines hold codes we don't surface


# ── Backward-compat bridge for the pre-T30 6-box scheme ────────────────


_LEGACY_BOX_CODES = frozenset(
    {
        VAT_BOX_TAXABLE_SALES,
        VAT_BOX_OUTPUT_TAX,
        VAT_BOX_TAXABLE_PURCHASES,
        VAT_BOX_INPUT_TAX_DEDUCTIBLE,
        VAT_BOX_INPUT_TAX_NON_DEDUCTIBLE,
        VAT_BOX_NET_VAT_DUE,
    }
)


@dataclass(frozen=True, slots=True)
class _LineValue:
    base: Decimal | None
    amount: Decimal


def _index_lines(
    lines: Iterable[TaxReturnLineDTO],
) -> dict[str, _LineValue]:
    """Index lines by box_code, folding pre-T30 legacy codes into L-codes."""
    raw: dict[str, _LineValue] = {}
    for line in lines:
        raw[line.box_code] = _LineValue(
            base=line.base_amount,
            amount=Decimal(line.amount or _ZERO),
        )

    # Promote legacy 6-box codes onto their L-code positions when an
    # L-code row is not already present (i.e. the return predates T30).
    if VAT_RETURN_LINE_L17 not in raw and (
        VAT_BOX_TAXABLE_SALES in raw or VAT_BOX_OUTPUT_TAX in raw
    ):
        raw[VAT_RETURN_LINE_L17] = _LineValue(
            base=raw.get(VAT_BOX_TAXABLE_SALES, _LineValue(None, _ZERO)).amount,
            amount=raw.get(VAT_BOX_OUTPUT_TAX, _LineValue(None, _ZERO)).amount,
        )
    if VAT_RETURN_LINE_L36 not in raw and VAT_BOX_OUTPUT_TAX in raw:
        raw[VAT_RETURN_LINE_L36] = _LineValue(
            base=None, amount=raw[VAT_BOX_OUTPUT_TAX].amount,
        )
    if VAT_RETURN_LINE_L26 not in raw and (
        VAT_BOX_TAXABLE_PURCHASES in raw or VAT_BOX_INPUT_TAX_DEDUCTIBLE in raw
    ):
        raw[VAT_RETURN_LINE_L26] = _LineValue(
            base=raw.get(VAT_BOX_TAXABLE_PURCHASES, _LineValue(None, _ZERO)).amount,
            amount=raw.get(VAT_BOX_INPUT_TAX_DEDUCTIBLE, _LineValue(None, _ZERO)).amount,
        )
    if VAT_RETURN_LINE_L30 not in raw and VAT_BOX_INPUT_TAX_DEDUCTIBLE in raw:
        raw[VAT_RETURN_LINE_L30] = _LineValue(
            base=None, amount=raw[VAT_BOX_INPUT_TAX_DEDUCTIBLE].amount,
        )
    if VAT_RETURN_LINE_L37 not in raw and VAT_BOX_INPUT_TAX_DEDUCTIBLE in raw:
        raw[VAT_RETURN_LINE_L37] = _LineValue(
            base=None, amount=raw[VAT_BOX_INPUT_TAX_DEDUCTIBLE].amount,
        )
    if VAT_RETURN_LINE_L40 not in raw and VAT_BOX_NET_VAT_DUE in raw:
        net = raw[VAT_BOX_NET_VAT_DUE].amount
        raw[VAT_RETURN_LINE_L40] = _LineValue(
            base=None, amount=net if net >= _ZERO else _ZERO,
        )
        raw[VAT_RETURN_LINE_L43] = _LineValue(
            base=None, amount=-net if net < _ZERO else _ZERO,
        )
    if VAT_RETURN_LINE_NON_DEDUCTIBLE not in raw and (
        VAT_BOX_INPUT_TAX_NON_DEDUCTIBLE in raw
    ):
        raw[VAT_RETURN_LINE_NON_DEDUCTIBLE] = _LineValue(
            base=None, amount=raw[VAT_BOX_INPUT_TAX_NON_DEDUCTIBLE].amount,
        )
    return raw


_MONTHS_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _month_label(period_start, period_end) -> str:
    if period_start is None or period_end is None:
        return "—"
    if (
        period_start.year == period_end.year
        and period_start.month == period_end.month
    ):
        return f"{_MONTHS_EN[period_start.month - 1]} {period_start.year}"
    return (
        f"{_MONTHS_EN[period_start.month - 1]} {period_start.year} – "
        f"{_MONTHS_EN[period_end.month - 1]} {period_end.year}"
    )


def _val(by_code: dict[str, _LineValue], code: str) -> Decimal:
    """Amount for an L-code, defaulting to zero."""
    v = by_code.get(code)
    return v.amount if v is not None else _ZERO


def _base(by_code: dict[str, _LineValue], code: str) -> Decimal | None:
    v = by_code.get(code)
    return v.base if v is not None else None


def build_vat_form_layout(tax_return: TaxReturnDTO) -> VATFormLayout:
    """Project a stored VAT return into the DGI sectioned form."""
    by_code = _index_lines(tax_return.lines)

    has_unmapped = any(
        line.box_code not in ALL_VAT_RETURN_LINE_CODES
        and line.box_code not in _LEGACY_BOX_CODES
        for line in tax_return.lines
    )

    # ── Section 4 — Turnover Realised ──────────────────────────────────
    section_4 = VATFormSection(
        number="4",
        title="Turnover Realised",
        columns=("Base (HT)", "Rate", "Tax amount"),
        rows=(
            VATFormRow(
                code="L17",
                label="Transactions taxable at standard rate",
                base=_base(by_code, VAT_RETURN_LINE_L17),
                rate="19.25 %",
                amount=_val(by_code, VAT_RETURN_LINE_L17),
            ),
            VATFormRow(
                code="L18",
                label="Amount of Excise Duty",
                base=_base(by_code, VAT_RETURN_LINE_L18),
                rate=None,
                amount=_val(by_code, VAT_RETURN_LINE_L18) or None,
                note="Detailed excise breakdown not yet surfaced.",
            ),
            VATFormRow(
                code="L19",
                label="Lodging tax for lodging establishments",
                base=_base(by_code, VAT_RETURN_LINE_L19),
                rate=None,
                amount=_val(by_code, VAT_RETURN_LINE_L19) or None,
            ),
            VATFormRow(
                code="L20",
                label="Other taxable transactions",
                base=_base(by_code, VAT_RETURN_LINE_L20),
                rate=None,
                amount=_val(by_code, VAT_RETURN_LINE_L20) or None,
            ),
            VATFormRow(
                code="L21",
                label="Exportations (zero-rated)",
                base=_base(by_code, VAT_RETURN_LINE_L21),
                rate="0 %",
                amount=_ZERO,
            ),
            VATFormRow(
                code="L22",
                label="Exempted turnover",
                base=_base(by_code, VAT_RETURN_LINE_L22),
                rate="—",
                amount=None,
            ),
            VATFormRow(
                code="L23",
                label="Global turnover excl. taxes (= L17+L18+L19+L20+L21)",
                base=_val(by_code, VAT_RETURN_LINE_L23) or None,
                rate=None,
                amount=None,
                emphasis=True,
            ),
        ),
    )

    # ── Section 5 — VAT Recoverable ────────────────────────────────────
    section_5 = VATFormSection(
        number="5",
        title="VAT Recoverable",
        columns=("Detail", "", "Amount"),
        rows=(
            VATFormRow(
                code="L24",
                label="Temporary pro-rata (partially-exempted)",
                amount=None,
                note="Pro-rata adjustment not yet supported — assumed 100 %.",
            ),
            VATFormRow(
                code="L25",
                label="Previous credit b/f (L43 of previous declaration)",
                amount=None,
                note="Credit carry-forward not yet linked.",
            ),
            VATFormRow(
                code="L26",
                label="VAT recoverable on local purchases of goods",
                base=_base(by_code, VAT_RETURN_LINE_L26),
                amount=_val(by_code, VAT_RETURN_LINE_L26),
            ),
            VATFormRow(
                code="L27",
                label="VAT recoverable on local services",
                base=_base(by_code, VAT_RETURN_LINE_L27),
                amount=_val(by_code, VAT_RETURN_LINE_L27) or None,
            ),
            VATFormRow(
                code="L28",
                label="VAT recoverable on imported goods",
                base=_base(by_code, VAT_RETURN_LINE_L28),
                amount=_val(by_code, VAT_RETURN_LINE_L28) or None,
            ),
            VATFormRow(
                code="L29",
                label="VAT recoverable on imported services",
                base=_base(by_code, VAT_RETURN_LINE_L29),
                amount=_val(by_code, VAT_RETURN_LINE_L29) or None,
            ),
            VATFormRow(
                code="L30",
                label="Total VAT recoverable (= L25+L26+L27+L28+L29)",
                amount=_val(by_code, VAT_RETURN_LINE_L30),
                emphasis=True,
            ),
            VATFormRow(
                code="L31",
                label="VAT recoverable at temporary pro-rata (L24 × L30)",
                amount=None,
            ),
        ),
    )

    # ── Section 6 — VAT Adjustment ─────────────────────────────────────
    section_6 = VATFormSection(
        number="6",
        title="VAT Adjustment",
        columns=("Detail", "", "Amount"),
        rows=(
            VATFormRow(code="L32", label="Adjustment of VAT recoverable / VAT retained at source (−)", amount=None),
            VATFormRow(code="L33", label="Adjustment of VAT absorbed by the State (−)", amount=None),
            VATFormRow(code="L34", label="Adjustment on disposals of fixed assets to be repaid (+)", amount=None),
            VATFormRow(code="L35", label="Adjustment of VAT to be repaid and others (+)", amount=None),
        ),
    )

    # ── Section 7 — VAT Payable or Credit ──────────────────────────────
    output_vat = _val(by_code, VAT_RETURN_LINE_L36)
    input_deductible = _val(by_code, VAT_RETURN_LINE_L37)
    vat_payable = _val(by_code, VAT_RETURN_LINE_L40)
    vat_credit = _val(by_code, VAT_RETURN_LINE_L43)

    section_7 = VATFormSection(
        number="7",
        title="VAT Payable or VAT Credit",
        columns=("Detail", "", "Amount"),
        rows=(
            VATFormRow(code="L36", label="VAT collected (= L17+L18+L19+L20)", amount=output_vat, emphasis=True),
            VATFormRow(code="L37", label="VAT recoverable (L30 or L31)", amount=input_deductible, emphasis=True),
            VATFormRow(code="L38", label="Adjustment of VAT to be recovered (= L32+L33)", amount=None),
            VATFormRow(code="L39", label="Adjustment of VAT to be repaid (= L34+L35)", amount=None),
            VATFormRow(code="L40", label="VAT payable (= L36 − L37 − L38 + L39)", amount=vat_payable, emphasis=True),
            VATFormRow(code="L41", label="VAT credit", amount=vat_credit, emphasis=True),
            VATFormRow(code="L42", label="Reimbursement requested", amount=None),
            VATFormRow(code="L43", label="Credit to be carried forward (= L41 − L42)", amount=vat_credit),
        ),
    )

    # ── Section 8 — Total of VAT Payable ───────────────────────────────
    total_payable = _val(by_code, VAT_RETURN_LINE_L47) or vat_payable
    section_8 = VATFormSection(
        number="8",
        title="Total of VAT Payable",
        columns=("Principal", "Additional Council Tax", "Fines", "Total"),
        rows=(
            VATFormRow(code="L44", label="VAT payable (L40)", amount=vat_payable),
            VATFormRow(code="L45", label="VAT retained at source (approved enterprise)", amount=None),
            VATFormRow(code="L46", label="VAT retained on remunerations paid abroad", amount=None),
            VATFormRow(code="L47", label="Amount payable (= L44 + L45 + L46)", amount=total_payable, emphasis=True),
        ),
    )

    period_label = (
        f"{tax_return.period_start.isoformat()} — "
        f"{tax_return.period_end.isoformat()}"
    )
    total_due = Decimal(tax_return.total_due_amount or _ZERO)
    total_paid = Decimal(tax_return.total_paid_amount or _ZERO)

    return VATFormLayout(
        return_id=tax_return.id,
        period_label=period_label,
        fiscal_year=tax_return.period_start.year if tax_return.period_start else 0,
        month_label=_month_label(tax_return.period_start, tax_return.period_end),
        sections=(section_4, section_5, section_6, section_7, section_8),
        total_due=total_due,
        total_paid=total_paid,
        outstanding=total_due - total_paid,
        has_unmapped_data=has_unmapped,
    )

