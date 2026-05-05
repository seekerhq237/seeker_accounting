"""Inventory Dashboard Service — P6 / Slice 7.4.

Aggregates KPIs for the inventory dashboard page:
  - Total inventory value
  - Items below reorder level
  - Expiring batches (within N days)
  - Ageing stock (> 180 days since last movement)
  - Open GRNI balance (goods received but not yet invoiced)
  - Draft document backlog count
  - Top-5 fastest movers (by qty issued in last 30 days)
  - Top-5 slowest movers (fewest issues in last 90 days, with stock)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.inventory.models.item import Item
from seeker_accounting.modules.inventory.models.stock_ledger_balance import StockLedgerBalance
from seeker_accounting.modules.inventory.models.stock_ledger_entry import StockLedgerEntry
from seeker_accounting.modules.inventory.repositories.stock_ledger_balance_repository import (
    StockLedgerBalanceRepository,
)

_ZERO_AMT = Decimal("0.00")
_ZERO = Decimal("0")

StockLedgerBalanceRepositoryFactory = Callable[[Session], StockLedgerBalanceRepository]


@dataclass
class InventoryKpiDTO:
    total_inventory_value: Decimal
    item_count_below_reorder: int
    item_count_expiring_batches: int
    item_count_ageing_stock: int
    grni_balance: Decimal
    draft_document_count: int


@dataclass
class ItemMoverDTO:
    item_id: int
    item_code: str
    item_name: str
    quantity_moved: Decimal


@dataclass
class InventoryDashboardDTO:
    kpis: InventoryKpiDTO
    top_movers: list[ItemMoverDTO]
    slow_movers: list[ItemMoverDTO]


class InventoryDashboardService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        stock_ledger_balance_repository_factory: StockLedgerBalanceRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._balance_repo_factory = stock_ledger_balance_repository_factory

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def get_dashboard(self, company_id: int) -> InventoryDashboardDTO:
        with self._uow_factory() as uow:
            kpis = self._compute_kpis(uow.session, company_id)
            top_movers = self._top_movers(uow.session, company_id, days=30, limit=5)
            slow_movers = self._slow_movers(uow.session, company_id, days=90, limit=5)
            return InventoryDashboardDTO(
                kpis=kpis,
                top_movers=top_movers,
                slow_movers=slow_movers,
            )

    # ------------------------------------------------------------------
    # KPI helpers
    # ------------------------------------------------------------------

    def _compute_kpis(self, session: Session, company_id: int) -> InventoryKpiDTO:
        today = date.today()

        # Total inventory value
        total_val_row = session.scalar(
            select(func.coalesce(func.sum(StockLedgerBalance.value), 0)).where(
                StockLedgerBalance.company_id == company_id
            )
        )
        total_value = Decimal(str(total_val_row))

        # Items below reorder
        below_reorder = self._count_below_reorder(session, company_id)

        # Expiring batches (within 30 days)
        expiring = self._count_expiring_batches(session, company_id, horizon_days=30)

        # Ageing stock (last movement > 180 days ago)
        ageing = self._count_ageing_stock(session, company_id, threshold_days=180)

        # GRNI balance (Dr GRNI = un-cleared accrual)
        grni_balance = self._compute_grni_balance(session, company_id)

        # Draft document backlog
        from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument
        draft_count = session.scalar(
            select(func.count(InventoryDocument.id)).where(
                InventoryDocument.company_id == company_id,
                InventoryDocument.status_code == "draft",
            )
        ) or 0

        return InventoryKpiDTO(
            total_inventory_value=total_value,
            item_count_below_reorder=below_reorder,
            item_count_expiring_batches=expiring,
            item_count_ageing_stock=ageing,
            grni_balance=grni_balance,
            draft_document_count=draft_count,
        )

    def _count_below_reorder(self, session: Session, company_id: int) -> int:
        from seeker_accounting.modules.inventory.models.item_reorder_profile import ItemReorderProfile
        stmt = (
            select(func.count(ItemReorderProfile.id))
            .join(
                StockLedgerBalance,
                (StockLedgerBalance.item_id == ItemReorderProfile.item_id)
                & (StockLedgerBalance.company_id == company_id),
                isouter=True,
            )
            .where(
                ItemReorderProfile.company_id == company_id,
                func.coalesce(StockLedgerBalance.quantity, 0) < ItemReorderProfile.min_qty,
            )
        )
        return session.scalar(stmt) or 0

    def _count_expiring_batches(
        self, session: Session, company_id: int, horizon_days: int
    ) -> int:
        from seeker_accounting.modules.inventory.models.item_batch import ItemBatch
        horizon = date.today() + timedelta(days=horizon_days)
        stmt = select(func.count(ItemBatch.id)).where(
            ItemBatch.company_id == company_id,
            ItemBatch.expiry_date.isnot(None),
            ItemBatch.expiry_date <= horizon,
            ItemBatch.expiry_date >= date.today(),
        )
        return session.scalar(stmt) or 0

    def _count_ageing_stock(
        self, session: Session, company_id: int, threshold_days: int
    ) -> int:
        cutoff = datetime.utcnow() - timedelta(days=threshold_days)
        stmt = (
            select(func.count(func.distinct(StockLedgerBalance.item_id)))
            .where(
                StockLedgerBalance.company_id == company_id,
                StockLedgerBalance.quantity > 0,
            )
            .join(
                StockLedgerEntry,
                StockLedgerEntry.id == StockLedgerBalance.last_movement_id,
                isouter=True,
            )
            .where(
                func.coalesce(StockLedgerEntry.created_at, datetime(1900, 1, 1)) <= cutoff
            )
        )
        return session.scalar(stmt) or 0

    def _compute_grni_balance(self, session: Session, company_id: int) -> Decimal:
        """Approximate GRNI balance from unmatched GRN lines.

        Returns total value of goods-received-purchase lines not yet
        linked to a supplier bill line.
        """
        from seeker_accounting.modules.inventory.models.inventory_document import (
            InventoryDocument,
        )
        from seeker_accounting.modules.inventory.models.inventory_document_line import (
            InventoryDocumentLine,
        )
        from seeker_accounting.modules.inventory.models.purchase_receipt_link import (
            PurchaseBillLineReceiptLink,
        )

        # Sum of line amounts on posted GRNs
        subq = (
            select(InventoryDocumentLine.id)
            .join(
                PurchaseBillLineReceiptLink,
                PurchaseBillLineReceiptLink.inventory_document_line_id
                == InventoryDocumentLine.id,
                isouter=True,
            )
            .where(PurchaseBillLineReceiptLink.id.is_(None))
        )
        stmt = (
            select(func.coalesce(func.sum(InventoryDocumentLine.line_amount), 0))
            .join(
                InventoryDocument,
                InventoryDocument.id == InventoryDocumentLine.inventory_document_id,
            )
            .where(
                InventoryDocument.company_id == company_id,
                InventoryDocument.document_type_code == "goods_receipt_purchase",
                InventoryDocument.status_code == "posted",
                InventoryDocumentLine.id.in_(subq),
            )
        )
        result = session.scalar(stmt)
        return Decimal(str(result)) if result else _ZERO_AMT

    # ------------------------------------------------------------------
    # Mover analysis
    # ------------------------------------------------------------------

    def _top_movers(
        self, session: Session, company_id: int, days: int, limit: int
    ) -> list[ItemMoverDTO]:
        cutoff = datetime.utcnow() - timedelta(days=days)
        stmt = (
            select(
                StockLedgerEntry.item_id,
                func.sum(StockLedgerEntry.quantity).label("total_qty"),
            )
            .where(
                StockLedgerEntry.company_id == company_id,
                StockLedgerEntry.direction == -1,
                StockLedgerEntry.created_at >= cutoff,
            )
            .group_by(StockLedgerEntry.item_id)
            .order_by(func.sum(StockLedgerEntry.quantity).desc())
            .limit(limit)
        )
        items_map = self._load_items_map(session, company_id)
        return [
            ItemMoverDTO(
                item_id=row.item_id,
                item_code=items_map.get(row.item_id, {}).get("code", ""),
                item_name=items_map.get(row.item_id, {}).get("name", ""),
                quantity_moved=Decimal(str(row.total_qty or 0)),
            )
            for row in session.execute(stmt)
        ]

    def _slow_movers(
        self, session: Session, company_id: int, days: int, limit: int
    ) -> list[ItemMoverDTO]:
        cutoff = datetime.utcnow() - timedelta(days=days)
        # Items with stock but fewest issues in period
        stmt = (
            select(
                StockLedgerBalance.item_id,
                func.coalesce(
                    func.sum(
                        select(func.sum(StockLedgerEntry.quantity))
                        .where(
                            StockLedgerEntry.item_id == StockLedgerBalance.item_id,
                            StockLedgerEntry.company_id == company_id,
                            StockLedgerEntry.direction == -1,
                            StockLedgerEntry.created_at >= cutoff,
                        )
                        .scalar_subquery()
                    ),
                    0,
                ).label("issued_qty"),
            )
            .where(
                StockLedgerBalance.company_id == company_id,
                StockLedgerBalance.quantity > 0,
            )
            .group_by(StockLedgerBalance.item_id)
            .order_by(
                func.coalesce(
                    select(func.sum(StockLedgerEntry.quantity))
                    .where(
                        StockLedgerEntry.item_id == StockLedgerBalance.item_id,
                        StockLedgerEntry.company_id == company_id,
                        StockLedgerEntry.direction == -1,
                        StockLedgerEntry.created_at >= cutoff,
                    )
                    .scalar_subquery(),
                    0,
                ).asc()
            )
            .limit(limit)
        )
        items_map = self._load_items_map(session, company_id)
        return [
            ItemMoverDTO(
                item_id=row.item_id,
                item_code=items_map.get(row.item_id, {}).get("code", ""),
                item_name=items_map.get(row.item_id, {}).get("name", ""),
                quantity_moved=Decimal(str(row.issued_qty or 0)),
            )
            for row in session.execute(stmt)
        ]

    def _load_items_map(self, session: Session, company_id: int) -> dict[int, dict]:
        stmt = select(Item.id, Item.item_code, Item.item_name).where(
            Item.company_id == company_id
        )
        return {row.id: {"code": row.item_code, "name": row.item_name} for row in session.execute(stmt)}
