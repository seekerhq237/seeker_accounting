from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument
from seeker_accounting.modules.inventory.models.inventory_document_line import InventoryDocumentLine
from seeker_accounting.modules.inventory.models.inventory_location import InventoryLocation
from seeker_accounting.modules.inventory.models.item import Item
from seeker_accounting.modules.reporting.dto.stock_valuation_report_dto import (
    StockValuationReportFilterDTO,
)


@dataclass(frozen=True, slots=True)
class StockValuationQueryRow:
    item_id: int
    item_code: str
    item_name: str
    unit_of_measure_code: str
    inventory_cost_method_code: str | None
    quantity_on_hand: Decimal
    total_value: Decimal
    missing_value_count: int


class StockValuationReportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_valuation_rows(
        self,
        filter_dto: StockValuationReportFilterDTO,
    ) -> list[StockValuationQueryRow]:
        signed_quantity = self._signed_quantity_expr()
        signed_value = self._signed_value_expr()

        stmt = (
            select(
                Item.id.label("item_id"),
                Item.item_code,
                Item.item_name,
                Item.unit_of_measure_code,
                Item.inventory_cost_method_code,
                func.coalesce(func.sum(signed_quantity), 0).label("quantity_on_hand"),
                func.coalesce(func.sum(signed_value), 0).label("total_value"),
                func.coalesce(
                    func.sum(case((InventoryDocumentLine.line_amount.is_(None), 1), else_=0)),
                    0,
                ).label("missing_value_count"),
            )
            .join(InventoryDocumentLine, InventoryDocumentLine.item_id == Item.id)
            .join(
                InventoryDocument,
                InventoryDocument.id == InventoryDocumentLine.inventory_document_id,
            )
            .where(*self._base_conditions(filter_dto))
            .group_by(
                Item.id,
                Item.item_code,
                Item.item_name,
                Item.unit_of_measure_code,
                Item.inventory_cost_method_code,
            )
            .order_by(Item.item_code.asc())
        )

        rows: list[StockValuationQueryRow] = []
        for row in self._session.execute(stmt):
            rows.append(
                StockValuationQueryRow(
                    item_id=row.item_id,
                    item_code=row.item_code,
                    item_name=row.item_name,
                    unit_of_measure_code=row.unit_of_measure_code,
                    inventory_cost_method_code=row.inventory_cost_method_code,
                    quantity_on_hand=self._to_quantity(row.quantity_on_hand),
                    total_value=self._to_amount(row.total_value),
                    missing_value_count=int(row.missing_value_count or 0),
                )
            )
        return rows

    def get_location_label(self, company_id: int, location_id: int) -> str | None:
        stmt = (
            select(InventoryLocation.code, InventoryLocation.name)
            .where(
                InventoryLocation.company_id == company_id,
                InventoryLocation.id == location_id,
            )
        )
        row = self._session.execute(stmt).one_or_none()
        if row is None:
            return None
        return f"{row.code} | {row.name}"

    def _base_conditions(self, filter_dto: StockValuationReportFilterDTO) -> list[object]:
        conditions: list[object] = [
            Item.company_id == filter_dto.company_id,
            InventoryDocument.company_id == filter_dto.company_id,
            InventoryDocument.status_code == "posted",
        ]
        if filter_dto.item_id is not None:
            conditions.append(Item.id == filter_dto.item_id)
        if filter_dto.location_id is not None:
            conditions.append(InventoryDocument.location_id == filter_dto.location_id)
        if filter_dto.as_of_date is not None:
            conditions.append(InventoryDocument.document_date <= filter_dto.as_of_date)
        return conditions

    @staticmethod
    def _signed_quantity_expr():
        return case(
            (InventoryDocument.document_type_code == "receipt", InventoryDocumentLine.quantity),
            (InventoryDocument.document_type_code == "issue", -InventoryDocumentLine.quantity),
            else_=InventoryDocumentLine.quantity,
        )

    @staticmethod
    def _signed_value_expr():
        sign_multiplier = case(
            (InventoryDocument.document_type_code == "issue", -1),
            (
                (InventoryDocument.document_type_code == "adjustment") & (InventoryDocumentLine.quantity < 0),
                -1,
            ),
            else_=1,
        )
        return sign_multiplier * func.coalesce(InventoryDocumentLine.line_amount, 0)

    @staticmethod
    def _to_quantity(value: object) -> Decimal:
        return Decimal(str(value or 0)).quantize(Decimal("0.0001"))

    @staticmethod
    def _to_amount(value: object) -> Decimal:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
