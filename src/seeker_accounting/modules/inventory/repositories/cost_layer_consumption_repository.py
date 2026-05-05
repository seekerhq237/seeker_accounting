"""Immutable cost-layer consumption repository.

Consumption records are append-only facts. This repository provides write
(append) and read (lookup by layer or document line) access only. It never
updates or deletes rows.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.cost_layer_consumption import CostLayerConsumption


class CostLayerConsumptionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, consumption: CostLayerConsumption) -> None:
        self._session.add(consumption)

    def list_for_layer(self, source_layer_id: int) -> list[CostLayerConsumption]:
        stmt = (
            select(CostLayerConsumption)
            .where(CostLayerConsumption.source_layer_id == source_layer_id)
            .order_by(CostLayerConsumption.id)
        )
        return list(self._session.scalars(stmt))

    def list_for_doc_line(self, consuming_doc_line_id: int) -> list[CostLayerConsumption]:
        stmt = (
            select(CostLayerConsumption)
            .where(CostLayerConsumption.consuming_doc_line_id == consuming_doc_line_id)
            .order_by(CostLayerConsumption.id)
        )
        return list(self._session.scalars(stmt))

    def total_consumed_value_for_doc_line(self, consuming_doc_line_id: int) -> Decimal:
        rows = self.list_for_doc_line(consuming_doc_line_id)
        return sum((r.consumed_value for r in rows), Decimal("0.00"))
