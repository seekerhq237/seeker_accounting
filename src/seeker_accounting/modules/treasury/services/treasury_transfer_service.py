from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.treasury.dto.treasury_transfer_commands import (
    CreateTreasuryTransferCommand,
    UpdateTreasuryTransferCommand,
)
from seeker_accounting.modules.treasury.dto.treasury_transfer_dto import (
    TreasuryTransferDetailDTO,
    TreasuryTransferListItemDTO,
)
from seeker_accounting.modules.treasury.models.treasury_transfer import TreasuryTransfer
from seeker_accounting.modules.treasury.repositories.financial_account_repository import FinancialAccountRepository
from seeker_accounting.modules.treasury.repositories.treasury_transfer_repository import TreasuryTransferRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
FinancialAccountRepositoryFactory = Callable[[Session], FinancialAccountRepository]
TreasuryTransferRepositoryFactory = Callable[[Session], TreasuryTransferRepository]


class TreasuryTransferService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        financial_account_repository_factory: FinancialAccountRepositoryFactory,
        treasury_transfer_repository_factory: TreasuryTransferRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._financial_account_repository_factory = financial_account_repository_factory
        self._treasury_transfer_repository_factory = treasury_transfer_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_treasury_transfers(
        self, company_id: int, status_code: str | None = None,
    ) -> list[TreasuryTransferListItemDTO]:
        self._permission_service.require_permission("treasury.transfers.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._treasury_transfer_repository_factory(uow.session)
            rows = repo.list_by_company(company_id, status_code=status_code)
            return [self._to_list_item_dto(r) for r in rows]

    def get_treasury_transfer(self, company_id: int, transfer_id: int) -> TreasuryTransferDetailDTO:
        self._permission_service.require_permission("treasury.transfers.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._treasury_transfer_repository_factory(uow.session)
            transfer = repo.get_detail(company_id, transfer_id)
            if transfer is None:
                raise NotFoundError(f"Treasury transfer with id {transfer_id} was not found.")
            return self._to_detail_dto(transfer)

    def create_draft_transfer(
        self, company_id: int, command: CreateTreasuryTransferCommand,
    ) -> TreasuryTransferDetailDTO:
        self._permission_service.require_permission("treasury.transfers.create")
        if command.amount <= Decimal("0.00"):
            raise ValidationError("Transfer amount must be greater than zero.")
        if command.from_financial_account_id == command.to_financial_account_id:
            raise ValidationError("Source and destination accounts must be different.")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            fa_repo = self._financial_account_repository_factory(uow.session)

            from_fa = fa_repo.get_by_id(company_id, command.from_financial_account_id)
            if from_fa is None or not from_fa.is_active:
                raise ValidationError("Source financial account must exist and be active.")
            to_fa = fa_repo.get_by_id(company_id, command.to_financial_account_id)
            if to_fa is None or not to_fa.is_active:
                raise ValidationError("Destination financial account must exist and be active.")

            draft_number = f"TF-DRAFT-{uuid.uuid4().hex[:8].upper()}"
            transfer = TreasuryTransfer(
                company_id=company_id,
                transfer_number=draft_number,
                from_financial_account_id=command.from_financial_account_id,
                to_financial_account_id=command.to_financial_account_id,
                transfer_date=command.transfer_date,
                currency_code=command.currency_code,
                exchange_rate=command.exchange_rate,
                amount=command.amount,
                status_code="draft",
                reference_number=command.reference_number,
                description=command.description,
                notes=command.notes,
            )
            repo = self._treasury_transfer_repository_factory(uow.session)
            repo.add(transfer)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import TREASURY_TRANSFER_CREATED
            self._record_audit(company_id, TREASURY_TRANSFER_CREATED, "TreasuryTransfer", transfer.id, "Created treasury transfer")
            return self.get_treasury_transfer(company_id, transfer.id)

    def update_draft_transfer(
        self, company_id: int, transfer_id: int, command: UpdateTreasuryTransferCommand,
    ) -> TreasuryTransferDetailDTO:
        self._permission_service.require_permission("treasury.transfers.edit")
        if command.amount <= Decimal("0.00"):
            raise ValidationError("Transfer amount must be greater than zero.")
        if command.from_financial_account_id == command.to_financial_account_id:
            raise ValidationError("Source and destination accounts must be different.")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._treasury_transfer_repository_factory(uow.session)
            fa_repo = self._financial_account_repository_factory(uow.session)

            transfer = repo.get_by_id(company_id, transfer_id)
            if transfer is None:
                raise NotFoundError(f"Treasury transfer with id {transfer_id} was not found.")
            if transfer.status_code != "draft":
                raise ValidationError("Only draft transfers can be edited.")

            from_fa = fa_repo.get_by_id(company_id, command.from_financial_account_id)
            if from_fa is None or not from_fa.is_active:
                raise ValidationError("Source financial account must exist and be active.")
            to_fa = fa_repo.get_by_id(company_id, command.to_financial_account_id)
            if to_fa is None or not to_fa.is_active:
                raise ValidationError("Destination financial account must exist and be active.")

            transfer.from_financial_account_id = command.from_financial_account_id
            transfer.to_financial_account_id = command.to_financial_account_id
            transfer.transfer_date = command.transfer_date
            transfer.currency_code = command.currency_code
            transfer.exchange_rate = command.exchange_rate
            transfer.amount = command.amount
            transfer.reference_number = command.reference_number
            transfer.description = command.description
            transfer.notes = command.notes
            repo.save(transfer)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import TREASURY_TRANSFER_UPDATED
            self._record_audit(company_id, TREASURY_TRANSFER_UPDATED, "TreasuryTransfer", transfer.id, "Updated treasury transfer")
            return self.get_treasury_transfer(company_id, transfer.id)

    def cancel_draft_transfer(self, company_id: int, transfer_id: int) -> None:
        self._permission_service.require_permission("treasury.transfers.cancel")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._treasury_transfer_repository_factory(uow.session)
            transfer = repo.get_by_id(company_id, transfer_id)
            if transfer is None:
                raise NotFoundError(f"Treasury transfer with id {transfer_id} was not found.")
            if transfer.status_code != "draft":
                raise ValidationError("Only draft transfers can be cancelled.")
            transfer.status_code = "cancelled"
            repo.save(transfer)
            uow.commit()

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _translate_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "transfer_number" in message:
            return ConflictError("A treasury transfer with this number already exists.")
        return ValidationError("Treasury transfer could not be saved.")

    def _to_list_item_dto(self, row: TreasuryTransfer) -> TreasuryTransferListItemDTO:
        return TreasuryTransferListItemDTO(
            id=row.id,
            company_id=row.company_id,
            transfer_number=row.transfer_number,
            from_financial_account_id=row.from_financial_account_id,
            from_account_name=row.from_financial_account.name if row.from_financial_account else "",
            to_financial_account_id=row.to_financial_account_id,
            to_account_name=row.to_financial_account.name if row.to_financial_account else "",
            transfer_date=row.transfer_date,
            currency_code=row.currency_code,
            amount=row.amount,
            status_code=row.status_code,
            reference_number=row.reference_number,
            posted_at=row.posted_at,
            updated_at=row.updated_at,
        )

    def _to_detail_dto(self, row: TreasuryTransfer) -> TreasuryTransferDetailDTO:
        return TreasuryTransferDetailDTO(
            id=row.id,
            company_id=row.company_id,
            transfer_number=row.transfer_number,
            from_financial_account_id=row.from_financial_account_id,
            from_account_name=row.from_financial_account.name if row.from_financial_account else "",
            to_financial_account_id=row.to_financial_account_id,
            to_account_name=row.to_financial_account.name if row.to_financial_account else "",
            transfer_date=row.transfer_date,
            currency_code=row.currency_code,
            exchange_rate=row.exchange_rate,
            amount=row.amount,
            status_code=row.status_code,
            reference_number=row.reference_number,
            description=row.description,
            notes=row.notes,
            posted_journal_entry_id=row.posted_journal_entry_id,
            posted_at=row.posted_at,
            posted_by_user_id=row.posted_by_user_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
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
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_TREASURY
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_TREASURY,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
