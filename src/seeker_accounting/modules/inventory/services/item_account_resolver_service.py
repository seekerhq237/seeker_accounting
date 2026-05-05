"""Item account resolver — resolves the GL accounts to use for a posting.

Resolution order (Phase 0 / Slice 1.1):

1. Per-(item, location) override row (``item_account_overrides``) when a
   location is given and a row exists for that (item, location).
2. Per-(item, NULL location) override row.
3. The item's own ``inventory_account_id`` / ``cogs_account_id`` /
   ``expense_account_id`` / ``revenue_account_id``.
4. The item's category default (when populated by future slices —
   currently treated as None and skipped).
5. Company defaults from ``CompanyAccountingSettings`` (deferred to a
   later slice; currently None).

The resolver is a pure read service: it never mutates data. Callers
remain responsible for raising domain exceptions when a required
account is None.
"""

from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.inventory.dto.item_dto import ResolvedItemAccountsDTO
from seeker_accounting.modules.inventory.repositories.item_account_override_repository import (
    ItemAccountOverrideRepository,
)
from seeker_accounting.modules.inventory.repositories.item_repository import (
    ItemRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError


CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
ItemRepositoryFactory = Callable[[Session], ItemRepository]
OverrideRepoFactory = Callable[[Session], ItemAccountOverrideRepository]


class ItemAccountResolverService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        item_repository_factory: ItemRepositoryFactory,
        item_account_override_repository_factory: OverrideRepoFactory,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._company_repo_factory = company_repository_factory
        self._item_repo_factory = item_repository_factory
        self._override_repo_factory = item_account_override_repository_factory

    def resolve_accounts(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None,
    ) -> ResolvedItemAccountsDTO:
        with self._uow_factory() as uow:
            return self._resolve_in_session(uow.session, company_id, item_id, location_id)

    def resolve_in_session(
        self,
        session: Session,
        company_id: int,
        item_id: int,
        location_id: int | None,
    ) -> ResolvedItemAccountsDTO:
        """Variant for callers that already hold an open session.

        Used by posting services so that the resolver participates in the
        caller's unit of work without opening a nested one.
        """
        return self._resolve_in_session(session, company_id, item_id, location_id)

    # ------------------------------------------------------------------

    def _resolve_in_session(
        self,
        session: Session,
        company_id: int,
        item_id: int,
        location_id: int | None,
    ) -> ResolvedItemAccountsDTO:
        company_repo = self._company_repo_factory(session)
        if company_repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

        item_repo = self._item_repo_factory(session)
        item = item_repo.get_by_id(company_id, item_id)
        if item is None:
            raise NotFoundError(f"Item with id {item_id} was not found.")

        override_repo = self._override_repo_factory(session)

        inventory_id = item.inventory_account_id
        cogs_id = item.cogs_account_id
        expense_id = item.expense_account_id
        revenue_id = item.revenue_account_id

        # 2. Item-level (NULL location) override
        item_default_override = override_repo.get_for_item_and_location(
            company_id, item_id, None
        )
        if item_default_override is not None:
            inventory_id = item_default_override.inventory_account_id or inventory_id
            cogs_id = item_default_override.cogs_account_id or cogs_id
            expense_id = item_default_override.expense_account_id or expense_id
            revenue_id = item_default_override.revenue_account_id or revenue_id

        # 1. Per-location override (highest precedence)
        if location_id is not None:
            location_override = override_repo.get_for_item_and_location(
                company_id, item_id, location_id
            )
            if location_override is not None:
                inventory_id = location_override.inventory_account_id or inventory_id
                cogs_id = location_override.cogs_account_id or cogs_id
                expense_id = location_override.expense_account_id or expense_id
                revenue_id = location_override.revenue_account_id or revenue_id

        return ResolvedItemAccountsDTO(
            item_id=item_id,
            location_id=location_id,
            inventory_account_id=inventory_id,
            cogs_account_id=cogs_id,
            expense_account_id=expense_id,
            revenue_account_id=revenue_id,
        )
