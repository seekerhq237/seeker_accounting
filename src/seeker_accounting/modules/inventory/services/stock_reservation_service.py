"""Stock reservation service.

Per ``docs/inventory_upgrade_plan.md`` Slice 2.4: reservations consume
"available" quantity without touching the immutable stock ledger. Lifecycle:

    pending → fulfilled  (called from posting service when an issue is posted
                          that references a reservation)
    pending → cancelled  (called when originating order/job is cancelled)
    pending → expired    (background or on-demand expiry via expire_stale)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.stock_reservation_dto import (
    CreateReservationCommand,
    StockPositionDTO,
    StockReservationDTO,
)
from seeker_accounting.modules.inventory.models.stock_reservation import StockReservation
from seeker_accounting.modules.inventory.repositories.stock_reservation_repository import (
    StockReservationRepository,
)
from seeker_accounting.modules.inventory.services.stock_ledger_query_service import (
    StockLedgerQueryService,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
StockReservationRepositoryFactory = Callable[[Session], StockReservationRepository]


class StockReservationService:
    """Manage pending stock reservations and compute ATP positions."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        stock_reservation_repository_factory: StockReservationRepositoryFactory,
        stock_ledger_query_service: StockLedgerQueryService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repo_factory = company_repository_factory
        self._reservation_repo_factory = stock_reservation_repository_factory
        self._ledger_query = stock_ledger_query_service

    # ------------------------------------------------------------------
    # Create / cancel / consume
    # ------------------------------------------------------------------

    def create_reservation(
        self,
        company_id: int,
        cmd: CreateReservationCommand,
    ) -> StockReservationDTO:
        """Create a pending reservation. Validates available ≥ requested."""
        with self._unit_of_work_factory() as uow:
            company_repo = self._company_repo_factory(uow.session)
            if company_repo.get_by_id(company_id) is None:
                raise NotFoundError(f"Company {company_id} not found.")

            if cmd.quantity <= Decimal("0"):
                raise ValidationError("Reservation quantity must be greater than zero.")

            reservation_repo = self._reservation_repo_factory(uow.session)

            # Compute available to reserve
            position = self._ledger_query.position(
                company_id=company_id,
                item_id=cmd.item_id,
                location_id=cmd.location_id,
            )
            reserved = reservation_repo.total_reserved_quantity(
                company_id, cmd.item_id, cmd.location_id
            )
            available = max(position.on_hand - reserved, Decimal("0"))
            if cmd.quantity > available:
                raise ValidationError(
                    f"Insufficient available stock for item id {cmd.item_id}. "
                    f"Available: {available}, requested: {cmd.quantity}."
                )

            reservation = StockReservation(
                company_id=company_id,
                item_id=cmd.item_id,
                location_id=cmd.location_id,
                quantity=cmd.quantity,
                source_module=cmd.source_module,
                source_document_id=cmd.source_document_id,
                source_document_line_id=cmd.source_document_line_id,
                status_code="pending",
                expires_at=cmd.expires_at,
            )
            reservation_repo.add(reservation)
            uow.commit()

            return self._to_dto(reservation)

    def cancel_reservation(
        self,
        company_id: int,
        reservation_id: int,
    ) -> StockReservationDTO:
        """Cancel a pending reservation."""
        with self._unit_of_work_factory() as uow:
            reservation_repo = self._reservation_repo_factory(uow.session)
            reservation = reservation_repo.get(reservation_id, company_id)
            if reservation is None:
                raise NotFoundError(f"Reservation {reservation_id} not found.")
            if reservation.status_code != "pending":
                raise ValidationError(
                    f"Only pending reservations can be cancelled "
                    f"(current status: {reservation.status_code!r})."
                )
            reservation.status_code = "cancelled"
            uow.commit()
            return self._to_dto(reservation)

    def consume_reservation(
        self,
        company_id: int,
        reservation_id: int,
    ) -> StockReservationDTO:
        """Mark a pending reservation fulfilled (called when related issue posts)."""
        with self._unit_of_work_factory() as uow:
            reservation_repo = self._reservation_repo_factory(uow.session)
            reservation = reservation_repo.get(reservation_id, company_id)
            if reservation is None:
                raise NotFoundError(f"Reservation {reservation_id} not found.")
            if reservation.status_code != "pending":
                raise ValidationError(
                    f"Only pending reservations can be consumed "
                    f"(current status: {reservation.status_code!r})."
                )
            reservation.status_code = "fulfilled"
            uow.commit()
            return self._to_dto(reservation)

    def cancel_reservations_for_source(
        self,
        company_id: int,
        source_module: str,
        source_document_id: int,
    ) -> int:
        """Cancel all pending reservations for a source document. Returns count."""
        with self._unit_of_work_factory() as uow:
            reservation_repo = self._reservation_repo_factory(uow.session)
            rows = reservation_repo.list_by_source(company_id, source_module, source_document_id)
            count = 0
            for r in rows:
                if r.status_code == "pending":
                    r.status_code = "cancelled"
                    count += 1
            uow.commit()
            return count

    def expire_stale_reservations(
        self,
        company_id: int,
        as_of: datetime | None = None,
    ) -> int:
        """Expire stale pending reservations. Returns count expired."""
        as_of = as_of or datetime.utcnow()
        with self._unit_of_work_factory() as uow:
            reservation_repo = self._reservation_repo_factory(uow.session)
            count = reservation_repo.expire_stale(company_id, as_of)
            uow.commit()
            return count

    # ------------------------------------------------------------------
    # ATP position query
    # ------------------------------------------------------------------

    def get_position(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None,
        on_order: Decimal = Decimal("0"),
    ) -> StockPositionDTO:
        """Return full ATP position for (company, item, location)."""
        ledger_pos = self._ledger_query.position(
            company_id=company_id,
            item_id=item_id,
            location_id=location_id,
        )
        with self._unit_of_work_factory() as uow:
            reservation_repo = self._reservation_repo_factory(uow.session)
            reserved = reservation_repo.total_reserved_quantity(
                company_id, item_id, location_id
            )
            uow.commit()

        return StockPositionDTO(
            company_id=company_id,
            item_id=item_id,
            location_id=location_id,
            on_hand=ledger_pos.on_hand,
            value=ledger_pos.value,
            avg_cost=ledger_pos.avg_cost,
            reserved=reserved,
            on_order=on_order,
        )

    def list_reservations_for_item_location(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None,
    ) -> list[StockReservationDTO]:
        with self._unit_of_work_factory() as uow:
            reservation_repo = self._reservation_repo_factory(uow.session)
            rows = reservation_repo.list_pending_for_item_location(
                company_id, item_id, location_id
            )
            uow.commit()
            return [self._to_dto(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dto(r: StockReservation) -> StockReservationDTO:
        return StockReservationDTO(
            id=r.id,
            company_id=r.company_id,
            item_id=r.item_id,
            location_id=r.location_id,
            quantity=r.quantity,
            source_module=r.source_module,
            source_document_id=r.source_document_id,
            source_document_line_id=r.source_document_line_id,
            status_code=r.status_code,
            expires_at=r.expires_at,
            created_at=r.created_at,
        )
