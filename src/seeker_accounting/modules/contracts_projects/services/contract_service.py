from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.reference_data.repositories.country_repository import CountryRepository
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.contracts_projects.dto.contract_dto import (
    ContractDetailDTO,
    ContractListItemDTO,
    CreateContractCommand,
    UpdateContractCommand,
)
from seeker_accounting.modules.contracts_projects.models.contract import Contract
from seeker_accounting.modules.contracts_projects.repositories.contract_change_order_repository import (
    ContractChangeOrderRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.contract_repository import ContractRepository
from seeker_accounting.modules.customers.repositories.customer_repository import CustomerRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

ContractRepositoryFactory = Callable[[Session], ContractRepository]
ContractChangeOrderRepositoryFactory = Callable[[Session], ContractChangeOrderRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CustomerRepositoryFactory = Callable[[Session], CustomerRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]

_VALID_CONTRACT_TYPES = frozenset({
    "fixed_price",
    "time_and_material",
    "cost_plus",
    "framework",
    "other",
})

_VALID_BILLING_BASES = frozenset({
    "milestone",
    "progress",
    "time_and_material",
    "fixed_schedule",
    "manual",
})

_VALID_CONTRACT_STATUSES = frozenset({
    "draft",
    "active",
    "on_hold",
    "completed",
    "closed",
    "cancelled",
})


class ContractService:
    """Manage contracts."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        contract_repository_factory: ContractRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
        customer_repository_factory: CustomerRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        change_order_repository_factory: ContractChangeOrderRepositoryFactory | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._contract_repository_factory = contract_repository_factory
        self._company_repository_factory = company_repository_factory
        self._customer_repository_factory = customer_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._change_order_repository_factory = change_order_repository_factory
        self._audit_service = audit_service

    def create_contract(self, command: CreateContractCommand) -> ContractDetailDTO:
        self._validate_create_command(command)

        with self._unit_of_work_factory() as uow:
            self._validate_dependencies(uow.session, command=command)
            repository = self._contract_repository_factory(uow.session)

            contract = Contract(
                company_id=command.company_id,
                contract_number=command.contract_number,
                contract_title=command.contract_title,
                customer_id=command.customer_id,
                contract_type_code=command.contract_type_code,
                currency_code=command.currency_code,
                exchange_rate=command.exchange_rate,
                base_contract_amount=command.base_contract_amount,
                start_date=command.start_date,
                planned_end_date=command.planned_end_date,
                status_code="draft",
                billing_basis_code=command.billing_basis_code,
                retention_percent=command.retention_percent,
                reference_number=command.reference_number,
                description=command.description,
                created_by_user_id=command.created_by_user_id,
            )
            repository.add(contract)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Contract could not be created.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import CONTRACT_CREATED
            self._record_audit(command.company_id, CONTRACT_CREATED, "Contract", contract.id, "Created contract")
            return self._to_detail_dto(contract, uow.session)

    def update_contract(self, contract_id: int, command: UpdateContractCommand) -> ContractDetailDTO:
        self._validate_update_command(command)

        with self._unit_of_work_factory() as uow:
            repository = self._contract_repository_factory(uow.session)
            contract = repository.get_by_id(contract_id)
            if contract is None:
                raise NotFoundError(f"Contract {contract_id} not found.")

            self._validate_dependencies(uow.session, command=command, contract=contract)

            contract.contract_title = command.contract_title
            contract.contract_type_code = command.contract_type_code
            contract.currency_code = command.currency_code
            contract.exchange_rate = command.exchange_rate
            contract.base_contract_amount = command.base_contract_amount
            contract.start_date = command.start_date
            contract.planned_end_date = command.planned_end_date
            contract.billing_basis_code = command.billing_basis_code
            contract.retention_percent = command.retention_percent
            contract.reference_number = command.reference_number
            contract.description = command.description
            contract.updated_by_user_id = command.updated_by_user_id

            repository.save(contract)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Contract could not be updated.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import CONTRACT_UPDATED
            self._record_audit(command.company_id, CONTRACT_UPDATED, "Contract", contract.id, "Updated contract")
            return self._to_detail_dto(contract, uow.session)

    def get_contract_detail(self, contract_id: int) -> ContractDetailDTO:
        with self._unit_of_work_factory() as uow:
            repository = self._contract_repository_factory(uow.session)
            contract = repository.get_by_id(contract_id)
            if contract is None:
                raise NotFoundError(f"Contract {contract_id} not found.")
            return self._to_detail_dto(contract, uow.session)

    def list_contracts(self, company_id: int) -> list[ContractListItemDTO]:
        with self._unit_of_work_factory() as uow:
            repository = self._contract_repository_factory(uow.session)
            contracts = repository.list_by_company(company_id)
            return [self._to_list_item_dto(contract, uow.session) for contract in contracts]

    def activate_contract(self, contract_id: int) -> ContractDetailDTO:
        return self._change_status(contract_id, "active", ["draft", "on_hold"])

    def put_contract_on_hold(self, contract_id: int) -> ContractDetailDTO:
        return self._change_status(contract_id, "on_hold", ["active"])

    def complete_contract(self, contract_id: int) -> ContractDetailDTO:
        return self._change_status(contract_id, "completed", ["active", "on_hold"])

    def close_contract(self, contract_id: int) -> ContractDetailDTO:
        return self._change_status(contract_id, "closed", ["completed"])

    def cancel_contract(self, contract_id: int) -> ContractDetailDTO:
        return self._change_status(contract_id, "cancelled", ["draft", "active", "on_hold"])

    def _change_status(self, contract_id: int, new_status: str, allowed_from: list[str]) -> ContractDetailDTO:
        with self._unit_of_work_factory() as uow:
            repository = self._contract_repository_factory(uow.session)
            contract = repository.get_by_id(contract_id)
            if contract is None:
                raise NotFoundError(f"Contract {contract_id} not found.")

            if contract.status_code not in allowed_from:
                raise ValidationError(
                    f"Cannot change contract status from '{contract.status_code}' to '{new_status}'."
                )

            contract.status_code = new_status
            repository.save(contract)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Contract status could not be updated.") from exc

            return self._to_detail_dto(contract, uow.session)

    def _validate_create_command(self, command: CreateContractCommand) -> None:
        if command.contract_type_code not in _VALID_CONTRACT_TYPES:
            raise ValidationError(
                f"Invalid contract type: {command.contract_type_code}. "
                f"Valid: {', '.join(sorted(_VALID_CONTRACT_TYPES))}."
            )
        if command.billing_basis_code is not None and command.billing_basis_code not in _VALID_BILLING_BASES:
            raise ValidationError(
                f"Invalid billing basis: {command.billing_basis_code}. "
                f"Valid: {', '.join(sorted(_VALID_BILLING_BASES))}."
            )
        if command.retention_percent is not None and command.retention_percent < 0:
            raise ValidationError("Retention percent cannot be negative.")
        if command.base_contract_amount is not None and command.base_contract_amount < 0:
            raise ValidationError("Base contract amount cannot be negative.")
        if command.start_date and command.planned_end_date and command.start_date > command.planned_end_date:
            raise ValidationError("Start date cannot be after planned end date.")

    def _validate_dependencies(self, session: Session, command: CreateContractCommand | UpdateContractCommand | None = None, contract: Contract | None = None) -> None:
        company_id = command.company_id if command is not None else contract.company_id
        customer_id = command.customer_id if command is not None else contract.customer_id
        currency_code = command.currency_code if command is not None else contract.currency_code

        if self._company_repository_factory(session).get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

        customer = self._customer_repository_factory(session).get_by_id(company_id, customer_id)
        if customer is None:
            raise NotFoundError(f"Customer {customer_id} not found.")

        if not self._currency_repository_factory(session).exists_active(currency_code):
            raise ValidationError(f"Currency code {currency_code} is not found or not active.")

    def _validate_update_command(self, command: UpdateContractCommand) -> None:
        if command.contract_type_code not in _VALID_CONTRACT_TYPES:
            raise ValidationError(
                f"Invalid contract type: {command.contract_type_code}. "
                f"Valid: {', '.join(sorted(_VALID_CONTRACT_TYPES))}."
            )
        if command.billing_basis_code is not None and command.billing_basis_code not in _VALID_BILLING_BASES:
            raise ValidationError(
                f"Invalid billing basis: {command.billing_basis_code}. "
                f"Valid: {', '.join(sorted(_VALID_BILLING_BASES))}."
            )
        if command.retention_percent is not None and command.retention_percent < 0:
            raise ValidationError("Retention percent cannot be negative.")
        if command.base_contract_amount is not None and command.base_contract_amount < 0:
            raise ValidationError("Base contract amount cannot be negative.")
        if command.start_date and command.planned_end_date and command.start_date > command.planned_end_date:
            raise ValidationError("Start date cannot be after planned end date.")

    def _to_list_item_dto(self, contract: Contract, session: Session) -> ContractListItemDTO:
        customer = self._customer_repository_factory(session).get_by_id(contract.company_id, contract.customer_id)
        customer_display_name = customer.display_name if customer else "Unknown"
        return ContractListItemDTO(
            id=contract.id,
            contract_number=contract.contract_number,
            contract_title=contract.contract_title,
            customer_display_name=customer_display_name,
            contract_type_code=contract.contract_type_code,
            status_code=contract.status_code,
            start_date=contract.start_date,
            planned_end_date=contract.planned_end_date,
            base_contract_amount=contract.base_contract_amount,
            currency_code=contract.currency_code,
            updated_at=contract.updated_at,
        )

    def _to_detail_dto(self, contract: Contract, session: Session) -> ContractDetailDTO:
        customer = self._customer_repository_factory(session).get_by_id(contract.company_id, contract.customer_id)
        customer_display_name = customer.display_name if customer else "Unknown"
        approved_by_display_name = None
        if contract.approved_by_user_id:
            # Assuming we have a way to get user, but for now skip
            pass

        delta_total = Decimal("0")
        if self._change_order_repository_factory is not None:
            co_repo = self._change_order_repository_factory(session)
            delta_total = co_repo.sum_approved_amount_delta(contract.id)

        base = contract.base_contract_amount
        current = (base + delta_total) if base is not None else None

        return ContractDetailDTO(
            id=contract.id,
            company_id=contract.company_id,
            contract_number=contract.contract_number,
            contract_title=contract.contract_title,
            customer_id=contract.customer_id,
            customer_display_name=customer_display_name,
            contract_type_code=contract.contract_type_code,
            currency_code=contract.currency_code,
            exchange_rate=contract.exchange_rate,
            base_contract_amount=contract.base_contract_amount,
            start_date=contract.start_date,
            planned_end_date=contract.planned_end_date,
            actual_end_date=contract.actual_end_date,
            status_code=contract.status_code,
            billing_basis_code=contract.billing_basis_code,
            retention_percent=contract.retention_percent,
            reference_number=contract.reference_number,
            description=contract.description,
            approved_at=contract.approved_at,
            approved_by_user_id=contract.approved_by_user_id,
            approved_by_display_name=approved_by_display_name,
            created_at=contract.created_at,
            updated_at=contract.updated_at,
            created_by_user_id=contract.created_by_user_id,
            updated_by_user_id=contract.updated_by_user_id,
            approved_change_order_delta_total=delta_total,
            current_contract_amount=current,
        )

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_type: str,
        entity_id: int | None,
        description: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_CONTRACTS
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_CONTRACTS,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
