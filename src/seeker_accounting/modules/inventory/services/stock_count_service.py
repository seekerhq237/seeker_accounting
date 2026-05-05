from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.inventory.dto.stock_count_dto import (
    ApproveStockCountSessionCommand,
    CreateStockCountPlanCommand,
    EnterStockCountLineCommand,
    StartStockCountSessionCommand,
    StockCountLineDTO,
    StockCountPlanDTO,
    StockCountSessionDTO,
)
from seeker_accounting.modules.inventory.dto.inventory_document_commands import (
    CreateInventoryDocumentCommand,
    InventoryDocumentLineCommand,
    SubmitInventoryDocumentCommand,
)
from seeker_accounting.modules.inventory.models.stock_count_line import StockCountLine
from seeker_accounting.modules.inventory.models.stock_count_plan import (
    StockCountPlan,
    StockCountPlanLocation,
)
from seeker_accounting.modules.inventory.models.stock_count_session import StockCountSession
from seeker_accounting.modules.inventory.repositories.inventory_document_repository import (
    InventoryDocumentRepository,
)
from seeker_accounting.modules.inventory.repositories.inventory_reason_code_repository import (
    InventoryReasonCodeRepository,
)
from seeker_accounting.modules.inventory.repositories.item_repository import ItemRepository
from seeker_accounting.modules.inventory.repositories.stock_count_repository import StockCountRepository
from seeker_accounting.modules.inventory.repositories.stock_ledger_balance_repository import StockLedgerBalanceRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService
    from seeker_accounting.modules.inventory.services.inventory_document_service import InventoryDocumentService
    from seeker_accounting.modules.inventory.services.inventory_posting_service import InventoryPostingService


CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
InventoryDocumentRepositoryFactory = Callable[[Session], InventoryDocumentRepository]
InventoryReasonCodeRepositoryFactory = Callable[[Session], InventoryReasonCodeRepository]
ItemRepositoryFactory = Callable[[Session], ItemRepository]
StockCountRepositoryFactory = Callable[[Session], StockCountRepository]
StockLedgerBalanceRepositoryFactory = Callable[[Session], StockLedgerBalanceRepository]


class StockCountService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        stock_count_repository_factory: StockCountRepositoryFactory,
        stock_ledger_balance_repository_factory: StockLedgerBalanceRepositoryFactory,
        inventory_document_repository_factory: InventoryDocumentRepositoryFactory | None = None,
        inventory_reason_code_repository_factory: InventoryReasonCodeRepositoryFactory | None = None,
        item_repository_factory: ItemRepositoryFactory | None = None,
        numbering_service: NumberingService | None = None,
        inventory_document_service: "InventoryDocumentService | None" = None,
        inventory_posting_service: "InventoryPostingService | None" = None,
        permission_service: PermissionService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._stock_count_repository_factory = stock_count_repository_factory
        self._stock_ledger_balance_repository_factory = stock_ledger_balance_repository_factory
        self._inventory_document_repository_factory = inventory_document_repository_factory
        self._inventory_reason_code_repository_factory = inventory_reason_code_repository_factory
        self._item_repository_factory = item_repository_factory
        self._numbering_service = numbering_service
        self._inventory_document_service = inventory_document_service
        self._inventory_posting_service = inventory_posting_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def create_plan(self, company_id: int, command: CreateStockCountPlanCommand) -> StockCountPlanDTO:
        self._require_permission("inventory.stock_counts.manage")
        if not command.location_ids:
            raise ValidationError("At least one stock count location is required.")
        location_ids = tuple(dict.fromkeys(int(value) for value in command.location_ids))
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            plan = StockCountPlan(
                company_id=company_id,
                plan_number=self._issue_number(uow.session, company_id, "STOCK_COUNT_PLAN", "SC-PLAN"),
                plan_date=command.plan_date,
                status_code="planning",
                cycle_class_code=self._normalize_optional_text(command.cycle_class_code),
                item_filter_json=self._normalize_optional_text(command.item_filter_json),
                notes=self._normalize_optional_text(command.notes),
                created_by_user_id=command.created_by_user_id,
                locations=[StockCountPlanLocation(location_id=location_id) for location_id in location_ids],
            )
            self._stock_count_repository_factory(uow.session).add_plan(plan)
            self._commit_or_translate(uow)
            self._record_audit(company_id, "STOCK_COUNT_PLAN_CREATED", "StockCountPlan", plan.id, f"Stock count plan {plan.plan_number} created.")
            return self._plan_to_dto(plan)

    def list_plans(self, company_id: int) -> list[StockCountPlanDTO]:
        self._require_permission("inventory.stock_counts.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._stock_count_repository_factory(uow.session)
            return [self._plan_to_dto(plan) for plan in repo.list_plans(company_id)]

    def list_sessions(self, company_id: int, plan_id: int | None = None) -> list[StockCountSessionDTO]:
        self._require_permission("inventory.stock_counts.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._stock_count_repository_factory(uow.session)
            return [self._session_to_dto(session, self._adjustment_document_ids(uow.session, company_id, session.id)) for session in repo.list_sessions(company_id, plan_id)]

    def start_session(self, company_id: int, command: StartStockCountSessionCommand) -> StockCountSessionDTO:
        self._require_permission("inventory.stock_counts.manage")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._stock_count_repository_factory(uow.session)
            plan = repo.get_plan(company_id, command.plan_id)
            if plan is None:
                raise NotFoundError(f"Stock count plan with id {command.plan_id} was not found.")
            if plan.status_code != "planning":
                raise ValidationError("Only planning stock count plans can be started.")
            location_ids = {row.location_id for row in plan.locations}
            balances = self._stock_ledger_balance_repository_factory(uow.session).list_for_company(company_id)
            lines: list[StockCountLine] = []
            for balance in balances:
                location_id = None if balance.location_id == 0 else balance.location_id
                if location_id not in location_ids:
                    continue
                lines.append(
                    StockCountLine(
                        item_id=balance.item_id,
                        location_id=location_id,
                        snapshot_quantity=balance.quantity,
                        snapshot_value=balance.value,
                    )
                )
            if not lines:
                raise ValidationError("The selected locations have no stock balance rows to freeze.")
            session = StockCountSession(
                company_id=company_id,
                plan_id=plan.id,
                session_number=self._issue_number(uow.session, company_id, "STOCK_COUNT_SESSION", "SC-SESSION"),
                session_date=command.session_date,
                status_code="frozen",
                frozen_at=datetime.utcnow(),
                frozen_by_user_id=command.frozen_by_user_id,
                notes=self._normalize_optional_text(command.notes),
                lines=lines,
            )
            plan.status_code = "frozen"
            repo.add_session(session)
            repo.save_plan(plan)
            self._commit_or_translate(uow)
            self._record_audit(company_id, "STOCK_COUNT_SESSION_STARTED", "StockCountSession", session.id, f"Stock count session {session.session_number} frozen.")
            return self._session_to_dto(
                session,
                self._adjustment_document_ids(uow.session, company_id, session.id),
            )

    def enter_count_line(self, company_id: int, command: EnterStockCountLineCommand) -> StockCountLineDTO:
        self._require_permission("inventory.stock_counts.manage")
        if command.counted_quantity < Decimal("0"):
            raise ValidationError("Counted quantity cannot be negative.")
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._stock_count_repository_factory(uow.session)
            line = repo.get_line(command.line_id)
            if line is None or line.session.company_id != company_id:
                raise NotFoundError(f"Stock count line with id {command.line_id} was not found.")
            if line.session.status_code != "frozen":
                raise ValidationError("Counts can only be entered on frozen sessions.")
            line.counted_quantity = command.counted_quantity
            line.variance_quantity = command.counted_quantity - line.snapshot_quantity
            avg_cost = Decimal("0.00")
            if line.snapshot_quantity:
                avg_cost = (line.snapshot_value / line.snapshot_quantity).quantize(Decimal("0.0001"))
            line.variance_value = (line.variance_quantity * avg_cost).quantize(Decimal("0.01"))
            line.variance_reason_code_id = command.variance_reason_code_id
            line.counted_by_user_id = command.counted_by_user_id
            line.counted_at = datetime.utcnow()
            line.notes = self._normalize_optional_text(command.notes)
            repo.save_line(line)
            self._commit_or_translate(uow)
            return self._line_to_dto(line)

    def approve_session(self, company_id: int, command: ApproveStockCountSessionCommand) -> StockCountSessionDTO:
        self._require_permission("inventory.stock_counts.manage")
        adjustment_commands: list[CreateInventoryDocumentCommand] = []
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            repo = self._stock_count_repository_factory(uow.session)
            session = repo.get_session(company_id, command.session_id)
            if session is None:
                raise NotFoundError(f"Stock count session with id {command.session_id} was not found.")
            if session.status_code != "frozen":
                raise ValidationError("Only frozen stock count sessions can be approved.")
            if any(line.counted_quantity is None for line in session.lines):
                raise ValidationError("All stock count lines must be counted before approval.")
            adjustment_commands = self._build_adjustment_document_commands(uow.session, company_id, session)
            session.status_code = "approved"
            session.approved_at = datetime.utcnow()
            session.approved_by_user_id = command.approved_by_user_id
            if command.notes:
                session.notes = self._normalize_optional_text(command.notes)
            repo.save_session(session)
            self._commit_or_translate(uow)
            self._record_audit(company_id, "STOCK_COUNT_SESSION_COMPLETED", "StockCountSession", session.id, f"Stock count session {session.session_number} approved.")
        adjustment_document_ids = self._create_adjustment_documents(company_id, adjustment_commands)
        if command.post_adjustments_immediately and adjustment_document_ids:
            self._post_adjustment_documents(
                company_id,
                adjustment_document_ids,
                command.approved_by_user_id,
            )
            self._mark_session_posted(company_id, command.session_id, command.approved_by_user_id)
        with self._unit_of_work_factory() as uow:
            session = self._stock_count_repository_factory(uow.session).get_session(company_id, command.session_id)
            if session is None:
                raise NotFoundError(f"Stock count session with id {command.session_id} was not found.")
            return self._session_to_dto(
                session,
                self._adjustment_document_ids(uow.session, company_id, session.id),
            )

    def _build_adjustment_document_commands(
        self,
        session: Session,
        company_id: int,
        count_session: StockCountSession,
    ) -> list[CreateInventoryDocumentCommand]:
        if self._adjustment_document_ids(session, company_id, count_session.id):
            return []
        variance_lines = [
            line
            for line in count_session.lines
            if (line.variance_quantity or Decimal("0.0000")) != Decimal("0.0000")
        ]
        if not variance_lines:
            return []
        if self._inventory_document_service is None:
            raise ValidationError("Inventory document service is not configured for stock count adjustments.")
        fallback_reason_id = self._count_variance_reason_id(session, company_id)
        grouped: dict[tuple[str, int | None, int], list[InventoryDocumentLineCommand]] = {}
        for line in variance_lines:
            variance_quantity = line.variance_quantity or Decimal("0.0000")
            reason_id = line.variance_reason_code_id or fallback_reason_id
            if reason_id is None:
                raise ValidationError("A count variance reason code is required before approval.")
            if variance_quantity > 0:
                document_type_code = "count_gain"
                quantity = variance_quantity
                unit_cost = self._variance_unit_cost(line)
            else:
                document_type_code = "count_loss"
                quantity = abs(variance_quantity)
                unit_cost = None
            grouped.setdefault((document_type_code, line.location_id, reason_id), []).append(
                InventoryDocumentLineCommand(
                    item_id=line.item_id,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    line_description=f"Stock count variance line {line.id}",
                )
            )
        commands: list[CreateInventoryDocumentCommand] = []
        for (document_type_code, location_id, reason_id), lines in grouped.items():
            commands.append(
                CreateInventoryDocumentCommand(
                    document_type_code=document_type_code,
                    document_date=count_session.session_date,
                    location_id=location_id,
                    reference_number=count_session.session_number,
                    notes=f"Variance adjustment from stock count {count_session.session_number}",
                    reason_code_id=reason_id,
                    source_module_code="inventory",
                    source_document_type="stock_count_session",
                    source_document_id=count_session.id,
                    stock_count_session_id=count_session.id,
                    lines=tuple(lines),
                )
            )
        return commands

    def _create_adjustment_documents(
        self,
        company_id: int,
        commands: list[CreateInventoryDocumentCommand],
    ) -> list[int]:
        if not commands:
            return []
        if self._inventory_document_service is None:
            raise ValidationError("Inventory document service is not configured for stock count adjustments.")
        document_ids: list[int] = []
        for command in commands:
            document = self._inventory_document_service.create_draft_document(company_id, command)
            document_ids.append(document.id)
        return document_ids

    def _post_adjustment_documents(
        self,
        company_id: int,
        document_ids: list[int],
        actor_user_id: int | None,
    ) -> None:
        if self._inventory_posting_service is None:
            raise ValidationError("Inventory posting service is not configured for stock count adjustments.")
        for document_id in document_ids:
            try:
                self._inventory_posting_service.post_inventory_document(
                    company_id,
                    document_id,
                    actor_user_id=actor_user_id,
                )
            except ValidationError as exc:
                if "submitted" not in str(exc).lower() or self._inventory_document_service is None:
                    raise
                self._inventory_document_service.submit_for_posting(
                    company_id,
                    document_id,
                    SubmitInventoryDocumentCommand(submitted_by_user_id=None),
                )
                self._inventory_posting_service.post_inventory_document(
                    company_id,
                    document_id,
                    actor_user_id=actor_user_id,
                )

    def _mark_session_posted(self, company_id: int, session_id: int, actor_user_id: int | None) -> None:
        with self._unit_of_work_factory() as uow:
            repo = self._stock_count_repository_factory(uow.session)
            session = repo.get_session(company_id, session_id)
            if session is None:
                raise NotFoundError(f"Stock count session with id {session_id} was not found.")
            session.posted_at = datetime.utcnow()
            session.posted_by_user_id = actor_user_id
            repo.save_session(session)
            self._commit_or_translate(uow)

    def _adjustment_document_ids(self, session: Session, company_id: int, stock_count_session_id: int) -> tuple[int, ...]:
        if self._inventory_document_repository_factory is None:
            return ()
        repo = self._inventory_document_repository_factory(session)
        return tuple(document.id for document in repo.list_by_stock_count_session(company_id, stock_count_session_id))

    def _count_variance_reason_id(self, session: Session, company_id: int) -> int | None:
        if self._inventory_reason_code_repository_factory is None:
            return None
        reason = self._inventory_reason_code_repository_factory(session).get_by_code(company_id, "count_variance")
        if reason is None or not reason.is_active:
            return None
        return reason.id

    @staticmethod
    def _variance_unit_cost(line: StockCountLine) -> Decimal:
        variance_quantity = abs(line.variance_quantity or Decimal("0.0000"))
        variance_value = abs(line.variance_value or Decimal("0.00"))
        if variance_quantity and variance_value:
            return (variance_value / variance_quantity).quantize(Decimal("0.0001"))
        if line.snapshot_quantity and line.snapshot_value:
            return (abs(line.snapshot_value) / abs(line.snapshot_quantity)).quantize(Decimal("0.0001"))
        standard_cost = getattr(line.item, "standard_cost", None)
        if standard_cost is not None and standard_cost > 0:
            return standard_cost.quantize(Decimal("0.0001"))
        raise ValidationError("Positive stock count variances require a non-zero cost or item standard cost.")

    def _require_permission(self, permission_code: str) -> None:
        if self._permission_service is not None:
            self._permission_service.require_permission(permission_code)

    def _require_company(self, session: Session, company_id: int) -> None:
        if self._company_repository_factory(session).get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _issue_number(self, session: Session, company_id: int, document_type_code: str, fallback_prefix: str) -> str:
        if self._numbering_service is not None:
            try:
                return self._numbering_service.issue_next_number(
                    session,
                    company_id=company_id,
                    document_type_code=document_type_code,
                )
            except Exception:
                pass
        return f"{fallback_prefix}-{uuid.uuid4().hex[:8].upper()}"

    def _commit_or_translate(self, uow) -> None:
        try:
            uow.commit()
        except IntegrityError as exc:
            raise ConflictError("Stock count record conflicts with an existing record.") from exc

    def _record_audit(self, company_id: int, event_type_code: str, entity_type: str, entity_id: int | None, description: str) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_INVENTORY

        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_INVENTORY,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        text = (value or "").strip()
        return text or None

    @staticmethod
    def _plan_to_dto(plan: StockCountPlan) -> StockCountPlanDTO:
        return StockCountPlanDTO(
            id=plan.id,
            company_id=plan.company_id,
            plan_number=plan.plan_number,
            plan_date=plan.plan_date,
            status_code=plan.status_code,
            location_ids=tuple(row.location_id for row in plan.locations),
            cycle_class_code=plan.cycle_class_code,
            item_filter_json=plan.item_filter_json,
            notes=plan.notes,
            created_by_user_id=plan.created_by_user_id,
        )

    @staticmethod
    def _session_to_dto(session: StockCountSession, adjustment_document_ids: tuple[int, ...] = ()) -> StockCountSessionDTO:
        return StockCountSessionDTO(
            id=session.id,
            company_id=session.company_id,
            plan_id=session.plan_id,
            session_number=session.session_number,
            session_date=session.session_date,
            status_code=session.status_code,
            frozen_at=session.frozen_at,
            frozen_by_user_id=session.frozen_by_user_id,
            approved_at=session.approved_at,
            approved_by_user_id=session.approved_by_user_id,
            posted_at=session.posted_at,
            posted_by_user_id=session.posted_by_user_id,
            notes=session.notes,
            lines=tuple(StockCountService._line_to_dto(line) for line in sorted(session.lines, key=lambda row: row.id or 0)),
            adjustment_document_ids=adjustment_document_ids,
        )

    @staticmethod
    def _line_to_dto(line: StockCountLine) -> StockCountLineDTO:
        return StockCountLineDTO(
            id=line.id,
            session_id=line.session_id,
            item_id=line.item_id,
            location_id=line.location_id,
            snapshot_quantity=line.snapshot_quantity,
            snapshot_value=line.snapshot_value,
            counted_quantity=line.counted_quantity,
            variance_quantity=line.variance_quantity,
            variance_value=line.variance_value,
            variance_reason_code_id=line.variance_reason_code_id,
            counted_by_user_id=line.counted_by_user_id,
            counted_at=line.counted_at,
            notes=line.notes,
        )