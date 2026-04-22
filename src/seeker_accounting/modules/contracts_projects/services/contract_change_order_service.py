from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.contracts_projects.dto.contract_change_order_commands import (
    ApproveContractChangeOrderCommand,
    CreateContractChangeOrderCommand,
    RejectContractChangeOrderCommand,
    SubmitContractChangeOrderCommand,
    UpdateContractChangeOrderCommand,
)
from seeker_accounting.modules.contracts_projects.dto.contract_change_order_dto import (
    ContractChangeOrderDetailDTO,
    ContractChangeOrderListItemDTO,
)
from seeker_accounting.modules.contracts_projects.models.contract_change_order import ContractChangeOrder
from seeker_accounting.modules.contracts_projects.repositories.contract_change_order_repository import (
    ContractChangeOrderRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.contract_repository import ContractRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

ContractChangeOrderRepositoryFactory = Callable[[Session], ContractChangeOrderRepository]
ContractRepositoryFactory = Callable[[Session], ContractRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]

_VALID_CHANGE_TYPES = frozenset({"scope", "price", "time", "mixed"})

_VALID_STATUSES = frozenset({"draft", "submitted", "approved", "rejected", "cancelled"})


class ContractChangeOrderService:
    """Manage contract change orders."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        change_order_repository_factory: ContractChangeOrderRepositoryFactory,
        contract_repository_factory: ContractRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._change_order_repository_factory = change_order_repository_factory
        self._contract_repository_factory = contract_repository_factory
        self._company_repository_factory = company_repository_factory

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_change_order(
        self, command: CreateContractChangeOrderCommand
    ) -> ContractChangeOrderDetailDTO:
        self._validate_create_command(command)

        with self._unit_of_work_factory() as uow:
            self._validate_company_and_contract(uow.session, command.company_id, command.contract_id)
            repo = self._change_order_repository_factory(uow.session)

            change_order = ContractChangeOrder(
                company_id=command.company_id,
                contract_id=command.contract_id,
                change_order_number=command.change_order_number,
                change_order_date=command.change_order_date,
                status_code="draft",
                change_type_code=command.change_type_code,
                description=command.description,
                contract_amount_delta=command.contract_amount_delta,
                days_extension=command.days_extension,
                effective_date=command.effective_date,
            )
            repo.add(change_order)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Change order could not be created.") from exc

            return self._to_detail_dto(change_order)

    # ------------------------------------------------------------------
    # Update (draft only)
    # ------------------------------------------------------------------

    def update_change_order(
        self, change_order_id: int, command: UpdateContractChangeOrderCommand
    ) -> ContractChangeOrderDetailDTO:
        self._validate_update_command(command)

        with self._unit_of_work_factory() as uow:
            repo = self._change_order_repository_factory(uow.session)
            co = repo.get_by_id(change_order_id)
            if co is None:
                raise NotFoundError(f"Change order {change_order_id} not found.")

            if co.status_code != "draft":
                raise ValidationError("Only draft change orders can be edited.")

            co.change_order_date = command.change_order_date
            co.change_type_code = command.change_type_code
            co.description = command.description
            co.contract_amount_delta = command.contract_amount_delta
            co.days_extension = command.days_extension
            co.effective_date = command.effective_date
            repo.save(co)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Change order could not be updated.") from exc

            return self._to_detail_dto(co)

    # ------------------------------------------------------------------
    # Workflow transitions
    # ------------------------------------------------------------------

    def submit_change_order(self, command: SubmitContractChangeOrderCommand) -> ContractChangeOrderDetailDTO:
        return self._transition_status(command.change_order_id, "submitted", ["draft"])

    def approve_change_order(self, command: ApproveContractChangeOrderCommand) -> ContractChangeOrderDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._change_order_repository_factory(uow.session)
            co = repo.get_by_id(command.change_order_id)
            if co is None:
                raise NotFoundError(f"Change order {command.change_order_id} not found.")

            if co.status_code != "submitted":
                raise ValidationError(
                    f"Cannot approve change order in '{co.status_code}' status. Must be 'submitted'."
                )

            co.status_code = "approved"
            co.approved_at = datetime.utcnow()
            co.approved_by_user_id = command.approved_by_user_id
            repo.save(co)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Change order could not be approved.") from exc

            return self._to_detail_dto(co)

    def reject_change_order(self, command: RejectContractChangeOrderCommand) -> ContractChangeOrderDetailDTO:
        return self._transition_status(command.change_order_id, "rejected", ["submitted"])

    def cancel_change_order(self, change_order_id: int) -> ContractChangeOrderDetailDTO:
        return self._transition_status(change_order_id, "cancelled", ["draft", "submitted"])

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_change_order_detail(self, change_order_id: int) -> ContractChangeOrderDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._change_order_repository_factory(uow.session)
            co = repo.get_by_id(change_order_id)
            if co is None:
                raise NotFoundError(f"Change order {change_order_id} not found.")
            return self._to_detail_dto(co)

    def list_change_orders(self, contract_id: int) -> list[ContractChangeOrderListItemDTO]:
        with self._unit_of_work_factory() as uow:
            repo = self._change_order_repository_factory(uow.session)
            change_orders = repo.list_by_contract(contract_id)
            return [self._to_list_item_dto(co) for co in change_orders]

    def get_approved_delta_total(self, contract_id: int) -> Decimal:
        with self._unit_of_work_factory() as uow:
            repo = self._change_order_repository_factory(uow.session)
            return repo.sum_approved_amount_delta(contract_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _transition_status(
        self, change_order_id: int, new_status: str, allowed_from: list[str]
    ) -> ContractChangeOrderDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._change_order_repository_factory(uow.session)
            co = repo.get_by_id(change_order_id)
            if co is None:
                raise NotFoundError(f"Change order {change_order_id} not found.")

            if co.status_code not in allowed_from:
                raise ValidationError(
                    f"Cannot change status from '{co.status_code}' to '{new_status}'."
                )

            co.status_code = new_status
            repo.save(co)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Status change could not be saved.") from exc

            return self._to_detail_dto(co)

    def _validate_create_command(self, command: CreateContractChangeOrderCommand) -> None:
        if not command.change_order_number or not command.change_order_number.strip():
            raise ValidationError("Change order number is required.")
        if command.change_type_code not in _VALID_CHANGE_TYPES:
            raise ValidationError(
                f"Invalid change type: {command.change_type_code}. "
                f"Valid: {', '.join(sorted(_VALID_CHANGE_TYPES))}."
            )
        if command.days_extension is not None and command.days_extension < 0:
            raise ValidationError("Days extension cannot be negative.")
        if (
            command.effective_date is not None
            and command.change_order_date is not None
            and command.effective_date < command.change_order_date
        ):
            raise ValidationError("Effective date cannot be before change order date.")

    def _validate_update_command(self, command: UpdateContractChangeOrderCommand) -> None:
        if command.change_type_code not in _VALID_CHANGE_TYPES:
            raise ValidationError(
                f"Invalid change type: {command.change_type_code}. "
                f"Valid: {', '.join(sorted(_VALID_CHANGE_TYPES))}."
            )
        if command.days_extension is not None and command.days_extension < 0:
            raise ValidationError("Days extension cannot be negative.")
        if (
            command.effective_date is not None
            and command.change_order_date is not None
            and command.effective_date < command.change_order_date
        ):
            raise ValidationError("Effective date cannot be before change order date.")

    def _validate_company_and_contract(self, session: Session, company_id: int, contract_id: int) -> None:
        if self._company_repository_factory(session).get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

        contract = self._contract_repository_factory(session).get_by_id(contract_id)
        if contract is None:
            raise NotFoundError(f"Contract {contract_id} not found.")
        if contract.company_id != company_id:
            raise ValidationError("Contract does not belong to the specified company.")

    def _to_list_item_dto(self, co: ContractChangeOrder) -> ContractChangeOrderListItemDTO:
        return ContractChangeOrderListItemDTO(
            id=co.id,
            change_order_number=co.change_order_number,
            change_order_date=co.change_order_date,
            status_code=co.status_code,
            change_type_code=co.change_type_code,
            description=co.description,
            contract_amount_delta=co.contract_amount_delta,
            days_extension=co.days_extension,
            effective_date=co.effective_date,
            updated_at=co.updated_at,
        )

    def _to_detail_dto(self, co: ContractChangeOrder) -> ContractChangeOrderDetailDTO:
        return ContractChangeOrderDetailDTO(
            id=co.id,
            company_id=co.company_id,
            contract_id=co.contract_id,
            change_order_number=co.change_order_number,
            change_order_date=co.change_order_date,
            status_code=co.status_code,
            change_type_code=co.change_type_code,
            description=co.description,
            contract_amount_delta=co.contract_amount_delta,
            days_extension=co.days_extension,
            effective_date=co.effective_date,
            approved_at=co.approved_at,
            approved_by_user_id=co.approved_by_user_id,
            approved_by_display_name=None,
            created_at=co.created_at,
            updated_at=co.updated_at,
        )
