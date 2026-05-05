from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.contracts_projects.dto.contract_progress_billing_dto import (
    ContractAdvanceBalanceDTO,
    ContractRetentionBalanceDTO,
    CreateProgressClaimCommand,
    CustomerAdvanceDTO,
    GenerateProgressInvoiceCommand,
    ProgressClaimDTO,
    ProgressClaimLineCommand,
    ProgressClaimLineDTO,
    ProgressInvoiceResultDTO,
    ReceiptAllocationDTO,
    RecordContractReceiptAllocationCommand,
    RecordCustomerAdvanceCommand,
    ReleaseRetentionCommand,
    RetentionMovementDTO,
)
from seeker_accounting.modules.contracts_projects.models.contract import Contract
from seeker_accounting.modules.contracts_projects.models.contract_customer_advance import ContractCustomerAdvance
from seeker_accounting.modules.contracts_projects.models.contract_progress_claim import ContractProgressClaim
from seeker_accounting.modules.contracts_projects.models.contract_progress_claim_line import ContractProgressClaimLine
from seeker_accounting.modules.contracts_projects.models.contract_receipt_allocation import ContractReceiptAllocation
from seeker_accounting.modules.contracts_projects.models.contract_retention_movement import ContractRetentionMovement
from seeker_accounting.modules.contracts_projects.repositories.contract_customer_advance_repository import (
    ContractCustomerAdvanceRepository,
)
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
from seeker_accounting.modules.sales.dto.sales_invoice_commands import CreateSalesInvoiceCommand, SalesInvoiceLineCommand
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

ContractRepositoryFactory = Callable[[Session], ContractRepository]
ContractProgressClaimRepositoryFactory = Callable[[Session], ContractProgressClaimRepository]
ContractCustomerAdvanceRepositoryFactory = Callable[[Session], ContractCustomerAdvanceRepository]
ContractRetentionMovementRepositoryFactory = Callable[[Session], ContractRetentionMovementRepository]
ContractReceiptAllocationRepositoryFactory = Callable[[Session], ContractReceiptAllocationRepository]

_MONEY = Decimal("0.01")
_QUANTITY = Decimal("0.0001")
_ZERO = Decimal("0.00")


class SalesInvoiceCreator(Protocol):
    def create_draft_invoice(self, company_id: int, command: CreateSalesInvoiceCommand): ...


class ContractProgressBillingService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        contract_repository_factory: ContractRepositoryFactory,
        progress_claim_repository_factory: ContractProgressClaimRepositoryFactory,
        advance_repository_factory: ContractCustomerAdvanceRepositoryFactory,
        retention_movement_repository_factory: ContractRetentionMovementRepositoryFactory,
        receipt_allocation_repository_factory: ContractReceiptAllocationRepositoryFactory,
        sales_invoice_service: SalesInvoiceCreator | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._contract_repository_factory = contract_repository_factory
        self._progress_claim_repository_factory = progress_claim_repository_factory
        self._advance_repository_factory = advance_repository_factory
        self._retention_movement_repository_factory = retention_movement_repository_factory
        self._receipt_allocation_repository_factory = receipt_allocation_repository_factory
        self._sales_invoice_service = sales_invoice_service

    def create_progress_claim(self, company_id: int, command: CreateProgressClaimCommand) -> ProgressClaimDTO:
        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, command.contract_id)
            repository = self._progress_claim_repository_factory(uow.session)
            if repository.get_by_claim_number(company_id, command.claim_number) is not None:
                raise ConflictError(f"Progress claim number {command.claim_number} already exists.")

            previous_certified_amount = self._money(
                command.previous_certified_amount
                if command.previous_certified_amount is not None
                else repository.sum_certified_amount(company_id, command.contract_id)
            )
            certified_amount = self._money(command.certified_amount)
            current_claim_amount = self._resolve_current_claim_amount(command, certified_amount, previous_certified_amount)
            earned_amount = self._money(command.earned_amount if command.earned_amount is not None else certified_amount)
            taxable_base_amount = self._money(command.taxable_base_amount if command.taxable_base_amount is not None else current_claim_amount)
            vat_amount = self._money(command.vat_amount)
            retention_percent = self._optional_percent(command.retention_percent, "Retention percent")
            retention_amount = self._resolve_retention_amount(command, current_claim_amount, retention_percent)
            advance_recovery_amount = self._money(command.advance_recovery_amount)
            withheld_vat_amount = self._money(command.withheld_vat_amount)
            withholding_tax_amount = self._money(command.withholding_tax_amount)
            net_receivable_amount = self._money(
                current_claim_amount
                + vat_amount
                - retention_amount
                - advance_recovery_amount
                - withheld_vat_amount
                - withholding_tax_amount
            )
            self._validate_claim_amounts(
                certified_amount=certified_amount,
                previous_certified_amount=previous_certified_amount,
                current_claim_amount=current_claim_amount,
                earned_amount=earned_amount,
                taxable_base_amount=taxable_base_amount,
                vat_amount=vat_amount,
                retention_amount=retention_amount,
                advance_recovery_amount=advance_recovery_amount,
                withheld_vat_amount=withheld_vat_amount,
                withholding_tax_amount=withholding_tax_amount,
                net_receivable_amount=net_receivable_amount,
            )
            lines = self._build_claim_lines(company_id, command.lines, current_claim_amount)
            certified_line_total = sum((line.certified_amount for line in lines), _ZERO).quantize(_MONEY)
            if lines and certified_line_total != current_claim_amount:
                raise ValidationError("Progress claim line certified total must match the current claim amount.")

            claim = ContractProgressClaim(
                company_id=company_id,
                contract_id=command.contract_id,
                claim_number=self._required_text(command.claim_number, "Progress claim number"),
                claim_date=command.claim_date,
                status_code="certified",
                billing_schedule_item_id=command.billing_schedule_item_id,
                sales_invoice_id=None,
                taxable_base_amount=taxable_base_amount,
                previous_certified_amount=previous_certified_amount,
                current_claim_amount=current_claim_amount,
                certified_amount=certified_amount,
                earned_amount=earned_amount,
                vat_amount=vat_amount,
                retention_percent=retention_percent,
                retention_amount=retention_amount,
                advance_recovery_amount=advance_recovery_amount,
                withheld_vat_amount=withheld_vat_amount,
                withholding_tax_amount=withholding_tax_amount,
                net_receivable_amount=net_receivable_amount,
                source_reference=self._optional_text(command.source_reference),
                notes=self._optional_text(command.notes),
                certified_at=datetime.now(timezone.utc).replace(tzinfo=None),
                certified_by_user_id=None,
                lines=lines,
            )
            repository.add(claim)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Progress claim could not be created.") from exc

            return self._to_claim_dto(claim)

    def generate_sales_invoice_from_claim(
        self,
        company_id: int,
        command: GenerateProgressInvoiceCommand,
    ) -> ProgressInvoiceResultDTO:
        if self._sales_invoice_service is None:
            raise ValidationError("Sales invoice service is not configured for progress billing.")

        with self._unit_of_work_factory() as uow:
            contract_repository = self._contract_repository_factory(uow.session)
            claim_repository = self._progress_claim_repository_factory(uow.session)
            retention_repository = self._retention_movement_repository_factory(uow.session)
            claim = claim_repository.get_by_company_and_id(company_id, command.claim_id)
            if claim is None:
                raise NotFoundError(f"Progress claim {command.claim_id} was not found.")
            if claim.status_code != "certified":
                raise ValidationError("Only certified progress claims can generate sales invoices.")
            if claim.sales_invoice_id is not None:
                raise ConflictError("Progress claim already has a sales invoice.")
            contract = contract_repository.get_by_company_and_id(company_id, claim.contract_id)
            if contract is None:
                raise NotFoundError(f"Contract {claim.contract_id} was not found for company {company_id}.")

            invoice_detail = self._sales_invoice_service.create_draft_invoice(
                company_id,
                self._build_sales_invoice_command(contract, claim, command),
            )
            claim.sales_invoice_id = invoice_detail.id
            claim.status_code = "invoiced"
            claim_repository.save(claim)

            if claim.retention_amount > _ZERO:
                retention_repository.add(
                    ContractRetentionMovement(
                        company_id=company_id,
                        contract_id=claim.contract_id,
                        progress_claim_id=claim.id,
                        sales_invoice_id=invoice_detail.id,
                        customer_receipt_id=None,
                        movement_date=command.invoice_date,
                        due_date=None,
                        movement_type_code="withheld",
                        status_code="open",
                        amount=self._money(claim.retention_amount),
                        notes=f"Retention withheld on progress claim {claim.claim_number}",
                    )
                )

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Progress invoice linkage could not be saved.") from exc

            return ProgressInvoiceResultDTO(
                progress_claim_id=claim.id,
                sales_invoice_id=invoice_detail.id,
                invoice_number=invoice_detail.invoice_number,
                gross_claim_amount=self._money(claim.current_claim_amount),
                vat_amount=self._money(claim.vat_amount),
                retention_amount=self._money(claim.retention_amount),
                advance_recovery_amount=self._money(claim.advance_recovery_amount),
                withheld_vat_amount=self._money(claim.withheld_vat_amount),
                withholding_tax_amount=self._money(claim.withholding_tax_amount),
                net_receivable_amount=self._money(claim.net_receivable_amount),
            )

    def record_customer_advance(self, company_id: int, command: RecordCustomerAdvanceCommand) -> ContractAdvanceBalanceDTO:
        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, command.contract_id)
            repository = self._advance_repository_factory(uow.session)
            if repository.get_by_advance_number(company_id, command.advance_number) is not None:
                raise ConflictError(f"Customer advance number {command.advance_number} already exists.")
            advance_amount = self._money(command.advance_amount)
            received_amount = self._money(command.received_amount)
            if advance_amount <= _ZERO:
                raise ValidationError("Customer advance amount must be greater than zero.")
            if received_amount < _ZERO or received_amount > advance_amount:
                raise ValidationError("Received customer advance amount must be between zero and the advance amount.")
            recovery_percent = self._optional_percent(command.recovery_percent, "Advance recovery percent")

            repository.add(
                ContractCustomerAdvance(
                    company_id=company_id,
                    contract_id=command.contract_id,
                    advance_number=self._required_text(command.advance_number, "Customer advance number"),
                    advance_date=command.advance_date,
                    status_code="received",
                    source_invoice_id=command.source_invoice_id,
                    customer_receipt_id=command.customer_receipt_id,
                    advance_amount=advance_amount,
                    received_amount=received_amount,
                    recovery_basis_code=self._optional_text(command.recovery_basis_code),
                    recovery_percent=recovery_percent,
                    notes=self._optional_text(command.notes),
                )
            )

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Customer advance could not be recorded.") from exc

            return self.get_advance_balance(company_id, command.contract_id)

    def get_advance_balance(self, company_id: int, contract_id: int) -> ContractAdvanceBalanceDTO:
        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, contract_id)
            received_amount = self._advance_repository_factory(uow.session).sum_received_amount(company_id, contract_id)
            recovered_amount = self._progress_claim_repository_factory(uow.session).sum_advance_recovery_amount(company_id, contract_id)
            return ContractAdvanceBalanceDTO(
                company_id=company_id,
                contract_id=contract_id,
                received_advance_amount=received_amount,
                recovered_advance_amount=recovered_amount,
                unrecovered_advance_amount=self._money(received_amount - recovered_amount),
            )

    def record_receipt_allocation(
        self,
        company_id: int,
        command: RecordContractReceiptAllocationCommand,
    ) -> Decimal:
        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, command.contract_id)
            gross_amount = self._money(command.gross_amount)
            net_receivable_amount = self._money(command.net_receivable_amount)
            withholding_vat_amount = self._money(command.withholding_vat_amount)
            withholding_tax_amount = self._money(command.withholding_tax_amount)
            retention_amount = self._money(command.retention_amount)
            advance_recovery_amount = self._money(command.advance_recovery_amount)
            total_allocated_amount = self._money(
                net_receivable_amount
                + withholding_vat_amount
                + withholding_tax_amount
                + retention_amount
                + advance_recovery_amount
            )
            if gross_amount <= _ZERO:
                raise ValidationError("Receipt allocation gross amount must be greater than zero.")
            if total_allocated_amount != gross_amount:
                raise ValidationError("Receipt allocation components must reconcile to the gross amount.")

            allocation = ContractReceiptAllocation(
                company_id=company_id,
                contract_id=command.contract_id,
                customer_receipt_id=command.customer_receipt_id,
                sales_invoice_id=command.sales_invoice_id,
                progress_claim_id=command.progress_claim_id,
                allocation_date=command.allocation_date,
                gross_amount=gross_amount,
                net_receivable_amount=net_receivable_amount,
                withholding_vat_amount=withholding_vat_amount,
                withholding_tax_amount=withholding_tax_amount,
                retention_amount=retention_amount,
                advance_recovery_amount=advance_recovery_amount,
                total_allocated_amount=total_allocated_amount,
                notes=self._optional_text(command.notes),
            )
            self._receipt_allocation_repository_factory(uow.session).add(allocation)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Contract receipt allocation could not be recorded.") from exc

            return total_allocated_amount

    def release_retention(self, company_id: int, command: ReleaseRetentionCommand) -> ContractRetentionBalanceDTO:
        if command.movement_type_code not in {"partial_release", "final_release", "write_off"}:
            raise ValidationError("Retention release type must be partial_release, final_release, or write_off.")
        amount = self._money(command.amount)
        if amount <= _ZERO:
            raise ValidationError("Retention release amount must be greater than zero.")

        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, command.contract_id)
            repository = self._retention_movement_repository_factory(uow.session)
            open_balance = repository.open_retention_balance(company_id, command.contract_id)
            if amount > open_balance:
                raise ValidationError("Retention release cannot exceed the open retention balance.")
            repository.add(
                ContractRetentionMovement(
                    company_id=company_id,
                    contract_id=command.contract_id,
                    progress_claim_id=command.progress_claim_id,
                    sales_invoice_id=command.sales_invoice_id,
                    customer_receipt_id=command.customer_receipt_id,
                    movement_date=command.movement_date,
                    due_date=None,
                    movement_type_code=command.movement_type_code,
                    status_code="posted",
                    amount=amount,
                    notes=self._optional_text(command.notes),
                )
            )

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ValidationError("Retention movement could not be recorded.") from exc

            return self.get_retention_balance(company_id, command.contract_id)

    def get_retention_balance(self, company_id: int, contract_id: int) -> ContractRetentionBalanceDTO:
        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, contract_id)
            open_balance = self._retention_movement_repository_factory(uow.session).open_retention_balance(
                company_id,
                contract_id,
            )
            return ContractRetentionBalanceDTO(
                company_id=company_id,
                contract_id=contract_id,
                open_retention_amount=open_balance,
            )

    # ------------------------------------------------------------------
    # List queries
    # ------------------------------------------------------------------

    def list_progress_claims(self, company_id: int, contract_id: int) -> tuple[ProgressClaimDTO, ...]:
        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, contract_id)
            claims = self._progress_claim_repository_factory(uow.session).list_by_contract(company_id, contract_id)
            return tuple(self._to_claim_dto(claim) for claim in claims)

    def list_customer_advances(self, company_id: int, contract_id: int) -> tuple[CustomerAdvanceDTO, ...]:
        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, contract_id)
            advances = self._advance_repository_factory(uow.session).list_by_contract(company_id, contract_id)
            return tuple(self._to_advance_dto(adv) for adv in advances)

    def list_retention_movements(self, company_id: int, contract_id: int) -> tuple[RetentionMovementDTO, ...]:
        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, contract_id)
            movements = self._retention_movement_repository_factory(uow.session).list_by_contract(company_id, contract_id)
            return tuple(self._to_retention_dto(mv) for mv in movements)

    def list_receipt_allocations(self, company_id: int, contract_id: int) -> tuple[ReceiptAllocationDTO, ...]:
        with self._unit_of_work_factory() as uow:
            self._require_contract(uow.session, company_id, contract_id)
            allocations = self._receipt_allocation_repository_factory(uow.session).list_by_contract(company_id, contract_id)
            return tuple(self._to_allocation_dto(alloc) for alloc in allocations)

    def _build_sales_invoice_command(
        self,
        contract: Contract,
        claim: ContractProgressClaim,
        command: GenerateProgressInvoiceCommand,
    ) -> CreateSalesInvoiceCommand:
        invoice_lines = self._build_sales_invoice_lines(claim, command.revenue_account_id, command.tax_code_id)
        return CreateSalesInvoiceCommand(
            customer_id=contract.customer_id,
            invoice_date=command.invoice_date,
            due_date=command.due_date,
            currency_code=contract.currency_code,
            exchange_rate=contract.exchange_rate,
            reference_number=claim.claim_number,
            notes=claim.notes,
            contract_id=contract.id,
            project_id=invoice_lines[0].project_id if invoice_lines else None,
            is_tax_inclusive=False,
            tax_point_date=command.invoice_date,
            lines=tuple(invoice_lines),
            withheld_vat_amount=claim.withheld_vat_amount,
        )

    def _build_sales_invoice_lines(
        self,
        claim: ContractProgressClaim,
        revenue_account_id: int,
        tax_code_id: int | None,
    ) -> list[SalesInvoiceLineCommand]:
        if revenue_account_id <= 0:
            raise ValidationError("Revenue account is required for progress invoice generation.")
        if claim.lines:
            return [
                SalesInvoiceLineCommand(
                    description=line.description,
                    quantity=Decimal("1.0000"),
                    unit_price=self._money(line.certified_amount),
                    tax_code_id=tax_code_id,
                    revenue_account_id=revenue_account_id,
                    contract_id=claim.contract_id,
                    project_id=line.project_id,
                    project_job_id=line.project_job_id,
                    project_cost_code_id=line.project_cost_code_id,
                )
                for line in claim.lines
                if line.certified_amount > _ZERO
            ]
        return [
            SalesInvoiceLineCommand(
                description=f"Progress claim {claim.claim_number}",
                quantity=Decimal("1.0000"),
                unit_price=self._money(claim.current_claim_amount),
                tax_code_id=tax_code_id,
                revenue_account_id=revenue_account_id,
                contract_id=claim.contract_id,
            )
        ]

    def _build_claim_lines(
        self,
        company_id: int,
        commands: tuple[ProgressClaimLineCommand, ...],
        current_claim_amount: Decimal,
    ) -> list[ContractProgressClaimLine]:
        lines: list[ContractProgressClaimLine] = []
        for line_number, command in enumerate(commands, start=1):
            quantity = self._quantity(command.quantity)
            unit_rate = self._money(command.unit_rate)
            claimed_amount = self._money(command.claimed_amount if command.claimed_amount is not None else quantity * unit_rate)
            certified_amount = self._money(command.certified_amount if command.certified_amount is not None else claimed_amount)
            if quantity <= Decimal("0.0000"):
                raise ValidationError("Progress claim line quantity must be greater than zero.")
            if claimed_amount < _ZERO or certified_amount < _ZERO:
                raise ValidationError("Progress claim line amounts cannot be negative.")
            lines.append(
                ContractProgressClaimLine(
                    company_id=company_id,
                    progress_claim_id=0,
                    line_number=line_number,
                    contract_line_id=command.contract_line_id,
                    billing_schedule_item_id=command.billing_schedule_item_id,
                    description=self._required_text(command.description, "Progress claim line description"),
                    quantity=quantity,
                    unit_rate=unit_rate,
                    claimed_amount=claimed_amount,
                    certified_amount=certified_amount,
                    project_id=command.project_id,
                    project_job_id=command.project_job_id,
                    project_cost_code_id=command.project_cost_code_id,
                )
            )
        if not lines and current_claim_amount <= _ZERO:
            raise ValidationError("Current claim amount must be greater than zero.")
        return lines

    def _resolve_current_claim_amount(
        self,
        command: CreateProgressClaimCommand,
        certified_amount: Decimal,
        previous_certified_amount: Decimal,
    ) -> Decimal:
        if command.current_claim_amount is not None:
            return self._money(command.current_claim_amount)
        return self._money(certified_amount - previous_certified_amount)

    def _resolve_retention_amount(
        self,
        command: CreateProgressClaimCommand,
        current_claim_amount: Decimal,
        retention_percent: Decimal | None,
    ) -> Decimal:
        if command.retention_amount is not None:
            return self._money(command.retention_amount)
        if retention_percent is None:
            return _ZERO
        return self._money(current_claim_amount * retention_percent / Decimal("100"))

    def _validate_claim_amounts(
        self,
        *,
        certified_amount: Decimal,
        previous_certified_amount: Decimal,
        current_claim_amount: Decimal,
        earned_amount: Decimal,
        taxable_base_amount: Decimal,
        vat_amount: Decimal,
        retention_amount: Decimal,
        advance_recovery_amount: Decimal,
        withheld_vat_amount: Decimal,
        withholding_tax_amount: Decimal,
        net_receivable_amount: Decimal,
    ) -> None:
        if certified_amount < _ZERO or previous_certified_amount < _ZERO:
            raise ValidationError("Certified amounts cannot be negative.")
        if current_claim_amount <= _ZERO:
            raise ValidationError("Current claim amount must be greater than zero.")
        if earned_amount < _ZERO or taxable_base_amount < _ZERO or vat_amount < _ZERO:
            raise ValidationError("Progress claim basis amounts cannot be negative.")
        if retention_amount < _ZERO or advance_recovery_amount < _ZERO:
            raise ValidationError("Retention and advance recovery amounts cannot be negative.")
        if withheld_vat_amount < _ZERO or withholding_tax_amount < _ZERO:
            raise ValidationError("Withholding amounts cannot be negative.")
        if retention_amount + advance_recovery_amount + withheld_vat_amount + withholding_tax_amount > current_claim_amount + vat_amount:
            raise ValidationError("Progress claim deductions cannot exceed the gross claim amount.")
        if net_receivable_amount < _ZERO:
            raise ValidationError("Progress claim net receivable cannot be negative.")

    def _require_contract(self, session: Session, company_id: int, contract_id: int) -> Contract:
        contract = self._contract_repository_factory(session).get_by_company_and_id(company_id, contract_id)
        if contract is None:
            raise NotFoundError(f"Contract {contract_id} was not found for company {company_id}.")
        return contract

    def _to_claim_dto(self, claim: ContractProgressClaim) -> ProgressClaimDTO:
        return ProgressClaimDTO(
            id=claim.id or 0,
            company_id=claim.company_id,
            contract_id=claim.contract_id,
            claim_number=claim.claim_number,
            claim_date=claim.claim_date,
            status_code=claim.status_code,
            billing_schedule_item_id=claim.billing_schedule_item_id,
            sales_invoice_id=claim.sales_invoice_id,
            taxable_base_amount=self._money(claim.taxable_base_amount),
            previous_certified_amount=self._money(claim.previous_certified_amount),
            current_claim_amount=self._money(claim.current_claim_amount),
            certified_amount=self._money(claim.certified_amount),
            earned_amount=self._money(claim.earned_amount),
            vat_amount=self._money(claim.vat_amount),
            retention_percent=claim.retention_percent,
            retention_amount=self._money(claim.retention_amount),
            advance_recovery_amount=self._money(claim.advance_recovery_amount),
            withheld_vat_amount=self._money(claim.withheld_vat_amount),
            withholding_tax_amount=self._money(claim.withholding_tax_amount),
            net_receivable_amount=self._money(claim.net_receivable_amount),
            source_reference=claim.source_reference,
            notes=claim.notes,
            certified_at=claim.certified_at,
            certified_by_user_id=claim.certified_by_user_id,
            lines=tuple(self._to_claim_line_dto(line) for line in claim.lines),
        )

    def _to_claim_line_dto(self, line: ContractProgressClaimLine) -> ProgressClaimLineDTO:
        return ProgressClaimLineDTO(
            id=line.id or 0,
            line_number=line.line_number,
            description=line.description,
            quantity=line.quantity,
            unit_rate=self._money(line.unit_rate),
            claimed_amount=self._money(line.claimed_amount),
            certified_amount=self._money(line.certified_amount),
            contract_line_id=line.contract_line_id,
            billing_schedule_item_id=line.billing_schedule_item_id,
            project_id=line.project_id,
            project_job_id=line.project_job_id,
            project_cost_code_id=line.project_cost_code_id,
        )

    def _to_advance_dto(self, adv: ContractCustomerAdvance) -> CustomerAdvanceDTO:
        return CustomerAdvanceDTO(
            id=adv.id or 0,
            company_id=adv.company_id,
            contract_id=adv.contract_id,
            advance_number=adv.advance_number,
            advance_date=adv.advance_date,
            status_code=adv.status_code,
            advance_amount=self._money(adv.advance_amount),
            received_amount=self._money(adv.received_amount),
            recovery_basis_code=adv.recovery_basis_code,
            recovery_percent=adv.recovery_percent,
            notes=adv.notes,
        )

    def _to_retention_dto(self, mv: ContractRetentionMovement) -> RetentionMovementDTO:
        return RetentionMovementDTO(
            id=mv.id or 0,
            company_id=mv.company_id,
            contract_id=mv.contract_id,
            movement_date=mv.movement_date,
            due_date=mv.due_date,
            movement_type_code=mv.movement_type_code,
            status_code=mv.status_code,
            amount=self._money(mv.amount),
            progress_claim_id=mv.progress_claim_id,
            sales_invoice_id=mv.sales_invoice_id,
            notes=mv.notes,
        )

    def _to_allocation_dto(self, alloc: ContractReceiptAllocation) -> ReceiptAllocationDTO:
        return ReceiptAllocationDTO(
            id=alloc.id or 0,
            company_id=alloc.company_id,
            contract_id=alloc.contract_id,
            allocation_date=alloc.allocation_date,
            gross_amount=self._money(alloc.gross_amount),
            net_receivable_amount=self._money(alloc.net_receivable_amount),
            withholding_vat_amount=self._money(alloc.withholding_vat_amount),
            withholding_tax_amount=self._money(alloc.withholding_tax_amount),
            retention_amount=self._money(alloc.retention_amount),
            advance_recovery_amount=self._money(alloc.advance_recovery_amount),
            total_allocated_amount=self._money(alloc.total_allocated_amount),
            progress_claim_id=alloc.progress_claim_id,
            sales_invoice_id=alloc.sales_invoice_id,
            notes=alloc.notes,
        )

    def _money(self, value: Decimal | int | str | None) -> Decimal:
        return Decimal(str(value or 0)).quantize(_MONEY, rounding=ROUND_HALF_UP)

    def _quantity(self, value: Decimal | int | str) -> Decimal:
        return Decimal(str(value)).quantize(_QUANTITY, rounding=ROUND_HALF_UP)

    def _optional_percent(self, value: Decimal | None, field_name: str) -> Decimal | None:
        if value is None:
            return None
        percent = Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
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
