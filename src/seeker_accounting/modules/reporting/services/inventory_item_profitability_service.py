"""Inventory Item Profitability Report Service — gross margin per item.

Joins:
  - sales invoice lines  (revenue, COGS)
  - stock ledger issues  (actual COGS from stock ledger, if cogs_amount is stamped)

Returns gross margin per item, optionally filtered by customer or period.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.inventory.models.item import Item
from seeker_accounting.platform.exceptions import ValidationError

_ZERO = Decimal("0")


@dataclass
class ItemProfitabilityFilterDTO:
    company_id: int
    date_from: date | None = None
    date_to: date | None = None
    customer_id: int | None = None
    item_id: int | None = None


@dataclass
class ItemProfitabilityRowDTO:
    item_id: int
    item_code: str
    item_name: str
    total_revenue: Decimal
    total_cogs: Decimal
    gross_margin: Decimal
    gross_margin_pct: Decimal


@dataclass
class ItemProfitabilityReportDTO:
    filters: ItemProfitabilityFilterDTO
    rows: list[ItemProfitabilityRowDTO]
    total_revenue: Decimal
    total_cogs: Decimal
    total_gross_margin: Decimal
    overall_margin_pct: Decimal


class InventoryItemProfitabilityService:
    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = unit_of_work_factory

    def get_report(self, filters: ItemProfitabilityFilterDTO) -> ItemProfitabilityReportDTO:
        if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
            raise ValidationError("date_from must be on or before date_to.")

        with self._uow_factory() as uow:
            return self._build(uow.session, filters)

    def _build(self, session: Session, f: ItemProfitabilityFilterDTO) -> ItemProfitabilityReportDTO:
        from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice
        from seeker_accounting.modules.sales.models.sales_invoice_line import SalesInvoiceLine

        items_map = {
            row.id: (row.item_code, row.item_name)
            for row in session.scalars(
                select(Item).where(Item.company_id == f.company_id)
            )
        }

        # Revenue and COGS from stamped invoice lines
        stmt = (
            select(
                SalesInvoiceLine.item_id,
                func.sum(SalesInvoiceLine.subtotal_amount).label("revenue"),
                func.sum(
                    func.coalesce(SalesInvoiceLine.cogs_amount, 0)
                ).label("cogs"),
            )
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .where(
                SalesInvoice.company_id == f.company_id,
                SalesInvoice.status_code == "posted",
                SalesInvoiceLine.item_id.isnot(None),
                *(
                    [SalesInvoice.invoice_date >= f.date_from]
                    if f.date_from
                    else []
                ),
                *(
                    [SalesInvoice.invoice_date <= f.date_to]
                    if f.date_to
                    else []
                ),
                *(
                    [SalesInvoice.customer_id == f.customer_id]
                    if f.customer_id
                    else []
                ),
                *(
                    [SalesInvoiceLine.item_id == f.item_id]
                    if f.item_id
                    else []
                ),
            )
            .group_by(SalesInvoiceLine.item_id)
            .order_by(func.sum(SalesInvoiceLine.subtotal_amount).desc())
        )

        rows: list[ItemProfitabilityRowDTO] = []
        total_rev = _ZERO
        total_cogs = _ZERO

        for r in session.execute(stmt):
            rev = Decimal(str(r.revenue or 0))
            cogs = Decimal(str(r.cogs or 0))
            gm = rev - cogs
            gm_pct = (gm / rev * 100).quantize(Decimal("0.01")) if rev else _ZERO
            code, name = items_map.get(r.item_id, ("", ""))
            rows.append(
                ItemProfitabilityRowDTO(
                    item_id=r.item_id,
                    item_code=code,
                    item_name=name,
                    total_revenue=rev,
                    total_cogs=cogs,
                    gross_margin=gm,
                    gross_margin_pct=gm_pct,
                )
            )
            total_rev += rev
            total_cogs += cogs

        overall_gm = total_rev - total_cogs
        overall_pct = (overall_gm / total_rev * 100).quantize(Decimal("0.01")) if total_rev else _ZERO

        return ItemProfitabilityReportDTO(
            filters=f,
            rows=rows,
            total_revenue=total_rev,
            total_cogs=total_cogs,
            total_gross_margin=overall_gm,
            overall_margin_pct=overall_pct,
        )
