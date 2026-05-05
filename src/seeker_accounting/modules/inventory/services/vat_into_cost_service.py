"""VAT-into-cost service — P5 / Slice 6.1.

For imported/purchased goods where input VAT is non-deductible (e.g. items
flagged is_vat_exempt_purchases=True or items in sectors where VAT is not
reclaimable), this service capitalises the non-recoverable VAT amount into the
purchase unit cost BEFORE the cost layer is created.

Usage: call adjust_unit_cost_for_non_deductible_vat() from within the
GoodsReceiptService.post_receipt() flow before appending to the stock ledger.

Algorithm:
  If the item.is_vat_exempt_purchases is True (or the tax code on the
  purchase line marks is_recoverable=False), the VAT amount for that line is
  added to the cost:

    effective_unit_cost = unit_cost + (vat_amount / quantity)

This preserves the true landed cost in the stock ledger (OHADA principle:
taxes non-refundable form part of the acquisition cost of stock, per SYSCOHADA
Art. 35 § 3).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.platform.numerics.rounding_policy import quantize_internal_cost


class VatIntoCostService:
    """Adjusts unit cost for non-deductible VAT (OHADA Art. 35 § 3)."""

    def adjust_unit_cost_for_non_deductible_vat(
        self,
        session: Session,
        *,
        item_id: int,
        unit_cost: Decimal,
        vat_amount_per_line: Decimal,
        quantity: Decimal,
        is_vat_recoverable: bool,
    ) -> Decimal:
        """Return the adjusted unit cost, capitalising non-recoverable VAT.

        If VAT is recoverable (normal deductible input VAT), returns
        unit_cost unchanged. If non-recoverable, adds vat_per_unit.
        """
        if is_vat_recoverable:
            return unit_cost

        item_repo = ItemRepository(session)
        item = item_repo.get(item_id)
        if item is None:
            return unit_cost

        # Item-level override: if item explicitly marks purchases as VAT-exempt
        # (non-deductible sector), capitalise regardless of tax code flag.
        if not item.is_vat_exempt_purchases and is_vat_recoverable:
            return unit_cost

        if quantity <= Decimal("0"):
            return unit_cost

        vat_per_unit = vat_amount_per_line / quantity
        return quantize_internal_cost(unit_cost + vat_per_unit)
