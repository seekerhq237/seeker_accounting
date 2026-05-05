from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.contracts_projects.dto.contract_commercial_dto import (
    ContractBillingScheduleItemCommand,
    ContractBillingScheduleItemDTO,
    ContractCommercialSummaryDTO,
    ContractLineCommand,
    ContractLineDTO,
)
from seeker_accounting.modules.contracts_projects.models.contract import Contract
from seeker_accounting.modules.contracts_projects.models.contract_billing_schedule_item import (
    ContractBillingScheduleItem,
)
from seeker_accounting.modules.contracts_projects.models.contract_line import ContractLine
from seeker_accounting.modules.contracts_projects.repositories.contract_billing_schedule_repository import (
    ContractBillingScheduleRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.contract_change_order_repository import (
    ContractChangeOrderRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.contract_customer_advance_repository import (
    ContractCustomerAdvanceRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.contract_line_repository import ContractLineRepository
from seeker_accounting.modules.contracts_projects.repositories.contract_progress_claim_repository import (
    ContractProgressClaimRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.contract_receipt_allocation_repository import (
    ContractReceiptAllocationRepository,
)
from seeker_accounting.modules.contracts_projects.repositories.contract_repository import ContractRepository
from seeker_accounting.modules.contracts_projects.repositories.contract_retention_movement_repository import (
    ContractRetentionMovementRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

ContractRepositoryFactory = Callable[[Session], ContractRepository]
ContractLineRepositoryFactory = Callable[[Session], ContractLineRepository]
ContractBillingScheduleRepositoryFactory = Callable[[Session], ContractBillingScheduleRepository]
ContractChangeOrderRepositoryFactory = Callable[[Session], ContractChangeOrderRepository]
ContractProgressClaimRepositoryFactory = Callable[[Session], ContractProgressClaimRepository]
ContractReceiptAllocationRepositoryFactory = Callable[[Session], ContractReceiptAllocationRepository]
ContractCustomerAdvanceRepositoryFactory = Callable[[Session], ContractCustomerAdvanceRepository]
ContractRetentionMovementRepositoryFactory = Callable[[Session], ContractRetentionMovementRepository]

_MONEY = Decimal("0.01")
_PERCENT = Decimal("0.0001")
_VALID_BILLING_BASIS_CODES = frozenset({"milestone", "progress", "time_and_material", "fixed_schedule", "manual"})
_VALID_SCHEDULE_TYPE_CODES = frozenset({"milestone", "percentage", "fixed", "time_and_material", "manual"})


class ContractCommercialService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        contract_repository_factory: ContractRepositoryFactory,
        contract_line_repository_factory: ContractLineRepositoryFactory,
        billing_schedule_repository_factory: ContractBillingScheduleRepositoryFactory,
        change_order_repository_factory: ContractChangeOrderRepositoryFactory | None = None,
        progress_claim_repository_factory: ContractProgressClaimRepositoryFactory | None = None,
        receipt_allocation_repository_factory: ContractReceiptAllocationRepositoryFactory | None = None,
        advance_repository_factory: ContractCustomerAdvanceRepositoryFactory | None = None,
        retention_movement_repository_factory: ContractRetentionMovementRepositoryFactory | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._contract_repository_factory = contract_repository_factory
        self._contract_line_repository_factory = contract_line_repository_factory
        self._billing_schedule_repository_factory = billing_schedule_repository_factory
        self._change_order_repository_factory = change_order_repository_factory
        self._progress_claim_repository_factory = progress_claim_repository_factory
        self._receipt_allocation_repository_factory = receipt_allocation_repository_factory
        self._advance_repository_factory = advance_repository_factory
        self._retention_movement_repository_factory = retention_movement_repository_factory

    def replace_contract_lines(
        self,
        company_id: int,
        contract_id: int,
        commands: tuple[ContractLineCommand, ...],
    ) -> tuple[ContractLineDTO, ...]:
        if not commands:
            raise ValidationError("At least one contract line is required.")

        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, contract_id)
            repository = self._contract_line_repository_factory(uow.session)
            lines = [self._build_contract_line(company_id, contract_id, line_number, command) for line_number, command in enumerate(commands, start=1)]
            repository.replace_base_lines(company_id, contract_id, lines)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Contract lines could not be saved.") from exc

            return tuple(self._to_line_dto(line) for line in lines)

    def list_contract_lines(self, company_id: int, contract_id: int) -> tuple[ContractLineDTO, ...]:
        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, contract_id)
            lines = self._contract_line_repository_factory(uow.session).list_by_contract(company_id, contract_id)
            return tuple(self._to_line_dto(line) for line in lines)

    def replace_billing_schedule(
        self,
        company_id: int,
        contract_id: int,
        commands: tuple[ContractBillingScheduleItemCommand, ...],
    ) -> tuple[ContractBillingScheduleItemDTO, ...]:
        if not commands:
            raise ValidationError("At least one billing schedule item is required.")

        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, contract_id)
            repository = self._billing_schedule_repository_factory(uow.session)
            items = [
                self._build_schedule_item(company_id, contract_id, line_number, command)
                for line_number, command in enumerate(commands, start=1)
            ]
            repository.replace_items(company_id, contract_id, items)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Billing schedule could not be saved.") from exc

            return tuple(self._to_schedule_item_dto(item) for item in items)

    def list_billing_schedule(self, company_id: int, contract_id: int) -> tuple[ContractBillingScheduleItemDTO, ...]:
        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, contract_id)
            items = self._billing_schedule_repository_factory(uow.session).list_by_contract(company_id, contract_id)
            return tuple(self._to_schedule_item_dto(item) for item in items)

    def get_contract_value_summary(self, company_id: int, contract_id: int) -> ContractCommercialSummaryDTO:
        with self._unit_of_work_factory() as uow:
            contract = self._require_contract(uow.session, company_id, contract_id)
            line_repository = self._contract_line_repository_factory(uow.session)
            schedule_repository = self._billing_schedule_repository_factory(uow.session)

            original_contract_value = line_repository.sum_base_line_amount(company_id, contract_id)
            if original_contract_value == Decimal("0.00") and contract.base_contract_amount is not None:
                original_contract_value = self._money(contract.base_contract_amount)

            approved_variations = self._approved_variations(uow.session, company_id, contract_id)
            current_contract_value = self._money(original_contract_value + approved_variations)
            schedule_total = schedule_repository.sum_active_amount(company_id, contract_id)
            schedule_variance = self._money(schedule_total - current_contract_value)
            billed_amount = self._progress_amount(uow.session, company_id, contract_id, "billed")
            certified_amount = self._progress_amount(uow.session, company_id, contract_id, "certified")
            earned_amount = self._progress_amount(uow.session, company_id, contract_id, "earned")
            collected_amount = self._collected_amount(uow.session, company_id, contract_id)
            recovered_advance_amount = self._progress_amount(uow.session, company_id, contract_id, "advance")
            received_advance_amount = self._received_advance_amount(uow.session, company_id, contract_id)
            open_retention_amount = self._open_retention_amount(uow.session, company_id, contract_id)
            unrecovered_advance = self._money(received_advance_amount - recovered_advance_amount)

            return ContractCommercialSummaryDTO(
                company_id=company_id,
                contract_id=contract_id,
                original_contract_value=original_contract_value,
                approved_variations=approved_variations,
                current_contract_value=current_contract_value,
                billing_schedule_total=schedule_total,
                billing_schedule_variance=schedule_variance,
                billed_amount=billed_amount,
                certified_amount=certified_amount,
                earned_amount=earned_amount,
                collected_amount=collected_amount,
                unrecovered_advance_amount=unrecovered_advance,
                open_retention_amount=open_retention_amount,
                schedule_reconciles_to_contract_value=schedule_variance == Decimal("0.00"),
            )

    def require_billing_schedule_reconciled(self, company_id: int, contract_id: int) -> None:
        summary = self.get_contract_value_summary(company_id, contract_id)
        if not summary.schedule_reconciles_to_contract_value:
            raise ValidationError(
                "Billing schedule total does not reconcile to the current contract value."
            )

    def _approved_variations(self, session: Session, company_id: int, contract_id: int) -> Decimal:
        line_repository = self._contract_line_repository_factory(session)
        if line_repository.count_approved_change_order_lines(company_id, contract_id) > 0:
            return line_repository.sum_approved_change_order_line_amount(company_id, contract_id)
        if self._change_order_repository_factory is None:
            return Decimal("0.00")
        return self._money(self._change_order_repository_factory(session).sum_approved_amount_delta(contract_id))

    def _progress_amount(self, session: Session, company_id: int, contract_id: int, kind: str) -> Decimal:
        if self._progress_claim_repository_factory is None:
            return Decimal("0.00")
        repository = self._progress_claim_repository_factory(session)
        if kind == "billed":
            return repository.sum_billed_amount(company_id, contract_id)
        if kind == "certified":
            return repository.sum_certified_amount(company_id, contract_id)
        if kind == "earned":
            return repository.sum_earned_amount(company_id, contract_id)
        if kind == "advance":
            return repository.sum_advance_recovery_amount(company_id, contract_id)
        raise ValidationError(f"Unsupported progress amount kind: {kind}.")

    def _collected_amount(self, session: Session, company_id: int, contract_id: int) -> Decimal:
        if self._receipt_allocation_repository_factory is None:
            return Decimal("0.00")
        return self._receipt_allocation_repository_factory(session).sum_collected_amount(company_id, contract_id)

    def _received_advance_amount(self, session: Session, company_id: int, contract_id: int) -> Decimal:
        if self._advance_repository_factory is None:
            return Decimal("0.00")
        return self._advance_repository_factory(session).sum_received_amount(company_id, contract_id)

    def _open_retention_amount(self, session: Session, company_id: int, contract_id: int) -> Decimal:
        if self._retention_movement_repository_factory is None:
            return Decimal("0.00")
        return self._retention_movement_repository_factory(session).open_retention_balance(company_id, contract_id)

    def _require_contract(self, session: Session, company_id: int, contract_id: int) -> Contract:
        contract = self._contract_repository_factory(session).get_by_company_and_id(company_id, contract_id)
        if contract is None:
            raise NotFoundError(f"Contract {contract_id} was not found for company {company_id}.")
        return contract

    def _build_contract_line(
        self,
        company_id: int,
        contract_id: int,
        line_number: int,
        command: ContractLineCommand,
    ) -> ContractLine:
        description = self._required_text(command.description, "Contract line description")
        quantity = self._decimal(command.quantity, "Quantity")
        unit_rate = self._money(command.unit_rate)
        line_amount = self._money(command.line_amount if command.line_amount is not None else quantity * unit_rate)
        if quantity <= 0:
            raise ValidationError("Contract line quantity must be greater than zero.")
        if unit_rate < 0 or line_amount < 0:
            raise ValidationError("Contract line amounts cannot be negative.")
        if command.billing_basis_code not in _VALID_BILLING_BASIS_CODES:
            raise ValidationError(f"Unsupported billing basis: {command.billing_basis_code}.")

        return ContractLine(
            company_id=company_id,
            contract_id=contract_id,
            line_number=line_number,
            description=description,
            quantity=quantity.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            unit_rate=unit_rate,
            line_amount=line_amount,
            tax_code_id=command.tax_code_id,
            tax_treatment_code=self._optional_text(command.tax_treatment_code),
            billing_basis_code=command.billing_basis_code,
            project_id=command.project_id,
            project_job_id=command.project_job_id,
            change_order_id=command.change_order_id,
            status_code="active",
            notes=self._optional_text(command.notes),
        )

    def _build_schedule_item(
        self,
        company_id: int,
        contract_id: int,
        line_number: int,
        command: ContractBillingScheduleItemCommand,
    ) -> ContractBillingScheduleItem:
        description = self._required_text(command.description, "Billing schedule description")
        scheduled_amount = self._money(command.scheduled_amount)
        if scheduled_amount < 0:
            raise ValidationError("Billing schedule amount cannot be negative.")
        if command.schedule_type_code not in _VALID_SCHEDULE_TYPE_CODES:
            raise ValidationError(f"Unsupported billing schedule type: {command.schedule_type_code}.")
        retention_percent = self._optional_percent(command.retention_percent, "Retention percent")
        advance_recovery_percent = self._optional_percent(command.advance_recovery_percent, "Advance recovery percent")
        billing_percent = self._optional_percent(command.billing_percent, "Billing percent")

        return ContractBillingScheduleItem(
            company_id=company_id,
            contract_id=contract_id,
            line_number=line_number,
            schedule_type_code=command.schedule_type_code,
            description=description,
            scheduled_date=command.scheduled_date,
            milestone_code=self._optional_text(command.milestone_code),
            billing_percent=billing_percent,
            scheduled_amount=scheduled_amount,
            retention_percent=retention_percent,
            advance_recovery_percent=advance_recovery_percent,
            time_material_reference=self._optional_text(command.time_material_reference),
            contract_line_id=command.contract_line_id,
            project_id=command.project_id,
            project_job_id=command.project_job_id,
            status_code=self._required_text(command.status_code, "Billing schedule status"),
            notes=self._optional_text(command.notes),
        )

    def _to_line_dto(self, line: ContractLine) -> ContractLineDTO:
        return ContractLineDTO(
            id=line.id or 0,
            company_id=line.company_id,
            contract_id=line.contract_id,
            line_number=line.line_number,
            description=line.description,
            quantity=self._decimal(line.quantity, "Quantity"),
            unit_rate=self._money(line.unit_rate),
            line_amount=self._money(line.line_amount),
            tax_code_id=line.tax_code_id,
            tax_treatment_code=line.tax_treatment_code,
            billing_basis_code=line.billing_basis_code,
            project_id=line.project_id,
            project_job_id=line.project_job_id,
            change_order_id=line.change_order_id,
            status_code=line.status_code,
            notes=line.notes,
        )

    def _to_schedule_item_dto(self, item: ContractBillingScheduleItem) -> ContractBillingScheduleItemDTO:
        return ContractBillingScheduleItemDTO(
            id=item.id or 0,
            company_id=item.company_id,
            contract_id=item.contract_id,
            line_number=item.line_number,
            schedule_type_code=item.schedule_type_code,
            description=item.description,
            scheduled_amount=self._money(item.scheduled_amount),
            scheduled_date=item.scheduled_date,
            milestone_code=item.milestone_code,
            billing_percent=item.billing_percent,
            retention_percent=item.retention_percent,
            advance_recovery_percent=item.advance_recovery_percent,
            time_material_reference=item.time_material_reference,
            contract_line_id=item.contract_line_id,
            project_id=item.project_id,
            project_job_id=item.project_job_id,
            status_code=item.status_code,
            notes=item.notes,
        )

    def _decimal(self, value: Decimal | int | str, field_name: str) -> Decimal:
        try:
            return Decimal(str(value))
        except Exception as exc:
            raise ValidationError(f"{field_name} must be a valid number.") from exc

    def _money(self, value: Decimal | int | str) -> Decimal:
        return Decimal(str(value or 0)).quantize(_MONEY, rounding=ROUND_HALF_UP)

    def _optional_percent(self, value: Decimal | None, field_name: str) -> Decimal | None:
        if value is None:
            return None
        percent = Decimal(str(value)).quantize(_PERCENT, rounding=ROUND_HALF_UP)
        if percent < 0 or percent > 100:
            raise ValidationError(f"{field_name} must be between 0 and 100.")
        return percent

    def _required_text(self, value: str | None, field_name: str) -> str:
        cleaned = self._optional_text(value)
        if not cleaned:
            raise ValidationError(f"{field_name} is required.")
        return cleaned

    def _optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
