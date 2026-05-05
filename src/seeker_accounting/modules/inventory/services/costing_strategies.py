"""Inventory costing strategies.

Per ``docs/inventory_upgrade_plan.md`` Slice 2.2: three strategies are
supported. Each strategy owns the consumption logic for a single issue or
negative-adjustment document line.

All strategies:
- Accept a ``CostLayerConsumptionRepository`` to write immutable consumption
  records alongside the existing ``InventoryCostLayerRepository`` mutations.
- Return the total consumed value (``Decimal``) for the posting service to
  use when building journal lines.
- Raise ``ValidationError`` on insufficient stock.

Strategy selection:
- ``Item.inventory_cost_method_code == "weighted_average"`` → ``WeightedAverageCostingStrategy``
- ``Item.inventory_cost_method_code == "fifo"`` → ``FifoCostingStrategy``
- ``Item.inventory_cost_method_code == "standard_cost"`` → ``StandardCostStrategy``

The posting service calls ``CostingStrategyRouter.consume_for_issue``, which
dispatches to the correct strategy, so callers never branch on the code
themselves.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from seeker_accounting.modules.inventory.models.cost_layer_consumption import CostLayerConsumption
from seeker_accounting.modules.inventory.models.inventory_cost_layer import InventoryCostLayer
from seeker_accounting.modules.inventory.repositories.cost_layer_consumption_repository import (
    CostLayerConsumptionRepository,
)
from seeker_accounting.modules.inventory.repositories.inventory_cost_layer_repository import (
    InventoryCostLayerRepository,
)
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.platform.numerics.rounding_policy import (
    quantize_amount,
    quantize_unit_cost,
)


class WeightedAverageCostingStrategy:
    """Consume stock at the current weighted-average cost across all layers.

    The avg is computed once per issue from all remaining layers; every layer
    is consumed proportionally (oldest-first for deduction bookkeeping only).
    A single ``CostLayerConsumption`` record is written per consumed layer
    slice.
    """

    def consume(
        self,
        *,
        cost_layer_repo: InventoryCostLayerRepository,
        consumption_repo: CostLayerConsumptionRepository,
        company_id: int,
        item_id: int,
        location_id: int | None,
        batch_id: int | None,
        quantity: Decimal,
        doc_line_id: int,
        posting_date: date,
    ) -> Decimal:
        on_hand = cost_layer_repo.get_stock_on_hand(
            company_id,
            item_id,
            location_id=location_id,
            location_aware=True,
            batch_id=batch_id,
            batch_aware=batch_id is not None,
        )
        if quantity > on_hand:
            raise ValidationError(
                f"Insufficient stock for item id {item_id}. "
                f"On hand: {on_hand}, requested: {quantity}."
            )
        avg_cost = cost_layer_repo.get_weighted_average_cost(
            company_id,
            item_id,
            location_id=location_id,
            location_aware=True,
            batch_id=batch_id,
            batch_aware=batch_id is not None,
        )
        if avg_cost is None:
            raise ValidationError(
                f"Cannot determine weighted average cost for item id {item_id} "
                "— no stock layers found."
            )
        total_value = quantize_amount(quantity * avg_cost)

        # Consume layers (oldest-first), writing consumption records.
        layers = cost_layer_repo.list_for_item(
            company_id, item_id,
            with_remaining_only=True,
            location_id=location_id,
            location_aware=True,
            batch_id=batch_id,
            batch_aware=batch_id is not None,
        )
        remaining_to_consume = quantity
        for layer in layers:
            if remaining_to_consume <= Decimal("0"):
                break
            consumed = min(remaining_to_consume, layer.quantity_remaining)
            # Consumed value per slice at avg cost (not layer cost).
            consumed_value = quantize_amount(consumed * avg_cost)
            layer.quantity_remaining -= consumed
            cost_layer_repo.save(layer)
            consumption_repo.add(CostLayerConsumption(
                source_layer_id=layer.id,
                consuming_doc_line_id=doc_line_id,
                consumed_quantity=consumed,
                consumed_value=consumed_value,
                posting_date=posting_date,
            ))
            remaining_to_consume -= consumed

        return total_value


class FifoCostingStrategy:
    """Consume stock FIFO: oldest layer first, at that layer's own unit cost.

    A ``CostLayerConsumption`` record is written for each layer slice consumed.
    """

    def consume(
        self,
        *,
        cost_layer_repo: InventoryCostLayerRepository,
        consumption_repo: CostLayerConsumptionRepository,
        company_id: int,
        item_id: int,
        location_id: int | None,
        batch_id: int | None,
        quantity: Decimal,
        doc_line_id: int,
        posting_date: date,
    ) -> Decimal:
        on_hand = cost_layer_repo.get_stock_on_hand(
            company_id,
            item_id,
            location_id=location_id,
            location_aware=True,
            batch_id=batch_id,
            batch_aware=batch_id is not None,
        )
        if quantity > on_hand:
            raise ValidationError(
                f"Insufficient stock for item id {item_id}. "
                f"On hand: {on_hand}, requested: {quantity}."
            )

        layers = cost_layer_repo.list_for_item(
            company_id, item_id,
            with_remaining_only=True,
            location_id=location_id,
            location_aware=True,
            batch_id=batch_id,
            batch_aware=batch_id is not None,
        )
        remaining_to_consume = quantity
        total_value = Decimal("0.00")
        for layer in layers:
            if remaining_to_consume <= Decimal("0"):
                break
            consumed = min(remaining_to_consume, layer.quantity_remaining)
            consumed_value = quantize_amount(consumed * layer.unit_cost)
            total_value += consumed_value
            layer.quantity_remaining -= consumed
            cost_layer_repo.save(layer)
            consumption_repo.add(CostLayerConsumption(
                source_layer_id=layer.id,
                consuming_doc_line_id=doc_line_id,
                consumed_quantity=consumed,
                consumed_value=consumed_value,
                posting_date=posting_date,
            ))
            remaining_to_consume -= consumed

        return quantize_amount(total_value)


class FefoCostingStrategy:
    """Consume stock by earliest batch expiry first, then layer age."""

    def consume(
        self,
        *,
        cost_layer_repo: InventoryCostLayerRepository,
        consumption_repo: CostLayerConsumptionRepository,
        company_id: int,
        item_id: int,
        location_id: int | None,
        batch_id: int | None,
        quantity: Decimal,
        doc_line_id: int,
        posting_date: date,
    ) -> Decimal:
        on_hand = cost_layer_repo.get_stock_on_hand(
            company_id,
            item_id,
            location_id=location_id,
            location_aware=True,
            batch_id=batch_id,
            batch_aware=batch_id is not None,
        )
        if quantity > on_hand:
            raise ValidationError(
                f"Insufficient stock for item id {item_id}. "
                f"On hand: {on_hand}, requested: {quantity}."
            )

        layers = cost_layer_repo.list_for_item_fefo(
            company_id,
            item_id,
            with_remaining_only=True,
            location_id=location_id,
            location_aware=True,
            batch_id=batch_id,
            batch_aware=batch_id is not None,
        )
        remaining_to_consume = quantity
        total_value = Decimal("0.00")
        for layer in layers:
            if remaining_to_consume <= Decimal("0"):
                break
            consumed = min(remaining_to_consume, layer.quantity_remaining)
            consumed_value = quantize_amount(consumed * layer.unit_cost)
            total_value += consumed_value
            layer.quantity_remaining -= consumed
            cost_layer_repo.save(layer)
            consumption_repo.add(CostLayerConsumption(
                source_layer_id=layer.id,
                consuming_doc_line_id=doc_line_id,
                consumed_quantity=consumed,
                consumed_value=consumed_value,
                posting_date=posting_date,
            ))
            remaining_to_consume -= consumed

        return quantize_amount(total_value)


class StandardCostStrategy:
    """Issue stock at the item's ``standard_cost``.

    The weighted-average deduction is still used for layer-tracking purposes
    (same as WAC), but the *journal value* uses ``standard_cost``. The
    difference between the standard value and the layer-weighted value is a
    **Purchase Price Variance** posted to the caller's variance account.

    This strategy returns ``(total_value_at_standard, ppc_variance)``.
    Callers that do not need the variance (e.g. legacy adjustment paths) may
    call ``consume(...)`` which returns only the standard value; the variance
    is recorded but the caller is responsible for posting it.
    """

    def consume(
        self,
        *,
        cost_layer_repo: InventoryCostLayerRepository,
        consumption_repo: CostLayerConsumptionRepository,
        company_id: int,
        item_id: int,
        location_id: int | None,
        batch_id: int | None,
        quantity: Decimal,
        doc_line_id: int,
        posting_date: date,
        standard_cost: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Returns (value_at_standard, purchase_price_variance).

        ``purchase_price_variance`` is positive when actual cost > standard
        cost (unfavourable). Callers should post this to a PPV GL account.
        """
        on_hand = cost_layer_repo.get_stock_on_hand(
            company_id,
            item_id,
            location_id=location_id,
            location_aware=True,
            batch_id=batch_id,
            batch_aware=batch_id is not None,
        )
        if quantity > on_hand:
            raise ValidationError(
                f"Insufficient stock for item id {item_id}. "
                f"On hand: {on_hand}, requested: {quantity}."
            )

        # Consume layers at their own unit cost (FIFO order) for deduction.
        layers = cost_layer_repo.list_for_item(
            company_id, item_id,
            with_remaining_only=True,
            location_id=location_id,
            location_aware=True,
            batch_id=batch_id,
            batch_aware=batch_id is not None,
        )
        remaining_to_consume = quantity
        actual_value = Decimal("0.00")
        for layer in layers:
            if remaining_to_consume <= Decimal("0"):
                break
            consumed = min(remaining_to_consume, layer.quantity_remaining)
            consumed_value = quantize_amount(consumed * layer.unit_cost)
            actual_value += consumed_value
            layer.quantity_remaining -= consumed
            cost_layer_repo.save(layer)
            consumption_repo.add(CostLayerConsumption(
                source_layer_id=layer.id,
                consuming_doc_line_id=doc_line_id,
                consumed_quantity=consumed,
                consumed_value=consumed_value,
                posting_date=posting_date,
            ))
            remaining_to_consume -= consumed

        standard_value = quantize_amount(quantity * standard_cost)
        variance = quantize_amount(actual_value - standard_value)
        return standard_value, variance


class CostingStrategyRouter:
    """Dispatch to the correct costing strategy based on item costing method.

    Usage (from posting service)::

        value = CostingStrategyRouter.consume_for_issue(
            costing_method_code=item.inventory_cost_method_code,
            standard_cost=item.standard_cost,
            cost_layer_repo=cost_layer_repo,
            consumption_repo=consumption_repo,
            company_id=company_id,
            item_id=item.id,
            location_id=doc.location_id,
            quantity=qty,
            doc_line_id=doc_line.id,
            posting_date=doc.document_date,
        )

    Returns ``(consumed_value, ppv_variance)`` — variance is ``Decimal('0.00')``
    for WAC and FIFO. The caller decides whether to post the variance.
    """

    _wac = WeightedAverageCostingStrategy()
    _fifo = FifoCostingStrategy()
    _fefo = FefoCostingStrategy()
    _standard = StandardCostStrategy()

    @classmethod
    def consume_for_issue(
        cls,
        *,
        costing_method_code: str,
        standard_cost: Decimal | None,
        cost_layer_repo: InventoryCostLayerRepository,
        consumption_repo: CostLayerConsumptionRepository,
        company_id: int,
        item_id: int,
        location_id: int | None,
        quantity: Decimal,
        doc_line_id: int,
        posting_date: date,
        batch_id: int | None = None,
    ) -> tuple[Decimal, Decimal]:
        """Returns ``(consumed_value, ppv_variance)``."""
        kwargs = dict(
            cost_layer_repo=cost_layer_repo,
            consumption_repo=consumption_repo,
            company_id=company_id,
            item_id=item_id,
            location_id=location_id,
            batch_id=batch_id,
            quantity=quantity,
            doc_line_id=doc_line_id,
            posting_date=posting_date,
        )
        if costing_method_code == "fifo":
            value = cls._fifo.consume(**kwargs)
            return value, Decimal("0.00")
        if costing_method_code == "fefo":
            value = cls._fefo.consume(**kwargs)
            return value, Decimal("0.00")
        elif costing_method_code == "standard_cost":
            if not standard_cost:
                raise ValidationError(
                    f"Item id {item_id} uses standard costing but has no standard_cost set."
                )
            value, variance = cls._standard.consume(**kwargs, standard_cost=standard_cost)
            return value, variance
        else:
            # weighted_average (default)
            value = cls._wac.consume(**kwargs)
            return value, Decimal("0.00")
