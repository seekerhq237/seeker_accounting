"""Reorder Planning Service — P6 / Slice 7.2.

Manages item reorder profiles and generates purchase suggestions when
on-hand + on-order falls below the minimum quantity threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.inventory.models.item_reorder_profile import ItemReorderProfile
from seeker_accounting.modules.inventory.repositories.item_reorder_profile_repository import (
    ItemReorderProfileRepository,
)
from seeker_accounting.modules.inventory.repositories.stock_ledger_balance_repository import (
    StockLedgerBalanceRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

_ZERO = Decimal("0")

ItemReorderProfileRepositoryFactory = Callable[[Session], ItemReorderProfileRepository]
StockLedgerBalanceRepositoryFactory = Callable[[Session], StockLedgerBalanceRepository]


@dataclass
class ReorderProfileDTO:
    id: int | None
    company_id: int
    item_id: int
    location_id: int | None
    min_qty: Decimal
    max_qty: Decimal | None
    safety_stock_qty: Decimal
    lead_time_override_days: int | None
    preferred_supplier_id: int | None


@dataclass
class ReorderSuggestionDTO:
    item_id: int
    item_code: str
    item_name: str
    location_id: int | None
    on_hand_qty: Decimal
    on_order_qty: Decimal
    min_qty: Decimal
    suggested_order_qty: Decimal
    preferred_supplier_id: int | None
    lead_time_days: int | None


class ReorderPlanningService:
    """Manages reorder profiles and generates purchase suggestions."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        reorder_profile_repository_factory: ItemReorderProfileRepositoryFactory,
        stock_ledger_balance_repository_factory: StockLedgerBalanceRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._profile_repo_factory = reorder_profile_repository_factory
        self._balance_repo_factory = stock_ledger_balance_repository_factory

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------

    def list_profiles(self, company_id: int) -> list[ReorderProfileDTO]:
        with self._uow_factory() as uow:
            repo = self._profile_repo_factory(uow.session)
            rows = repo.list_by_company(company_id)
            return [_profile_to_dto(r) for r in rows]

    def save_profile(self, cmd: ReorderProfileDTO) -> int:
        with self._uow_factory() as uow:
            repo = self._profile_repo_factory(uow.session)

            if cmd.id is not None:
                row = repo.get(cmd.id)
                if row is None or row.company_id != cmd.company_id:
                    raise NotFoundError(f"Reorder profile {cmd.id} not found.")
            else:
                existing = repo.get_for_item_location(
                    cmd.company_id, cmd.item_id, cmd.location_id
                )
                if existing is not None:
                    raise ConflictError(
                        "A reorder profile already exists for this item/location."
                    )
                row = ItemReorderProfile(company_id=cmd.company_id)
                repo.add(row)

            row.item_id = cmd.item_id
            row.location_id = cmd.location_id
            row.min_qty = cmd.min_qty
            row.max_qty = cmd.max_qty
            row.safety_stock_qty = cmd.safety_stock_qty
            row.lead_time_override_days = cmd.lead_time_override_days
            row.preferred_supplier_id = cmd.preferred_supplier_id

            uow.session.flush()
            uow.commit()
            return row.id

    def delete_profile(self, company_id: int, profile_id: int) -> None:
        with self._uow_factory() as uow:
            repo = self._profile_repo_factory(uow.session)
            row = repo.get(profile_id)
            if row is None or row.company_id != company_id:
                raise NotFoundError(f"Reorder profile {profile_id} not found.")
            repo.delete(row)
            uow.commit()

    # ------------------------------------------------------------------
    # Suggestion generation
    # ------------------------------------------------------------------

    def generate_suggestions(
        self, company_id: int, location_id: int | None = None
    ) -> list[ReorderSuggestionDTO]:
        """Return items where on-hand falls below min_qty threshold."""
        with self._uow_factory() as uow:
            profile_repo = self._profile_repo_factory(uow.session)
            balance_repo = self._balance_repo_factory(uow.session)

            profiles = profile_repo.list_by_company(company_id)
            if location_id is not None:
                profiles = [p for p in profiles if p.location_id == location_id]

            items_by_id = self._load_items_map(uow.session, company_id)
            on_order_by_item = self._compute_on_order(uow.session, company_id)

            suggestions = []
            for profile in profiles:
                balance = balance_repo.get(company_id, profile.item_id, profile.location_id)
                on_hand = balance.quantity if balance else _ZERO
                on_order = on_order_by_item.get(profile.item_id, _ZERO)
                available = on_hand + on_order

                if available >= profile.min_qty:
                    continue

                # Suggest up to max_qty or min_qty * 2 as a sensible default
                target_qty = profile.max_qty or (profile.min_qty * Decimal("2"))
                suggest_qty = target_qty - available

                item = items_by_id.get(profile.item_id)
                suggestions.append(
                    ReorderSuggestionDTO(
                        item_id=profile.item_id,
                        item_code=item.item_code if item else str(profile.item_id),
                        item_name=item.item_name if item else "",
                        location_id=profile.location_id,
                        on_hand_qty=on_hand,
                        on_order_qty=on_order,
                        min_qty=profile.min_qty,
                        suggested_order_qty=suggest_qty if suggest_qty > _ZERO else _ZERO,
                        preferred_supplier_id=profile.preferred_supplier_id,
                        lead_time_days=profile.lead_time_override_days,
                    )
                )
            return suggestions

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_items_map(self, session: Session, company_id: int) -> dict:
        from seeker_accounting.modules.inventory.models.item import Item
        stmt = select(Item).where(Item.company_id == company_id)
        return {item.id: item for item in session.scalars(stmt)}

    def _compute_on_order(self, session: Session, company_id: int) -> dict[int, Decimal]:
        """Sum un-received quantity from approved/open purchase order lines."""
        from seeker_accounting.modules.purchases.models.purchase_order import PurchaseOrder
        from seeker_accounting.modules.purchases.models.purchase_order_line import PurchaseOrderLine
        stmt = (
            select(
                PurchaseOrderLine.item_id,
                PurchaseOrderLine.quantity,
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .where(
                PurchaseOrder.company_id == company_id,
                PurchaseOrder.status_code.in_(("approved", "partially_received")),
                PurchaseOrderLine.item_id.isnot(None),
            )
        )
        on_order: dict[int, Decimal] = {}
        for row in session.execute(stmt):
            item_id = row.item_id
            qty = Decimal(str(row.quantity)) if row.quantity else _ZERO
            on_order[item_id] = on_order.get(item_id, _ZERO) + qty
        return on_order


def _profile_to_dto(row: ItemReorderProfile) -> ReorderProfileDTO:
    return ReorderProfileDTO(
        id=row.id,
        company_id=row.company_id,
        item_id=row.item_id,
        location_id=row.location_id,
        min_qty=row.min_qty,
        max_qty=row.max_qty,
        safety_stock_qty=row.safety_stock_qty,
        lead_time_override_days=row.lead_time_override_days,
        preferred_supplier_id=row.preferred_supplier_id,
    )
