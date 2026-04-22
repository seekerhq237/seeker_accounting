from __future__ import annotations

from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.inventory_valuation_dto import (
    InventoryStockPositionDTO,
    InventoryValuationSummaryDTO,
)
from seeker_accounting.modules.inventory.repositories.inventory_cost_layer_repository import (
    InventoryCostLayerRepository,
)
from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.platform.exceptions import NotFoundError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
ItemRepositoryFactory = Callable[[Session], ItemRepository]
InventoryCostLayerRepositoryFactory = Callable[[Session], InventoryCostLayerRepository]


class InventoryValuationService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        item_repository_factory: ItemRepositoryFactory,
        inventory_cost_layer_repository_factory: InventoryCostLayerRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._item_repository_factory = item_repository_factory
        self._inventory_cost_layer_repository_factory = inventory_cost_layer_repository_factory

    def get_stock_position(self, company_id: int, item_id: int) -> InventoryStockPositionDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            item_repo = self._item_repository_factory(uow.session)
            cost_repo = self._inventory_cost_layer_repository_factory(uow.session)

            item = item_repo.get_by_id(company_id, item_id)
            if item is None:
                raise NotFoundError(f"Item with id {item_id} was not found.")

            qty = cost_repo.get_stock_on_hand(company_id, item_id)
            total_val = cost_repo.get_total_value(company_id, item_id)
            avg_cost = cost_repo.get_weighted_average_cost(company_id, item_id)

            is_low = False
            if item.reorder_level_quantity is not None and qty <= item.reorder_level_quantity:
                is_low = True

            return InventoryStockPositionDTO(
                item_id=item.id,
                item_code=item.item_code,
                item_name=item.item_name,
                unit_of_measure_code=item.unit_of_measure_code,
                quantity_on_hand=qty,
                total_value=total_val,
                weighted_average_cost=avg_cost,
                reorder_level_quantity=item.reorder_level_quantity,
                is_low_stock=is_low,
            )

    def list_stock_positions(
        self,
        company_id: int,
        low_stock_only: bool = False,
    ) -> list[InventoryStockPositionDTO]:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            item_repo = self._item_repository_factory(uow.session)
            cost_repo = self._inventory_cost_layer_repository_factory(uow.session)

            # Get all stock items
            items = item_repo.list_by_company(company_id, active_only=True, item_type_code="stock")

            # Get aggregated stock data
            stock_map: dict[int, tuple[Decimal, Decimal]] = {}
            for item_id, qty, val in cost_repo.list_all_items_stock(company_id):
                stock_map[item_id] = (qty, val)

            positions: list[InventoryStockPositionDTO] = []
            for item in items:
                qty, total_val = stock_map.get(item.id, (Decimal("0"), Decimal("0")))
                avg_cost = (total_val / qty).quantize(Decimal("0.0001")) if qty > 0 else None

                is_low = False
                if item.reorder_level_quantity is not None and qty <= item.reorder_level_quantity:
                    is_low = True

                if low_stock_only and not is_low:
                    continue

                positions.append(InventoryStockPositionDTO(
                    item_id=item.id,
                    item_code=item.item_code,
                    item_name=item.item_name,
                    unit_of_measure_code=item.unit_of_measure_code,
                    quantity_on_hand=qty,
                    total_value=total_val,
                    weighted_average_cost=avg_cost,
                    reorder_level_quantity=item.reorder_level_quantity,
                    is_low_stock=is_low,
                ))

            return positions

    def get_inventory_valuation_summary(self, company_id: int) -> InventoryValuationSummaryDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            item_repo = self._item_repository_factory(uow.session)
            cost_repo = self._inventory_cost_layer_repository_factory(uow.session)

            items = item_repo.list_by_company(company_id, active_only=True, item_type_code="stock")
            stock_map: dict[int, tuple[Decimal, Decimal]] = {}
            for item_id, qty, val in cost_repo.list_all_items_stock(company_id):
                stock_map[item_id] = (qty, val)

            total_items = 0
            total_qty = Decimal("0")
            total_val = Decimal("0")
            low_stock_count = 0

            for item in items:
                qty, val = stock_map.get(item.id, (Decimal("0"), Decimal("0")))
                if qty > 0:
                    total_items += 1
                    total_qty += qty
                    total_val += val

                if item.reorder_level_quantity is not None and qty <= item.reorder_level_quantity:
                    low_stock_count += 1

            return InventoryValuationSummaryDTO(
                total_items_with_stock=total_items,
                total_quantity_on_hand=total_qty,
                total_inventory_value=total_val,
                low_stock_item_count=low_stock_count,
            )

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")
