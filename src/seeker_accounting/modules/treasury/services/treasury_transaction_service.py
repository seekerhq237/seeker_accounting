from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import AccountRepository
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import CurrencyRepository
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.job_costing.services.project_dimension_validation_service import (
    ProjectDimensionValidationService,
)
from seeker_accounting.modules.treasury.dto.treasury_transaction_commands import (
    CreateTreasuryTransactionCommand,
    TreasuryTransactionLineCommand,
    UpdateTreasuryTransactionCommand,
)
from seeker_accounting.modules.treasury.dto.treasury_transaction_dto import (
    TreasuryTransactionDetailDTO,
    TreasuryTransactionLineDTO,
    TreasuryTransactionListItemDTO,
)
from seeker_accounting.modules.treasury.models.treasury_transaction import TreasuryTransaction
from seeker_accounting.modules.treasury.models.treasury_transaction_line import TreasuryTransactionLine
from seeker_accounting.modules.treasury.repositories.financial_account_repository import FinancialAccountRepository
from seeker_accounting.modules.treasury.repositories.treasury_transaction_line_repository import (
    TreasuryTransactionLineRepository,
)
from seeker_accounting.modules.treasury.repositories.treasury_transaction_repository import (
    TreasuryTransactionRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]
FinancialAccountRepositoryFactory = Callable[[Session], FinancialAccountRepository]
TreasuryTransactionRepositoryFactory = Callable[[Session], TreasuryTransactionRepository]
TreasuryTransactionLineRepositoryFactory = Callable[[Session], TreasuryTransactionLineRepository]

_ALLOWED_TRANSACTION_TYPE_CODES = {"cash_receipt", "cash_payment", "bank_receipt", "bank_payment"}


class TreasuryTransactionService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        currency_repository_factory: CurrencyRepositoryFactory,
        financial_account_repository_factory: FinancialAccountRepositoryFactory,
        treasury_transaction_repository_factory: TreasuryTransactionRepositoryFactory,
        treasury_transaction_line_repository_factory: TreasuryTransactionLineRepositoryFactory,
        project_dimension_validation_service: ProjectDimensionValidationService,
        permission_service: PermissionService,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._account_repository_factory = account_repository_factory
        self._currency_repository_factory = currency_repository_factory
        self._financial_account_repository_factory = financial_account_repository_factory
        self._treasury_transaction_repository_factory = treasury_transaction_repository_factory
        self._treasury_transaction_line_repository_factory = treasury_transaction_line_repository_factory
        self._project_dimension_validation_service = project_dimension_validation_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_treasury_transactions(
        self,
        company_id: int,
        status_code: str | None = None,
        transaction_type_code: str | None = None,
    ) -> list[TreasuryTransactionListItemDTO]:
        self._permission_service.require_permission("treasury.transactions.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._treasury_transaction_repository_factory(uow.session)
            rows = repo.list_by_company(company_id, status_code=status_code, transaction_type_code=transaction_type_code)
            return [self._to_list_item_dto(r) for r in rows]

    def list_treasury_transactions_page(
        self,
        company_id: int,
        status_code: str | None = None,
        transaction_type_code: str | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> "PaginatedResult[TreasuryTransactionListItemDTO]":
        """Paginated + searchable treasury transaction listing."""
        from seeker_accounting.shared.dto.paginated_result import (
            PaginatedResult,
            normalize_page,
            normalize_page_size,
        )

        self._permission_service.require_permission("treasury.transactions.view")
        safe_page = normalize_page(page)
        safe_size = normalize_page_size(page_size)
        offset = (safe_page - 1) * safe_size

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._treasury_transaction_repository_factory(uow.session)
            total = repo.count_filtered(
                company_id,
                status_code=status_code,
                transaction_type_code=transaction_type_code,
                query=query,
            )
            rows = repo.list_filtered_page(
                company_id,
                status_code=status_code,
                transaction_type_code=transaction_type_code,
                query=query,
                limit=safe_size,
                offset=offset,
            )
            items = tuple(self._to_list_item_dto(r) for r in rows)

        return PaginatedResult(
            items=items,
            total_count=total,
            page=safe_page,
            page_size=safe_size,
        )

    def list_treasury_transactions_page(
        self,
        company_id: int,
        status_code: str | None = None,
        transaction_type_code: str | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> "PaginatedResult[TreasuryTransactionListItemDTO]":
        """Paginated + searchable treasury transaction listing."""
        from seeker_accounting.shared.dto.paginated_result import (
            PaginatedResult,
            normalize_page,
            normalize_page_size,
        )

        self._permission_service.require_permission("treasury.transactions.view")
        safe_page = normalize_page(page)
        safe_size = normalize_page_size(page_size)
        offset = (safe_page - 1) * safe_size

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._treasury_transaction_repository_factory(uow.session)
            total = repo.count_filtered(
                company_id,
                status_code=status_code,
                transaction_type_code=transaction_type_code,
                query=query,
            )
            rows = repo.list_filtered_page(
                company_id,
                status_code=status_code,
                transaction_type_code=transaction_type_code,
                query=query,
                limit=safe_size,
                offset=offset,
            )
            items = tuple(self._to_list_item_dto(r) for r in rows)

        return PaginatedResult(
            items=items,
            total_count=total,
            page=safe_page,
            page_size=safe_size,
        )

    def get_treasury_transaction(
        self, company_id: int, transaction_id: int
    ) -> TreasuryTransactionDetailDTO:
        self._permission_service.require_permission("treasury.transactions.view")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._treasury_transaction_repository_factory(uow.session)
            txn = repo.get_detail(company_id, transaction_id)
            if txn is None:
                raise NotFoundError(f"Treasury transaction with id {transaction_id} was not found.")
            return self._to_detail_dto(txn)

    def create_draft_transaction(
        self,
        company_id: int,
        command: CreateTreasuryTransactionCommand,
    ) -> TreasuryTransactionDetailDTO:
        self._permission_service.require_permission("treasury.transactions.create")
        normalized_command = self._normalize_create_command(command)
        self._validate_transaction_type(normalized_command.transaction_type_code)
        if not normalized_command.lines:
            raise ValidationError("At least one counterpart line is required.")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            fa_repo = self._financial_account_repository_factory(uow.session)
            account_repo = self._account_repository_factory(uow.session)

            fa = fa_repo.get_by_id(company_id, normalized_command.financial_account_id)
            if fa is None or not fa.is_active:
                raise ValidationError("Financial account must exist and be active.")

            self._project_dimension_validation_service.validate_header_dimensions(
                session=uow.session,
                company_id=company_id,
                contract_id=normalized_command.contract_id,
                project_id=normalized_command.project_id,
            )
            transaction_lines, total = self._build_transaction_lines(
                session=uow.session,
                company_id=company_id,
                header_contract_id=normalized_command.contract_id,
                header_project_id=normalized_command.project_id,
                lines=normalized_command.lines,
                account_repo=account_repo,
            )

            draft_number = f"TT-DRAFT-{uuid.uuid4().hex[:8].upper()}"
            txn = TreasuryTransaction(
                company_id=company_id,
                transaction_number=draft_number,
                transaction_type_code=normalized_command.transaction_type_code,
                financial_account_id=normalized_command.financial_account_id,
                transaction_date=normalized_command.transaction_date,
                currency_code=normalized_command.currency_code,
                exchange_rate=normalized_command.exchange_rate,
                total_amount=total,
                status_code="draft",
                reference_number=normalized_command.reference_number,
                description=normalized_command.description,
                notes=normalized_command.notes,
                contract_id=normalized_command.contract_id,
                project_id=normalized_command.project_id,
            )
            repo = self._treasury_transaction_repository_factory(uow.session)
            repo.add(txn)
            uow.session.flush()

            for line in transaction_lines:
                line.treasury_transaction_id = txn.id
                uow.session.add(line)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import TREASURY_TRANSACTION_CREATED
            self._record_audit(company_id, TREASURY_TRANSACTION_CREATED, "TreasuryTransaction", txn.id, "Created treasury transaction")
            return self.get_treasury_transaction(company_id, txn.id)

    def update_draft_transaction(
        self,
        company_id: int,
        transaction_id: int,
        command: UpdateTreasuryTransactionCommand,
    ) -> TreasuryTransactionDetailDTO:
        self._permission_service.require_permission("treasury.transactions.edit")
        normalized_command = self._normalize_update_command(command)
        self._validate_transaction_type(normalized_command.transaction_type_code)
        if not normalized_command.lines:
            raise ValidationError("At least one counterpart line is required.")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._treasury_transaction_repository_factory(uow.session)
            fa_repo = self._financial_account_repository_factory(uow.session)
            account_repo = self._account_repository_factory(uow.session)
            line_repo = self._treasury_transaction_line_repository_factory(uow.session)

            txn = repo.get_by_id(company_id, transaction_id)
            if txn is None:
                raise NotFoundError(f"Treasury transaction with id {transaction_id} was not found.")
            if txn.status_code != "draft":
                raise ValidationError("Only draft transactions can be edited.")

            fa = fa_repo.get_by_id(company_id, normalized_command.financial_account_id)
            if fa is None or not fa.is_active:
                raise ValidationError("Financial account must exist and be active.")

            self._project_dimension_validation_service.validate_header_dimensions(
                session=uow.session,
                company_id=company_id,
                contract_id=normalized_command.contract_id,
                project_id=normalized_command.project_id,
            )
            transaction_lines, total = self._build_transaction_lines(
                session=uow.session,
                company_id=company_id,
                header_contract_id=normalized_command.contract_id,
                header_project_id=normalized_command.project_id,
                lines=normalized_command.lines,
                account_repo=account_repo,
            )

            txn.transaction_type_code = normalized_command.transaction_type_code
            txn.financial_account_id = normalized_command.financial_account_id
            txn.transaction_date = normalized_command.transaction_date
            txn.currency_code = normalized_command.currency_code
            txn.exchange_rate = normalized_command.exchange_rate
            txn.total_amount = total
            txn.reference_number = normalized_command.reference_number
            txn.description = normalized_command.description
            txn.notes = normalized_command.notes
            txn.contract_id = normalized_command.contract_id
            txn.project_id = normalized_command.project_id
            repo.save(txn)

            line_repo.delete_for_transaction(txn.id)
            uow.session.flush()

            for line in transaction_lines:
                line.treasury_transaction_id = txn.id
                uow.session.add(line)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc

            from seeker_accounting.modules.audit.event_type_catalog import TREASURY_TRANSACTION_UPDATED
            self._record_audit(company_id, TREASURY_TRANSACTION_UPDATED, "TreasuryTransaction", txn.id, "Updated treasury transaction")
            return self.get_treasury_transaction(company_id, txn.id)

    def cancel_draft_transaction(self, company_id: int, transaction_id: int) -> None:
        self._permission_service.require_permission("treasury.transactions.cancel")
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._treasury_transaction_repository_factory(uow.session)
            txn = repo.get_by_id(company_id, transaction_id)
            if txn is None:
                raise NotFoundError(f"Treasury transaction with id {transaction_id} was not found.")
            if txn.status_code != "draft":
                raise ValidationError("Only draft transactions can be cancelled.")
            txn.status_code = "cancelled"
            repo.save(txn)
            uow.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize_create_command(self, command: CreateTreasuryTransactionCommand) -> CreateTreasuryTransactionCommand:
        return CreateTreasuryTransactionCommand(
            transaction_type_code=command.transaction_type_code,
            financial_account_id=command.financial_account_id,
            transaction_date=command.transaction_date,
            currency_code=command.currency_code,
            reference_number=command.reference_number,
            description=command.description,
            notes=command.notes,
            exchange_rate=command.exchange_rate,
            contract_id=self._normalize_optional_id(command.contract_id),
            project_id=self._normalize_optional_id(command.project_id),
            lines=self._normalize_line_commands(command.lines),
        )

    def _normalize_update_command(self, command: UpdateTreasuryTransactionCommand) -> UpdateTreasuryTransactionCommand:
        return UpdateTreasuryTransactionCommand(
            transaction_type_code=command.transaction_type_code,
            financial_account_id=command.financial_account_id,
            transaction_date=command.transaction_date,
            currency_code=command.currency_code,
            reference_number=command.reference_number,
            description=command.description,
            notes=command.notes,
            exchange_rate=command.exchange_rate,
            contract_id=self._normalize_optional_id(command.contract_id),
            project_id=self._normalize_optional_id(command.project_id),
            lines=self._normalize_line_commands(command.lines),
        )

    def _normalize_line_commands(
        self,
        lines: tuple[TreasuryTransactionLineCommand, ...],
    ) -> tuple[TreasuryTransactionLineCommand, ...]:
        normalized_lines: list[TreasuryTransactionLineCommand] = []
        for line in lines:
            normalized_lines.append(
                TreasuryTransactionLineCommand(
                    account_id=line.account_id,
                    line_description=line.line_description,
                    amount=line.amount,
                    party_type=line.party_type,
                    party_id=line.party_id,
                    tax_code_id=line.tax_code_id,
                    contract_id=self._normalize_optional_id(line.contract_id),
                    project_id=self._normalize_optional_id(line.project_id),
                    project_job_id=self._normalize_optional_id(line.project_job_id),
                    project_cost_code_id=self._normalize_optional_id(line.project_cost_code_id),
                )
            )
        return tuple(normalized_lines)

    def _build_transaction_lines(
        self,
        *,
        session: Session,
        company_id: int,
        header_contract_id: int | None,
        header_project_id: int | None,
        lines: tuple[TreasuryTransactionLineCommand, ...],
        account_repo: AccountRepository,
    ) -> tuple[list[TreasuryTransactionLine], Decimal]:
        total = Decimal("0.00")
        built_lines: list[TreasuryTransactionLine] = []
        for idx, line_cmd in enumerate(lines, start=1):
            if line_cmd.amount <= Decimal("0.00"):
                raise ValidationError("Each line amount must be greater than zero.")
            acct = account_repo.get_by_id(company_id, line_cmd.account_id)
            if acct is None or not acct.is_active:
                raise ValidationError(f"Line account {line_cmd.account_id} must exist and be active in this company.")
            resolved_dimensions = self._project_dimension_validation_service.resolve_line_dimensions(
                header_contract_id=header_contract_id,
                header_project_id=header_project_id,
                line_contract_id=line_cmd.contract_id,
                line_project_id=line_cmd.project_id,
                line_project_job_id=line_cmd.project_job_id,
                line_project_cost_code_id=line_cmd.project_cost_code_id,
            )
            self._project_dimension_validation_service.validate_line_dimensions(
                session=session,
                company_id=company_id,
                contract_id=resolved_dimensions.contract_id,
                project_id=resolved_dimensions.project_id,
                project_job_id=resolved_dimensions.project_job_id,
                project_cost_code_id=resolved_dimensions.project_cost_code_id,
                line_number=idx,
            )
            built_lines.append(
                TreasuryTransactionLine(
                    treasury_transaction_id=0,
                    line_number=idx,
                    account_id=line_cmd.account_id,
                    line_description=line_cmd.line_description,
                    party_type=line_cmd.party_type,
                    party_id=line_cmd.party_id,
                    tax_code_id=line_cmd.tax_code_id,
                    amount=line_cmd.amount,
                    contract_id=resolved_dimensions.contract_id,
                    project_id=resolved_dimensions.project_id,
                    project_job_id=resolved_dimensions.project_job_id,
                    project_cost_code_id=resolved_dimensions.project_cost_code_id,
                )
            )
            total += line_cmd.amount
        return built_lines, total

    def _normalize_optional_id(self, value: int | None) -> int | None:
        if value is None:
            return None
        if value <= 0:
            raise ValidationError("Dimension identifiers must be greater than zero.")
        return value

    def _validate_transaction_type(self, type_code: str) -> None:
        if type_code not in _ALLOWED_TRANSACTION_TYPE_CODES:
            raise ValidationError(f"Transaction type code must be one of: {', '.join(sorted(_ALLOWED_TRANSACTION_TYPE_CODES))}")

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _translate_integrity_error(self, exc: IntegrityError) -> ValidationError | ConflictError:
        message = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
        if "unique" in message and "transaction_number" in message:
            return ConflictError("A treasury transaction with this number already exists.")
        return ValidationError("Treasury transaction could not be saved.")

    def _to_list_item_dto(self, row: TreasuryTransaction) -> TreasuryTransactionListItemDTO:
        fa = row.financial_account
        return TreasuryTransactionListItemDTO(
            id=row.id,
            company_id=row.company_id,
            transaction_number=row.transaction_number,
            transaction_type_code=row.transaction_type_code,
            financial_account_id=row.financial_account_id,
            financial_account_name=fa.name if fa else "",
            transaction_date=row.transaction_date,
            currency_code=row.currency_code,
            total_amount=row.total_amount,
            status_code=row.status_code,
            reference_number=row.reference_number,
            posted_at=row.posted_at,
            updated_at=row.updated_at,
        )

    def _to_detail_dto(self, row: TreasuryTransaction) -> TreasuryTransactionDetailDTO:
        fa = row.financial_account
        line_dtos = tuple(
            TreasuryTransactionLineDTO(
                id=line.id,
                line_number=line.line_number,
                account_id=line.account_id,
                account_code=line.account.account_code if line.account else "",
                account_name=line.account.account_name if line.account else "",
                line_description=line.line_description or "",
                party_type=line.party_type,
                party_id=line.party_id,
                tax_code_id=line.tax_code_id,
                tax_code_code=line.tax_code.code if line.tax_code else None,
                amount=line.amount,
                contract_id=line.contract_id,
                project_id=line.project_id,
                project_job_id=line.project_job_id,
                project_cost_code_id=line.project_cost_code_id,
            )
            for line in sorted(row.lines, key=lambda l: l.line_number)
        )
        return TreasuryTransactionDetailDTO(
            id=row.id,
            company_id=row.company_id,
            transaction_number=row.transaction_number,
            transaction_type_code=row.transaction_type_code,
            financial_account_id=row.financial_account_id,
            financial_account_name=fa.name if fa else "",
            transaction_date=row.transaction_date,
            currency_code=row.currency_code,
            exchange_rate=row.exchange_rate,
            total_amount=row.total_amount,
            status_code=row.status_code,
            reference_number=row.reference_number,
            description=row.description,
            notes=row.notes,
            posted_journal_entry_id=row.posted_journal_entry_id,
            posted_at=row.posted_at,
            posted_by_user_id=row.posted_by_user_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            contract_id=row.contract_id,
            project_id=row.project_id,
            lines=line_dtos,
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
