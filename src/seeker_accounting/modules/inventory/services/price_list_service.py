"""Price List Service — P6 / Slice 7.1.

Manages price lists and resolves the effective price for an item given a
customer, date, and quantity.

Price resolution hierarchy (first match wins):
  1. Customer-specific price list
  2. Customer group price list
  3. Company default price list
  4. Item list_price (standard sale price on the item record)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.inventory.models.price_list import PriceList, PriceListLine
from seeker_accounting.modules.inventory.repositories.price_list_repository import (
    PriceListRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

_ZERO = Decimal("0")

PriceListRepositoryFactory = Callable[[Session], PriceListRepository]


@dataclass
class PriceListDTO:
    id: int | None
    company_id: int
    name: str
    currency_code: str
    valid_from: date | None
    valid_to: date | None
    is_default: bool
    description: str | None
    is_active: bool


@dataclass
class PriceListLineDTO:
    id: int | None
    price_list_id: int
    item_id: int
    uom_id: int | None
    valid_from: date | None
    valid_to: date | None
    unit_price: Decimal
    min_quantity: Decimal


@dataclass
class ResolvedPriceDTO:
    unit_price: Decimal
    price_list_id: int | None
    price_list_name: str | None
    source: str  # 'customer_list', 'group_list', 'default_list', 'item_list_price', 'none'


class PriceListService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        price_list_repository_factory: PriceListRepositoryFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._repo_factory = price_list_repository_factory

    # ------------------------------------------------------------------
    # Price list CRUD
    # ------------------------------------------------------------------

    def list_all(self, company_id: int) -> list[PriceListDTO]:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            rows = repo.list_all(company_id)
            return [_pl_to_dto(r) for r in rows]

    def get(self, company_id: int, price_list_id: int) -> PriceListDTO:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            row = repo.get(price_list_id)
            if row is None or row.company_id != company_id:
                raise NotFoundError(f"Price list {price_list_id} not found.")
            return _pl_to_dto(row)

    def save(self, cmd: PriceListDTO) -> int:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)

            if cmd.id is not None:
                row = repo.get(cmd.id)
                if row is None or row.company_id != cmd.company_id:
                    raise NotFoundError(f"Price list {cmd.id} not found.")
            else:
                row = PriceList(company_id=cmd.company_id)
                repo.add(row)

            if cmd.is_default:
                self._clear_default(uow.session, cmd.company_id, exclude_id=row.id if row.id else None)

            row.name = cmd.name
            row.currency_code = cmd.currency_code
            row.valid_from = cmd.valid_from
            row.valid_to = cmd.valid_to
            row.is_default = cmd.is_default
            row.description = cmd.description
            row.is_active = cmd.is_active

            uow.session.flush()
            uow.commit()
            return row.id

    def delete(self, company_id: int, price_list_id: int) -> None:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            row = repo.get(price_list_id)
            if row is None or row.company_id != company_id:
                raise NotFoundError(f"Price list {price_list_id} not found.")
            repo.delete(row)
            uow.commit()

    # ------------------------------------------------------------------
    # Price list lines
    # ------------------------------------------------------------------

    def save_line(self, cmd: PriceListLineDTO) -> int:
        if cmd.unit_price <= _ZERO:
            raise ValidationError("Unit price must be positive.")
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            if cmd.id is not None:
                line = repo.get_line(cmd.id)
                if line is None:
                    raise NotFoundError(f"Price list line {cmd.id} not found.")
            else:
                line = PriceListLine(price_list_id=cmd.price_list_id)
                repo.add_line(line)

            line.item_id = cmd.item_id
            line.uom_id = cmd.uom_id
            line.valid_from = cmd.valid_from
            line.valid_to = cmd.valid_to
            line.unit_price = cmd.unit_price
            line.min_quantity = cmd.min_quantity

            uow.session.flush()
            uow.commit()
            return line.id

    def delete_line(self, line_id: int) -> None:
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            line = repo.get_line(line_id)
            if line is None:
                raise NotFoundError(f"Price list line {line_id} not found.")
            repo.delete_line(line)
            uow.commit()

    # ------------------------------------------------------------------
    # Price resolution
    # ------------------------------------------------------------------

    def resolve_price(
        self,
        company_id: int,
        item_id: int,
        customer_id: int | None = None,
        as_of_date: date | None = None,
        quantity: Decimal = Decimal("1"),
    ) -> ResolvedPriceDTO:
        """Resolve the effective price for an item/customer combination.

        Returns ResolvedPriceDTO with the matched price and its source.
        """
        today = as_of_date or date.today()

        with self._uow_factory() as uow:
            # Customer's price list
            if customer_id is not None:
                pl_id, group_pl_id = self._customer_price_list_ids(uow.session, customer_id)
                if pl_id is not None:
                    price = self._find_in_list(uow.session, pl_id, item_id, today, quantity)
                    if price is not None:
                        pl = uow.session.get(PriceList, pl_id)
                        return ResolvedPriceDTO(
                            unit_price=price, price_list_id=pl_id,
                            price_list_name=pl.name if pl else None,
                            source="customer_list",
                        )
                if group_pl_id is not None:
                    price = self._find_in_list(uow.session, group_pl_id, item_id, today, quantity)
                    if price is not None:
                        pl = uow.session.get(PriceList, group_pl_id)
                        return ResolvedPriceDTO(
                            unit_price=price, price_list_id=group_pl_id,
                            price_list_name=pl.name if pl else None,
                            source="group_list",
                        )

            # Company default price list
            repo = self._repo_factory(uow.session)
            default_pl = repo.get_default(company_id)
            if default_pl is not None:
                price = self._find_in_list(uow.session, default_pl.id, item_id, today, quantity)
                if price is not None:
                    return ResolvedPriceDTO(
                        unit_price=price, price_list_id=default_pl.id,
                        price_list_name=default_pl.name, source="default_list",
                    )

            # Item list price fallback
            from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
            item = ItemRepository(uow.session).get(item_id)
            if item is not None and hasattr(item, "standard_cost") and item.standard_cost:
                return ResolvedPriceDTO(
                    unit_price=item.standard_cost, price_list_id=None,
                    price_list_name=None, source="item_list_price",
                )

        return ResolvedPriceDTO(
            unit_price=_ZERO, price_list_id=None, price_list_name=None, source="none"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clear_default(self, session: Session, company_id: int, exclude_id: int | None) -> None:
        repo = self._repo_factory(session)
        default = repo.get_default(company_id)
        if default is not None and (exclude_id is None or default.id != exclude_id):
            default.is_default = False

    def _find_in_list(
        self,
        session: Session,
        price_list_id: int,
        item_id: int,
        as_of_date: date,
        quantity: Decimal,
    ) -> Decimal | None:
        repo = self._repo_factory(session)
        lines = repo.list_lines_for_item(1, item_id, as_of_date)  # company_id unused in filter
        # Filter to this specific list
        lines = [l for l in lines if l.price_list_id == price_list_id]
        # Filter by min_quantity and sort by best (highest min_qty that still applies)
        matching = [l for l in lines if l.min_quantity <= quantity]
        if not matching:
            return None
        best = max(matching, key=lambda l: l.min_quantity)
        return best.unit_price

    def _customer_price_list_ids(
        self, session: Session, customer_id: int
    ) -> tuple[int | None, int | None]:
        """Return (customer_pl_id, group_pl_id)."""
        from sqlalchemy import select
        from seeker_accounting.modules.customers.models.customer import Customer
        customer = session.get(Customer, customer_id)
        if customer is None:
            return None, None
        cust_pl = customer.price_list_id
        group_pl: int | None = None
        if customer.customer_group_id:
            from seeker_accounting.modules.customers.models.customer_group import CustomerGroup
            group = session.get(CustomerGroup, customer.customer_group_id)
            if group:
                group_pl = group.price_list_id
        return cust_pl, group_pl


def _pl_to_dto(row: PriceList) -> PriceListDTO:
    return PriceListDTO(
        id=row.id,
        company_id=row.company_id,
        name=row.name,
        currency_code=row.currency_code,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        is_default=row.is_default,
        description=row.description,
        is_active=row.is_active,
    )
