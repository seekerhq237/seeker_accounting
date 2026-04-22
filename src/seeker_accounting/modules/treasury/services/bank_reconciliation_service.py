from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.treasury.dto.bank_reconciliation_commands import (
    AddReconciliationMatchCommand,
    CreateReconciliationSessionCommand,
)
from seeker_accounting.modules.treasury.dto.bank_reconciliation_dto import (
    ReconciliationMatchDTO,
    ReconciliationSessionDetailDTO,
    ReconciliationSessionListItemDTO,
    ReconciliationSummaryDTO,
)
from seeker_accounting.modules.treasury.models.bank_reconciliation_match import BankReconciliationMatch
from seeker_accounting.modules.treasury.models.bank_reconciliation_session import BankReconciliationSession
from seeker_accounting.modules.treasury.repositories.bank_reconciliation_match_repository import (
    BankReconciliationMatchRepository,
)
from seeker_accounting.modules.treasury.repositories.bank_reconciliation_session_repository import (
    BankReconciliationSessionRepository,
)
from seeker_accounting.modules.treasury.repositories.bank_statement_line_repository import (
    BankStatementLineRepository,
)
from seeker_accounting.modules.treasury.repositories.financial_account_repository import FinancialAccountRepository
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
FinancialAccountRepositoryFactory = Callable[[Session], FinancialAccountRepository]
BankReconciliationSessionRepositoryFactory = Callable[[Session], BankReconciliationSessionRepository]
BankReconciliationMatchRepositoryFactory = Callable[[Session], BankReconciliationMatchRepository]
BankStatementLineRepositoryFactory = Callable[[Session], BankStatementLineRepository]

_ALLOWED_MATCH_ENTITY_TYPES = {
    "treasury_transaction",
    "customer_receipt",
    "supplier_payment",
    "treasury_transfer",
}


class BankReconciliationService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        financial_account_repository_factory: FinancialAccountRepositoryFactory,
        bank_reconciliation_session_repository_factory: BankReconciliationSessionRepositoryFactory,
        bank_reconciliation_match_repository_factory: BankReconciliationMatchRepositoryFactory,
        bank_statement_line_repository_factory: BankStatementLineRepositoryFactory,
        audit_service: AuditService | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._financial_account_repository_factory = financial_account_repository_factory
        self._bank_reconciliation_session_repository_factory = bank_reconciliation_session_repository_factory
        self._bank_reconciliation_match_repository_factory = bank_reconciliation_match_repository_factory
        self._bank_statement_line_repository_factory = bank_statement_line_repository_factory
        self._audit_service = audit_service

    def list_reconciliation_sessions(
        self,
        company_id: int,
        financial_account_id: int | None = None,
    ) -> list[ReconciliationSessionListItemDTO]:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._bank_reconciliation_session_repository_factory(uow.session)
            rows = repo.list_by_company(company_id, financial_account_id=financial_account_id)
            return [self._to_list_item_dto(r) for r in rows]

    def get_reconciliation_session(
        self, company_id: int, session_id: int,
    ) -> ReconciliationSessionDetailDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            repo = self._bank_reconciliation_session_repository_factory(uow.session)
            recon_session = repo.get_detail(company_id, session_id)
            if recon_session is None:
                raise NotFoundError(f"Reconciliation session with id {session_id} was not found.")
            return self._to_detail_dto(recon_session)

    def create_reconciliation_session(
        self,
        company_id: int,
        command: CreateReconciliationSessionCommand,
        actor_user_id: int | None = None,
    ) -> ReconciliationSessionDetailDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            fa_repo = self._financial_account_repository_factory(uow.session)
            fa = fa_repo.get_by_id(company_id, command.financial_account_id)
            if fa is None:
                raise ValidationError("Financial account must belong to the company.")

            session_repo = self._bank_reconciliation_session_repository_factory(uow.session)
            recon_session = BankReconciliationSession(
                company_id=company_id,
                financial_account_id=command.financial_account_id,
                statement_end_date=command.statement_end_date,
                statement_ending_balance=command.statement_ending_balance,
                status_code="draft",
                notes=command.notes,
                created_by_user_id=actor_user_id,
            )
            session_repo.add(recon_session)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import BANK_RECONCILIATION_SESSION_CREATED
            self._record_audit(company_id, BANK_RECONCILIATION_SESSION_CREATED, "BankReconciliationSession", recon_session.id, "Created bank reconciliation session")
            return self.get_reconciliation_session(company_id, recon_session.id)

    def add_match(
        self,
        company_id: int,
        session_id: int,
        command: AddReconciliationMatchCommand,
    ) -> ReconciliationMatchDTO:
        if command.match_entity_type not in _ALLOWED_MATCH_ENTITY_TYPES:
            raise ValidationError(
                f"Match entity type must be one of: {', '.join(sorted(_ALLOWED_MATCH_ENTITY_TYPES))}"
            )
        if command.matched_amount <= Decimal("0.00"):
            raise ValidationError("Matched amount must be greater than zero.")

        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            session_repo = self._bank_reconciliation_session_repository_factory(uow.session)
            match_repo = self._bank_reconciliation_match_repository_factory(uow.session)
            line_repo = self._bank_statement_line_repository_factory(uow.session)

            recon_session = session_repo.get_by_id(company_id, session_id)
            if recon_session is None:
                raise NotFoundError(f"Reconciliation session with id {session_id} was not found.")
            if recon_session.status_code != "draft":
                raise ValidationError("Matches can only be added to draft reconciliation sessions.")

            statement_line = line_repo.get_by_id(company_id, command.bank_statement_line_id)
            if statement_line is None:
                raise ValidationError("Bank statement line must belong to the company.")

            # Check that the match doesn't exceed statement line amount
            line_amount = statement_line.debit_amount + statement_line.credit_amount
            already_matched = match_repo.get_total_matched_for_statement_line(statement_line.id)
            remaining = line_amount - already_matched
            if command.matched_amount > remaining:
                raise ValidationError(
                    f"Matched amount ({command.matched_amount}) exceeds remaining unmatched amount ({remaining})."
                )

            match = BankReconciliationMatch(
                company_id=company_id,
                reconciliation_session_id=session_id,
                bank_statement_line_id=command.bank_statement_line_id,
                match_entity_type=command.match_entity_type,
                match_entity_id=command.match_entity_id,
                matched_amount=command.matched_amount,
            )
            match_repo.add(match)

            # Mark statement line as reconciled if fully matched
            new_total_matched = already_matched + command.matched_amount
            if new_total_matched >= line_amount:
                statement_line.is_reconciled = True
                line_repo.save(statement_line)

            uow.commit()

            return ReconciliationMatchDTO(
                id=match.id,
                company_id=match.company_id,
                reconciliation_session_id=match.reconciliation_session_id,
                bank_statement_line_id=match.bank_statement_line_id,
                match_entity_type=match.match_entity_type,
                match_entity_id=match.match_entity_id,
                matched_amount=match.matched_amount,
                created_at=match.created_at,
            )

    def remove_match(
        self,
        company_id: int,
        session_id: int,
        match_id: int,
    ) -> None:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            session_repo = self._bank_reconciliation_session_repository_factory(uow.session)
            match_repo = self._bank_reconciliation_match_repository_factory(uow.session)
            line_repo = self._bank_statement_line_repository_factory(uow.session)

            recon_session = session_repo.get_by_id(company_id, session_id)
            if recon_session is None:
                raise NotFoundError(f"Reconciliation session with id {session_id} was not found.")
            if recon_session.status_code != "draft":
                raise ValidationError("Matches can only be removed from draft reconciliation sessions.")

            match = match_repo.get_by_id(company_id, match_id)
            if match is None or match.reconciliation_session_id != session_id:
                raise NotFoundError(f"Match with id {match_id} was not found in session {session_id}.")

            statement_line = line_repo.get_by_id(company_id, match.bank_statement_line_id)
            match_repo.delete(match)

            if statement_line is not None:
                statement_line.is_reconciled = False
                line_repo.save(statement_line)

            uow.commit()

    def complete_session(
        self,
        company_id: int,
        session_id: int,
        actor_user_id: int | None = None,
    ) -> ReconciliationSessionDetailDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            session_repo = self._bank_reconciliation_session_repository_factory(uow.session)

            recon_session = session_repo.get_by_id(company_id, session_id)
            if recon_session is None:
                raise NotFoundError(f"Reconciliation session with id {session_id} was not found.")
            if recon_session.status_code != "draft":
                raise ValidationError("Only draft reconciliation sessions can be completed.")

            recon_session.status_code = "completed"
            recon_session.completed_at = datetime.utcnow()
            recon_session.completed_by_user_id = actor_user_id
            session_repo.save(recon_session)
            uow.commit()

            from seeker_accounting.modules.audit.event_type_catalog import BANK_RECONCILIATION_SESSION_COMPLETED
            self._record_audit(company_id, BANK_RECONCILIATION_SESSION_COMPLETED, "BankReconciliationSession", recon_session.id, "Completed bank reconciliation session")
            return self.get_reconciliation_session(company_id, recon_session.id)

    def get_reconciliation_summary(
        self,
        company_id: int,
        session_id: int,
    ) -> ReconciliationSummaryDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company_exists(uow.session, company_id)
            session_repo = self._bank_reconciliation_session_repository_factory(uow.session)
            match_repo = self._bank_reconciliation_match_repository_factory(uow.session)
            line_repo = self._bank_statement_line_repository_factory(uow.session)

            recon_session = session_repo.get_by_id(company_id, session_id)
            if recon_session is None:
                raise NotFoundError(f"Reconciliation session with id {session_id} was not found.")

            matches = match_repo.list_for_session(session_id)
            total_matched = sum((m.matched_amount for m in matches), Decimal("0.00"))

            all_lines = line_repo.list_by_financial_account(
                company_id, recon_session.financial_account_id
            )
            matched_count = sum(1 for l in all_lines if l.is_reconciled)
            unmatched_count = sum(1 for l in all_lines if not l.is_reconciled)

            return ReconciliationSummaryDTO(
                total_matched_amount=total_matched,
                unmatched_statement_count=unmatched_count,
                matched_statement_count=matched_count,
            )

    def _require_company_exists(self, session: Session | None, company_id: int) -> None:
        if session is None:
            raise RuntimeError("Unit of work has no active session.")
        repo = self._company_repository_factory(session)
        if repo.get_by_id(company_id) is None:
            raise NotFoundError(f"Company with id {company_id} was not found.")

    def _to_list_item_dto(self, row: BankReconciliationSession) -> ReconciliationSessionListItemDTO:
        fa = row.financial_account
        return ReconciliationSessionListItemDTO(
            id=row.id,
            company_id=row.company_id,
            financial_account_id=row.financial_account_id,
            financial_account_name=fa.name if fa else "",
            statement_end_date=row.statement_end_date,
            statement_ending_balance=row.statement_ending_balance,
            status_code=row.status_code,
            match_count=len(row.matches) if row.matches else 0,
            completed_at=row.completed_at,
            created_at=row.created_at,
        )

    def _to_detail_dto(self, row: BankReconciliationSession) -> ReconciliationSessionDetailDTO:
        fa = row.financial_account
        match_dtos = tuple(
            ReconciliationMatchDTO(
                id=m.id,
                company_id=m.company_id,
                reconciliation_session_id=m.reconciliation_session_id,
                bank_statement_line_id=m.bank_statement_line_id,
                match_entity_type=m.match_entity_type,
                match_entity_id=m.match_entity_id,
                matched_amount=m.matched_amount,
                created_at=m.created_at,
            )
            for m in (row.matches or [])
        )
        return ReconciliationSessionDetailDTO(
            id=row.id,
            company_id=row.company_id,
            financial_account_id=row.financial_account_id,
            financial_account_name=fa.name if fa else "",
            statement_end_date=row.statement_end_date,
            statement_ending_balance=row.statement_ending_balance,
            status_code=row.status_code,
            notes=row.notes,
            completed_at=row.completed_at,
            completed_by_user_id=row.completed_by_user_id,
            created_at=row.created_at,
            created_by_user_id=row.created_by_user_id,
            matches=match_dtos,
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
