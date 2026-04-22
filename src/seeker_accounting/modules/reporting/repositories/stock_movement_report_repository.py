from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument
from seeker_accounting.modules.inventory.models.inventory_document_line import InventoryDocumentLine
from seeker_accounting.modules.inventory.models.inventory_location import InventoryLocation
from seeker_accounting.modules.inventory.models.item import Item
from seeker_accounting.modules.reporting.dto.stock_movement_report_dto import (
    StockMovementReportFilterDTO,
)


@dataclass(frozen=True, slots=True)
class StockMovementItemIdentityRow:
    item_id: int
    item_code: str
    item_name: str
    unit_of_measure_code: str


@dataclass(frozen=True, slots=True)
class StockMovementSummaryQueryRow:
    item_id: int
    item_code: str
    item_name: str
    unit_of_measure_code: str
    opening_quantity: Decimal
    inward_quantity: Decimal
    outward_quantity: Decimal
    movement_count: int


@dataclass(frozen=True, slots=True)
class StockMovementDetailQueryRow:
    document_line_id: int
    inventory_document_id: int
    posted_journal_entry_id: int | None
    item_id: int
    item_code: str
    item_name: str
    document_date: date
    document_number: str
    document_type_code: str
    reference_number: str | None
    location_id: int | None
    location_code: str | None
    location_name: str | None
    quantity: Decimal
    unit_cost: Decimal | None
    line_amount: Decimal | None


class StockMovementReportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_item_identity(self, company_id: int, item_id: int) -> StockMovementItemIdentityRow | None:
        stmt = (
            select(
                Item.id,
                Item.item_code,
                Item.item_name,
                Item.unit_of_measure_code,
            )
            .where(Item.company_id == company_id, Item.id == item_id)
        )
        row = self._session.execute(stmt).one_or_none()
        if row is None:
            return None
        return StockMovementItemIdentityRow(
            item_id=row.id,
            item_code=row.item_code,
            item_name=row.item_name,
            unit_of_measure_code=row.unit_of_measure_code,
        )

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

    def list_summary_rows(
        self,
        filter_dto: StockMovementReportFilterDTO,
    ) -> list[StockMovementSummaryQueryRow]:
        signed_quantity = self._signed_quantity_expr()
        opening_condition = self._opening_condition(filter_dto.date_from)
        period_condition = self._period_condition(filter_dto.date_from, filter_dto.date_to)

        stmt = (
            select(
                Item.id.label("item_id"),
                Item.item_code,
                Item.item_name,
                Item.unit_of_measure_code,
                func.coalesce(
                    func.sum(case((opening_condition, signed_quantity), else_=0)),
                    0,
                ).label("opening_quantity"),
                func.coalesce(
                    func.sum(case((and_(period_condition, signed_quantity > 0), signed_quantity), else_=0)),
                    0,
                ).label("inward_quantity"),
                func.coalesce(
                    func.sum(case((and_(period_condition, signed_quantity < 0), -signed_quantity), else_=0)),
                    0,
                ).label("outward_quantity"),
                func.coalesce(
                    func.sum(case((period_condition, 1), else_=0)),
                    0,
                ).label("movement_count"),
            )
            .join(InventoryDocumentLine, InventoryDocumentLine.item_id == Item.id)
            .join(
                InventoryDocument,
                InventoryDocument.id == InventoryDocumentLine.inventory_document_id,
            )
            .where(*self._base_conditions(filter_dto))
            .group_by(Item.id, Item.item_code, Item.item_name, Item.unit_of_measure_code)
            .order_by(Item.item_code.asc())
        )

        rows: list[StockMovementSummaryQueryRow] = []
        for row in self._session.execute(stmt):
            rows.append(
                StockMovementSummaryQueryRow(
                    item_id=row.item_id,
                    item_code=row.item_code,
                    item_name=row.item_name,
                    unit_of_measure_code=row.unit_of_measure_code,
                    opening_quantity=self._to_quantity(row.opening_quantity),
                    inward_quantity=self._to_quantity(row.inward_quantity),
                    outward_quantity=self._to_quantity(row.outward_quantity),
                    movement_count=int(row.movement_count or 0),
                )
            )
        return rows

    def list_item_detail_rows(
        self,
        filter_dto: StockMovementReportFilterDTO,
        item_id: int,
    ) -> list[StockMovementDetailQueryRow]:
        # Use base_quantity (stock UoM) if available, otherwise fall back to quantity for backward compatibility
        qty_expr = func.coalesce(InventoryDocumentLine.base_quantity, InventoryDocumentLine.quantity)
        stmt = (
            select(
                InventoryDocumentLine.id.label("document_line_id"),
                InventoryDocument.id.label("inventory_document_id"),
                InventoryDocument.posted_journal_entry_id,
                Item.id.label("item_id"),
                Item.item_code,
                Item.item_name,
                InventoryDocument.document_date,
                InventoryDocument.document_number,
                InventoryDocument.document_type_code,
                InventoryDocument.reference_number,
                InventoryLocation.id.label("location_id"),
                InventoryLocation.code.label("location_code"),
                InventoryLocation.name.label("location_name"),
                qty_expr.label("quantity"),
                InventoryDocumentLine.unit_cost,
                InventoryDocumentLine.line_amount,
            )
            .join(Item, Item.id == InventoryDocumentLine.item_id)
            .join(
                InventoryDocument,
                InventoryDocument.id == InventoryDocumentLine.inventory_document_id,
            )
            .outerjoin(
                InventoryLocation,
                InventoryLocation.id == InventoryDocument.location_id,
            )
            .where(*self._base_conditions(filter_dto), Item.id == item_id)
        )

        if filter_dto.date_from is not None:
            stmt = stmt.where(InventoryDocument.document_date >= filter_dto.date_from)
        if filter_dto.date_to is not None:
            stmt = stmt.where(InventoryDocument.document_date <= filter_dto.date_to)

        stmt = stmt.order_by(
            InventoryDocument.document_date.asc(),
            InventoryDocument.id.asc(),
            InventoryDocumentLine.line_number.asc(),
            InventoryDocumentLine.id.asc(),
        )

        rows: list[StockMovementDetailQueryRow] = []
        for row in self._session.execute(stmt):
            rows.append(
                StockMovementDetailQueryRow(
                    document_line_id=row.document_line_id,
                    inventory_document_id=row.inventory_document_id,
                    posted_journal_entry_id=row.posted_journal_entry_id,
                    item_id=row.item_id,
                    item_code=row.item_code,
                    item_name=row.item_name,
                    document_date=row.document_date,
                    document_number=row.document_number,
                    document_type_code=row.document_type_code,
                    reference_number=row.reference_number,
                    location_id=row.location_id,
                    location_code=row.location_code,
                    location_name=row.location_name,
                    quantity=self._to_quantity(row.quantity),
                    unit_cost=self._to_decimal(row.unit_cost),
                    line_amount=self._to_amount(row.line_amount),
                )
            )
        return rows

    def get_opening_quantity(
        self,
        filter_dto: StockMovementReportFilterDTO,
        item_id: int,
    ) -> Decimal:
        if filter_dto.date_from is None:
            return Decimal("0.0000")

        signed_quantity = self._signed_quantity_expr()
        stmt = (
            select(func.coalesce(func.sum(signed_quantity), 0))
            .join(Item, Item.id == InventoryDocumentLine.item_id)
            .join(
                InventoryDocument,
                InventoryDocument.id == InventoryDocumentLine.inventory_document_id,
            )
            .where(
                *self._base_conditions(filter_dto),
                Item.id == item_id,
                InventoryDocument.document_date < filter_dto.date_from,
            )
        )
        return self._to_quantity(self._session.execute(stmt).scalar_one())

    def _base_conditions(self, filter_dto: StockMovementReportFilterDTO) -> list[object]:
        conditions: list[object] = [
            Item.company_id == filter_dto.company_id,
            InventoryDocument.company_id == filter_dto.company_id,
            InventoryDocument.status_code == "posted",
        ]
        if filter_dto.item_id is not None:
            conditions.append(Item.id == filter_dto.item_id)
        if filter_dto.location_id is not None:
            conditions.append(InventoryDocument.location_id == filter_dto.location_id)
        if filter_dto.date_to is not None:
            conditions.append(InventoryDocument.document_date <= filter_dto.date_to)
        return conditions

    @staticmethod
    def _signed_quantity_expr():
        # Use base_quantity (stock UoM) if available, otherwise fall back to quantity for backward compatibility
        qty_expr = func.coalesce(InventoryDocumentLine.base_quantity, InventoryDocumentLine.quantity)
        return case(
            (InventoryDocument.document_type_code == "receipt", qty_expr),
            (InventoryDocument.document_type_code == "issue", -qty_expr),
            else_=qty_expr,
        )

    @staticmethod
    def _opening_condition(date_from: date | None):
        if date_from is None:
            return False
        return InventoryDocument.document_date < date_from

    @staticmethod
    def _period_condition(date_from: date | None, date_to: date | None):
        conditions: list[object] = []
        if date_from is not None:
            conditions.append(InventoryDocument.document_date >= date_from)
        if date_to is not None:
            conditions.append(InventoryDocument.document_date <= date_to)
        if not conditions:
            return True
        return and_(*conditions)

    @staticmethod
    def _to_quantity(value: object) -> Decimal:
        return Decimal(str(value or 0)).quantize(Decimal("0.0001"))

    @staticmethod
    def _to_amount(value: object) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value)).quantize(Decimal("0.01"))

    @staticmethod
    def _to_decimal(value: object) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))
